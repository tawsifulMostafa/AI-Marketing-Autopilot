from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class ProductCategory(StrEnum):
    WINNING = "Winning"
    AT_RISK = "At Risk"
    NEW = "New"


@dataclass(frozen=True)
class ObserverConfig:
    """Thresholds used to classify products from commerce data."""

    lookback_days: int = 30
    new_product_days: int = 30
    winning_min_units_sold: int = 5
    winning_min_revenue: Decimal = Decimal("250.00")
    low_inventory_threshold: int = 5
    overstock_inventory_threshold: int = 50
    low_sales_units_threshold: int = 1


@dataclass(frozen=True)
class ProductObservation:
    product_id: str
    legacy_product_id: str | None
    title: str
    category: ProductCategory
    units_sold: int
    revenue: Decimal
    inventory_quantity: int | None
    created_at: datetime | None
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "legacy_product_id": self.legacy_product_id,
            "title": self.title,
            "category": self.category.value,
            "units_sold": self.units_sold,
            "revenue": str(self.revenue),
            "inventory_quantity": self.inventory_quantity,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reasons": self.reasons,
        }


class DataObserverAgent:
    """Classifies Shopify products from raw product and order payloads."""

    def __init__(
        self,
        config: ObserverConfig | None = None,
        *,
        now: datetime | None = None,
    ) -> None:
        self.config = config or ObserverConfig()
        self.now = normalize_datetime(now) or datetime.now(UTC)

    def analyze_products(
        self,
        products: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> list[ProductObservation]:
        sales_by_product = self._build_sales_index(orders)

        observations = [
            self._observe_product(product, sales_by_product)
            for product in products
        ]

        return sorted(
            observations,
            key=lambda observation: (
                category_rank(observation.category),
                -observation.units_sold,
                -observation.revenue,
                observation.title.lower(),
            ),
        )

    def analyze_as_dicts(
        self,
        products: list[dict[str, Any]],
        orders: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            observation.as_dict()
            for observation in self.analyze_products(products, orders)
        ]

    def _observe_product(
        self,
        product: dict[str, Any],
        sales_by_product: dict[str, dict[str, Any]],
    ) -> ProductObservation:
        product_id = str(product.get("id") or product.get("legacyResourceId") or "")
        legacy_product_id = stringify_optional(product.get("legacyResourceId"))
        product_keys = product_identity_keys(product)

        sales = {"units_sold": 0, "revenue": Decimal("0.00")}
        for key in product_keys:
            if key in sales_by_product:
                sales = sales_by_product[key]
                break

        units_sold = int(sales["units_sold"])
        revenue = Decimal(sales["revenue"])
        inventory_quantity = product_inventory(product)
        created_at = parse_shopify_datetime(product.get("createdAt"))

        category, reasons = self._categorize_product(
            units_sold=units_sold,
            revenue=revenue,
            inventory_quantity=inventory_quantity,
            created_at=created_at,
        )

        return ProductObservation(
            product_id=product_id,
            legacy_product_id=legacy_product_id,
            title=str(product.get("title") or "Untitled product"),
            category=category,
            units_sold=units_sold,
            revenue=revenue,
            inventory_quantity=inventory_quantity,
            created_at=created_at,
            reasons=reasons,
        )

    def _categorize_product(
        self,
        *,
        units_sold: int,
        revenue: Decimal,
        inventory_quantity: int | None,
        created_at: datetime | None,
    ) -> tuple[ProductCategory, list[str]]:
        reasons: list[str] = []
        is_new = created_at is not None and created_at >= self.now - timedelta(
            days=self.config.new_product_days
        )
        has_low_inventory = (
            inventory_quantity is not None
            and inventory_quantity <= self.config.low_inventory_threshold
        )
        has_overstock_risk = (
            inventory_quantity is not None
            and inventory_quantity >= self.config.overstock_inventory_threshold
            and units_sold <= self.config.low_sales_units_threshold
        )
        is_winning = (
            units_sold >= self.config.winning_min_units_sold
            and revenue >= self.config.winning_min_revenue
            and not has_low_inventory
        )

        if is_winning:
            reasons.append(
                f"Sold {units_sold} units and generated {revenue} revenue in the lookback window."
            )
            if inventory_quantity is not None:
                reasons.append(f"Inventory is healthy at {inventory_quantity} units.")
            return ProductCategory.WINNING, reasons

        if has_low_inventory and units_sold > 0:
            reasons.append(
                f"Inventory is low at {inventory_quantity} units while product is still selling."
            )
            return ProductCategory.AT_RISK, reasons

        if has_overstock_risk and not is_new:
            reasons.append(
                f"Only sold {units_sold} units with {inventory_quantity} units still in stock."
            )
            return ProductCategory.AT_RISK, reasons

        if is_new:
            reasons.append(
                f"Product was created within the last {self.config.new_product_days} days."
            )
            return ProductCategory.NEW, reasons

        if units_sold == 0:
            reasons.append("No sales found in the current lookback window.")
        else:
            reasons.append(
                f"Sales are below winning thresholds: {units_sold} units and {revenue} revenue."
            )

        return ProductCategory.AT_RISK, reasons

    def _build_sales_index(
        self,
        orders: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        sales_by_product: dict[str, dict[str, Any]] = {}
        cutoff = self.now - timedelta(days=self.config.lookback_days)

        for order in orders:
            order_created_at = parse_shopify_datetime(order.get("createdAt"))
            if order_created_at is not None and order_created_at < cutoff:
                continue

            for line_item in connection_nodes(order.get("lineItems")):
                product = line_item.get("product") or {}
                keys = product_identity_keys(product)
                if not keys:
                    continue

                quantity = int(line_item.get("quantity") or 0)
                revenue = line_item_revenue(line_item)

                for key in keys:
                    bucket = sales_by_product.setdefault(
                        key,
                        {"units_sold": 0, "revenue": Decimal("0.00")},
                    )
                    bucket["units_sold"] += quantity
                    bucket["revenue"] += revenue

        return sales_by_product


def product_identity_keys(product: dict[str, Any]) -> set[str]:
    keys = {
        stringify_optional(product.get("id")),
        stringify_optional(product.get("legacyResourceId")),
    }
    return {key for key in keys if key}


def product_inventory(product: dict[str, Any]) -> int | None:
    if product.get("totalInventory") is not None:
        return int(product["totalInventory"])

    variant_inventory = [
        variant.get("inventoryQuantity")
        for variant in connection_nodes(product.get("variants"))
        if variant.get("inventoryQuantity") is not None
    ]
    if not variant_inventory:
        return None

    return sum(int(quantity) for quantity in variant_inventory)


def line_item_revenue(line_item: dict[str, Any]) -> Decimal:
    discounted_total = money_amount(line_item, "discountedTotalSet")
    if discounted_total is not None:
        return discounted_total

    unit_price = money_amount(line_item, "originalUnitPriceSet") or Decimal("0.00")
    quantity = Decimal(str(line_item.get("quantity") or 0))
    return unit_price * quantity


def money_amount(payload: dict[str, Any], field_name: str) -> Decimal | None:
    money = (
        payload.get(field_name, {})
        .get("shopMoney", {})
        .get("amount")
    )
    if money is None:
        return None

    try:
        return Decimal(str(money))
    except InvalidOperation:
        return Decimal("0.00")


def connection_nodes(connection: Any) -> list[dict[str, Any]]:
    if not isinstance(connection, dict):
        return []

    return [
        edge.get("node", {})
        for edge in connection.get("edges", [])
        if isinstance(edge, dict)
    ]


def parse_shopify_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        return normalize_datetime(value)

    if not isinstance(value, str):
        return None

    try:
        return normalize_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def stringify_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def category_rank(category: ProductCategory) -> int:
    return {
        ProductCategory.WINNING: 0,
        ProductCategory.AT_RISK: 1,
        ProductCategory.NEW: 2,
    }[category]
