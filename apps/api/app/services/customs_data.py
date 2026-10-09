"""Authoritative customs-data boundary (G18, B-02).

Knowledge datasets (HS_RULES, TARIFF, FTA, POLICY) carry provenance. A dataset may be used for a
*real customs filing decision* (APP_MODE=full) only when it is

    not demo  ·  verified by an ADMIN/SENIOR_REVIEWER  ·  is_authoritative  ·  effective on the date
    ·  not superseded  ·  the only candidate for its kind on that date (otherwise: reviewer required)

Demo mode and limited mode may keep using `is_demo=true` datasets, visibly labelled. Nothing in
this module fetches data from the internet: a CustomsDataProvider is an explicit, owner-selected
source (file package today; a licensed feed adapter later). The decision engine never scrapes.

Exceptions are fail-closed signals for the evaluators:
    NoActiveDataset      nothing usable → CRITICAL "knowledge unavailable" issue, case BLOCKED
    ConflictingDatasets  two usable candidates → CRITICAL "knowledge conflict" issue, reviewer required
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import DomainError
from app.models.identity import User
from app.models.knowledge import HsRule, KnowledgeDataset
from app.services import audit

KINDS = ("HS_RULES", "TARIFF", "FTA", "POLICY")
VERIFIER_ROLES = {"ADMIN", "SENIOR_REVIEWER"}
REQUIRED_PROVENANCE = ("source_authority", "source_document", "source_reference", "effective_from", "version")


class NoActiveDataset(Exception):
    pass


class ConflictingDatasets(NoActiveDataset):
    """More than one usable dataset covers the date: the system refuses to pick; a reviewer must."""


# --- packages & providers ------------------------------------------------------------------------
@dataclass
class DatasetPackage:
    kind: str
    version: str
    label: str
    effective_from: date
    effective_to: date | None = None
    source_authority: str | None = None  # e.g. the issuing ministry/agency (owner-selected, B-02)
    source_document: str | None = None  # legal document number / title
    source_reference: str | None = None  # URL or archive reference of the legal source
    payload: dict[str, Any] = field(default_factory=dict)  # TARIFF/FTA/POLICY body, or {"rules": [...]} for HS_RULES
    is_demo: bool = False
    notes: str | None = None

    def checksum(self) -> str:
        return canonical_checksum(self.payload)


def canonical_checksum(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


class CustomsDataProvider(Protocol):
    name: str

    def fetch(self, kind: str | None = None) -> list[DatasetPackage]: ...


class DemoFixtureProvider:
    """Wraps the hand-written demo fixtures. Everything it yields is is_demo=True and can never be verified."""

    name = "demo-fixtures"

    def fetch(self, kind: str | None = None) -> list[DatasetPackage]:
        from app.services import demo_fixtures as fx

        src = {"HS_RULES": ("Demo HS heading rules", fx.HS_RULES_DEMO), "TARIFF": ("Demo tariff rates", fx.TARIFF_DEMO),
               "FTA": ("Demo FTA / C/O rules", fx.FTA_DEMO), "POLICY": ("Demo specialized-management policy", fx.POLICY_DEMO)}
        out = []
        for k, (label, data) in src.items():
            if kind and k != kind:
                continue
            payload = {kk: v for kk, v in data.items() if kk not in ("version", "effective_from")}
            out.append(DatasetPackage(kind=k, version=data["version"], label=f"{label} · {fx.DEMO_LABEL}",
                                      effective_from=date.fromisoformat(data["effective_from"]), source_authority=None,
                                      source_document=None, source_reference=fx.DEMO_SOURCE, payload=payload, is_demo=True))
        return out


class FileImportProvider:
    """Imports an owner-supplied JSON package (schema: docs/G18_CUSTOMS_DATA_SCHEMA.md). No network."""

    name = "file-import"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self, kind: str | None = None) -> list[DatasetPackage]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        return [p for p in (package_from_dict(i) for i in items) if not kind or p.kind == kind]


def package_from_dict(d: dict[str, Any]) -> DatasetPackage:
    missing = [k for k in ("kind", "version", "label", "effective_from", "payload") if k not in d]
    if missing:
        raise DomainError("INVALID_PACKAGE", f"dataset package missing fields: {missing}", status_code=422)
    if d["kind"] not in KINDS:
        raise DomainError("INVALID_PACKAGE", f"unknown kind {d['kind']!r}", status_code=422)
    if not isinstance(d["payload"], dict):
        raise DomainError("INVALID_PACKAGE", "payload must be an object", status_code=422)
    return DatasetPackage(kind=d["kind"], version=str(d["version"]), label=str(d["label"]),
                          effective_from=date.fromisoformat(str(d["effective_from"])),
                          effective_to=date.fromisoformat(str(d["effective_to"])) if d.get("effective_to") else None,
                          source_authority=d.get("source_authority"), source_document=d.get("source_document"),
                          source_reference=d.get("source_reference"), payload=d["payload"], is_demo=bool(d.get("is_demo", False)),
                          notes=d.get("notes"))


# --- registration / verification / supersession ---------------------------------------------------
def register(db: Session, pkg: DatasetPackage, actor_user: User, *, reason: str) -> KnowledgeDataset:
    """Store a package as an INACTIVE, UNVERIFIED dataset. Activation (PATCH) and verification are separate, audited steps."""
    if db.execute(select(KnowledgeDataset).where(KnowledgeDataset.kind == pkg.kind, KnowledgeDataset.version == pkg.version)).scalar():
        raise DomainError("DUPLICATE_DATASET", f"{pkg.kind} {pkg.version} already exists")
    ds = KnowledgeDataset(kind=pkg.kind, version=pkg.version, label=pkg.label, source=pkg.source_reference or pkg.source_document or "unspecified",
                          is_demo=pkg.is_demo, effective_from=pkg.effective_from, effective_to=pkg.effective_to, is_active=False,
                          source_authority=pkg.source_authority, source_document=pkg.source_document, source_reference=pkg.source_reference,
                          ingested_at=datetime.now(UTC), is_authoritative=False, checksum=pkg.checksum(), notes=pkg.notes)
    if pkg.kind == "HS_RULES":
        rules = pkg.payload.get("rules")
        if not isinstance(rules, list) or not rules:
            raise DomainError("INVALID_PACKAGE", "HS_RULES payload must contain a non-empty 'rules' list", status_code=422)
        db.add(ds)
        db.flush()
        for r in rules:
            db.add(HsRule(dataset_id=ds.id, heading=str(r["heading"]), title=str(r["title"]), keywords=list(r["keywords"]),
                          exclusions=list(r.get("exclusions", [])), required_attributes=list(r.get("required_attributes", [])),
                          base_confidence=float(r["base_confidence"]), notes=r.get("notes")))
        ds.notes = json.dumps({"rules": rules}, ensure_ascii=False)
    else:
        ds.notes = json.dumps(pkg.payload, ensure_ascii=False)
        db.add(ds)
    db.flush()
    audit.record(db, tenant_id=actor_user.tenant_id, actor=audit.Actor.user(actor_user), action="knowledge.dataset_imported",
                 entity_type="knowledge_dataset", entity_id=ds.id, reason=reason,
                 after={"kind": ds.kind, "version": ds.version, "is_demo": ds.is_demo, "checksum": ds.checksum,
                        "source_authority": ds.source_authority, "source_document": ds.source_document})
    return ds


def stored_payload(ds: KnowledgeDataset) -> dict[str, Any]:
    return json.loads(ds.notes) if ds.notes else {}


def provenance_problems(ds: KnowledgeDataset) -> list[str]:
    problems = [f for f in REQUIRED_PROVENANCE if not getattr(ds, f, None)]
    if ds.is_demo:
        problems.append("is_demo")
    if ds.checksum and ds.checksum != canonical_checksum(stored_payload(ds)):
        problems.append("checksum_mismatch")
    if not ds.checksum:
        problems.append("checksum")
    return problems


def verify(db: Session, ds: KnowledgeDataset, verifier: User, *, reason: str) -> KnowledgeDataset:
    """Mark a dataset authoritative. Fails closed: demo data, missing legal source or checksum mismatch → 409 MISSING_AUTHORITY."""
    if verifier.role not in VERIFIER_ROLES:
        raise DomainError("FORBIDDEN", "only ADMIN or SENIOR_REVIEWER may verify a dataset", status_code=403)
    problems = provenance_problems(ds)
    if problems:
        raise DomainError("MISSING_AUTHORITY", "dataset cannot be marked authoritative", details={"problems": problems})
    before = {"is_authoritative": ds.is_authoritative, "verified_at": ds.verified_at}
    ds.verified_at = datetime.now(UTC)
    ds.verified_by = verifier.id
    ds.is_authoritative = True
    audit.record(db, tenant_id=verifier.tenant_id, actor=audit.Actor.user(verifier), action="knowledge.dataset_verified",
                 entity_type="knowledge_dataset", entity_id=ds.id, before=before, reason=reason,
                 after={"is_authoritative": True, "verified_at": ds.verified_at, "checksum": ds.checksum, "kind": ds.kind, "version": ds.version})
    db.flush()
    return ds


def supersede(db: Session, old: KnowledgeDataset, new: KnowledgeDataset, actor_user: User, *, reason: str) -> None:
    if old.kind != new.kind:
        raise DomainError("INVALID_SUPERSESSION", "datasets of different kinds cannot supersede each other")
    old.superseded_at = datetime.now(UTC)
    new.supersedes_id = old.id
    audit.record(db, tenant_id=actor_user.tenant_id, actor=audit.Actor.user(actor_user), action="knowledge.dataset_superseded",
                 entity_type="knowledge_dataset", entity_id=old.id, reason=reason,
                 after={"superseded_by": str(new.id), "new_version": new.version, "kind": old.kind})
    db.flush()


# --- selection (the only path evaluators use) -----------------------------------------------------
def candidates(db: Session, kind: str, on: date) -> list[KnowledgeDataset]:
    stmt = (select(KnowledgeDataset).where(KnowledgeDataset.kind == kind, KnowledgeDataset.is_active.is_(True),
                                           KnowledgeDataset.effective_from <= on, KnowledgeDataset.superseded_at.is_(None))
            .where((KnowledgeDataset.effective_to.is_(None)) | (KnowledgeDataset.effective_to >= on))
            .order_by(KnowledgeDataset.effective_from.desc(), KnowledgeDataset.created_at.desc()))
    return list(db.execute(stmt).scalars().all())


def _usable_for_filing(ds: KnowledgeDataset) -> bool:
    return bool(ds.is_authoritative and ds.verified_at and not ds.is_demo)


def select_dataset(db: Session, kind: str, on: date | None = None, *, mode: str | None = None) -> KnowledgeDataset:
    """Pick the dataset for `kind` on date `on` under `mode` (default: configured APP_MODE).

    full: authoritative candidates only; exactly one → ok; several → ConflictingDatasets; none → NoActiveDataset.
    demo/limited: prefer authoritative candidates (same conflict rule among them); otherwise the latest demo dataset.
    Expired (effective_to < on) and superseded datasets are never candidates in any mode.
    """
    on = on or date.today()
    mode = mode or get_settings().app_mode
    cands = candidates(db, kind, on)
    authoritative = [c for c in cands if _usable_for_filing(c)]
    if len(authoritative) > 1:
        raise ConflictingDatasets(f"{kind}: {len(authoritative)} authoritative datasets effective on {on}: "
                                  + ", ".join(c.version for c in authoritative) + " — reviewer must resolve")
    if authoritative:
        return authoritative[0]
    if mode == "full":
        raise NoActiveDataset(f"{kind}: no verified authoritative dataset effective on {on} (demo/unverified data refused in full mode)")
    if not cands:
        raise NoActiveDataset(kind)
    return cands[0]


def describe(ds: KnowledgeDataset) -> dict[str, Any]:
    return {"kind": ds.kind, "version": ds.version, "is_demo": ds.is_demo, "is_authoritative": ds.is_authoritative,
            "effective_from": ds.effective_from.isoformat(), "effective_to": ds.effective_to.isoformat() if ds.effective_to else None,
            "verified_at": ds.verified_at.isoformat() if ds.verified_at else None, "source_authority": ds.source_authority,
            "checksum": ds.checksum}


def active_dataset_ages(db: Session) -> dict[str, tuple[int, bool]]:
    """kind → (days since effective_from of the selected dataset, authoritative?) for /metrics."""
    out: dict[str, tuple[int, bool]] = {}
    today = date.today()
    for kind in KINDS:
        try:
            ds = select_dataset(db, kind, today)
        except NoActiveDataset:
            continue
        out[kind] = ((today - ds.effective_from).days, _usable_for_filing(ds))
    return out


def new_id() -> uuid.UUID:
    return uuid.uuid4()
