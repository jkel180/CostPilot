"""Reproducible forecasting pipeline with rolling-origin backtesting.

Steps (spec section 8):
 1. load validated observations of one series            -> :func:`prepare_series`
 2. check missing values / outliers / frequency           -> gaps <= 2 months interpolated, longer gaps cut
 3-5. naive + seasonal naive baselines, statistical models -> :mod:`app.forecasting.models`
 6. rolling-origin backtest (each forecast sees only data up to its origin)
 7. compare models per horizon (MAE, WAPE, directional accuracy, interval coverage)
 8. select a model only if it beats the best baseline; otherwise flag ``below_baseline``
 9-11. forecast, store with versions, set quality status  -> :func:`run_forecast`

Prediction intervals are empirical: the 80% quantile of the absolute errors the model
made at that horizon in the backtest. During the backtest an interval only uses errors
whose target month was already known at the origin, so coverage is measured honestly.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from importlib.metadata import version

import numpy as np

from app.forecasting import models as model_registry
from app.forecasting.models import ForecastModel

PIPELINE_VERSION = "1.0"
HORIZONS = (1, 3, 6)
MIN_TRAIN = 36
MAX_ORIGINS = 36
MIN_BACKTESTS = 12
INTERVAL_LEVEL = 0.80
MIN_ERRORS_FOR_INTERVAL = 8
MAX_GAP_INTERPOLATED = 2


def model_version() -> str:
    return f"costpilot-forecast/{PIPELINE_VERSION} statsmodels/{version('statsmodels')} numpy/{version('numpy')}"


def settings() -> dict:
    return {
        "horizons": list(HORIZONS), "min_train_months": MIN_TRAIN, "max_backtest_origins": MAX_ORIGINS,
        "min_backtests": MIN_BACKTESTS, "interval_level": INTERVAL_LEVEL,
        "interval_method": "empirical quantile of absolute backtest errors per model and horizon",
        "selection": "lowest MAE per horizon; accepted only if lower than the best baseline's MAE",
        "max_gap_interpolated_months": MAX_GAP_INTERPOLATED,
        "models": [m.name for m in model_registry.MODELS],
    }


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


@dataclass
class PreparedSeries:
    dates: list[date]
    values: np.ndarray
    notes: list[str] = field(default_factory=list)
    panel: dict = field(default_factory=dict)  # support series used by pooled models

    @property
    def data_version(self) -> str:
        payload = "\n".join(f"{d.isoformat()}:{v:.6f}" for d, v in zip(self.dates, self.values))
        return hashlib.sha256(payload.encode()).hexdigest()


def prepare_series(points: list[tuple[date, float]]) -> PreparedSeries:
    """Monthly series ending at the latest point. Gaps of up to 2 months are filled by
    log-linear interpolation (recorded in notes); anything before a longer gap is dropped."""
    pts = sorted((date(d.year, d.month, 1), float(v)) for d, v in points if v and v > 0)
    notes: list[str] = []
    if not pts:
        return PreparedSeries([], np.array([]), ["no observations"])
    # walk back from the end to the start of the last segment with acceptable gaps
    start = len(pts) - 1
    while start > 0:
        gap = _months_between(pts[start - 1][0], pts[start][0]) - 1
        if gap > MAX_GAP_INTERPOLATED:
            notes.append(f"series starts {pts[start][0]:%Y-%m}: earlier data dropped after a {gap}-month gap")
            break
        start -= 1
    seg = pts[start:]
    dates, values = [seg[0][0]], [seg[0][1]]
    for (d0, v0), (d1, v1) in zip(seg, seg[1:]):
        gap = _months_between(d0, d1) - 1
        for k in range(1, gap + 1):
            frac = k / (gap + 1)
            dates.append(_add_months(d0, k))
            values.append(float(np.exp(np.log(v0) + frac * (np.log(v1) - np.log(v0)))))
            notes.append(f"{dates[-1]:%Y-%m} interpolated (missing or not validated)")
        dates.append(d1)
        values.append(v1)
    return PreparedSeries(dates, np.array(values), notes)


@dataclass
class Metric:
    model: str
    label: str
    is_baseline: bool
    horizon: int
    n: int
    mae: float | None
    wape: float | None
    directional_accuracy: float | None
    interval_coverage: float | None
    selected: bool = False


@dataclass
class HorizonForecast:
    horizon: int
    target_date: date
    model: str
    value: float
    lower: float
    upper: float
    quality: str  # reliable | below_baseline | insufficient_data
    baseline: str
    baseline_mae: float | None
    model_mae: float | None


@dataclass
class PipelineResult:
    series: PreparedSeries
    metrics: list[Metric]
    forecasts: list[HorizonForecast]
    status: str  # success | insufficient_data


def _backtest(y: np.ndarray, models: tuple[ForecastModel, ...]) -> dict[tuple[str, int], list[tuple[int, float, float, float]]]:
    """Return {(model, h): [(origin, forecast, actual, last_observed), ...]} in origin order."""
    n, hmax = len(y), max(HORIZONS)
    first = max(MIN_TRAIN - 1, n - 1 - MAX_ORIGINS)
    records: dict[tuple[str, int], list[tuple[int, float, float, float]]] = {}
    for t in range(first, n - 1):
        history = y[: t + 1]  # strictly data known at the origin
        cache: dict[str, np.ndarray] = {}
        for m in models:
            if len(history) < m.min_history:
                continue
            try:
                if m.components and all(c in cache for c in m.components):
                    fc = sum(cache[c] for c in m.components) / len(m.components)
                else:
                    fc = m.predict(history, hmax)
            except ValueError:
                continue
            cache[m.name] = fc
            for h in HORIZONS:
                if t + h < n:
                    records.setdefault((m.name, h), []).append((t, float(fc[h - 1]), float(y[t + h]), float(y[t])))
    return records


def _quantile(abs_errors: list[float]) -> float:
    return float(np.quantile(np.asarray(abs_errors), INTERVAL_LEVEL))


def _metrics(model: ForecastModel, h: int, recs: list[tuple[int, float, float, float]]) -> Metric:
    if not recs:
        return Metric(model.name, model.label, model.is_baseline, h, 0, None, None, None, None)
    fc = np.array([r[1] for r in recs])
    act = np.array([r[2] for r in recs])
    last = np.array([r[3] for r in recs])
    err = np.abs(fc - act)
    # direction: excluded when the forecast predicts no change (naive) or the actual did not move
    pred_dir, act_dir = np.sign(fc - last), np.sign(act - last)
    mask = (pred_dir != 0) & (act_dir != 0)
    # coverage: interval at each origin from errors whose target month was known by then
    covered = evaluated = 0
    for i, (t, f, a, _) in enumerate(recs):
        known = [abs(r[1] - r[2]) for r in recs[:i] if r[0] + h <= t]
        if len(known) >= MIN_ERRORS_FOR_INTERVAL:
            q = _quantile(known)
            evaluated += 1
            covered += int(f - q <= a <= f + q)
    return Metric(
        model.name, model.label, model.is_baseline, h, len(recs),
        mae=float(err.mean()),
        wape=float(err.sum() / np.abs(act).sum()) if np.abs(act).sum() else None,
        directional_accuracy=float((pred_dir[mask] == act_dir[mask]).mean()) if mask.any() else None,
        interval_coverage=covered / evaluated if evaluated else None,
    )


def _align_panel(series: PreparedSeries, panel_points: dict[str, list[tuple[date, float]]]) -> dict[str, np.ndarray]:
    out = {}
    for name, pts in panel_points.items():
        by_month = {date(d.year, d.month, 1): float(v) for d, v in pts if v and v > 0}
        out[name] = np.array([by_month.get(d, np.nan) for d in series.dates])
    return out


def input_version(series: PreparedSeries, panel: dict[str, np.ndarray]) -> str:
    """Hash of the benchmark series plus every support series actually used."""
    if not panel:
        return series.data_version
    h = hashlib.sha256(series.data_version.encode())
    for name in sorted(panel):
        h.update(name.encode())
        h.update(np.nan_to_num(panel[name], nan=-1.0).round(6).tobytes())
    return h.hexdigest()


def run_pipeline(
    points: list[tuple[date, float]],
    models: tuple[ForecastModel, ...] | None = None,
    panel_points: dict[str, list[tuple[date, float]]] | None = None,
) -> PipelineResult:
    from app.forecasting.pooled import make_pooled_models

    models = models if models is not None else model_registry.MODELS
    series = prepare_series(points)
    y = series.values
    panel = _align_panel(series, panel_points or {})
    pooled = make_pooled_models(series.dates, panel) if panel else ()
    models = tuple(models) + tuple(pooled)
    series.panel = {k: v for k, v in panel.items()} if pooled else {}
    if len(y) < MIN_TRAIN + MIN_BACKTESTS:
        series.notes.append(
            f"{len(y)} usable months; at least {MIN_TRAIN + MIN_BACKTESTS} are needed to backtest forecasts"
        )
        return PipelineResult(series, [], [], "insufficient_data")

    records = _backtest(y, models)
    metrics = [_metrics(m, h, records.get((m.name, h), [])) for h in HORIZONS for m in models]
    by_key = {(m.model, m.horizon): m for m in metrics}
    forecasts: list[HorizonForecast] = []
    last_date = series.dates[-1]
    for h in HORIZONS:
        usable = [m for m in metrics if m.horizon == h and m.mae is not None and m.n >= MIN_BACKTESTS]
        baselines = [m for m in usable if m.is_baseline]
        candidates = [m for m in usable if not m.is_baseline]
        if not baselines:
            continue
        best_base = min(baselines, key=lambda m: m.mae)
        best = min(candidates, key=lambda m: m.mae) if candidates else None
        if best is not None and best.mae < best_base.mae:
            chosen, quality = best, "reliable"
        else:
            chosen, quality = best_base, "below_baseline"
        chosen.selected = True
        model = next(m for m in models if m.name == chosen.model)
        value = float(model.predict(y, h)[h - 1])
        errs = [abs(r[1] - r[2]) for r in records[(chosen.model, h)]]
        q = _quantile(errs)
        forecasts.append(
            HorizonForecast(
                horizon=h, target_date=_add_months(last_date, h), model=chosen.model, value=value,
                lower=max(value - q, 0.0), upper=value + q, quality=quality,
                baseline=best_base.model, baseline_mae=best_base.mae, model_mae=by_key[(chosen.model, h)].mae,
            )
        )
    return PipelineResult(series, metrics, forecasts, "success")


# --------------------------------------------------------------------------- persistence


def _dec(x: float | None, places: str = "0.000001") -> Decimal | None:
    return None if x is None else Decimal(str(x)).quantize(Decimal(places), ROUND_HALF_UP)


def start_run(db, commodity, triggered_by: uuid.UUID | None = None):
    """Record a ``running`` run so the UI can show progress; :func:`complete_run` fills it."""
    from app import market
    from app.models import ForecastRun, ObservationDataType

    run = ForecastRun(
        id=uuid.uuid4(), commodity_id=commodity.id, series_geography=market.BENCHMARK_GEOGRAPHY,
        series_data_type=ObservationDataType.customs_unit_value.value, generated_at=datetime.now(UTC),
        status="running", model_version=model_version(), settings=settings(), notes=[], triggered_by=triggered_by,
    )
    db.add(run)
    db.commit()
    return run


def complete_run(db, run_id: uuid.UUID):
    """Run the pipeline on the benchmark series and store backtests and forecasts on the run."""
    from app import market
    from app.models import Commodity, Forecast, ForecastBacktest, ForecastQualityStatus, ForecastRun, ObservationDataType

    run = db.get(ForecastRun, run_id)
    commodity = db.get(Commodity, run.commodity_id)
    try:
        obs = market.series(db, commodity, ObservationDataType.customs_unit_value, [market.BENCHMARK_GEOGRAPHY]).get(
            market.BENCHMARK_GEOGRAPHY, []
        )
        panel_obs = {
            g: [(o.observation_date, float(o.value)) for o in pts]
            for g, pts in market.series(db, commodity, ObservationDataType.customs_unit_value, include_panel=True).items()
            if ":" in g
        }
        result = run_pipeline([(o.observation_date, float(o.value)) for o in obs], panel_points=panel_obs)
        s = result.series
        run.product_spec_id = obs[-1].product_spec_id if obs else None
        run.currency = obs[-1].currency if obs else None
        run.unit = obs[-1].unit if obs else None
        run.status = result.status
        run.input_data_version = input_version(s, s.panel) if len(s.values) else None
        if s.panel:
            run.settings = {**run.settings, "pooled_support_series": sorted(s.panel)}
        run.n_observations = len(s.values)
        run.first_date = s.dates[0] if s.dates else None
        run.last_date = s.dates[-1] if s.dates else None
        run.last_value = _dec(float(s.values[-1])) if len(s.values) else None
        run.notes = s.notes[:50]
        today = run.generated_at.date()
        for m in result.metrics:
            if m.n == 0:
                continue
            db.add(ForecastBacktest(
                commodity_id=commodity.id, run_id=run.id, model_name=m.model, model_version=run.model_version,
                input_data_version=run.input_data_version or "", evaluation_date=today, horizon_months=m.horizon,
                mae=_dec(m.mae), wape=_dec(m.wape), directional_accuracy=_dec(m.directional_accuracy, "0.0001"),
                interval_coverage=_dec(m.interval_coverage, "0.0001"),
                benchmark_name=next((f.baseline for f in result.forecasts if f.horizon == m.horizon), "naive"),
                n_origins=m.n, is_baseline=m.is_baseline, selected=m.selected,
            ))
        for f in result.forecasts:
            lower, value, upper = _dec(f.lower), _dec(f.value), _dec(f.upper)
            db.add(Forecast(
                commodity_id=commodity.id, product_spec_id=run.product_spec_id, run_id=run.id,
                forecast_date=today, target_date=f.target_date, horizon_months=f.horizon,
                forecast_value=value, lower_bound=min(lower, value), upper_bound=max(upper, value),
                currency=run.currency or "EUR", unit=run.unit or "kg", model_name=f.model,
                model_version=run.model_version, input_data_version=run.input_data_version or "",
                quality_status=ForecastQualityStatus(f.quality), interval_level=_dec(INTERVAL_LEVEL, "0.01"),
            ))
        db.commit()
    except Exception as exc:  # noqa: BLE001 - recorded on the run
        db.rollback()
        run = db.get(ForecastRun, run_id)
        run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
    return run


def run_forecast(db, commodity, triggered_by: uuid.UUID | None = None):
    """Synchronous convenience: start and complete a run."""
    return complete_run(db, start_run(db, commodity, triggered_by).id)


def run_forecast_in_background(run_id: uuid.UUID, session_factory) -> None:
    """Entry point for FastAPI background tasks: uses its own session."""
    with session_factory() as db:
        complete_run(db, run_id)
