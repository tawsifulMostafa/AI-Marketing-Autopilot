"""Version 1 API routes."""

from fastapi import APIRouter

from app.api.v1.approvals import router as approvals_router
from app.api.v1.decisions import router as decisions_router
from app.api.v1.stores import router as stores_router

api_router = APIRouter()
api_router.include_router(approvals_router)
api_router.include_router(decisions_router)
api_router.include_router(stores_router)

__all__ = ["api_router"]
