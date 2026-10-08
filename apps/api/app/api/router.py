from fastapi import APIRouter

from app.api import auth, cases, documents, goods, masterdata, pipeline
from app.services import hs_engine

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(masterdata.router)
api_router.include_router(cases.router)
api_router.include_router(documents.router)
api_router.include_router(pipeline.router)
api_router.include_router(goods.router)

# pipeline evaluators run in this order after field mapping
pipeline.PIPELINE_STEPS.append(hs_engine.evaluate)
