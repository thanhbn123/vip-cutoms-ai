"""Versioned, effective-dated knowledge datasets. Fail closed when nothing is active.

G18: selection is delegated to app.services.customs_data.select_dataset, which applies the
runtime mode (demo/limited may use demo data; full requires verified authoritative data) and
refuses to choose between conflicting datasets. The demo seed below only ever creates
is_demo=True datasets and only runs where the mode allows demo data.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.modes import policy
from app.models.knowledge import HsRule, KnowledgeDataset
from app.services import demo_fixtures as fx
from app.services.customs_data import ConflictingDatasets, NoActiveDataset, select_dataset

__all__ = ["ConflictingDatasets", "NoActiveDataset", "active_dataset", "require_dataset", "seed_demo", "dataset_payload"]


def active_dataset(db: Session, kind: str, on: date | None = None) -> KnowledgeDataset | None:
    try:
        return select_dataset(db, kind, on)
    except NoActiveDataset:
        return None


def require_dataset(db: Session, kind: str, on: date | None = None) -> KnowledgeDataset:
    """Dataset for `kind` under the configured mode. Raises NoActiveDataset / ConflictingDatasets (fail closed)."""
    s = get_settings()
    try:
        return select_dataset(db, kind, on)
    except ConflictingDatasets:
        raise
    except NoActiveDataset:
        if s.is_development and policy(s).demo_data_allowed:
            seed_demo(db)
            return select_dataset(db, kind, on)
        raise


def _seed(db: Session, kind: str, version: str, effective_from: str, label: str, notes: str | None = None) -> KnowledgeDataset | None:
    if db.execute(select(KnowledgeDataset).where(KnowledgeDataset.kind == kind, KnowledgeDataset.version == version)).scalar():
        return None
    ds = KnowledgeDataset(kind=kind, version=version, label=f"{label} · {fx.DEMO_LABEL}", source=fx.DEMO_SOURCE, is_demo=True,
                          effective_from=date.fromisoformat(effective_from), is_active=True, notes=notes)
    db.add(ds)
    db.flush()
    return ds


def seed_demo(db: Session) -> list[str]:
    """Idempotent demo seed. Only demo datasets; never pretends to be authoritative."""
    created: list[str] = []
    ds = _seed(db, "HS_RULES", fx.HS_RULES_DEMO["version"], fx.HS_RULES_DEMO["effective_from"], "Demo HS heading rules")
    if ds:
        for r in fx.HS_RULES_DEMO["rules"]:
            db.add(HsRule(dataset_id=ds.id, heading=r["heading"], title=r["title"], keywords=r["keywords"],
                          exclusions=r.get("exclusions", []), required_attributes=r.get("required_attributes", []),
                          base_confidence=r["base_confidence"], notes=r.get("notes")))
        created.append("HS_RULES")
    for seeder in EXTRA_SEEDERS:
        created += seeder(db)
    db.flush()
    return created


EXTRA_SEEDERS: list = []  # G06 registers tariff / FTA / policy demo seeders


def _seed_json_datasets(db: Session) -> list[str]:
    created = []
    for kind, data, label in (("TARIFF", fx.TARIFF_DEMO, "Demo tariff rates"), ("FTA", fx.FTA_DEMO, "Demo FTA / C/O rules"),
                              ("POLICY", fx.POLICY_DEMO, "Demo specialized-management policy")):
        ds = _seed(db, kind, data["version"], data["effective_from"], label)
        if ds:
            ds.notes = __import__("json").dumps({k: v for k, v in data.items() if k not in ("version", "effective_from")})
            created.append(kind)
    return created


EXTRA_SEEDERS.append(_seed_json_datasets)


def dataset_payload(ds: KnowledgeDataset) -> dict:
    """JSON-encoded body for TARIFF/FTA/POLICY datasets (HS_RULES live in hs_rules)."""
    import json

    return json.loads(ds.notes) if ds.notes else {}
