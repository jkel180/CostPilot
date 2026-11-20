"""Cost model (one per organization and commodity) and the cost simulator.

Results always separate the three kinds of numbers: observed (benchmark), forecast
(model output) and the organization's own assumptions (volumes, price, pass-through).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app import audit, market
from app.deps import DbSession, EditorCtx, OrgCtx
from app.forecasting.read import forecasts_for, latest_completed_run
from app.models import CostModel
from app.routers.market import get_commodity
from app.schemas import CostModelIn, CostModelOut, MarketGap, SimScenario, SimulationRequest, SimulationResult
from app.simulator import SimulationInput, change_pct, monthly_quantity, scenario, target_savings
from app.units import price_per_kg

router = APIRouter(tags=["cost"])


def _get_model(db, org_id, commodity_id) -> CostModel | None:
    return db.scalar(
        select(CostModel).where(CostModel.organization_id == org_id, CostModel.commodity_id == commodity_id)
    )


def _out(m: CostModel) -> CostModelOut:
    return CostModelOut(
        id=m.id, name=m.name, expected_volume=m.expected_volume, volume_period=m.volume_period,
        current_purchase_price=m.current_purchase_price, target_purchase_price=m.target_purchase_price,
        currency=m.currency, unit=m.unit, pass_through_pct=m.pass_through_pct,
        commodity_cost_share_pct=m.commodity_cost_share_pct, notes=(m.assumptions_json or {}).get("notes"),
        updated_at=m.updated_at,
    )


@router.get("/cost-model", response_model=CostModelOut | None)
def get_cost_model(ctx: OrgCtx, db: DbSession, commodity: str = Query("lemon_juice_concentrate", max_length=64)):
    m = _get_model(db, ctx.organization.id, get_commodity(db, commodity).id)
    return _out(m) if m else None


@router.put("/cost-model", response_model=CostModelOut)
def put_cost_model(payload: CostModelIn, ctx: EditorCtx, db: DbSession,
                   commodity: str = Query("lemon_juice_concentrate", max_length=64)) -> CostModelOut:
    com = get_commodity(db, commodity)
    m = _get_model(db, ctx.organization.id, com.id)
    data = payload.model_dump(exclude={"notes"})
    if m is None:
        m = CostModel(organization_id=ctx.organization.id, commodity_id=com.id, created_by=ctx.user.id, **data)
        db.add(m)
    else:
        for k, v in data.items():
            setattr(m, k, v)
    m.assumptions_json = {"notes": payload.notes} if payload.notes else {}
    db.flush()
    audit.record(db, action="cost_model.saved", entity_type="cost_model", entity_id=m.id, user_id=ctx.user.id,
                 organization_id=ctx.organization.id, details={"fields": sorted(data)})
    db.commit()
    db.refresh(m)
    return _out(m)


def market_gap(db, com, price: Decimal, unit: str, currency: str) -> MarketGap:
    b = market.benchmark(db, com)
    if b is None:
        return MarketGap(available=False, rule="No validated benchmark available")
    per_kg, rule = price_per_kg(price, unit, currency, b["observation"].currency or "EUR")
    if per_kg is None:
        return MarketGap(available=False, rule=rule)
    bench = b["observation"].value
    return MarketGap(
        available=True, customer_price_per_kg=per_kg.quantize(Decimal("0.0001"), ROUND_HALF_UP),
        benchmark_per_kg=bench, benchmark_date=b["observation"].observation_date,
        gap_pct=change_pct(per_kg, bench).quantize(Decimal("0.1"), ROUND_HALF_UP),
        rule=f"{rule}; gap = (your price - customs benchmark) / customs benchmark. The benchmark is a border "
             "value of a broader product code, so a positive gap is expected (delivery, specification, margins).",
    )


def simulate(db, ctx, com, req: SimulationRequest) -> SimulationResult:
    model = _get_model(db, ctx.organization.id, com.id)
    fields = ("expected_volume", "volume_period", "current_purchase_price", "pass_through_pct")
    given = {f: getattr(req, f) for f in fields if getattr(req, f) is not None}
    if model is None and len(given) < 3:  # pass-through defaults to 100%
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Save a cost model or provide expected_volume, volume_period and current_purchase_price")
    vals = {f: given.get(f, getattr(model, f) if model else None) for f in fields}
    vals["pass_through_pct"] = vals["pass_through_pct"] if vals["pass_through_pct"] is not None else Decimal(100)
    source = "request" if model is None else ("cost_model" if not given else "mixed")
    currency, unit = (model.currency, model.unit) if model else ("EUR", "kg")

    inp = SimulationInput(
        monthly_quantity=monthly_quantity(vals["expected_volume"], vals["volume_period"]),
        current_price=vals["current_purchase_price"], months=req.months,
        pass_through=vals["pass_through_pct"] / 100,
    )
    scenarios: list[SimScenario] = []
    run = latest_completed_run(db, com)
    horizon_used, note = None, None
    pt = f"{vals['pass_through_pct']:.0f}%"
    if run and run.status == "success" and run.last_value:
        fcs = forecasts_for(db, run)
        usable = [f for f in fcs if f.horizon_months <= req.months] or fcs[:1]
        if usable:
            f = usable[-1]
            horizon_used = f.horizon_months
            if req.months > f.horizon_months:
                note = (f"Forecasts reach {f.horizon_months} months ahead; the {f.horizon_months}-month price is applied "
                        f"to the whole {req.months}-month period.")
            if f.quality != "reliable":
                note = ((note + " ") if note else "") + (
                    "No model beat the naive benchmark in backtesting: the base case is effectively 'no change'.")
            level = int((f.interval_level or Decimal("0.8")) * 100)
            for key, label, price, assumption in (
                ("downside", "Forecast · lower prices", f.lower, f"Lower bound of the {level}% interval at {f.horizon_months} months"),
                ("base", "Forecast · base", f.value, f"Central forecast at {f.horizon_months} months ({f.model_label})"),
                ("upside", "Forecast · higher prices", f.upper, f"Upper bound of the {level}% interval at {f.horizon_months} months"),
            ):
                bench_change = change_pct(price, run.last_value)
                scenarios.append(SimScenario(
                    key=key, label=label, source="forecast", forecast_quality=f.quality,
                    assumption=f"{assumption}; benchmark change passed on at {pt}", **scenario(inp, bench_change),
                ))
    else:
        note = "No forecast available yet: only custom scenarios are shown."
    for c in req.custom_changes_pct:
        scenarios.append(SimScenario(
            key=f"custom_{c}", label=f"Benchmark {'+' if c > 0 else ''}{c.normalize()}%", source="custom",
            assumption=f"User-defined benchmark change of {c.normalize()}%, passed on at {pt}", **scenario(inp, c),
        ))
    return SimulationResult(
        inputs={k: str(v) for k, v in vals.items()} | {"months": req.months},
        inputs_source=source, monthly_quantity=inp.monthly_quantity.quantize(Decimal("0.01"), ROUND_HALF_UP),
        currency=currency, unit=unit, months=req.months,
        market_gap=market_gap(db, com, inp.current_price, unit, currency),
        forecast_horizon_used=horizon_used, forecast_note=note,
        target_annual_savings=target_savings(inp.current_price, model.target_purchase_price if model else None,
                                             inp.monthly_quantity),
        scenarios=scenarios,
    )


@router.post("/simulator", response_model=SimulationResult)
def run_simulation(req: SimulationRequest, ctx: OrgCtx, db: DbSession,
                   commodity: str = Query("lemon_juice_concentrate", max_length=64)) -> SimulationResult:
    return simulate(db, ctx, get_commodity(db, commodity), req)
