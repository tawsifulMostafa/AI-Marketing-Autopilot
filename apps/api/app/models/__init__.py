"""SQLAlchemy model registry."""

from app.models.auth import User
from app.models.campaign import AdPlatform, Campaign, CampaignMetric, CampaignStatus
from app.models.decision import (
    AIDecision,
    ActionProposal,
    ActionType,
    DecisionStatus,
    RiskLevel,
)
from app.models.organization import Organization, OrganizationMember, UserRole
from app.models.product import (
    Product,
    ProductInsight,
    ProductPerformanceLabel,
    ProductStatus,
)

__all__ = [
    "Organization",
    "OrganizationMember",
    "AdPlatform",
    "AIDecision",
    "ActionProposal",
    "ActionType",
    "Campaign",
    "CampaignMetric",
    "CampaignStatus",
    "DecisionStatus",
    "Product",
    "ProductInsight",
    "ProductPerformanceLabel",
    "ProductStatus",
    "RiskLevel",
    "User",
    "UserRole",
]
