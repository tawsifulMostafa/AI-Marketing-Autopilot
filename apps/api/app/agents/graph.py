from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.creative_agent import CreativeConfigurationError, CreativeEngineAgent
from app.agents.strategist_agent import AIStrategistAgent
from app.core.config import Settings
from app.models import ActionProposal, ActionType, ApprovalRequest
from app.services.approval_service import ApprovalService
from app.services.ingestion_service import IngestionResult, ShopifyIngestionService


@dataclass(frozen=True)
class DailyPlanResult:
    ingestion: IngestionResult
    decisions_count: int
    creative_assets: list[dict[str, Any]]
    approval_requests: list[ApprovalRequest]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ingestion": self.ingestion.as_dict(),
            "decisions_count": self.decisions_count,
            "creative_assets": self.creative_assets,
            "approval_requests": [
                {
                    "id": str(approval.id),
                    "status": approval.status.value,
                    "ai_decision_id": str(approval.ai_decision_id) if approval.ai_decision_id else None,
                    "action_proposal_id": (
                        str(approval.action_proposal_id)
                        if approval.action_proposal_id
                        else None
                    ),
                    "requested_message": approval.requested_message,
                }
                for approval in self.approval_requests
            ],
        }


class DailyPlanOrchestrator:
    """Runs MarketFlow's daily autonomous plan up to human approval."""

    def __init__(
        self,
        *,
        db: AsyncSession,
        settings: Settings,
    ) -> None:
        self.db = db
        self.settings = settings

    async def run(
        self,
        *,
        organization_id: uuid.UUID,
        store_id: uuid.UUID,
        product_pages: int = 2,
        order_pages: int = 2,
        page_size: int = 50,
        lookback_days: int = 30,
    ) -> DailyPlanResult:
        ingestion = await ShopifyIngestionService(
            db=self.db,
            settings=self.settings,
        ).sync_and_analyze(
            store_id=store_id,
            product_pages=product_pages,
            order_pages=order_pages,
            page_size=page_size,
        )

        strategy = await AIStrategistAgent(
            db=self.db,
            settings=self.settings,
        ).run(
            organization_id=organization_id,
            store_id=store_id,
            lookback_days=lookback_days,
        )

        creative_assets = await self._generate_creative_for_launches(
            organization_id=organization_id,
            store_id=store_id,
            proposals=[
                proposal
                for decision in strategy.decisions
                for proposal in decision.proposals
            ],
        )

        approval_service = ApprovalService(db=self.db)
        approval_requests: list[ApprovalRequest] = []
        for decision in strategy.decisions:
            for proposal in decision.proposals:
                approval = await approval_service.create_for_proposal(
                    organization_id=organization_id,
                    decision=decision,
                    proposal=proposal,
                )
                approval_requests.append(approval)

        await self.db.commit()
        return DailyPlanResult(
            ingestion=ingestion,
            decisions_count=len(strategy.decisions),
            creative_assets=creative_assets,
            approval_requests=approval_requests,
        )

    async def _generate_creative_for_launches(
        self,
        *,
        organization_id: uuid.UUID,
        store_id: uuid.UUID,
        proposals: list[ActionProposal],
    ) -> list[dict[str, Any]]:
        creative_assets: list[dict[str, Any]] = []

        for proposal in proposals:
            if proposal.decision.action_type not in {
                ActionType.LAUNCH_CAMPAIGN,
                ActionType.GENERATE_CREATIVE,
            }:
                continue
            if proposal.target_type != "product" or proposal.target_id is None:
                continue

            try:
                creative = await CreativeEngineAgent(
                    db=self.db,
                    settings=self.settings,
                ).generate_for_product(
                    organization_id=organization_id,
                    store_id=store_id,
                    product_id=proposal.target_id,
                )
            except CreativeConfigurationError:
                proposal.payload = {
                    **proposal.payload,
                    "creative_generation_status": "skipped_missing_openai_api_key",
                }
                continue

            creative_payload = creative.as_dict()
            first_variant = creative_payload["variants"][0] if creative_payload["variants"] else {}
            proposal.payload = {
                **proposal.payload,
                "creative_asset_id": creative_payload["creative_asset_id"],
                "image_prompt": creative_payload["image_prompt"],
                "primary_text": first_variant.get("primary_text"),
                "headline": first_variant.get("headline"),
                "description": first_variant.get("description"),
                "creative_generation_status": "generated",
            }
            creative_assets.append(creative_payload)

        return creative_assets
