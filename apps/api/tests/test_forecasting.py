"""Forecasting pipeline: data preparation, no look-ahead, baseline comparison, persistence.

Series here are synthetic and exist only inside tests.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pytest
from sqlalchemy import select

from app.forecasting import models as registry
from app.forecasting import pipeline
from app.forecasting.models import ForecastModel
from app.forecasting.pipeline import HORIZONS, _backtest, prepare_series, run_forecast, run_pipeline
from app.models import (
    Commodity, DataSource, Forecast, ForecastBacktest, MarketObservation, ObservationDataType, ProductSpec,
    QualityStatus,
)

FAST = tuple(m for m in registry.MODELS if m.name in ("naive", "seasonal_naive", "ets"))


def months(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    return [date(start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1, 1) for i in range(n)]


def trend_series(n: int = 60) -> list[tuple[date, float]]:
    return [(d, 2.0 + 0.02 * i) for i, d in enumerate(months(n))]


# ------------------------------------------------------------------ data preparation


def test_short_gaps_are_interpolated_and_noted():
    pts = [(d, 2.0) for d in months(10)]
    del pts[4:6]  # two missing months
    s = prepare_series(pts)
    assert len(s.values) == 10 and len([n for n in s.notes if "interpolated" in n]) == 2


def test_long_gap_cuts_the_older_segment():
    pts = [(d, 2.0) for d in months(20)]
    del pts[5:8]  # three missing months
    s = prepare_series(pts)
    assert s.dates[0] == date(2020, 9, 1) and any("dropped" in n for n in s.notes)


def test_data_version_identifies_the_exact_input():
    a = prepare_series(trend_series(20)).data_version
    assert a == prepare_series(trend_series(20)).data_version
    changed = trend_series(20)
    changed[-1] = (changed[-1][0], changed[-1][1] + 0.001)
    assert prepare_series(changed).data_version != a


# ------------------------------------------------------------------ no look-ahead


def test_backtest_forecasts_never_use_future_values():
    rng = np.random.default_rng(1)
    y = np.exp(np.cumsum(rng.normal(0, 0.03, 70))) * 2
    k = 55
    y2 = y.copy()
    y2[k:] *= 3  # change only the future after index k
    r1, r2 = _backtest(y, FAST), _backtest(y2, FAST)
    for key, recs in r1.items():
        for (t, fc, _, _), (t2, fc2, _, _) in zip(recs, r2[key]):
            assert t == t2
            if t < k:  # origin before the change: identical forecast
                assert fc == pytest.approx(fc2, rel=1e-9), (key, t)


# ------------------------------------------------------------------ baseline comparison


def _trend_model(y, h):  # extrapolates the last step: perfect on a linear trend
    return y[-1] + (y[-1] - y[-2]) * np.arange(1, h + 1)


def _biased_model(y, h):
    return np.repeat(y[-1] + 1.0, h)


GOOD = ForecastModel("trend", "Linear trend", False, 2, _trend_model)
BAD = ForecastModel("biased", "Biased", False, 2, _biased_model)
NAIVE = registry.BY_NAME["naive"]


def test_model_that_beats_naive_is_selected_as_reliable():
    r = run_pipeline(trend_series(), models=(NAIVE, GOOD))
    assert r.status == "success" and {f.horizon for f in r.forecasts} == set(HORIZONS)
    for f in r.forecasts:
        assert (f.model, f.quality, f.baseline) == ("trend", "reliable", "naive")
        assert f.lower <= f.value <= f.upper
    assert r.forecasts[0].value == pytest.approx(2.0 + 0.02 * 60)


def test_when_no_model_beats_the_baseline_it_is_flagged():
    r = run_pipeline(trend_series(), models=(NAIVE, BAD))
    for f in r.forecasts:
        assert (f.model, f.quality) == ("naive", "below_baseline")
    selected = [m for m in r.metrics if m.selected]
    assert all(m.model == "naive" for m in selected)


def test_metrics_include_mae_wape_direction_and_coverage():
    r = run_pipeline(trend_series(), models=(NAIVE, GOOD))
    good = next(m for m in r.metrics if m.model == "trend" and m.horizon == 1)
    naive = next(m for m in r.metrics if m.model == "naive" and m.horizon == 1)
    assert good.mae == pytest.approx(0, abs=1e-9) and naive.mae == pytest.approx(0.02)
    assert good.directional_accuracy == 1.0 and naive.directional_accuracy is None  # naive predicts no change
    assert naive.wape > 0 and naive.interval_coverage is not None


def test_short_history_is_insufficient():
    r = run_pipeline(trend_series(40), models=(NAIVE, GOOD))
    assert r.status == "insufficient_data" and r.forecasts == [] and r.series.notes


# ------------------------------------------------------------------ persistence


@pytest.fixture
def fast_models(monkeypatch):
    monkeypatch.setattr(registry, "MODELS", FAST)


def seed_benchmark(db, n=60):
    com = db.scalar(select(Commodity))
    src = db.scalar(select(DataSource).where(DataSource.name.like("Eurostat%")))
    spec = db.scalar(select(ProductSpec))
    rng = np.random.default_rng(7)
    for i, d in enumerate(months(n)):
        v = 2.0 + 0.01 * i + 0.15 * np.sin(2 * np.pi * i / 12) + rng.normal(0, 0.02)
        db.add(MarketObservation(
            commodity_id=com.id, source_id=src.id, product_spec_id=spec.id, observation_date=d,
            geography="EXT_EU27_2020", value=Decimal(f"{v:.6f}"), currency="EUR", unit="kg",
            data_type=ObservationDataType.customs_unit_value, quality_status=QualityStatus.validated,
        ))
    db.commit()
    return com


def test_run_is_stored_with_versions_backtests_and_forecasts(db, fast_models):
    com = seed_benchmark(db)
    run = run_forecast(db, com)
    assert run.status == "success", run.error
    assert len(run.input_data_version) == 64 and run.model_version.startswith("costpilot-forecast/")
    assert run.n_observations == 60 and run.last_date == date(2024, 12, 1)
    assert run.settings["interval_level"] == 0.8
    fcs = db.scalars(select(Forecast).where(Forecast.run_id == run.id)).all()
    assert sorted(f.horizon_months for f in fcs) == [1, 3, 6]
    assert all(f.input_data_version == run.input_data_version for f in fcs)
    assert {f.target_date for f in fcs} == {date(2025, 1, 1), date(2025, 3, 1), date(2025, 6, 1)}
    bts = db.scalars(select(ForecastBacktest).where(ForecastBacktest.run_id == run.id)).all()
    assert len(bts) == 9 and sum(b.selected for b in bts) == 3 and any(b.is_baseline for b in bts)


def test_same_input_gives_same_forecast(db, fast_models):
    com = seed_benchmark(db)
    a, b = run_forecast(db, com), run_forecast(db, com)
    assert a.input_data_version == b.input_data_version
    va = {f.horizon_months: f.forecast_value for f in db.scalars(select(Forecast).where(Forecast.run_id == a.id))}
    vb = {f.horizon_months: f.forecast_value for f in db.scalars(select(Forecast).where(Forecast.run_id == b.id))}
    assert va == vb


def test_failure_is_recorded(db, monkeypatch):
    com = seed_benchmark(db)

    def boom(points, models=None):
        raise RuntimeError("numerical failure")

    monkeypatch.setattr(pipeline, "run_pipeline", boom)
    run = run_forecast(db, com)
    assert run.status == "failed" and "numerical failure" in run.error


# ------------------------------------------------------------------ endpoints


def test_forecast_endpoints(actor, db, fast_models):
    seed_benchmark(db)
    u = actor("u@x.com")
    assert u.get("/api/v1/forecasts/latest").json()["run"] is None
    assert u.post("/api/v1/admin/forecasts/run").status_code == 403
    ops = actor("ops@costpilot.test")
    r = ops.post("/api/v1/admin/forecasts/run")
    assert r.status_code == 202, r.text  # completed by the background task after the response
    body = u.get("/api/v1/forecasts/latest").json()
    assert body["run"]["status"] == "success" and body["running"] is False
    assert [f["horizon_months"] for f in body["forecasts"]] == [1, 3, 6]
    assert {s["key"] for s in body["scenarios"]} == {"downside", "base", "upside"}
    assert len(body["backtests"]) == 9 and len(body["history"]) == 48

    org = u.create_org()
    k = {x["key"]: x for x in u.get("/api/v1/dashboard/summary", org=org).json()["kpis"]}
    assert k["forecast_3m"]["status"] == "available" and k["forecast_3m"]["value_kind"] == "forecast"
    assert k["forecast_3m"]["quality"] in ("reliable", "below_baseline")


def test_stored_strings_fit_their_columns():
    """SQLite ignores VARCHAR lengths, PostgreSQL does not: check them explicitly."""
    from app.models import Forecast as F, ForecastBacktest as B, ForecastRun as R

    mv = pipeline.model_version()
    for model in (F, B, R):
        assert len(mv) <= model.__table__.c.model_version.type.length, model.__tablename__
    longest_model = max(len(m.name) for m in registry.MODELS)
    assert longest_model <= F.__table__.c.model_name.type.length
    assert longest_model <= B.__table__.c.model_name.type.length
