from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import (
    AIDecision,
    ActionProposal,
    ActionType,
    Campaign,
    CampaignMetric,
    DecisionStatus,
    Product,
    ProductInsight,
    RiskLevel,
)


STRATEGIST_PROMPT_VERSION = "strategist_v1"

STRATEGIST_SYSTEM_PROMPT = """
You are MarketFlow AI's Strategist Agent, an autonomous CMO for small e-commerce stores.
Use only the supplied product insights and campaign metrics. Do not invent unavailable facts.
Return concise, approval-ready marketing action proposals as strict JSON.

Decision rules:
- Recommend launch_campaign for winning products when inventory is healthy and there is no conflicting poor campaign evidence.
- Recommend pause_campaign when campaign ROAS is below 1.5 and spend is meaningful.
- Recommend scale_budget only when ROAS is strong and risk remains manageable.
- Recommend reduce_budget when performance is weak but not bad enough to pause.
- Recommend generate_creative when a product is promising but needs fresh ads before spend changes.
- Every proposal must include clear reasoning, risk level, expected impact, and a machine-readable payload.
- Budget changes and ad launches must require approval.
"""

STRATEGIST_USER_PROMPT_TEMPLATE = """
Analyze this store context and produce action proposals.

Store context JSON:
{context_json}

Return JSON with this shape:
{{
  "proposals": [
    {{
      "title": "Launch a Meta ad for Example Product",
      "summary": "Short executive summary.",
      "action_type": "launch_campaign",
      "risk_level": "medium",
      "confidence": 0.75,
      "target_type": "product",
      "target_id": "uuid-from-context-or-null",
      "requires_approval": true,
      "reasoning": {{
        "summary": "Why this action is recommended.",
        "evidence": ["Specific metric from context"]
      }},
      "expected_impact": {{
        "metric": "revenue",
        "estimate": "Expected directional impact.",
        "timeframe": "7-14 days"
      }},
      "payload": {{
        "channel": "meta",
        "product_id": "uuid-from-context-or-null",
        "product_title": "Product title when relevant",
        "campaign_id": "uuid-from-context-or-null",
        "current_roas": 0,
        "recommended_daily_budget": 0,
        "notes": "Execution notes"
      }}
    }}
  ]
}}
"""

STRATEGY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "summary",
                    "action_type",
                    "risk_level",
                    "confidence",
                    "target_type",
                    "target_id",
                    "requires_approval",
                    "reasoning",
                    "expected_impact",
                    "payload",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "action_type": {
                        "type": "string",
                        "enum": [action.value for action in ActionType],
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": [risk.value for risk in RiskLevel],
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "target_type": {
                        "type": "string",
                        "enum": ["product", "campaign", "store"],
                    },
                    "target_id": {
                        "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}],
                    },
                    "requires_approval": {"type": "boolean"},
                    "reasoning": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["summary", "evidence"],
                        "properties": {
                            "summary": {"type": "string"},
                            "evidence": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "expected_impact": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["metric", "estimate", "timeframe"],
                        "properties": {
                            "metric": {"type": "string"},
                            "estimate": {"type": "string"},
                            "timeframe": {"type": "string"},
                        },
                    },
                    "payload": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "channel",
                            "product_id",
                            "product_title",
                            "campaign_id",
                            "current_roas",
                            "recommended_daily_budget",
                            "notes",
                        ],
                        "properties": {
                            "channel": {"type": "string"},
                            "product_id": {
                                "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}],
                            },
                            "product_title": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                            },
                            "campaign_id": {
                                "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}],
                            },
                            "current_roas": {
                                "anyOf": [{"type": "number"}, {"type": "null"}],
                            },
                            "recommended_daily_budget": {
                                "anyOf": [{"type": "number"}, {"type": "null"}],
                            },
                            "notes": {"type": "string"},
                        },
                    },
                },
            },
        }
    },
}


class StrategistConfigurationError(Exception):
    """Raised when the Strategist Agent is missing required configuration."""


@dataclass(frozen=True)
class StrategyRunResult:
    decisions: list[AIDecision]

    def as_dict(self) -> dict[str, Any]:
        return {
            "decisions": [
                {
                    "id": str(decision.id),
                    "title": decision.title,
                    "summary": decision.summary,
                    "action_type": decision.action_type.value,
                    "risk_level": decision.risk_level.value,
                    "confidence": str(decision.confidence),
                    "expected_impact": decision.expected_impact,
                    "reasoning": decision.reasoning,
                    "proposals": [
                        {
                            "id": str(proposal.id),
                            "target_type": proposal.target_type,
                            "target_id": str(proposal.target_id) if proposal.target_id else None,
                            "requires_approval": proposal.requires_approval,
                            "status": proposal.status.value,
                            "payload": proposal.payload,
                        }
                        for proposal in decision.proposals
                    ],
                }
                for decision in self.decisions
            ]
        }


class AIStrategistAgent:
    """Uses GPT-5.4 to turn product and campaign data into action proposals."""

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
                raise StrategistConfigurationError("OPENAI_API_KEY is not configured.")
            self.openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def run(
        self,
        *,
        organization_id: uuid.UUID,
        store_id: uuid.UUID | None = None,
        lookback_days: int = 30,
    ) -> StrategyRunResult:
        context = await self._build_context(
            organization_id=organization_id,
            store_id=store_id,
            lookback_days=lookback_days,
        )
        payload = await self._generate_strategy_payload(context)
        decisions = await self._persist_proposals(
            organization_id=organization_id,
            store_id=store_id,
            proposals=payload.get("proposals", []),
            known_target_ids=set(context["known_target_ids"]),
        )
        await self.db.commit()
        return StrategyRunResult(decisions=decisions)

    async def _build_context(
        self,
        *,
        organization_id: uuid.UUID,
        store_id: uuid.UUID | None,
        lookback_days: int,
    ) -> dict[str, Any]:
        cutoff_date = date.today() - timedelta(days=lookback_days)

        product_stmt = (
            select(Product, ProductInsight)
            .join(ProductInsight, ProductInsight.product_id == Product.id)
            .where(ProductInsight.snapshot_date >= cutoff_date)
            .order_by(ProductInsight.snapshot_date.desc(), ProductInsight.revenue.desc())
            .limit(50)
        )
        if store_id is not None:
            product_stmt = product_stmt.where(Product.store_id == store_id)

        product_rows = (await self.db.execute(product_stmt)).all()

        campaign_stmt = (
            select(Campaign, CampaignMetric)
            .join(CampaignMetric, CampaignMetric.campaign_id == Campaign.id)
            .where(
                Campaign.organization_id == organization_id,
                CampaignMetric.metric_date >= cutoff_date,
            )
            .order_by(CampaignMetric.metric_date.desc(), CampaignMetric.spend.desc())
            .limit(50)
        )
        if store_id is not None:
            campaign_stmt = campaign_stmt.where(Campaign.store_id == store_id)

        campaign_rows = (await self.db.execute(campaign_stmt)).all()

        products = [
            {
                "product_id": str(product.id),
                "title": product.title,
                "performance_label": insight.performance_label.value,
                "snapshot_date": insight.snapshot_date.isoformat(),
                "units_sold": insight.units_sold,
                "revenue": decimal_to_float(insight.revenue),
                "inventory_quantity": product.inventory_quantity,
                "price": decimal_to_float(product.price),
                "confidence": decimal_to_float(insight.confidence),
                "explanation": insight.explanation,
            }
            for product, insight in product_rows
        ]
        campaigns = [
            {
                "campaign_id": str(campaign.id),
                "name": campaign.name,
                "platform": campaign.platform.value,
                "status": campaign.status.value,
                "metric_date": metric.metric_date.isoformat(),
                "spend": decimal_to_float(metric.spend),
                "revenue": decimal_to_float(metric.revenue),
                "roas": decimal_to_float(metric.roas),
                "conversions": metric.conversions,
                "clicks": metric.clicks,
                "daily_budget": decimal_to_float(campaign.daily_budget),
            }
            for campaign, metric in campaign_rows
        ]

        known_target_ids = {
            item["product_id"] for item in products
        } | {
            item["campaign_id"] for item in campaigns
        }

        return {
            "organization_id": str(organization_id),
            "store_id": str(store_id) if store_id else None,
            "lookback_days": lookback_days,
            "generated_at": datetime.now(UTC).isoformat(),
            "products": products,
            "campaigns": campaigns,
            "known_target_ids": sorted(known_target_ids),
        }

    async def _generate_strategy_payload(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = STRATEGIST_USER_PROMPT_TEMPLATE.format(
            context_json=json.dumps(context, indent=2, sort_keys=True)
        )
        response = await self.openai_client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": STRATEGIST_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "marketflow_strategy_proposals",
                    "strict": True,
                    "schema": STRATEGY_RESPONSE_SCHEMA,
                }
            },
        )
        output_text = extract_response_text(response)
        try:
            return json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Strategist LLM returned invalid JSON: {output_text}") from exc

    async def _persist_proposals(
        self,
        *,
        organization_id: uuid.UUID,
        store_id: uuid.UUID | None,
        proposals: list[dict[str, Any]],
        known_target_ids: set[str],
    ) -> list[AIDecision]:
        decisions: list[AIDecision] = []

        for proposal in proposals:
            target_id = parse_known_uuid(proposal.get("target_id"), known_target_ids)
            action_type = ActionType(proposal["action_type"])
            risk_level = RiskLevel(proposal["risk_level"])

            decision = AIDecision(
                organization_id=organization_id,
                store_id=store_id,
                status=DecisionStatus.PENDING_APPROVAL,
                title=proposal["title"],
                summary=proposal["summary"],
                action_type=action_type,
                risk_level=risk_level,
                confidence=Decimal(str(proposal["confidence"])),
                expected_impact=proposal["expected_impact"],
                reasoning=proposal["reasoning"],
                model_name=self.model,
                prompt_version=STRATEGIST_PROMPT_VERSION,
            )
            self.db.add(decision)
            await self.db.flush()

            action = ActionProposal(
                ai_decision_id=decision.id,
                target_type=proposal["target_type"],
                target_id=target_id,
                payload=sanitize_payload(proposal["payload"], known_target_ids),
                requires_approval=bool(proposal["requires_approval"]),
                status=DecisionStatus.PENDING_APPROVAL,
            )
            self.db.add(action)
            decision.proposals.append(action)
            decisions.append(decision)

        await self.db.flush()
        return decisions


def extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    output = getattr(response, "output", [])
    for item in output:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                return text

    raise ValueError("Strategist LLM response did not include output text.")


def parse_known_uuid(value: Any, known_target_ids: set[str]) -> uuid.UUID | None:
    if not value or str(value) not in known_target_ids:
        return None
    return uuid.UUID(str(value))


def sanitize_payload(payload: dict[str, Any], known_target_ids: set[str]) -> dict[str, Any]:
    cleaned = dict(payload)
    for key in ("product_id", "campaign_id"):
        value = cleaned.get(key)
        if value and str(value) not in known_target_ids:
            cleaned[key] = None
    return cleaned


def decimal_to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)
