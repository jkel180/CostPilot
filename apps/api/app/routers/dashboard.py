"""Main dashboard summary.

Each KPI is either backed by stored data (with provenance) or explicitly
``not_available`` with the reason. The API never fabricates a value to fill a slot.
"""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app import market
from app.deps import DbSession, OrgCtx
from app.models import Alert, Commodity, CustomerPurchase, DataSource, MarketObservation, ObservationDataType
from app.purchases import group_wapp
from app.schemas import CommodityOut, DashboardSummary, DataStatus, Kpi, Provenance, SeriesPoint

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DEFAULT_COMMODITY = "lemon_juice_concentrate"


def _benchmark_kpis(db, com) -> list[Kpi]:
    b = market.benchmark(db, com)
    if b is None:
        reason = "No validated market observations yet."
        return [
            Kpi(key="current_market_benchmark", label="Current Market Benchmark", status="not_available", reason=reason),
            Kpi(key="monthly_price_change", label="Monthly Price Change", status="not_available", reason=reason),
        ]
    o, src = b["observation"], b["source"]
    prov = Provenance(
        source_id=src.id, source_name=src.name, data_type=o.data_type, observation_date=o.observation_date,
        collected_at=o.collected_at, is_synthetic=src.is_synthetic,
    )
    scope = "EU import unit value from outside the EU (customs), not a spot price"
    if b["spec"]:
        scope += f" · {b['spec'].specification_name.split(' - ')[0]}"
    kpis = [
        Kpi(key="current_market_benchmark", label="Current Market Benchmark", status="available", value=o.value,
            unit=o.unit, currency=o.currency, value_kind="observed", provenance=prov, note=scope)
    ]
    if b["mom_pct"] is None:
        kpis.append(Kpi(key="monthly_price_change", label="Monthly Price Change", status="not_available",
                        reason="No validated value for the previous month."))
    else:
        kpis.append(
            Kpi(key="monthly_price_change", label="Monthly Price Change", status="available", value=b["mom_pct"],
                unit="%", value_kind="calculated", provenance=prov,
                note=f"{o.observation_date:%b %Y} vs {b['previous'].observation_date:%b %Y}")
        )
    return kpis


def _customer_price_kpi(db, org_id, com) -> Kpi:
    since = date.today() - timedelta(days=365)
    ps = db.scalars(
        select(CustomerPurchase).where(
            CustomerPurchase.organization_id == org_id,
            CustomerPurchase.commodity_id == com.id,
            CustomerPurchase.purchase_date >= since,
        )
    ).all()
    label = "Customer Average Purchase Price"
    if not ps:
        return Kpi(key="customer_avg_purchase_price", label=label, status="not_available",
                   reason="No purchases in the last 12 months. Upload them in My Purchases.")
    groups = group_wapp(ps, lambda p: "all")
    if len(groups) > 1:
        return Kpi(key="customer_avg_purchase_price", label=label, status="not_available",
                   reason="Purchases use different units or currencies; see My Purchases for each group.")
    g = groups[0]
    return Kpi(key="customer_avg_purchase_price", label=label, status="available", value=g["weighted_avg_price"],
               unit=g["unit"], currency=g["currency"], value_kind="calculated",
               note=f"Weighted average of {g['purchases']} purchases, last 12 months")


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
    active_sources = (
        db.scalar(
            select(func.count(func.distinct(MarketObservation.source_id))).where(
                MarketObservation.commodity_id == com.id
            )
        )
        or 0
    )

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

    forecast_reason = "Forecasting pipeline with backtesting arrives in Sprint 3."
    kpis = [
        *_benchmark_kpis(db, com),
        Kpi(key="forecast_3m", label="3-Month Forecast", status="not_available", reason=forecast_reason),
        Kpi(key="forecast_6m", label="6-Month Forecast", status="not_available", reason=forecast_reason),
        _customer_price_kpi(db, org_id, com),
        Kpi(key="estimated_cost_exposure", label="Estimated Cost Exposure", status="not_available",
            reason="Cost model arrives in Sprint 3."),
    ]

    bench_pts = market.series(db, com, ObservationDataType.customs_unit_value, [market.BENCHMARK_GEOGRAPHY]).get(
        market.BENCHMARK_GEOGRAPHY, []
    )[-36:]

    return DashboardSummary(
        commodity=CommodityOut.model_validate(com),
        organization_currency=ctx.organization.currency,
        kpis=kpis,
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
        benchmark_series=[
            SeriesPoint(date=p.observation_date, value=p.value, quality_status=p.quality_status.value) for p in bench_pts
        ],
        benchmark_label=market.BENCHMARK_LABEL if bench_pts else None,
    )
