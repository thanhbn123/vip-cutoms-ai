from fastapi import APIRouter

from app.api import auth, cases, copilot, declaration, documents, goods, knowledge, masterdata, memory, pipeline, review
from app.services import evaluators

api_router = APIRouter()
for r in (auth, masterdata, cases, documents, pipeline, goods, knowledge, declaration, review, copilot, memory):
    api_router.include_router(r.router)

evaluators.ensure_registered()
