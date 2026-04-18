from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models import AIDecision

router = APIRouter(prefix="/decisions", tags=["decisions"])


def serialize_decision(decision: AIDecision) -> dict:
    return {
        "id": decision.id,
        "organization_id": decision.organization_id,
        "store_id": decision.store_id,
        "status": decision.status,
        "title": decision.title,
        "summary": decision.summary,
        "action_type": decision.action_type,
        "risk_level": decision.risk_level,
        "confidence": decision.confidence,
        "expected_impact": decision.expected_impact,
        "reasoning": decision.reasoning,
        "model_name": decision.model_name,
        "prompt_version": decision.prompt_version,
        "created_at": decision.created_at,
        "proposals": [
            {
                "id": proposal.id,
                "target_type": proposal.target_type,
                "target_id": proposal.target_id,
                "payload": proposal.payload,
                "requires_approval": proposal.requires_approval,
                "status": proposal.status,
                "created_at": proposal.created_at,
            }
            for proposal in decision.proposals
        ],
    }


@router.get("")
async def list_decisions(
    organization_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    limit: int = 25,
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = (
        select(AIDecision)
        .options(selectinload(AIDecision.proposals))
        .order_by(AIDecision.created_at.desc())
        .limit(min(limit, 100))
    )

    if organization_id is not None:
        stmt = stmt.where(AIDecision.organization_id == organization_id)
    if store_id is not None:
        stmt = stmt.where(AIDecision.store_id == store_id)

    decisions = (await db.scalars(stmt)).all()
    return {"items": [serialize_decision(decision) for decision in decisions]}
