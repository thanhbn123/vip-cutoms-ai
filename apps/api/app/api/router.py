from fastapi import APIRouter

from app.api import auth, cases, masterdata

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(masterdata.router)
api_router.include_router(cases.router)
