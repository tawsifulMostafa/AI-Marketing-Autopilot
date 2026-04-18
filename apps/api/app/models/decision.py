from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.core.database import Base


class DecisionStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    EXPIRED = "expired"


class ActionType(str, enum.Enum):
    LAUNCH_CAMPAIGN = "launch_campaign"
    PAUSE_CAMPAIGN = "pause_campaign"
    SCALE_BUDGET = "scale_budget"
    REDUCE_BUDGET = "reduce_budget"
    CREATE_DISCOUNT = "create_discount"
    GENERATE_CREATIVE = "generate_creative"
    UPDATE_TARGETING = "update_targeting"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AIDecision(Base):
    __tablename__ = "ai_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[DecisionStatus] = mapped_column(
        Enum(
            DecisionStatus,
            name="decision_status",
            create_type=False,
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=DecisionStatus.PENDING_APPROVAL,
        server_default=DecisionStatus.DRAFT.value,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[ActionType] = mapped_column(
        Enum(
            ActionType,
            name="action_type",
            create_type=False,
            values_callable=lambda actions: [action.value for action in actions],
        ),
        nullable=False,
    )
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(
            RiskLevel,
            name="risk_level",
            create_type=False,
            values_callable=lambda risks: [risk.value for risk in risks],
        ),
        default=RiskLevel.MEDIUM,
        server_default=RiskLevel.MEDIUM.value,
        nullable=False,
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.0000"),
        server_default="0",
        nullable=False,
    )
    expected_impact: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    reasoning: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    proposals: Mapped[list[ActionProposal]] = relationship(
        "ActionProposal",
        back_populates="decision",
        cascade="all, delete-orphan",
    )


class ActionProposal(Base):
    __tablename__ = "action_proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    ai_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    status: Mapped[DecisionStatus] = mapped_column(
        Enum(
            DecisionStatus,
            name="decision_status",
            create_type=False,
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=DecisionStatus.PENDING_APPROVAL,
        server_default=DecisionStatus.PENDING_APPROVAL.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    decision: Mapped[AIDecision] = relationship("AIDecision", back_populates="proposals")
