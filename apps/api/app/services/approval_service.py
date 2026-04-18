from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.execution_agent import ExecutionAgent
from app.models import (
    AIDecision,
    ActionProposal,
    ApprovalRequest,
    ApprovalStatus,
    DecisionStatus,
)


class ApprovalNotFoundError(Exception):
    """Raised when an approval request cannot be found."""


class ApprovalStateError(Exception):
    """Raised when an approval request cannot transition to the requested state."""


@dataclass(frozen=True)
class ApprovalDecisionResult:
    approval_request: ApprovalRequest
    execution: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "approval_request_id": str(self.approval_request.id),
            "status": self.approval_request.status.value,
            "ai_decision_id": (
                str(self.approval_request.ai_decision_id)
                if self.approval_request.ai_decision_id
                else None
            ),
            "action_proposal_id": (
                str(self.approval_request.action_proposal_id)
                if self.approval_request.action_proposal_id
                else None
            ),
            "execution": self.execution,
        }


class ApprovalService:
    """Creates approval requests and handles approve/reject user decisions."""

    def __init__(self, *, db: AsyncSession) -> None:
        self.db = db

    async def create_for_proposal(
        self,
        *,
        organization_id: uuid.UUID,
        decision: AIDecision,
        proposal: ActionProposal,
        message: str | None = None,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            organization_id=organization_id,
            ai_decision_id=decision.id,
            action_proposal_id=proposal.id,
            status=ApprovalStatus.PENDING,
            requested_message=message or default_approval_message(decision, proposal),
        )
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def approve(
        self,
        *,
        approval_request_id: uuid.UUID,
        approver_user_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> ApprovalDecisionResult:
        approval = await self._get_pending_approval(approval_request_id)
        proposal = await self._get_proposal(approval)
        decision = proposal.decision

        approval.status = ApprovalStatus.APPROVED
        approval.approver_user_id = approver_user_id
        approval.approver_note = note
        approval.decided_at = datetime.now(UTC)

        proposal.status = DecisionStatus.APPROVED
        decision.status = DecisionStatus.APPROVED

        execution = await ExecutionAgent(db=self.db).execute_approved_action(
            organization_id=approval.organization_id,
            proposal=proposal,
        )
        if execution.log.status == "published":
            proposal.status = DecisionStatus.EXECUTED
            decision.status = DecisionStatus.EXECUTED
        else:
            proposal.status = DecisionStatus.FAILED
            decision.status = DecisionStatus.FAILED

        await self.db.commit()
        return ApprovalDecisionResult(
            approval_request=approval,
            execution=execution.as_dict(),
        )

    async def reject(
        self,
        *,
        approval_request_id: uuid.UUID,
        approver_user_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> ApprovalDecisionResult:
        approval = await self._get_pending_approval(approval_request_id)
        proposal = await self._get_proposal(approval)

        approval.status = ApprovalStatus.REJECTED
        approval.approver_user_id = approver_user_id
        approval.approver_note = note
        approval.decided_at = datetime.now(UTC)

        proposal.status = DecisionStatus.REJECTED
        proposal.decision.status = DecisionStatus.REJECTED

        await self.db.commit()
        return ApprovalDecisionResult(approval_request=approval)

    async def _get_pending_approval(self, approval_request_id: uuid.UUID) -> ApprovalRequest:
        result = await self.db.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == approval_request_id)
        )
        approval = result.scalar_one_or_none()
        if approval is None:
            raise ApprovalNotFoundError(f"Approval request {approval_request_id} was not found.")
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalStateError(
                f"Approval request {approval_request_id} is already {approval.status.value}."
            )
        return approval

    async def _get_proposal(self, approval: ApprovalRequest) -> ActionProposal:
        if approval.action_proposal_id is None:
            raise ApprovalStateError("Approval request is not linked to an action proposal.")

        result = await self.db.execute(
            select(ActionProposal)
            .options(selectinload(ActionProposal.decision))
            .where(ActionProposal.id == approval.action_proposal_id)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            raise ApprovalStateError("Linked action proposal was not found.")
        return proposal


def default_approval_message(decision: AIDecision, proposal: ActionProposal) -> str:
    return (
        f"Approval requested for '{decision.title}'. "
        f"Action: {decision.action_type.value}. Risk: {decision.risk_level.value}. "
        f"Summary: {decision.summary}"
    )
