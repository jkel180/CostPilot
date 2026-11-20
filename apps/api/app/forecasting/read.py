"""Read the latest forecast run and turn it into API objects (forecasts, backtests, scenarios)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import market
from app.forecasting.models import BY_NAME
from app.models import Commodity, Forecast, ForecastBacktest, ForecastRun, ObservationDataType, ProductSpec
from app.schemas import (
    BacktestOut,
    ForecastBundle,
    ForecastPointOut,
    ForecastRunOut,
    ScenarioOut,
    SeriesPoint,
)

STALE_RUNNING = timedelta(minutes=30)


def _label(name: str) -> str:
    m = BY_NAME.get(name)
    return m.label if m else name


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def is_running(db: Session, commodity: Commodity) -> bool:
    latest = db.scalar(
        select(ForecastRun).where(ForecastRun.commodity_id == commodity.id).order_by(ForecastRun.generated_at.desc()).limit(1)
    )
    return bool(latest and latest.status == "running" and datetime.now(UTC) - _aware(latest.generated_at) < STALE_RUNNING)


def latest_completed_run(db: Session, commodity: Commodity) -> ForecastRun | None:
    return db.scalar(
        select(ForecastRun)
        .where(ForecastRun.commodity_id == commodity.id, ForecastRun.status.in_(("success", "insufficient_data")))
        .order_by(ForecastRun.generated_at.desc())
        .limit(1)
    )


def forecasts_for(db: Session, run: ForecastRun) -> list[ForecastPointOut]:
    backtests = {(b.model_name, b.horizon_months): b for b in db.scalars(select(ForecastBacktest).where(ForecastBacktest.run_id == run.id))}
    out = []
    for f in db.scalars(select(Forecast).where(Forecast.run_id == run.id).order_by(Forecast.horizon_months)):
        model_bt = backtests.get((f.model_name, f.horizon_months))
        base_name = model_bt.benchmark_name if model_bt else None
        base_bt = backtests.get((base_name, f.horizon_months)) if base_name else None
        improvement = None
        if model_bt and base_bt and model_bt.mae is not None and base_bt.mae:
            improvement = ((base_bt.mae - model_bt.mae) / base_bt.mae * 100).quantize(Decimal("0.1"), ROUND_HALF_UP)
        out.append(ForecastPointOut(
            horizon_months=f.horizon_months, target_date=f.target_date, value=f.forecast_value,
            lower=f.lower_bound, upper=f.upper_bound, interval_level=f.interval_level,
            model=f.model_name, model_label=_label(f.model_name), quality=f.quality_status.value,
            baseline=base_name, model_mae=model_bt.mae if model_bt else None,
            baseline_mae=base_bt.mae if base_bt else None, improvement_pct=improvement,
        ))
    return out


def scenarios_for(run: ForecastRun, forecasts: list[ForecastPointOut]) -> list[ScenarioOut]:
    """Downside / base / upside from the stored forecast and its prediction interval."""
    if not run.last_value:
        return []
    out = []
    for f in forecasts:
        level = int((f.interval_level or Decimal("0.8")) * 100)
        cov = f"{level}% prediction interval from the model's backtest errors at {f.horizon_months} month(s)"
        for key, label, price, assumption in (
            ("downside", "Lower prices", f.lower, f"Lower bound of the {cov}"),
            ("base", "Base", f.value, f"Central forecast ({f.model_label})"),
            ("upside", "Higher prices", f.upper, f"Upper bound of the {cov}"),
        ):
            out.append(ScenarioOut(
                key=key, label=label, horizon_months=f.horizon_months, price=price,
                change_pct=((price - run.last_value) / run.last_value * 100).quantize(Decimal("0.01"), ROUND_HALF_UP),
                assumption=assumption,
            ))
    return out


def last_failure(db: Session, commodity: Commodity, after: ForecastRun | None) -> ForecastRunOut | None:
    q = select(ForecastRun).where(ForecastRun.commodity_id == commodity.id, ForecastRun.status == "failed")
    if after is not None:
        q = q.where(ForecastRun.generated_at > after.generated_at)
    failed = db.scalar(q.order_by(ForecastRun.generated_at.desc()).limit(1))
    return ForecastRunOut.model_validate(failed, from_attributes=True) if failed else None


def bundle(db: Session, commodity: Commodity) -> ForecastBundle:
    run = latest_completed_run(db, commodity)
    failed = last_failure(db, commodity, run)
    history = market.series(db, commodity, ObservationDataType.customs_unit_value, [market.BENCHMARK_GEOGRAPHY]).get(
        market.BENCHMARK_GEOGRAPHY, []
    )[-48:]
    spec = db.get(ProductSpec, history[-1].product_spec_id) if history and history[-1].product_spec_id else None
    if run is None:
        return ForecastBundle(
            run=None, running=is_running(db, commodity), last_failed_run=failed, series_label=market.BENCHMARK_LABEL,
            scope=spec.specification_name if spec else None,
            history=[SeriesPoint(date=o.observation_date, value=o.value, quality_status=o.quality_status.value) for o in history],
            forecasts=[], backtests=[], scenarios=[],
        )
    fcs = forecasts_for(db, run)
    bts = db.scalars(
        select(ForecastBacktest).where(ForecastBacktest.run_id == run.id)
        .order_by(ForecastBacktest.horizon_months, ForecastBacktest.is_baseline.desc(), ForecastBacktest.mae)
    ).all()
    return ForecastBundle(
        run=ForecastRunOut.model_validate(run, from_attributes=True),
        running=is_running(db, commodity),
        last_failed_run=failed,
        series_label=market.BENCHMARK_LABEL,
        scope=spec.specification_name if spec else None,
        history=[SeriesPoint(date=o.observation_date, value=o.value, quality_status=o.quality_status.value) for o in history],
        forecasts=fcs,
        backtests=[
            BacktestOut(
                model=b.model_name, model_label=_label(b.model_name), horizon_months=b.horizon_months,
                is_baseline=b.is_baseline, selected=b.selected, n_origins=b.n_origins, mae=b.mae, wape=b.wape,
                directional_accuracy=b.directional_accuracy, interval_coverage=b.interval_coverage,
            )
            for b in bts
        ],
        scenarios=scenarios_for(run, fcs),
    )
