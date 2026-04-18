from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import DataObserverAgent, ProductCategory, ProductObservation
from app.core.config import Settings
from app.integrations.shopify import ShopifyAdminClient
from app.models import Product, ProductInsight, ProductPerformanceLabel, ProductStatus


class IngestionConfigurationError(Exception):
    """Raised when required integration settings are missing."""


@dataclass(frozen=True)
class IngestionResult:
    store_id: uuid.UUID
    products_fetched: int
    orders_fetched: int
    observations: list[ProductObservation]

    def as_dict(self) -> dict[str, Any]:
        return {
            "store_id": str(self.store_id),
            "products_fetched": self.products_fetched,
            "orders_fetched": self.orders_fetched,
            "observations": [observation.as_dict() for observation in self.observations],
        }


class ShopifyIngestionService:
    """Fetches Shopify data, runs the Observer Agent, and persists product insights."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
        observer: DataObserverAgent | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.observer = observer or DataObserverAgent()

    async def sync_and_analyze(
        self,
        *,
        store_id: uuid.UUID,
        product_pages: int = 2,
        order_pages: int = 2,
        page_size: int = 50,
    ) -> IngestionResult:
        shop_url = self._required_setting("shopify_store_url", self.settings.shopify_store_url)
        access_token = self._required_setting(
            "shopify_access_token",
            self.settings.shopify_access_token,
        )

        async with ShopifyAdminClient(
            shop_domain=shop_url,
            access_token=access_token,
            api_version=self.settings.shopify_api_version,
        ) as client:
            products = await client.iter_products(page_size=page_size, max_pages=product_pages)
            orders = await client.iter_orders(page_size=page_size, max_pages=order_pages)

        observations = self.observer.analyze_products(products=products, orders=orders)
        product_by_external_id = {str(product.get("id")): product for product in products}

        for observation in observations:
            raw_product = product_by_external_id.get(observation.product_id, {})
            product = await self._upsert_product(
                store_id=store_id,
                raw_product=raw_product,
                observation=observation,
            )
            await self._upsert_product_insight(product=product, observation=observation)

        await self.db.commit()

        return IngestionResult(
            store_id=store_id,
            products_fetched=len(products),
            orders_fetched=len(orders),
            observations=observations,
        )

    @staticmethod
    def _required_setting(name: str, value: str | None) -> str:
        placeholders = {"", "your-store.myshopify.com", "shpat_your_admin_api_access_token"}
        if value is None or value in placeholders:
            raise IngestionConfigurationError(f"{name.upper()} is not configured.")
        return value

    async def _upsert_product(
        self,
        *,
        store_id: uuid.UUID,
        raw_product: dict[str, Any],
        observation: ProductObservation,
    ) -> Product:
        external_product_id = observation.product_id
        result = await self.db.execute(
            select(Product).where(
                Product.store_id == store_id,
                Product.external_product_id == external_product_id,
            )
        )
        product = result.scalar_one_or_none()

        if product is None:
            product = Product(
                store_id=store_id,
                external_product_id=external_product_id,
                title=observation.title,
            )
            self.db.add(product)

        product.title = observation.title
        product.handle = raw_product.get("handle")
        product.description = raw_product.get("description")
        product.product_type = raw_product.get("productType")
        product.vendor = raw_product.get("vendor")
        product.status = normalize_product_status(raw_product.get("status"))
        product.image_url = featured_image_url(raw_product)
        product.price = product_price(raw_product)
        product.inventory_quantity = observation.inventory_quantity
        product.product_metadata = {
            "shopify": {
                "id": raw_product.get("id") or observation.product_id,
                "legacy_resource_id": observation.legacy_product_id,
                "created_at": raw_product.get("createdAt"),
                "updated_at": raw_product.get("updatedAt"),
            }
        }

        await self.db.flush()
        return product

    async def _upsert_product_insight(
        self,
        *,
        product: Product,
        observation: ProductObservation,
    ) -> ProductInsight:
        snapshot_date = datetime.now(UTC).date()
        result = await self.db.execute(
            select(ProductInsight).where(
                ProductInsight.product_id == product.id,
                ProductInsight.snapshot_date == snapshot_date,
            )
        )
        insight = result.scalar_one_or_none()

        if insight is None:
            insight = ProductInsight(product_id=product.id, snapshot_date=snapshot_date)
            self.db.add(insight)

        insight.performance_label = map_observer_category(observation.category)
        insight.units_sold = observation.units_sold
        insight.revenue = observation.revenue
        insight.confidence = observation_confidence(observation.category)
        insight.explanation = " ".join(observation.reasons)

        return insight


def map_observer_category(category: ProductCategory) -> ProductPerformanceLabel:
    return {
        ProductCategory.WINNING: ProductPerformanceLabel.WINNING,
        ProductCategory.AT_RISK: ProductPerformanceLabel.AT_RISK,
        ProductCategory.NEW: ProductPerformanceLabel.NEW,
    }[category]


def observation_confidence(category: ProductCategory) -> Decimal:
    return {
        ProductCategory.WINNING: Decimal("0.8000"),
        ProductCategory.AT_RISK: Decimal("0.7000"),
        ProductCategory.NEW: Decimal("0.6000"),
    }[category]


def normalize_product_status(value: Any) -> ProductStatus:
    status = str(value or "").lower()
    if status == "draft":
        return ProductStatus.DRAFT
    if status == "archived":
        return ProductStatus.ARCHIVED
    return ProductStatus.ACTIVE


def featured_image_url(raw_product: dict[str, Any]) -> str | None:
    featured_image = raw_product.get("featuredImage") or {}
    return featured_image.get("url")


def product_price(raw_product: dict[str, Any]) -> Decimal | None:
    amount = (
        raw_product.get("priceRangeV2", {})
        .get("minVariantPrice", {})
        .get("amount")
    )
    if amount is None:
        return None
    return Decimal(str(amount))
