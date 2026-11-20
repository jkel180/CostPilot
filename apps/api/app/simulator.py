"""Cost model calculations (spec 3.4). Pure functions on Decimals, no database access.

Assumptions are explicit inputs, never hidden:
* the customer's price moves by ``benchmark change x pass-through`` (100% = proportional);
* quantities are spread evenly over the months of the period.

Formulas
--------
price_change_pct  = benchmark_change_pct x pass_through
scenario_price    = current_price x (1 + price_change_pct / 100)
monthly_impact    = (scenario_price - current_price) x monthly_quantity
period_impact     = monthly_impact x months              (Cost Impact = price change x quantity)
annualized_impact = monthly_impact x 12
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TWO = Decimal("0.01")
SIX = Decimal("0.000001")


@dataclass(frozen=True)
class SimulationInput:
    monthly_quantity: Decimal
    current_price: Decimal
    months: int
    pass_through: Decimal  # fraction: 1 = 100%

    @property
    def period_quantity(self) -> Decimal:
        return self.monthly_quantity * self.months


def monthly_quantity(expected_volume: Decimal, volume_period: str) -> Decimal:
    if volume_period == "monthly":
        return expected_volume
    if volume_period == "annual":
        return expected_volume / 12
    raise ValueError("volume_period must be 'monthly' or 'annual'")


def scenario(inp: SimulationInput, benchmark_change_pct: Decimal) -> dict:
    price_change_pct = benchmark_change_pct * inp.pass_through
    price = inp.current_price * (1 + price_change_pct / 100)
    monthly_impact = (price - inp.current_price) * inp.monthly_quantity
    return {
        "benchmark_change_pct": benchmark_change_pct.quantize(TWO, ROUND_HALF_UP),
        "price_change_pct": price_change_pct.quantize(TWO, ROUND_HALF_UP),
        "scenario_price": price.quantize(SIX, ROUND_HALF_UP),
        "period_quantity": inp.period_quantity.quantize(TWO, ROUND_HALF_UP),
        "expected_spend": (price * inp.period_quantity).quantize(TWO, ROUND_HALF_UP),
        "baseline_spend": (inp.current_price * inp.period_quantity).quantize(TWO, ROUND_HALF_UP),
        "period_impact": (monthly_impact * inp.months).quantize(TWO, ROUND_HALF_UP),
        "annualized_impact": (monthly_impact * 12).quantize(TWO, ROUND_HALF_UP),
    }


def change_pct(new: Decimal, old: Decimal) -> Decimal:
    return (new - old) / old * 100


def target_savings(current_price: Decimal, target_price: Decimal | None, monthly_qty: Decimal) -> Decimal | None:
    """Annual saving if the target price were achieved (negative if the target is above the current price)."""
    if target_price is None:
        return None
    return ((current_price - target_price) * monthly_qty * 12).quantize(TWO, ROUND_HALF_UP)
