"""Versioned, effective-dated knowledge datasets. Fail closed when nothing is active."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.knowledge import HsRule, KnowledgeDataset
from app.services import demo_fixtures as fx


class NoActiveDataset(Exception):
    pass


def active_dataset(db: Session, kind: str, on: date | None = None) -> KnowledgeDataset | None:
    on = on or date.today()
    stmt = (select(KnowledgeDataset).where(KnowledgeDataset.kind == kind, KnowledgeDataset.is_active.is_(True),
                                           KnowledgeDataset.effective_from <= on)
            .where((KnowledgeDataset.effective_to.is_(None)) | (KnowledgeDataset.effective_to >= on))
            .order_by(KnowledgeDataset.effective_from.desc(), KnowledgeDataset.created_at.desc()))
    return db.execute(stmt).scalars().first()


def require_dataset(db: Session, kind: str, on: date | None = None) -> KnowledgeDataset:
    ds = active_dataset(db, kind, on)
    if ds is None and get_settings().is_development:
        seed_demo(db)
        ds = active_dataset(db, kind, on)
    if ds is None:
        raise NoActiveDataset(kind)
    return ds


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
