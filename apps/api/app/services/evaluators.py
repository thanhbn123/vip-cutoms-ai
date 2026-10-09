"""Ordered registry of deterministic evaluators run after field mapping.

Registration is self-contained (not an import side effect of the HTTP router) so scripts, seeds and tests that call
`run_pipeline` directly get the same evaluation as the API.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models.case import CustomsCase
from app.services import audit

STEPS: list[Callable[[Session, CustomsCase, audit.Actor], None]] = []
_registered = False


def ensure_registered() -> None:
    """Idempotent: evaluators in order (origin before valuation so tax sees C/O decisions), learning hooks."""
    global _registered
    if _registered:
        return
    from app.api import goods
    from app.services import hs_engine, memory, origin, policy, valuation

    if not STEPS:
        STEPS.extend([hs_engine.evaluate, origin.evaluate, valuation.evaluate, policy.evaluate])
    if memory.boost_candidates not in hs_engine.HISTORY_BOOSTERS:
        hs_engine.HISTORY_BOOSTERS.append(memory.boost_candidates)
    if memory.record_approved not in goods.DECISION_HOOKS:
        goods.DECISION_HOOKS.append(memory.record_approved)
    _registered = True


def run_all(db: Session, case: CustomsCase, actor: audit.Actor) -> None:
    ensure_registered()
    for step in STEPS:
        step(db, case, actor)
