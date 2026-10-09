"""Document parsing + field mapping with lineage + cross-document conflict detection.

Deterministic. Provider output is validated (key whitelist, confidence range, non-empty value)
before persistence. Critical fields are never auto-accepted (fail closed).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import ProviderError
from app.ai.gateway import get_provider
from app.ai.redaction import redact
from app.core.rbac import Perm
from app.models.base import utcnow
from app.models.case import CustomsCase
from app.models.document import Document
from app.models.extraction import CaseField, ExtractedField
from app.models.identity import Customer, Supplier, User
from app.services import audit
from app.services.issues import IssueSpec, sync
from app.services.normalize import norm_name, norm_text, parse_decimal
from app.storage.base import get_storage

AUTO_ACCEPT_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.70


@dataclass(frozen=True)
class FieldDef:
    key: str
    section: str
    label: str
    critical: bool
    sources: tuple[str, ...]  # document types in priority order
    source_keys: tuple[str, ...] = ()  # extracted key aliases (defaults to key)
    numeric: bool = False
    compare: str = "text"  # text | name | number


FIELD_DEFS: list[FieldDef] = [
    FieldDef("invoice.number", "invoice", "Invoice No.", True, ("INVOICE", "PACKING_LIST", "CO"),
             ("invoice.number", "packing.invoice_ref", "co.invoice_ref")),
    FieldDef("invoice.date", "invoice", "Invoice date", False, ("INVOICE",)),
    FieldDef("party.exporter", "general", "Exporter", True, ("INVOICE", "CONTRACT", "CO"), ("party.exporter", "co.exporter"), compare="name"),
    FieldDef("party.importer", "general", "Importer", True, ("INVOICE", "CONTRACT", "BILL_OF_LADING", "CO"),
             ("party.importer", "party.consignee", "co.importer"), compare="name"),
    FieldDef("valuation.incoterm", "valuation", "Incoterm", True, ("INVOICE", "CONTRACT")),
    FieldDef("valuation.currency", "valuation", "Currency", True, ("INVOICE",)),
    FieldDef("invoice.total_amount", "valuation", "Invoice value", True, ("INVOICE",), numeric=True, compare="number"),
    FieldDef("valuation.freight", "valuation", "Freight", True, ("BILL_OF_LADING", "INVOICE"), numeric=True, compare="number"),
    FieldDef("valuation.insurance", "valuation", "Insurance", True, ("INVOICE",), numeric=True, compare="number"),
    FieldDef("shipment.total_packages", "transport", "Total packages", True, ("PACKING_LIST", "BILL_OF_LADING", "INVOICE"),
             numeric=True, compare="number"),
    FieldDef("shipment.gross_weight", "transport", "Gross weight (kg)", False, ("PACKING_LIST", "BILL_OF_LADING", "INVOICE"),
             numeric=True, compare="number"),
    FieldDef("shipment.net_weight", "transport", "Net weight (kg)", False, ("PACKING_LIST",), numeric=True, compare="number"),
    FieldDef("bl.number", "transport", "B/L No.", True, ("BILL_OF_LADING",)),
    FieldDef("bl.date", "transport", "B/L date", False, ("BILL_OF_LADING",)),
    FieldDef("transport.vessel", "transport", "Vessel", False, ("BILL_OF_LADING",)),
    FieldDef("transport.port_of_loading", "transport", "Port of loading", False, ("BILL_OF_LADING",)),
    FieldDef("transport.port_of_discharge", "transport", "Port of discharge", False, ("BILL_OF_LADING",)),
    FieldDef("co.form", "origin", "C/O form", True, ("CO",)),
    FieldDef("co.number", "origin", "C/O reference", True, ("CO",)),
    FieldDef("co.date", "origin", "C/O issued date", False, ("CO",)),
    FieldDef("co.origin_country", "origin", "Origin country", True, ("CO",)),
    FieldDef("contract.number", "general", "Contract No.", False, ("CONTRACT",)),
]
FIELD_BY_KEY = {f.key: f for f in FIELD_DEFS}
ITEM_KEY_RE = re.compile(r"^items\[(\d+)\]\.(line_no|description|model|quantity|unit|unit_price|amount|packages|origin_criterion)$")
KNOWN_SOURCE_KEYS = {k for f in FIELD_DEFS for k in (f.source_keys or (f.key,))} | {
    "catalogue.model", "catalogue.function", "catalogue.voltage", "catalogue.power", "catalogue.application",
}


def _valid_key(key: str) -> bool:
    return key in KNOWN_SOURCE_KEYS or bool(ITEM_KEY_RE.match(key))


# ---------------------------------------------------------------------------- parsing
def parse_document(db: Session, case: CustomsCase, doc: Document, actor: audit.Actor) -> int:
    provider = get_provider()
    data = get_storage().get(doc.storage_key)
    try:
        result = provider.extract_document(doc.doc_type, doc.filename, data)
    except ProviderError as exc:
        # Fail closed (G18): a failed real provider yields NO extracted values, never a guess. The document is marked
        # PARSE_FAILED, the pipeline raises a CRITICAL issue, and critical fields stay NEEDS_REVIEW with no value.
        doc.status = "PARSE_FAILED"
        doc.parse_provider = provider.name
        doc.parse_provider_version = getattr(provider, "version", None)
        doc.parsed_at = utcnow()
        doc.parse_confidence = 0.0
        doc.parse_warnings = [f"provider failure: {type(exc).__name__}: {redact(str(exc))}"]
        db.flush()
        audit.record(db, tenant_id=case.tenant_id, actor=actor, action="document.parse_failed", entity_type="document", entity_id=doc.id,
                     case_id=case.id, after={"status": doc.status, "provider": provider.name, "error": type(exc).__name__},
                     evidence={"warnings": doc.parse_warnings})
        return 0
    run_id = uuid.uuid4()
    kept = 0
    rejected: list[str] = []
    for v in result.values:
        if not _valid_key(v.key) or not (0.0 <= v.confidence <= 1.0) or not str(v.value).strip():
            rejected.append(v.key)
            continue
        db.add(ExtractedField(tenant_id=case.tenant_id, case_id=case.id, document_id=doc.id, parse_run_id=run_id, key=v.key,
                              value=str(v.value).strip(), confidence=v.confidence, method=v.method, provider=result.provider,
                              provider_version=result.provider_version, source_ref=v.source_ref))
        kept += 1
    doc.parse_provider = result.provider
    doc.parse_provider_version = result.provider_version
    doc.parsed_at = utcnow()
    doc.parse_warnings = list(result.warnings) + ([f"rejected unvalidated keys: {sorted(set(rejected))}"] if rejected else [])
    doc.parse_confidence = round(sum(v.confidence for v in result.values) / len(result.values), 3) if result.values else 0.0
    doc.status = "PARSED" if kept else "PARSE_FAILED"
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=actor, action="document.parsed", entity_type="document", entity_id=doc.id,
                 case_id=case.id, after={"fields": kept, "status": doc.status, "provider": result.provider,
                                         "provider_version": result.provider_version, "parse_run_id": str(run_id)},
                 evidence={"warnings": doc.parse_warnings})
    return kept


def current_extractions(db: Session, case: CustomsCase) -> list[tuple[Document, ExtractedField]]:
    """Latest parse run of each *current* document."""
    docs = db.execute(select(Document).where(Document.case_id == case.id, Document.is_current.is_(True),
                                             Document.status == "PARSED")).scalars().all()
    out: list[tuple[Document, ExtractedField]] = []
    for d in docs:
        latest_run = db.execute(select(ExtractedField.parse_run_id).where(ExtractedField.document_id == d.id)
                                .order_by(ExtractedField.extracted_at.desc()).limit(1)).scalar()
        if latest_run is None:
            continue
        for f in db.execute(select(ExtractedField).where(ExtractedField.document_id == d.id,
                                                         ExtractedField.parse_run_id == latest_run)).scalars():
            out.append((d, f))
    return out


# ---------------------------------------------------------------------------- mapping
def _same(a: str, b: str, how: str) -> bool:
    if how == "number":
        da, db_ = parse_decimal(a), parse_decimal(b)
        return da is not None and db_ is not None and da == db_
    if how == "name":
        return norm_name(a) == norm_name(b)
    return norm_text(a) == norm_text(b)


def map_fields(db: Session, case: CustomsCase, actor: audit.Actor) -> list[IssueSpec]:
    pairs = current_extractions(db, case)
    by_key: dict[str, list[tuple[Document, ExtractedField]]] = {}
    for d, f in pairs:
        by_key.setdefault(f.key, []).append((d, f))
    existing = {cf.key: cf for cf in db.execute(select(CaseField).where(CaseField.case_id == case.id)).scalars()}
    specs: list[IssueSpec] = []
    present_doc_types = {d.doc_type for d, _ in pairs}

    for fd in FIELD_DEFS:
        candidates: list[tuple[Document, ExtractedField]] = []
        for doc_type in fd.sources:
            for src_key in fd.source_keys or (fd.key,):
                for d, f in by_key.get(src_key, []):
                    if d.doc_type == doc_type:
                        candidates.append((d, f))
        cf = existing.get(fd.key)
        if not candidates:
            if fd.critical and cf is None and (set(fd.sources) & present_doc_types):
                # a source document exists but did not yield the field → explicit NEEDS_REVIEW, never a fabricated value
                cf = CaseField(tenant_id=case.tenant_id, case_id=case.id, key=fd.key, section=fd.section, label=fd.label,
                               value=None, confidence=0.0, is_critical=True, review_status="NEEDS_REVIEW", origin="AI",
                               reasoning="Không tìm thấy giá trị trong chứng từ hiện có; cần nhập/duyệt thủ công.",
                               rule_ref="MAP-MISSING-CRITICAL")
                db.add(cf)
                existing[fd.key] = cf
                specs.append(IssueSpec(f"missing:{fd.key}", "FIELD_MISSING", "WARNING", "MISSING_DATA",
                                       f"Thiếu {fd.label}", "Chứng từ nguồn đã có nhưng không trích xuất được giá trị.",
                                       target_ref=fd.key, auto_resolvable=True))
            continue

        primary_doc, primary = candidates[0]
        others = [(d, f) for d, f in candidates[1:] if not _same(primary.value, f.value, fd.compare)]
        alternatives = [{"value": f.value, "document_id": str(d.id), "doc_type": d.doc_type, "source_ref": f.source_ref,
                         "confidence": f.confidence} for d, f in others]
        if others:
            specs.append(IssueSpec(
                f"conflict:{fd.key}", "DOCUMENT_CONFLICT", "WARNING", "DOCUMENT_CONFLICT",
                f"{fd.label}: chứng từ không khớp",
                " vs ".join(f"{d.doc_type}={f.value}" for d, f in [candidates[0], *others]),
                target_ref=fd.key, auto_resolvable=True,
                evidence=[{"document_id": str(d.id), "doc_type": d.doc_type, "value": f.value, "source_ref": f.source_ref}
                          for d, f in [candidates[0], *others]],
            ))

        if fd.numeric and parse_decimal(primary.value) is None:
            specs.append(IssueSpec(f"invalid:{fd.key}", "FIELD_INVALID", "WARNING", "VALIDATION", f"{fd.label}: không phải số",
                                   f"Giá trị '{primary.value}' không đọc được thành số.", target_ref=fd.key, auto_resolvable=True))

        if cf is not None and cf.review_status == "APPROVED":
            # Never silently overwrite human-approved values; surface divergence instead.
            if not _same(cf.value or "", primary.value, fd.compare):
                specs.append(IssueSpec(f"approved_diverges:{fd.key}", "APPROVED_VALUE_DIVERGES", "WARNING", "DOCUMENT_CONFLICT",
                                       f"{fd.label}: chứng từ mới khác giá trị đã duyệt",
                                       f"Đã duyệt '{cf.value}', chứng từ hiện ghi '{primary.value}'.", target_ref=fd.key,
                                       auto_resolvable=True))
            cf.alternatives = alternatives
            continue
        if cf is not None and cf.origin in ("MANUAL", "REVIEWER") and cf.review_status != "REJECTED":
            cf.alternatives = alternatives
            continue

        if others:
            status = "NEEDS_REVIEW"
        elif fd.critical:
            status = "NEEDS_REVIEW"  # critical fields always need a human eye (AI_RULES: confidence is not authority)
        elif primary.confidence >= AUTO_ACCEPT_THRESHOLD:
            status = "AUTO_ACCEPTABLE"
        elif primary.confidence >= REVIEW_THRESHOLD:
            status = "NEEDS_REVIEW"
        else:
            status = "BLOCKED"
        reasoning = f"Lấy từ {primary_doc.doc_type} ({primary.source_ref}) theo thứ tự ưu tiên nguồn {list(fd.sources)}."
        if others:
            reasoning += " Có giá trị khác trong chứng từ khác → cần reviewer chọn."
        before = None
        if cf is None:
            cf = CaseField(tenant_id=case.tenant_id, case_id=case.id, key=fd.key, section=fd.section, label=fd.label)
            db.add(cf)
            existing[fd.key] = cf
        else:
            before = {"value": cf.value, "review_status": cf.review_status}
        cf.value = primary.value
        cf.confidence = primary.confidence
        cf.is_critical = fd.critical
        cf.review_status = status
        cf.origin = "AI"
        cf.method = primary.method
        cf.source_document_id = primary_doc.id
        cf.source_extracted_field_id = primary.id
        cf.source_ref = primary.source_ref
        cf.reasoning = reasoning
        cf.rule_ref = "MAP-PRIORITY-SOURCE"
        cf.alternatives = alternatives
        db.flush()
        if before is None or before["value"] != cf.value:
            audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.ai(), action="field.mapped", entity_type="case_field",
                         entity_id=cf.id, case_id=case.id, before=before,
                         after={"key": fd.key, "value": cf.value, "confidence": cf.confidence, "review_status": status},
                         evidence={"document_id": str(primary_doc.id), "source_ref": primary.source_ref, "method": primary.method})

    # Master-data cross-check (importer/exporter vs case customer/supplier)
    customer = db.get(Customer, case.customer_id)
    imp = existing.get("party.importer")
    if customer and imp and imp.value and norm_name(imp.value) != norm_name(customer.name):
        specs.append(IssueSpec("mismatch:importer", "IMPORTER_MISMATCH", "WARNING", "DOCUMENT_CONFLICT",
                               "Importer trên chứng từ khác khách hàng của hồ sơ",
                               f"Chứng từ: '{imp.value}' · Hồ sơ: '{customer.name}'", target_ref="party.importer", auto_resolvable=True))
    if case.supplier_id:
        supplier = db.get(Supplier, case.supplier_id)
        exp = existing.get("party.exporter")
        if supplier and exp and exp.value and norm_name(exp.value) != norm_name(supplier.name):
            specs.append(IssueSpec("mismatch:exporter", "EXPORTER_MISMATCH", "WARNING", "DOCUMENT_CONFLICT",
                                   "Exporter trên chứng từ khác nhà cung cấp của hồ sơ",
                                   f"Chứng từ: '{exp.value}' · Hồ sơ: '{supplier.name}'", target_ref="party.exporter",
                                   auto_resolvable=True))

    # Valuation sanity: FOB without freight/insurance → missing data warnings (deterministic, not legal advice)
    inc = existing.get("valuation.incoterm")
    if inc and inc.value and norm_text(inc.value).startswith(("FOB", "EXW", "FCA")):
        for k, label in (("valuation.freight", "cước vận tải"), ("valuation.insurance", "phí bảo hiểm")):
            f = existing.get(k)
            if f is None or not f.value:
                specs.append(IssueSpec(f"valuation_missing:{k}", "VALUATION_INPUT_MISSING", "WARNING", "VALUATION",
                                       f"Thiếu {label} cho điều kiện {inc.value}",
                                       "Trị giá tính thuế theo điều kiện này cần khoản cộng; chưa có chứng từ/giá trị.",
                                       target_ref=k, auto_resolvable=True))
    sync(db, case, specs, "mapping")
    return specs


def set_field_manual(db: Session, case: CustomsCase, user: User, key: str, value: str, reason: str) -> CaseField:
    """Operator/Reviewer edit. Critical fields set by a Reviewer become APPROVED; by an Operator → NEEDS_REVIEW."""
    from app.core.rbac import has_perm

    fd = FIELD_BY_KEY.get(key)
    if fd is None:
        raise ValueError(f"unknown field key {key}")
    cf = db.execute(select(CaseField).where(CaseField.case_id == case.id, CaseField.key == key)).scalar()
    before = {"value": cf.value, "review_status": cf.review_status, "origin": cf.origin} if cf else None
    if cf is None:
        cf = CaseField(tenant_id=case.tenant_id, case_id=case.id, key=key, section=fd.section, label=fd.label)
        db.add(cf)
    reviewer = has_perm(user.role, Perm.PROPOSAL_DECIDE)
    cf.value = value
    cf.confidence = 1.0
    cf.is_critical = fd.critical
    cf.origin = "REVIEWER" if reviewer else "MANUAL"
    cf.method = "manual"
    cf.source_document_id = None
    cf.source_extracted_field_id = None
    cf.source_ref = f"user:{user.email}"
    cf.reasoning = reason
    cf.rule_ref = "MANUAL-ENTRY"
    cf.updated_by = user.id
    if fd.critical and not reviewer:
        cf.review_status = "NEEDS_REVIEW"
    else:
        cf.review_status = "APPROVED"
        cf.approved_by = user.id
        cf.approved_at = utcnow()
    db.flush()
    audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.user(user), action="field.manual_set", entity_type="case_field",
                 entity_id=cf.id, case_id=case.id, before=before,
                 after={"key": key, "value": value, "review_status": cf.review_status}, reason=reason)
    return cf
