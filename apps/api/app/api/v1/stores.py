from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import DailyPlanOrchestrator
from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.services import IngestionConfigurationError, ShopifyIngestionService

router = APIRouter(prefix="/stores", tags=["stores"])


class DailyPlanRequest(BaseModel):
    organization_id: uuid.UUID
    product_pages: int = 2
    order_pages: int = 2
    page_size: int = 50
    lookback_days: int = 30


@router.get("/{store_id}/sync-and-analyze")
async def sync_and_analyze_store(
    store_id: uuid.UUID,
    product_pages: int = Query(default=2, ge=1, le=20),
    order_pages: int = Query(default=2, ge=1, le=20),
    page_size: int = Query(default=50, ge=1, le=250),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    service = ShopifyIngestionService(db=db, settings=settings)

    try:
        result = await service.sync_and_analyze(
            store_id=store_id,
            product_pages=product_pages,
            order_pages=order_pages,
            page_size=page_size,
        )
    except IngestionConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Shopify sync failed: {exc}",
        ) from exc

    return result.as_dict()


@router.post("/{store_id}/daily-plan")
async def run_daily_plan(
    store_id: uuid.UUID,
    payload: DailyPlanRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    orchestrator = DailyPlanOrchestrator(db=db, settings=settings)

    try:
        result = await orchestrator.run(
            organization_id=payload.organization_id,
            store_id=store_id,
            product_pages=payload.product_pages,
            order_pages=payload.order_pages,
            page_size=payload.page_size,
            lookback_days=payload.lookback_days,
        )
    except IngestionConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Daily plan failed: {exc}",
        ) from exc

    return result.as_dict()
