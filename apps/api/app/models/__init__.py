"""SQLAlchemy model registry."""

from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.auth import User
from app.models.campaign import AdPlatform, Campaign, CampaignMetric, CampaignStatus
from app.models.creative import CreativeAsset, CreativeVariant
from app.models.decision import (
    AIDecision,
    ActionProposal,
    ActionType,
    DecisionStatus,
    RiskLevel,
)
from app.models.execution import ExecutionLog
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
    "ApprovalRequest",
    "ApprovalStatus",
    "Campaign",
    "CampaignMetric",
    "CampaignStatus",
    "CreativeAsset",
    "CreativeVariant",
    "DecisionStatus",
    "ExecutionLog",
    "Product",
    "ProductInsight",
    "ProductPerformanceLabel",
    "ProductStatus",
    "RiskLevel",
    "User",
    "UserRole",
]
