"""Forecasting models.

Every model is a pure function ``(history, h) -> h point forecasts``: it sees only the
history it is given, so the backtest can never leak future values into a forecast.
Statistical models work on log prices (prices are positive and move multiplicatively).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

SEASON = 12


@dataclass(frozen=True)
class ForecastModel:
    name: str
    label: str
    is_baseline: bool
    min_history: int
    fn: Callable[[np.ndarray, int], np.ndarray]
    #: averaged models: in the backtest their components' forecasts are reused
    components: tuple[str, ...] = ()

    def predict(self, y: np.ndarray, h: int) -> np.ndarray:
        if len(y) < self.min_history:
            raise ValueError(f"{self.name} needs at least {self.min_history} observations")
        out = np.asarray(self.fn(np.asarray(y, dtype=float), h), dtype=float)
        if out.shape != (h,) or not np.all(np.isfinite(out)):
            raise ValueError(f"{self.name} produced an invalid forecast")
        return out


def _naive(y: np.ndarray, h: int) -> np.ndarray:
    return np.repeat(y[-1], h)


def _seasonal_naive(y: np.ndarray, h: int) -> np.ndarray:
    last_season = y[-SEASON:]
    return np.array([last_season[i % SEASON] for i in range(h)])


def _ets(y: np.ndarray, h: int) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(np.log(y), trend="add", damped_trend=True, initialization_method="estimated").fit()
    return np.exp(fit.forecast(h))


def _ets_seasonal(y: np.ndarray, h: int) -> np.ndarray:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(
            np.log(y), trend="add", damped_trend=True, seasonal="add", seasonal_periods=SEASON,
            initialization_method="estimated",
        ).fit()
    return np.exp(fit.forecast(h))


ARIMA_ORDERS = ((1, 1, 0), (0, 1, 1), (1, 1, 1))


def _arima(y: np.ndarray, h: int) -> np.ndarray:
    """ARIMA on log prices; the order is chosen by AIC on the given history only."""
    from statsmodels.tsa.arima.model import ARIMA

    best = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for order in ARIMA_ORDERS:
            try:
                fit = ARIMA(np.log(y), order=order).fit()
            except Exception:  # noqa: BLE001 - a failing order is just skipped
                continue
            if best is None or fit.aic < best.aic:
                best = fit
    if best is None:
        raise ValueError("no ARIMA order could be fitted")
    return np.exp(best.forecast(h))


def _ensemble(y: np.ndarray, h: int) -> np.ndarray:
    return (_ets(y, h) + _arima(y, h)) / 2


MODELS: tuple[ForecastModel, ...] = (
    ForecastModel("naive", "Naive (last value)", True, 1, _naive),
    ForecastModel("seasonal_naive", "Seasonal naive (same month last year)", True, SEASON, _seasonal_naive),
    ForecastModel("ets", "Exponential smoothing (damped trend)", False, 24, _ets),
    ForecastModel("ets_seasonal", "Exponential smoothing (damped trend + seasonality)", False, 36, _ets_seasonal),
    ForecastModel("arima", "ARIMA (order by AIC)", False, 24, _arima),
    ForecastModel("ensemble", "Ensemble (mean of ETS and ARIMA)", False, 24, _ensemble, components=("ets", "arima")),
)
BY_NAME = {m.name: m for m in MODELS}
