from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text

from app.core.database import Base


class ProductStatus(str, enum.Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class ProductPerformanceLabel(str, enum.Enum):
    WINNING = "winning"
    STABLE = "stable"
    UNDERPERFORMING = "underperforming"
    NEW = "new"
    AT_RISK = "at_risk"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("store_id", "external_product_id", name="uq_products_store_external_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    external_product_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    handle: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type: Mapped[str | None] = mapped_column(String, nullable=True)
    vendor: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(
            ProductStatus,
            name="product_status",
            create_type=False,
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=ProductStatus.ACTIVE,
        server_default=ProductStatus.ACTIVE.value,
        nullable=False,
    )
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    inventory_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
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

    insights: Mapped[list[ProductInsight]] = relationship(
        "ProductInsight",
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductInsight(Base):
    __tablename__ = "product_insights"
    __table_args__ = (
        UniqueConstraint("product_id", "snapshot_date", name="uq_product_insights_product_snapshot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    performance_label: Mapped[ProductPerformanceLabel] = mapped_column(
        Enum(
            ProductPerformanceLabel,
            name="product_performance_label",
            create_type=False,
            values_callable=lambda labels: [label.value for label in labels],
        ),
        nullable=False,
    )
    units_sold: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    revenue: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        server_default="0",
        nullable=False,
    )
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    inventory_velocity: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    stockout_risk: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    attributed_ad_spend: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0.00"),
        server_default="0",
        nullable=False,
    )
    attributed_roas: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        default=Decimal("0.0000"),
        server_default="0",
        nullable=False,
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    product: Mapped[Product] = relationship("Product", back_populates="insights")
