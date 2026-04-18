from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import CreativeAsset, CreativeVariant, Product
from app.agents.strategist_agent import extract_response_text


CREATIVE_PROMPT_VERSION = "creative_v1"

CREATIVE_SYSTEM_PROMPT = """
You are MarketFlow AI's Creative Engine for e-commerce ads.
Generate conversion-focused ad copy that is specific, truthful, and safe for paid social.
Use only the supplied product attributes. Do not invent discounts, certifications, reviews, awards, scarcity, medical claims, or guarantees.
Return exactly three ad copy variants and one descriptive image generation prompt as strict JSON.
"""

CREATIVE_USER_PROMPT_TEMPLATE = """
Create ad creative for this product.

Product JSON:
{product_json}

Brand guidance:
- Tone: clear, energetic, benefit-led, not hype-heavy.
- Audience: small e-commerce shoppers who may be discovering the product for the first time.
- Channel: Meta/Facebook/Instagram feed ads.
- Keep headlines under 60 characters when possible.
- Keep descriptions short and concrete.

Return JSON with this shape:
{{
  "image_prompt": "A detailed prompt for an image generation model.",
  "variants": [
    {{
      "primary_text": "Main ad text.",
      "headline": "Short headline.",
      "description": "Short supporting description.",
      "call_to_action": "Shop Now",
      "score": 0.80,
      "rationale": "Why this variant should work."
    }}
  ]
}}
"""

CREATIVE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["image_prompt", "variants"],
    "properties": {
        "image_prompt": {"type": "string"},
        "variants": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "primary_text",
                    "headline",
                    "description",
                    "call_to_action",
                    "score",
                    "rationale",
                ],
                "properties": {
                    "primary_text": {"type": "string"},
                    "headline": {"type": "string"},
                    "description": {"type": "string"},
                    "call_to_action": {"type": "string"},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                },
            },
        },
    },
}


class CreativeConfigurationError(Exception):
    """Raised when the Creative Engine is missing required configuration."""


@dataclass(frozen=True)
class CreativeRunResult:
    asset: CreativeAsset

    def as_dict(self) -> dict[str, Any]:
        return {
            "creative_asset_id": str(self.asset.id),
            "product_id": str(self.asset.product_id) if self.asset.product_id else None,
            "asset_type": self.asset.asset_type,
            "provider": self.asset.provider,
            "image_prompt": self.asset.prompt,
            "variants": [
                {
                    "id": str(variant.id),
                    "variant_index": variant.variant_index,
                    "primary_text": variant.primary_text,
                    "headline": variant.headline,
                    "description": variant.description,
                    "call_to_action": variant.call_to_action,
                    "score": str(variant.score) if variant.score is not None else None,
                    "metadata": variant.variant_metadata,
                }
                for variant in sorted(self.asset.variants, key=lambda item: item.variant_index)
            ],
        }


class CreativeEngineAgent:
    """Generates ad copy variants and image prompts for a product."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
        openai_client: AsyncOpenAI | None = None,
        model: str | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.model = model or settings.openai_model or "gpt-5.4"

        if openai_client is not None:
            self.openai_client = openai_client
        else:
            if not settings.openai_api_key:
                raise CreativeConfigurationError("OPENAI_API_KEY is not configured.")
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_for_product(
        self,
        *,
        organization_id: uuid.UUID,
        product_id: uuid.UUID,
        store_id: uuid.UUID | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> CreativeRunResult:
        product = await self._load_product(product_id)
        product_context = {
            "product_id": str(product_id),
            "title": title or product.title,
            "description": description or product.description,
            "product_type": product.product_type,
            "vendor": product.vendor,
            "price": str(product.price) if product.price is not None else None,
            "inventory_quantity": product.inventory_quantity,
            "image_url": product.image_url,
        }

        payload = await self._generate_creative_payload(product_context)
        asset = await self._persist_creative(
            organization_id=organization_id,
            store_id=store_id or product.store_id,
            product_id=product_id,
            product_context=product_context,
            creative_payload=payload,
        )
        await self.db.commit()
        return CreativeRunResult(asset=asset)

    async def _load_product(self, product_id: uuid.UUID) -> Product:
        result = await self.db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if product is None:
            raise ValueError(f"Product {product_id} was not found.")
        return product

    async def _generate_creative_payload(self, product_context: dict[str, Any]) -> dict[str, Any]:
        prompt = CREATIVE_USER_PROMPT_TEMPLATE.format(
            product_json=json.dumps(product_context, indent=2, sort_keys=True)
        )
        response = await self.openai_client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": CREATIVE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "marketflow_creative_variants",
                    "strict": True,
                    "schema": CREATIVE_RESPONSE_SCHEMA,
                }
            },
        )
        output_text = extract_response_text(response)
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Creative LLM returned invalid JSON: {output_text}") from exc

        if len(payload.get("variants", [])) != 3:
            raise ValueError("Creative LLM must return exactly 3 variants.")
        return payload

    async def _persist_creative(
        self,
        *,
        organization_id: uuid.UUID,
        store_id: uuid.UUID | None,
        product_id: uuid.UUID,
        product_context: dict[str, Any],
        creative_payload: dict[str, Any],
    ) -> CreativeAsset:
        asset = CreativeAsset(
            organization_id=organization_id,
            store_id=store_id,
            product_id=product_id,
            asset_type="image_prompt",
            provider=self.settings.image_provider,
            prompt=creative_payload["image_prompt"],
            generation_metadata={
                "prompt_version": CREATIVE_PROMPT_VERSION,
                "copy_model": self.model,
                "image_model": self.settings.image_model,
                "image_generation_status": "placeholder_prompt_only",
                "product_context": product_context,
            },
        )
        self.db.add(asset)
        await self.db.flush()

        for index, variant_payload in enumerate(creative_payload["variants"], start=1):
            variant = CreativeVariant(
                creative_asset_id=asset.id,
                variant_index=index,
                primary_text=variant_payload["primary_text"],
                headline=variant_payload["headline"],
                description=variant_payload["description"],
                call_to_action=variant_payload["call_to_action"],
                score=Decimal(str(variant_payload["score"])),
                variant_metadata={
                    "rationale": variant_payload["rationale"],
                    "prompt_version": CREATIVE_PROMPT_VERSION,
                },
            )
            self.db.add(variant)
            asset.variants.append(variant)

        await self.db.flush()
        return asset
