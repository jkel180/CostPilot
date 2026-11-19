"""Main dashboard summary.

Sprint 1 skeleton: the KPI slots and data-update status are real queries, but every
KPI stays ``not_available`` until the corresponding pipeline exists (market data in
Sprint 2, forecasts / purchase analytics / cost model in Sprint 3). The API never
fabricates a value to fill a slot.
"""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.deps import DbSession, OrgCtx
from app.models import Alert, Commodity, CustomerPurchase, DataSource, MarketObservation
from app.schemas import CommodityOut, DashboardSummary, DataStatus, Kpi

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DEFAULT_COMMODITY = "lemon_juice_concentrate"

KPI_SLOTS: list[tuple[str, str, str]] = [
    ("current_market_benchmark", "Current Market Benchmark", "Market data ingestion arrives in Sprint 2."),
    ("monthly_price_change", "Monthly Price Change", "Market data ingestion arrives in Sprint 2."),
    ("forecast_3m", "3-Month Forecast", "Forecasting pipeline with backtesting arrives in Sprint 3."),
    ("forecast_6m", "6-Month Forecast", "Forecasting pipeline with backtesting arrives in Sprint 3."),
    ("customer_avg_purchase_price", "Customer Average Purchase Price", "Purchase CSV import arrives in Sprint 2; WAPP in Sprint 3."),
    ("estimated_cost_exposure", "Estimated Cost Exposure", "Cost model arrives in Sprint 3."),
]


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    ctx: OrgCtx,
    db: DbSession,
    commodity: str = Query(default=DEFAULT_COMMODITY, max_length=64),
) -> DashboardSummary:
    com = db.scalar(select(Commodity).where(Commodity.code == commodity, Commodity.active.is_(True)))
    if com is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")

    obs_count, latest_obs, latest_collected = db.execute(
        select(
            func.count(MarketObservation.id),
            func.max(MarketObservation.observation_date),
            func.max(MarketObservation.collected_at),
        ).where(MarketObservation.commodity_id == com.id)
    ).one()
    synthetic_present = (
        db.scalar(
            select(func.count(MarketObservation.id))
            .join(DataSource, DataSource.id == MarketObservation.source_id)
            .where(MarketObservation.commodity_id == com.id, DataSource.is_synthetic.is_(True))
        )
        or 0
    ) > 0
    active_sources = db.scalar(select(func.count(DataSource.id)).where(DataSource.active.is_(True))) or 0

    org_id = ctx.organization.id
    purchase_count, latest_purchase = db.execute(
        select(func.count(CustomerPurchase.id), func.max(CustomerPurchase.purchase_date)).where(
            CustomerPurchase.organization_id == org_id, CustomerPurchase.commodity_id == com.id
        )
    ).one()
    active_alerts = (
        db.scalar(
            select(func.count(Alert.id)).where(
                Alert.organization_id == org_id, Alert.commodity_id == com.id, Alert.active.is_(True)
            )
        )
        or 0
    )

    return DashboardSummary(
        commodity=CommodityOut.model_validate(com),
        organization_currency=ctx.organization.currency,
        kpis=[Kpi(key=k, label=label, status="not_available", reason=reason) for k, label, reason in KPI_SLOTS],
        data_status=DataStatus(
            market_observations=obs_count,
            latest_observation_date=latest_obs,
            latest_collected_at=latest_collected,
            active_sources=active_sources,
            synthetic_data_present=synthetic_present,
            customer_purchases=purchase_count,
            latest_purchase_date=latest_purchase,
        ),
        active_alerts=active_alerts,
    )
