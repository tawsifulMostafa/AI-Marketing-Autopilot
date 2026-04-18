from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.integrations.meta_ads import (
    MetaAdsConfigurationError,
    MetaAdsPublishError,
    MetaAdsPublisher,
    MetaAdsPublisherConfig,
)
from app.models import ActionProposal, AdPlatform, ExecutionLog


@dataclass(frozen=True)
class ExecutionResult:
    log: ExecutionLog

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_log_id": str(self.log.id),
            "status": self.log.status,
            "platform": self.log.platform.value if self.log.platform else None,
            "operation": self.log.operation,
            "request_payload": self.log.request_payload,
            "response_payload": self.log.response_payload,
        }


class ExecutionAgent:
    """Publishes approved ad actions to Meta Ads and records the outbound payload."""

    def __init__(self, *, db: AsyncSession, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    async def execute_approved_action(
        self,
        *,
        organization_id,
        proposal: ActionProposal,
    ) -> ExecutionResult:
        try:
            publisher = MetaAdsPublisher(MetaAdsPublisherConfig.from_settings(self.settings))
            result = await asyncio.to_thread(publisher.publish_action, proposal)
        except (MetaAdsConfigurationError, MetaAdsPublishError) as exc:
            payload = build_meta_ads_simulation_payload(proposal)
            log = ExecutionLog(
                organization_id=organization_id,
                action_proposal_id=proposal.id,
                platform=AdPlatform.META,
                operation=f"publish_{proposal.decision.action_type.value}",
                request_payload=payload,
                response_payload={"error": str(exc), "published": False},
                status="failed",
                error_message=str(exc),
            )
            self.db.add(log)
            await self.db.flush()
            return ExecutionResult(log=log)

        log = ExecutionLog(
            organization_id=organization_id,
            action_proposal_id=proposal.id,
            platform=AdPlatform.META,
            operation=result.operation,
            request_payload=result.request_payload,
            response_payload=result.response_payload,
            external_object_id=result.external_object_id,
            status=result.status,
        )
        self.db.add(log)
        await self.db.flush()
        return ExecutionResult(log=log)


# Backward-compatible alias for older imports while approvals move to real publishing.
ExecutionSimulationAgent = ExecutionAgent


def build_meta_ads_simulation_payload(proposal: ActionProposal) -> dict[str, Any]:
    action_payload = proposal.payload or {}
    budget = {
        "recommended_daily_budget": action_payload.get("recommended_daily_budget"),
        "budget_change_percent": action_payload.get("budget_change_percent"),
        "currency": action_payload.get("currency", "USD"),
    }
    targeting = action_payload.get(
        "targeting",
        {
            "geo_locations": ["configured_store_market"],
            "audience": "prospecting_or_retargeting_to_be_selected_by_executor",
            "placements": ["facebook_feed", "instagram_feed", "instagram_stories"],
        },
    )

    return {
        "destination": "meta_ads_api",
        "mode": "simulation",
        "action_type": proposal.decision.action_type.value,
        "target_type": proposal.target_type,
        "target_id": str(proposal.target_id) if proposal.target_id else None,
        "campaign": {
            "name": action_payload.get("campaign_name") or proposal.decision.title,
            "objective": action_payload.get("objective", "OUTCOME_SALES"),
            "channel": action_payload.get("channel", "meta"),
            "product_id": action_payload.get("product_id"),
            "product_title": action_payload.get("product_title"),
            "campaign_id": action_payload.get("campaign_id"),
        },
        "budget": budget,
        "targeting": targeting,
        "creative": {
            "creative_asset_id": action_payload.get("creative_asset_id"),
            "primary_text": action_payload.get("primary_text"),
            "headline": action_payload.get("headline"),
            "description": action_payload.get("description"),
            "image_prompt": action_payload.get("image_prompt"),
        },
        "source_action_payload": action_payload,
    }
