from __future__ import annotations

from dataclasses import dataclass

from models import BillingPlan
from schemas import BillingPlanConfigResponse


@dataclass(frozen=True, slots=True)
class PlanConfig:
    plan: BillingPlan
    name: str
    monthly_price: int
    annual_price_monthly_equivalent: int
    ai_refresh_limit: int
    pdp_view_soft_limit: int
    history_days: int
    recommended: bool = False


TRIAL_DAYS = 14
TRIAL_AI_REFRESH_LIMIT = 50
TRIAL_PDP_VIEW_SOFT_LIMIT = 25_000

PLAN_CONFIGS: dict[BillingPlan, PlanConfig] = {
    BillingPlan.STARTER: PlanConfig(
        plan=BillingPlan.STARTER,
        name="SKU Lens Starter",
        monthly_price=19,
        annual_price_monthly_equivalent=15,
        ai_refresh_limit=50,
        pdp_view_soft_limit=25_000,
        history_days=30,
    ),
    BillingPlan.GROWTH: PlanConfig(
        plan=BillingPlan.GROWTH,
        name="SKU Lens Growth",
        monthly_price=39,
        annual_price_monthly_equivalent=29,
        ai_refresh_limit=150,
        pdp_view_soft_limit=100_000,
        history_days=90,
        recommended=True,
    ),
    BillingPlan.PRO: PlanConfig(
        plan=BillingPlan.PRO,
        name="SKU Lens Pro",
        monthly_price=79,
        annual_price_monthly_equivalent=59,
        ai_refresh_limit=500,
        pdp_view_soft_limit=500_000,
        history_days=365,
    ),
}

PLAN_RANK: dict[BillingPlan, int] = {
    BillingPlan.STARTER: 1,
    BillingPlan.GROWTH: 2,
    BillingPlan.PRO: 3,
}


def plan_config_response(config: PlanConfig) -> BillingPlanConfigResponse:
    return BillingPlanConfigResponse(
        ai_refresh_limit=config.ai_refresh_limit,
        annual_price_monthly_equivalent=config.annual_price_monthly_equivalent,
        history_days=config.history_days,
        monthly_price=config.monthly_price,
        name=config.name,
        pdp_view_soft_limit=config.pdp_view_soft_limit,
        plan=config.plan,
        recommended=config.recommended,
    )


def plan_matrix() -> list[BillingPlanConfigResponse]:
    return [plan_config_response(PLAN_CONFIGS[plan]) for plan in PLAN_CONFIGS]
