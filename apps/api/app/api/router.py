from fastapi import APIRouter

from app.api import auth, cases, documents, goods, knowledge, masterdata, pipeline
from app.services import evaluators, hs_engine, origin, policy, valuation

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(masterdata.router)
api_router.include_router(cases.router)
api_router.include_router(documents.router)
api_router.include_router(pipeline.router)
api_router.include_router(goods.router)
api_router.include_router(knowledge.router)

# Deterministic evaluators, run in this order after field mapping (origin before valuation so tax sees C/O decisions).
if not evaluators.STEPS:
    evaluators.STEPS.extend([hs_engine.evaluate, origin.evaluate, valuation.evaluate, policy.evaluate])
