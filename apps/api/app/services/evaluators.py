"""Ordered registry of deterministic evaluators run after field mapping (populated in app.api.router)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models.case import CustomsCase
from app.services import audit

STEPS: list[Callable[[Session, CustomsCase, audit.Actor], None]] = []


def run_all(db: Session, case: CustomsCase, actor: audit.Actor) -> None:
    for step in STEPS:
        step(db, case, actor)
