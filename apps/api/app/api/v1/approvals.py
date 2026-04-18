from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models import ApprovalRequest, ApprovalStatus
from app.models.decision import ActionProposal
from app.services import ApprovalNotFoundError, ApprovalService, ApprovalStateError

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    approver_user_id: uuid.UUID | None = None
    note: str | None = None


def serialize_approval(approval: ApprovalRequest) -> dict:
    proposal = approval.proposal
    decision = proposal.decision if proposal else None

    return {
        "id": approval.id,
        "organization_id": approval.organization_id,
        "status": approval.status,
        "requested_message": approval.requested_message,
        "approver_user_id": approval.approver_user_id,
        "approver_note": approval.approver_note,
        "decided_at": approval.decided_at,
        "expires_at": approval.expires_at,
        "created_at": approval.created_at,
        "proposal": {
            "id": proposal.id,
            "status": proposal.status,
            "target_type": proposal.target_type,
            "target_id": proposal.target_id,
            "payload": proposal.payload,
            "requires_approval": proposal.requires_approval,
        }
        if proposal
        else None,
        "decision": {
            "id": decision.id,
            "title": decision.title,
            "summary": decision.summary,
            "action_type": decision.action_type,
            "risk_level": decision.risk_level,
            "confidence": decision.confidence,
            "expected_impact": decision.expected_impact,
            "reasoning": decision.reasoning,
            "status": decision.status,
            "created_at": decision.created_at,
        }
        if decision
        else None,
    }


@router.get("")
async def list_approvals(
    status_filter: ApprovalStatus | None = ApprovalStatus.PENDING,
    organization_id: uuid.UUID | None = None,
    limit: int = 25,
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = (
        select(ApprovalRequest)
        .options(
            selectinload(ApprovalRequest.proposal).selectinload(ActionProposal.decision),
        )
        .order_by(ApprovalRequest.created_at.desc())
        .limit(min(limit, 100))
    )

    if status_filter is not None:
        stmt = stmt.where(ApprovalRequest.status == status_filter)
    if organization_id is not None:
        stmt = stmt.where(ApprovalRequest.organization_id == organization_id)

    approvals = (await db.scalars(stmt)).all()
    return {"items": [serialize_approval(approval) for approval in approvals]}


@router.post("/{approval_request_id}/approve")
async def approve_request(
    approval_request_id: uuid.UUID,
    payload: ApprovalDecisionRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ApprovalService(db=db)
    payload = payload or ApprovalDecisionRequest()

    try:
        result = await service.approve(
            approval_request_id=approval_request_id,
            approver_user_id=payload.approver_user_id,
            note=payload.note,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return result.as_dict()


@router.post("/{approval_request_id}/reject")
async def reject_request(
    approval_request_id: uuid.UUID,
    payload: ApprovalDecisionRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ApprovalService(db=db)
    payload = payload or ApprovalDecisionRequest()

    try:
        result = await service.reject(
            approval_request_id=approval_request_id,
            approver_user_id=payload.approver_user_id,
            note=payload.note,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return result.as_dict()
