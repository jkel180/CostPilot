"""Main dashboard summary.

Each KPI is either backed by stored data (with provenance) or explicitly
``not_available`` with the reason. The API never fabricates a value to fill a slot.
"""

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from collections import defaultdict
from decimal import Decimal

from app import market
from app.deps import DbSession, OrgCtx
from app.forecasting.read import forecasts_for, latest_completed_run
from app.purchases import weighted_average_price
from app.schemas import SimulationRequest
from app.units import price_per_kg, quantity_in_kg
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


def _forecast_kpis(db, com) -> tuple[list[Kpi], list]:
    run = latest_completed_run(db, com)
    fcs = forecasts_for(db, run) if run and run.status == "success" else []
    kpis = []
    for h in (3, 6):
        key, label = f"forecast_{h}m", f"{h}-Month Forecast"
        f = next((x for x in fcs if x.horizon_months == h), None)
        if f is None:
            reason = ("Not enough validated history to backtest a forecast." if run and run.status == "insufficient_data"
                      else "No forecast has been generated yet.")
            kpis.append(Kpi(key=key, label=label, status="not_available", reason=reason))
            continue
        level = int((f.interval_level or Decimal("0.8")) * 100)
        rng = f"{level}% range {f.lower:.2f}-{f.upper:.2f}"
        if f.quality == "reliable":
            note = f"{rng} · {f.model_label}, {f.improvement_pct}% lower error than the {f.baseline} baseline"
        else:
            note = f"{rng} · no model beat the naive baseline: not a reliable prediction"
        kpis.append(Kpi(key=key, label=label, status="available", value=f.value, unit=run.unit, currency=run.currency,
                        value_kind="forecast", note=note, quality=f.quality))
    return kpis, fcs


def _customer_series(db, org_id, com) -> tuple[list[SeriesPoint], str | None]:
    """Monthly weighted average of the organization's purchases in EUR/kg (explicit unit rules only)."""
    ps = db.scalars(select(CustomerPurchase).where(
        CustomerPurchase.organization_id == org_id, CustomerPurchase.commodity_id == com.id)).all()
    if not ps:
        return [], None
    months: dict[date, list] = defaultdict(list)
    skipped = 0
    for p in ps:
        per_kg, _ = price_per_kg(p.unit_price, p.unit, p.currency)
        qty = quantity_in_kg(p.quantity, p.unit)
        if per_kg is None or qty is None:
            skipped += 1
            continue
        months[p.purchase_date.replace(day=1)].append((qty, per_kg))
    pts = [SeriesPoint(date=d, value=weighted_average_price(v).quantize(Decimal("0.0001")), quality_status="validated")
           for d, v in sorted(months.items())]
    note = (f"{skipped} purchases in other currencies or non-mass units are not shown (no conversion rule)."
            if skipped else None)
    return pts, note


def _exposure(db, ctx, com) -> tuple[Kpi, list]:
    from app.routers.cost import _get_model, simulate  # avoid an import cycle

    label = "Estimated Cost Exposure"
    if _get_model(db, ctx.organization.id, com.id) is None:
        return Kpi(key="estimated_cost_exposure", label=label, status="not_available",
                   reason="Set up your cost model in Cost Simulator."), []
    sim = simulate(db, ctx, com, SimulationRequest(months=3, custom_changes_pct=[Decimal(-10), Decimal(10)]))
    by_key = {x.key: x for x in sim.scenarios}
    base = by_key.get("base")
    if base is None:
        return Kpi(key="estimated_cost_exposure", label=label, status="not_available",
                   reason="Needs a forecast of the market benchmark."), sim.scenarios
    low, high = by_key["downside"].period_impact, by_key["upside"].period_impact
    note = (f"Next 3 months, base forecast vs your current price on {sim.monthly_quantity:,.0f} {sim.unit}/month; "
            f"range {low:,.0f} to {high:,.0f} {sim.currency}")
    return Kpi(key="estimated_cost_exposure", label=label, status="available", value=base.period_impact,
               unit="3 months", currency=sim.currency, value_kind="calculated", quality=base.forecast_quality,
               note=note), sim.scenarios


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

    forecast_kpis, fcs = _forecast_kpis(db, com)
    exposure, cost_scenarios = _exposure(db, ctx, com)
    kpis = [*_benchmark_kpis(db, com), *forecast_kpis, _customer_price_kpi(db, org_id, com), exposure]
    customer_series, customer_note = _customer_series(db, org_id, com)

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
        forecast_points=fcs,
        customer_series=customer_series,
        customer_series_note=customer_note,
        cost_scenarios=cost_scenarios,
        cost_scenarios_months=3 if cost_scenarios else None,
    )
