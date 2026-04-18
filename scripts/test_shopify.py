from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
API_DIR = ROOT_DIR / "apps" / "api"

if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.core.config import get_settings  # noqa: E402
from app.integrations.shopify import ShopifyAdminClient  # noqa: E402


PLACEHOLDER_VALUES = {
    "",
    "your-store.myshopify.com",
    "shpat_your_admin_api_access_token",
}


async def main() -> int:
    settings = get_settings()

    shop_url = settings.shopify_store_url or ""
    access_token = settings.shopify_access_token or ""

    if shop_url in PLACEHOLDER_VALUES or access_token in PLACEHOLDER_VALUES:
        print(
            "Set SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN in "
            f"{ROOT_DIR / '.env'} before running this script."
        )
        return 1

    async with ShopifyAdminClient(
        shop_domain=shop_url,
        access_token=access_token,
        api_version=settings.shopify_api_version,
    ) as client:
        page = await client.get_products(first=5)

    if not page.nodes:
        print("No products found.")
        return 0

    print("First 5 Shopify products:")
    for index, product in enumerate(page.nodes, start=1):
        print(f"{index}. {product.get('title', '(untitled product)')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
