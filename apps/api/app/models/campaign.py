from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.core.database import Base


class AdPlatform(str, enum.Enum):
    META = "meta"
    GOOGLE = "google"
    TIKTOK = "tiktok"
    EMAIL = "email"


class CampaignStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ad_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    platform: Mapped[AdPlatform] = mapped_column(
        Enum(
            AdPlatform,
            name="ad_platform",
            create_type=False,
            values_callable=lambda platforms: [platform.value for platform in platforms],
        ),
        nullable=False,
    )
    external_campaign_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    objective: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(
            CampaignStatus,
            name="campaign_status",
            create_type=False,
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=CampaignStatus.DRAFT,
        server_default=CampaignStatus.DRAFT.value,
        nullable=False,
    )
    daily_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    lifetime_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    campaign_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_by_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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

    metrics: Mapped[list[CampaignMetric]] = relationship(
        "CampaignMetric",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class CampaignMetric(Base):
    __tablename__ = "campaign_metrics"
    __table_args__ = (
        UniqueConstraint("campaign_id", "metric_date", name="uq_campaign_metrics_campaign_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    spend: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0", nullable=False)
    roas: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ctr: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    cpc: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    cpa: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="metrics")
