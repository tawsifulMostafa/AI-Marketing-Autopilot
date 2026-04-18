from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import Settings
from app.models import ActionProposal, ActionType


class MetaAdsConfigurationError(Exception):
    """Raised when required Meta Ads settings are missing."""


class MetaAdsPublishError(Exception):
    """Raised when the Meta Marketing API rejects a publish request."""


@dataclass(frozen=True)
class MetaAdsPublisherConfig:
    app_id: str
    app_secret: str
    access_token: str
    ad_account_id: str
    page_id: str
    api_version: str = "v21.0"
    default_campaign_status: str = "PAUSED"
    default_ad_status: str = "PAUSED"

    @classmethod
    def from_settings(cls, settings: Settings) -> MetaAdsPublisherConfig:
        missing = [
            name
            for name, value in {
                "META_APP_ID": settings.meta_app_id,
                "META_APP_SECRET": settings.meta_app_secret,
                "META_ACCESS_TOKEN": settings.meta_access_token,
                "META_AD_ACCOUNT_ID": settings.meta_ad_account_id,
                "META_PAGE_ID": settings.meta_page_id,
            }.items()
            if not value
        ]
        if missing:
            raise MetaAdsConfigurationError(
                "Missing Meta Ads settings: " + ", ".join(sorted(missing))
            )

        return cls(
            app_id=str(settings.meta_app_id),
            app_secret=str(settings.meta_app_secret),
            access_token=str(settings.meta_access_token),
            ad_account_id=normalize_ad_account_id(str(settings.meta_ad_account_id)),
            page_id=str(settings.meta_page_id),
            api_version=settings.meta_api_version,
            default_campaign_status=settings.meta_default_campaign_status.upper(),
            default_ad_status=settings.meta_default_ad_status.upper(),
        )


@dataclass(frozen=True)
class MetaAdsPublishResult:
    operation: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    external_object_id: str | None
    status: str = "published"


class MetaAdsPublisher:
    """Publishes approved MarketFlow action proposals to the Meta Marketing API."""

    def __init__(self, config: MetaAdsPublisherConfig) -> None:
        self.config = config

    def publish_action(self, proposal: ActionProposal) -> MetaAdsPublishResult:
        self._init_sdk()
        action_type = proposal.decision.action_type

        if action_type == ActionType.LAUNCH_CAMPAIGN:
            return self._launch_campaign(proposal)
        if action_type == ActionType.PAUSE_CAMPAIGN:
            return self._pause_campaign(proposal)
        if action_type in {ActionType.SCALE_BUDGET, ActionType.REDUCE_BUDGET}:
            return self._update_budget(proposal)
        if action_type == ActionType.GENERATE_CREATIVE:
            return self._create_creative(proposal)

        raise MetaAdsPublishError(f"Meta publishing is not implemented for {action_type.value}.")

    def _init_sdk(self) -> None:
        try:
            from facebook_business.api import FacebookAdsApi
        except ImportError as exc:
            raise MetaAdsConfigurationError(
                "facebook-business is not installed. Run `pip install facebook-business`."
            ) from exc

        FacebookAdsApi.init(
            app_id=self.config.app_id,
            app_secret=self.config.app_secret,
            access_token=self.config.access_token,
            api_version=self.config.api_version,
        )

    def _launch_campaign(self, proposal: ActionProposal) -> MetaAdsPublishResult:
        from facebook_business.adobjects.ad import Ad
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.adobjects.adcreative import AdCreative
        from facebook_business.adobjects.adset import AdSet
        from facebook_business.adobjects.campaign import Campaign

        payload = build_meta_publish_payload(proposal, self.config)
        account = AdAccount(self.config.ad_account_id)

        try:
            campaign = account.create_campaign(
                fields=[],
                params={
                    Campaign.Field.name: payload["campaign"]["name"],
                    Campaign.Field.objective: payload["campaign"]["objective"],
                    Campaign.Field.status: payload["campaign"]["status"],
                    Campaign.Field.special_ad_categories: payload["campaign"][
                        "special_ad_categories"
                    ],
                },
            )
            campaign_id = str(campaign.get("id"))

            adset_params = {
                AdSet.Field.name: payload["adset"]["name"],
                AdSet.Field.campaign_id: campaign_id,
                AdSet.Field.daily_budget: payload["adset"]["daily_budget"],
                AdSet.Field.billing_event: payload["adset"]["billing_event"],
                AdSet.Field.optimization_goal: payload["adset"]["optimization_goal"],
                AdSet.Field.bid_strategy: payload["adset"]["bid_strategy"],
                AdSet.Field.targeting: payload["adset"]["targeting"],
                AdSet.Field.status: payload["adset"]["status"],
            }
            adset = account.create_ad_set(fields=[], params=adset_params)
            adset_id = str(adset.get("id"))

            creative = account.create_ad_creative(
                fields=[],
                params={
                    AdCreative.Field.name: payload["creative"]["name"],
                    AdCreative.Field.object_story_spec: payload["creative"][
                        "object_story_spec"
                    ],
                },
            )
            creative_id = str(creative.get("id"))

            ad = account.create_ad(
                fields=[],
                params={
                    Ad.Field.name: payload["ad"]["name"],
                    Ad.Field.adset_id: adset_id,
                    Ad.Field.creative: {"creative_id": creative_id},
                    Ad.Field.status: payload["ad"]["status"],
                },
            )
            ad_id = str(ad.get("id"))
        except Exception as exc:  # SDK wraps API errors in custom exception classes.
            raise MetaAdsPublishError(format_meta_exception(exc)) from exc

        return MetaAdsPublishResult(
            operation="publish_launch_campaign",
            request_payload=payload,
            external_object_id=ad_id,
            response_payload={
                "campaign_id": campaign_id,
                "adset_id": adset_id,
                "creative_id": creative_id,
                "ad_id": ad_id,
                "status": payload["ad"]["status"],
            },
        )

    def _create_creative(self, proposal: ActionProposal) -> MetaAdsPublishResult:
        from facebook_business.adobjects.adaccount import AdAccount
        from facebook_business.adobjects.adcreative import AdCreative

        payload = build_meta_publish_payload(proposal, self.config)
        account = AdAccount(self.config.ad_account_id)

        try:
            creative = account.create_ad_creative(
                fields=[],
                params={
                    AdCreative.Field.name: payload["creative"]["name"],
                    AdCreative.Field.object_story_spec: payload["creative"][
                        "object_story_spec"
                    ],
                },
            )
            creative_id = str(creative.get("id"))
        except Exception as exc:
            raise MetaAdsPublishError(format_meta_exception(exc)) from exc

        return MetaAdsPublishResult(
            operation="publish_generate_creative",
            request_payload=payload,
            response_payload={"creative_id": creative_id},
            external_object_id=creative_id,
        )

    def _pause_campaign(self, proposal: ActionProposal) -> MetaAdsPublishResult:
        from facebook_business.adobjects.ad import Ad
        from facebook_business.adobjects.adset import AdSet
        from facebook_business.adobjects.campaign import Campaign

        action_payload = proposal.payload or {}
        object_id, object_type = resolve_meta_object(action_payload, default_type="campaign")
        request_payload = {
            "action_type": proposal.decision.action_type.value,
            "object_type": object_type,
            "object_id": object_id,
            "status": "PAUSED",
        }

        try:
            if object_type == "ad":
                Ad(object_id).api_update(params={"status": "PAUSED"})
            elif object_type == "adset":
                AdSet(object_id).api_update(params={"status": "PAUSED"})
            else:
                Campaign(object_id).api_update(params={"status": "PAUSED"})
        except Exception as exc:
            raise MetaAdsPublishError(format_meta_exception(exc)) from exc

        return MetaAdsPublishResult(
            operation=f"publish_pause_{object_type}",
            request_payload=request_payload,
            response_payload={"object_id": object_id, "object_type": object_type, "status": "PAUSED"},
            external_object_id=object_id,
        )

    def _update_budget(self, proposal: ActionProposal) -> MetaAdsPublishResult:
        from facebook_business.adobjects.adset import AdSet
        from facebook_business.adobjects.campaign import Campaign

        action_payload = proposal.payload or {}
        daily_budget = to_meta_minor_units(action_payload.get("recommended_daily_budget"))
        if daily_budget is None:
            raise MetaAdsPublishError("recommended_daily_budget is required for budget updates.")

        object_id, object_type = resolve_meta_object(action_payload, default_type="adset")
        request_payload = {
            "action_type": proposal.decision.action_type.value,
            "object_type": object_type,
            "object_id": object_id,
            "daily_budget": daily_budget,
            "currency": action_payload.get("currency", "USD"),
        }

        try:
            if object_type == "campaign":
                Campaign(object_id).api_update(params={"daily_budget": daily_budget})
            elif object_type == "adset":
                AdSet(object_id).api_update(params={"daily_budget": daily_budget})
            else:
                raise MetaAdsPublishError("Budget updates require a campaign or adset Meta ID.")
        except MetaAdsPublishError:
            raise
        except Exception as exc:
            raise MetaAdsPublishError(format_meta_exception(exc)) from exc

        return MetaAdsPublishResult(
            operation=f"publish_update_{object_type}_budget",
            request_payload=request_payload,
            response_payload={
                "object_id": object_id,
                "object_type": object_type,
                "daily_budget": daily_budget,
            },
            external_object_id=object_id,
        )


def build_meta_publish_payload(
    proposal: ActionProposal,
    config: MetaAdsPublisherConfig,
) -> dict[str, Any]:
    action_payload = proposal.payload or {}
    product_title = action_payload.get("product_title") or "MarketFlow Product"
    campaign_name = action_payload.get("campaign_name") or proposal.decision.title
    destination_url = first_present(
        action_payload,
        "destination_url",
        "product_url",
        "url",
        default="https://example.com",
    )
    daily_budget = to_meta_minor_units(action_payload.get("recommended_daily_budget")) or 1000
    objective = str(action_payload.get("objective") or "OUTCOME_TRAFFIC")
    ad_status = str(action_payload.get("ad_status") or config.default_ad_status).upper()
    campaign_status = str(
        action_payload.get("campaign_status") or config.default_campaign_status
    ).upper()

    primary_text = str(
        action_payload.get("primary_text")
        or action_payload.get("notes")
        or f"Discover {product_title} today."
    )
    headline = str(action_payload.get("headline") or product_title)
    description = str(
        action_payload.get("description")
        or action_payload.get("notes")
        or "Recommended by MarketFlow AI."
    )

    return {
        "destination": "meta_ads_api",
        "mode": "real_publish",
        "action_type": proposal.decision.action_type.value,
        "target_type": proposal.target_type,
        "target_id": str(proposal.target_id) if proposal.target_id else None,
        "campaign": {
            "name": campaign_name,
            "objective": objective,
            "status": campaign_status,
            "special_ad_categories": action_payload.get("special_ad_categories", []),
        },
        "adset": {
            "name": action_payload.get("adset_name") or f"{campaign_name} - Prospecting",
            "daily_budget": daily_budget,
            "billing_event": action_payload.get("billing_event", "IMPRESSIONS"),
            "optimization_goal": action_payload.get("optimization_goal", "LINK_CLICKS"),
            "bid_strategy": action_payload.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
            "targeting": normalize_targeting(action_payload.get("targeting")),
            "status": campaign_status,
        },
        "creative": {
            "name": action_payload.get("creative_name") or f"{product_title} Creative",
            "object_story_spec": {
                "page_id": config.page_id,
                "link_data": {
                    "message": primary_text,
                    "link": destination_url,
                    "name": headline,
                    "description": description,
                    "call_to_action": {
                        "type": action_payload.get("call_to_action", "SHOP_NOW"),
                        "value": {"link": destination_url},
                    },
                    **optional_picture(action_payload),
                },
            },
        },
        "ad": {
            "name": action_payload.get("ad_name") or f"{product_title} Ad",
            "status": ad_status,
        },
        "source_action_payload": action_payload,
    }


def normalize_ad_account_id(account_id: str) -> str:
    account_id = account_id.strip()
    return account_id if account_id.startswith("act_") else f"act_{account_id}"


def normalize_targeting(targeting: Any) -> dict[str, Any]:
    if isinstance(targeting, dict) and targeting:
        normalized = dict(targeting)
    else:
        normalized = {"geo_locations": {"countries": ["US"]}, "age_min": 18, "age_max": 65}

    geo_locations = normalized.get("geo_locations")
    if isinstance(geo_locations, list):
        normalized["geo_locations"] = {"countries": geo_locations}

    return normalized


def optional_picture(payload: dict[str, Any]) -> dict[str, str]:
    image_hash = payload.get("image_hash")
    if image_hash:
        return {"image_hash": str(image_hash)}

    image_url = payload.get("image_url") or payload.get("public_url")
    if image_url:
        return {"picture": str(image_url)}

    return {}


def first_present(payload: dict[str, Any], *keys: str, default: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return default


def to_meta_minor_units(value: Any) -> int | None:
    if value in (None, ""):
        return None

    try:
        return int((Decimal(str(value)) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError):
        raise MetaAdsPublishError(f"Invalid budget value: {value!r}") from None


def resolve_meta_object(
    payload: dict[str, Any],
    *,
    default_type: str,
) -> tuple[str, str]:
    if payload.get("external_ad_id") or payload.get("meta_ad_id"):
        return str(payload.get("external_ad_id") or payload.get("meta_ad_id")), "ad"
    if payload.get("external_adset_id") or payload.get("meta_adset_id"):
        return str(payload.get("external_adset_id") or payload.get("meta_adset_id")), "adset"
    if payload.get("external_campaign_id") or payload.get("meta_campaign_id"):
        return (
            str(payload.get("external_campaign_id") or payload.get("meta_campaign_id")),
            "campaign",
        )

    key = f"external_{default_type}_id"
    raise MetaAdsPublishError(
        f"{key}, meta_{default_type}_id, or a more specific Meta object id is required."
    )


def format_meta_exception(exc: Exception) -> str:
    api_error_message = getattr(exc, "api_error_message", None)
    if callable(api_error_message):
        message = api_error_message()
        if message:
            return str(message)

    return str(exc)
