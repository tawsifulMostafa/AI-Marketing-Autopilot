"""Version 1 API routes."""

from fastapi import APIRouter

from app.api.v1.stores import router as stores_router

api_router = APIRouter()
api_router.include_router(stores_router)

__all__ = ["api_router"]
