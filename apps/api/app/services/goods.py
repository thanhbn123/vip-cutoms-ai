"""Build/refresh goods items from current extractions. Human-edited fields are never overwritten."""

from __future__ import annotations

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.case import CustomsCase
from app.models.document import Document
from app.models.extraction import ExtractedField
from app.models.goods import GoodsItem
from app.models.identity import Supplier
from app.services import audit
from app.services.issues import IssueSpec
from app.services.mapping import ITEM_KEY_RE, current_extractions
from app.services.normalize import norm_name, norm_text, parse_decimal

MATERIAL_WORDS = {"pvc": "PVC", "plastic": "plastic", "steel": "steel", "stainless": "stainless steel", "iron": "iron",
                  "copper": "copper", "aluminium": "aluminium", "aluminum": "aluminium", "rubber": "rubber"}


def _attrs_from_description(desc: str, source_ref: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    low = desc.lower()
    for w, label in MATERIAL_WORDS.items():
        if re.search(rf"\b{re.escape(w)}\b", low):
            out["material"] = {"value": label, "source": "invoice-description", "source_ref": source_ref}
            break
    m = re.search(r"\bfor\s+([a-z0-9 \-]{3,40}?)(?:[,.;]|$)", low)
    if m:
        out["application"] = {"value": m.group(1).strip(), "source": "invoice-description", "source_ref": source_ref}
    return out


def fingerprint(supplier_name: str | None, model: str | None, description: str) -> str:
    key = "|".join([norm_name(supplier_name), norm_text(model), norm_text(description)])
    return hashlib.sha256(key.encode()).hexdigest()


def build_items(db: Session, case: CustomsCase, actor: audit.Actor) -> list[IssueSpec]:
    pairs = current_extractions(db, case)
    rows: dict[str, dict[int, dict[str, tuple[ExtractedField, Document]]]] = {}
    catalogues: list[dict[str, tuple[ExtractedField, Document]]] = []
    cat_by_doc: dict[str, dict[str, tuple[ExtractedField, Document]]] = {}
    for d, f in pairs:
        m = ITEM_KEY_RE.match(f.key)
        if m:
            rows.setdefault(d.doc_type, {}).setdefault(int(m.group(1)), {})[m.group(2)] = (f, d)
        elif f.key.startswith("catalogue."):
            cat_by_doc.setdefault(str(d.id), {})[f.key.split(".", 1)[1]] = (f, d)
    catalogues = list(cat_by_doc.values())

    supplier = db.get(Supplier, case.supplier_id) if case.supplier_id else None
    existing = {i.line_no: i for i in db.execute(select(GoodsItem).where(GoodsItem.case_id == case.id)).scalars()}
    specs: list[IssueSpec] = []
    inv_rows = rows.get("INVOICE", {})
    pl_rows = rows.get("PACKING_LIST", {})
    co_rows = rows.get("CO", {})
    for line_no in sorted(set(inv_rows) | set(existing)):
        inv = inv_rows.get(line_no)
        item = existing.get(line_no)
        if inv is None:
            if item and "description" not in item.manual_fields:
                specs.append(IssueSpec(f"item_missing:{line_no}", "ITEM_NOT_ON_INVOICE", "WARNING", "DOCUMENT_CONFLICT",
                                       f"Item {line_no} không còn trên Invoice hiện tại", target_ref=f"item:{line_no}", auto_resolvable=True))
            continue
        desc_f, desc_doc = inv["description"]
        new = item is None
        if new:
            item = GoodsItem(tenant_id=case.tenant_id, case_id=case.id, line_no=line_no, description=desc_f.value, manual_fields=[],
                             attributes={}, attribute_sources=[])
            db.add(item)
            existing[line_no] = item
        manual = set(item.manual_fields or [])
        before = {"description": item.description, "model": item.model, "quantity": item.quantity}
        for col in ("description", "model", "quantity", "unit", "unit_price", "amount"):
            if col in manual or col not in inv:
                continue
            setattr(item, col, inv[col][0].value or None)
        pl = pl_rows.get(line_no)
        if pl and "packages" in pl:
            item.packages = pl["packages"][0].value
        co = co_rows.get(line_no)
        if co:
            item.origin_criterion = co.get("origin_criterion", (None,))[0].value if co.get("origin_criterion") else None
            co_model = co.get("model", (None,))[0].value if co.get("model") else ""
            item.co_line_matched = bool(co_model) and norm_text(co_model) == norm_text(item.model)
            if not item.co_line_matched:
                specs.append(IssueSpec(f"co_line:{line_no}", "CO_LINE_MISMATCH", "WARNING", "CO",
                                       f"C/O Item {line_no}: mô tả/model không khớp Invoice",
                                       f"C/O model='{co_model or '(thiếu)'}' · Invoice model='{item.model}'", target_ref=f"item:{line_no}",
                                       auto_resolvable=True,
                                       evidence=[{"document_id": str(co["description"][1].id), "source_ref": co["description"][0].source_ref}]))
        else:
            item.co_line_matched = None
        item.source_document_id = desc_doc.id
        item.source_ref = desc_f.source_ref

        # technical attributes: description heuristics + catalogue docs matching the model
        attrs: dict[str, dict] = {k: v for k, v in (item.attributes or {}).items() if v.get("source") == "manual"}
        attrs = _attrs_from_description(item.description, desc_f.source_ref) | attrs
        sources = []
        for cat in catalogues:
            cat_model = cat.get("model")
            if cat_model and item.model and norm_text(cat_model[0].value) == norm_text(item.model):
                for k, (f, d) in cat.items():
                    if k != "model" and k not in attrs:
                        attrs[k] = {"value": f.value, "source": "catalogue", "source_ref": f.source_ref, "document_id": str(d.id)}
                sources.append({"document_id": str(cat_model[1].id), "doc_type": "CATALOGUE"})
        item.attributes = attrs
        item.attribute_sources = sources
        item.fingerprint = fingerprint(supplier.name if supplier else None, item.model, item.description)

        qty, price, amount = parse_decimal(item.quantity), parse_decimal(item.unit_price), parse_decimal(item.amount)
        if qty is not None and price is not None and amount is not None and abs(qty * price - amount) > 0.01:
            specs.append(IssueSpec(f"item_amount:{line_no}", "ITEM_AMOUNT_MISMATCH", "WARNING", "VALIDATION",
                                   f"Item {line_no}: số lượng × đơn giá ≠ thành tiền", f"{qty} × {price} ≠ {amount}",
                                   target_ref=f"item:{line_no}", auto_resolvable=True))
        pl_qty = parse_decimal(pl["quantity"][0].value) if pl and "quantity" in pl else None
        if pl_qty is not None and qty is not None and pl_qty != qty:
            specs.append(IssueSpec(f"item_qty:{line_no}", "ITEM_QTY_CONFLICT", "WARNING", "DOCUMENT_CONFLICT",
                                   f"Item {line_no}: số lượng Invoice {qty} ≠ Packing List {pl_qty}", target_ref=f"item:{line_no}",
                                   auto_resolvable=True))
        if item.hs_status == "APPROVED" and (before["description"] != item.description or before["model"] != item.model):
            specs.append(IssueSpec(f"hs_item_changed:{line_no}", "APPROVED_HS_ITEM_CHANGED", "WARNING", "HS",
                                   f"Item {line_no}: mô tả/model thay đổi sau khi HS đã duyệt", target_ref=f"item:{line_no}",
                                   auto_resolvable=False))
        db.flush()
        if new:
            audit.record(db, tenant_id=case.tenant_id, actor=audit.Actor.ai(), action="item.created", entity_type="goods_item",
                         entity_id=item.id, case_id=case.id,
                         after={"line_no": line_no, "description": item.description, "model": item.model, "quantity": item.quantity},
                         evidence={"document_id": str(desc_doc.id), "source_ref": desc_f.source_ref})
    return specs
