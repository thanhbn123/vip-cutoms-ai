from fastapi import APIRouter

from app.api import auth, cases, documents, masterdata

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(masterdata.router)
api_router.include_router(cases.router)
api_router.include_router(documents.router)
