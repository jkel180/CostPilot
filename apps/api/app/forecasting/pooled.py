"""Pooled (global) regression across related import series.

Why: one monthly series has ~90 points, too few for a regression to learn anything
stable. The same product imported by the main EU countries moves with the same market;
learning one model across all of them gives ~10x more examples (Nov 2026 evaluation:
docs/valutazione-fattori-esterni.md).

Model, per horizon k (direct forecasting):
    log(s[i+k] / s[i]) = a + b . features(s, i)   for every series s and month i
features: own 1- and 3-month change, deviation from own 12-month mean, target month
(sin/cos), benchmark 1- and 3-month change. Ridge regression (alpha = 10, fixed).

No look-ahead: a forecast from origin t trains only on pairs with i + k <= t and reads
features at t; the panel arrays are cut at t.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from app.forecasting.models import ForecastModel, BY_NAME

ALPHA = 10.0
MIN_PAIRS = 30
MIN_PANEL_MONTHS = 60


def _lg(a: float, b: float) -> float:
    return float(np.log(a / b)) if (np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0) else np.nan


def _features(arr: np.ndarray, bench: np.ndarray, months: list[int], i: int, k: int) -> np.ndarray | None:
    if i < 12:
        return None
    win = arr[i - 11: i + 1]
    dev = _lg(arr[i], float(np.nanmean(win))) if np.isfinite(win).sum() >= 9 else np.nan
    tm = (months[i] - 1 + k) % 12
    return np.array([
        _lg(arr[i], arr[i - 1]), _lg(arr[i], arr[i - 3]), dev,
        np.sin(2 * np.pi * tm / 12), np.cos(2 * np.pi * tm / 12),
        _lg(bench[i], bench[i - 1]), _lg(bench[i], bench[i - 3]),
    ])


def _ridge(X: np.ndarray, z: np.ndarray, x: np.ndarray) -> float:
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    A = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    R = ALPHA * np.eye(A.shape[1])
    R[0, 0] = 0
    w = np.linalg.solve(A.T @ A + R, A.T @ z)
    return float(np.hstack([1, (x - mu) / sd]) @ w)


def make_pooled_models(dates: list[date], panel: dict[str, np.ndarray]) -> tuple[ForecastModel, ...]:
    """Build the pooled model and its average with ETS for a benchmark aligned to ``dates``."""
    panel = {k: v for k, v in panel.items() if np.isfinite(v).sum() >= MIN_PANEL_MONTHS}
    if len(panel) < 3:
        return ()
    months = [d.month for d in dates]

    def pooled(history: np.ndarray, h: int) -> np.ndarray:
        t = len(history) - 1
        bench = history
        series = [bench] + [v[: t + 1] for v in panel.values()]
        out = []
        for k in range(1, h + 1):
            X, Z = [], []
            for arr in series:
                for i in range(12, t - k + 1):
                    f = _features(arr, bench, months, i, k)
                    z = _lg(arr[i + k], arr[i])
                    if f is not None and np.isfinite(f).all() and np.isfinite(z):
                        X.append(f)
                        Z.append(z)
            x = _features(bench, bench, months, t, k)
            if x is None or not np.isfinite(x).all() or len(X) < MIN_PAIRS:
                raise ValueError("not enough pooled training pairs")
            out.append(bench[t] * np.exp(_ridge(np.array(X), np.array(Z), x)))
        return np.array(out)

    def ets_pooled(history: np.ndarray, h: int) -> np.ndarray:
        return (BY_NAME["ets"].fn(history, h) + pooled(history, h)) / 2

    return (
        ForecastModel("pooled", "Pooled regression across EU import series", False, 36, pooled),
        ForecastModel("ets_pooled", "Ensemble (ETS + pooled regression)", False, 36, ets_pooled,
                      components=("ets", "pooled")),
    )
