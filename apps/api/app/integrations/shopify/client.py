from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


class ShopifyClientError(Exception):
    """Base exception for Shopify integration failures."""


class ShopifyGraphQLError(ShopifyClientError):
    """Raised when Shopify returns GraphQL errors or user errors."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


@dataclass(frozen=True)
class PageInfo:
    has_next_page: bool
    end_cursor: str | None


@dataclass(frozen=True)
class ShopifyPage:
    nodes: list[dict[str, Any]]
    page_info: PageInfo


class ShopifyAdminClient:
    """Async Shopify Admin GraphQL client for fetching commerce data."""

    def __init__(
        self,
        shop_domain: str,
        access_token: str,
        *,
        api_version: str | None = None,
        timeout: float = 30.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.shop_domain = normalize_shop_domain(shop_domain)
        self.access_token = access_token
        self.api_version = api_version or get_settings().shopify_api_version
        self.endpoint = (
            f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"
        )
        self._owns_http_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> ShopifyAdminClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._client.aclose()

    async def graphql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.post(
            self.endpoint,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.access_token,
            },
            json={"query": query, "variables": variables or {}},
        )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ShopifyClientError(
                f"Shopify returned a non-JSON response with status {response.status_code}."
            ) from exc

        if response.is_error:
            message = payload.get("errors") or payload.get("error") or response.text
            raise ShopifyClientError(
                f"Shopify request failed with status {response.status_code}: {message}"
            )

        errors = payload.get("errors")
        if errors:
            raise ShopifyGraphQLError("Shopify GraphQL query failed.", errors)

        return payload.get("data", {})

    async def get_shop(self) -> dict[str, Any]:
        data = await self.graphql(
            """
            query MarketFlowShop {
              shop {
                id
                name
                myshopifyDomain
                primaryDomain {
                  host
                  url
                }
                currencyCode
                ianaTimezone
                email
                plan {
                  displayName
                  partnerDevelopment
                  shopifyPlus
                }
              }
            }
            """
        )
        return data["shop"]

    async def get_products(
        self,
        *,
        first: int = 50,
        after: str | None = None,
        query: str | None = None,
    ) -> ShopifyPage:
        data = await self.graphql(
            """
            query MarketFlowProducts($first: Int!, $after: String, $query: String) {
              products(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
                edges {
                  cursor
                  node {
                    id
                    legacyResourceId
                    title
                    handle
                    description
                    productType
                    vendor
                    status
                    totalInventory
                    featuredImage {
                      url
                      altText
                    }
                    priceRangeV2 {
                      minVariantPrice {
                        amount
                        currencyCode
                      }
                      maxVariantPrice {
                        amount
                        currencyCode
                      }
                    }
                    variants(first: 50) {
                      edges {
                        node {
                          id
                          legacyResourceId
                          title
                          sku
                          price
                          inventoryQuantity
                        }
                      }
                    }
                    updatedAt
                    createdAt
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """,
            {"first": first, "after": after, "query": query},
        )
        return parse_connection(data["products"])

    async def get_orders(
        self,
        *,
        first: int = 50,
        after: str | None = None,
        query: str | None = None,
    ) -> ShopifyPage:
        data = await self.graphql(
            """
            query MarketFlowOrders($first: Int!, $after: String, $query: String) {
              orders(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
                edges {
                  cursor
                  node {
                    id
                    legacyResourceId
                    name
                    createdAt
                    updatedAt
                    displayFinancialStatus
                    displayFulfillmentStatus
                    currencyCode
                    subtotalPriceSet {
                      shopMoney {
                        amount
                        currencyCode
                      }
                    }
                    totalPriceSet {
                      shopMoney {
                        amount
                        currencyCode
                      }
                    }
                    totalTaxSet {
                      shopMoney {
                        amount
                        currencyCode
                      }
                    }
                    totalDiscountsSet {
                      shopMoney {
                        amount
                        currencyCode
                      }
                    }
                    customer {
                      id
                      legacyResourceId
                      email
                      displayName
                    }
                    lineItems(first: 100) {
                      edges {
                        node {
                          id
                          title
                          quantity
                          discountedTotalSet {
                            shopMoney {
                              amount
                              currencyCode
                            }
                          }
                          originalUnitPriceSet {
                            shopMoney {
                              amount
                              currencyCode
                            }
                          }
                          product {
                            id
                            legacyResourceId
                          }
                          variant {
                            id
                            legacyResourceId
                            sku
                          }
                        }
                      }
                    }
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """,
            {"first": first, "after": after, "query": query},
        )
        return parse_connection(data["orders"])

    async def get_customers(
        self,
        *,
        first: int = 50,
        after: str | None = None,
        query: str | None = None,
    ) -> ShopifyPage:
        data = await self.graphql(
            """
            query MarketFlowCustomers($first: Int!, $after: String, $query: String) {
              customers(first: $first, after: $after, query: $query, sortKey: UPDATED_AT) {
                edges {
                  cursor
                  node {
                    id
                    legacyResourceId
                    email
                    displayName
                    createdAt
                    updatedAt
                    amountSpent {
                      amount
                      currencyCode
                    }
                    numberOfOrders
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """,
            {"first": first, "after": after, "query": query},
        )
        return parse_connection(data["customers"])

    async def iter_products(
        self,
        *,
        page_size: int = 50,
        query: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        return await collect_pages(
            lambda after: self.get_products(first=page_size, after=after, query=query),
            max_pages=max_pages,
        )

    async def iter_orders(
        self,
        *,
        page_size: int = 50,
        query: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        return await collect_pages(
            lambda after: self.get_orders(first=page_size, after=after, query=query),
            max_pages=max_pages,
        )

    async def iter_customers(
        self,
        *,
        page_size: int = 50,
        query: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        return await collect_pages(
            lambda after: self.get_customers(first=page_size, after=after, query=query),
            max_pages=max_pages,
        )


def normalize_shop_domain(shop_domain: str) -> str:
    candidate = shop_domain.strip().lower()
    if not candidate:
        raise ValueError("Shopify shop domain is required.")

    if "://" in candidate:
        parsed = urlparse(candidate)
        candidate = parsed.netloc or parsed.path

    candidate = candidate.strip("/")
    if "." not in candidate:
        candidate = f"{candidate}.myshopify.com"

    if not candidate.endswith(".myshopify.com") and "." not in candidate:
        raise ValueError("Shopify shop domain must be a valid hostname.")

    return candidate


def parse_connection(connection: dict[str, Any]) -> ShopifyPage:
    nodes = [edge["node"] for edge in connection.get("edges", [])]
    page_info = connection.get("pageInfo", {})
    return ShopifyPage(
        nodes=nodes,
        page_info=PageInfo(
            has_next_page=bool(page_info.get("hasNextPage")),
            end_cursor=page_info.get("endCursor"),
        ),
    )


async def collect_pages(
    fetch_page: Any,
    *,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    after: str | None = None
    pages_fetched = 0

    while True:
        page = await fetch_page(after)
        nodes.extend(page.nodes)
        pages_fetched += 1

        if not page.page_info.has_next_page:
            break
        if max_pages is not None and pages_fetched >= max_pages:
            break

        after = page.page_info.end_cursor

    return nodes
