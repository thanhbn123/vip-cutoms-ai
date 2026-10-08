from fastapi import APIRouter

from app.api import auth, cases, copilot, declaration, documents, goods, knowledge, masterdata, memory, pipeline, review
from app.services import evaluators, hs_engine, origin, policy, valuation
from app.services import memory as memory_service

api_router = APIRouter()
for r in (auth, masterdata, cases, documents, pipeline, goods, knowledge, declaration, review, copilot, memory):
    api_router.include_router(r.router)

# Deterministic evaluators, run in this order after field mapping (origin before valuation so tax sees C/O decisions).
if not evaluators.STEPS:
    evaluators.STEPS.extend([hs_engine.evaluate, origin.evaluate, valuation.evaluate, policy.evaluate])
# Historical learning: approved memory nudges HS candidates; approvals enter memory.
if not hs_engine.HISTORY_BOOSTERS:
    hs_engine.HISTORY_BOOSTERS.append(memory_service.boost_candidates)
if not goods.DECISION_HOOKS:
    goods.DECISION_HOOKS.append(memory_service.record_approved)
