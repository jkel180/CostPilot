"""Explicit, traceable unit rules.

Prices are only converted between mass units (kg, t, lb) with fixed factors, and never
across currencies or to/from volume units (litres need a density that depends on the
product's Brix). Anything else is reported as not comparable.
"""

from __future__ import annotations

from decimal import Decimal

KG_PER_UNIT = {"kg": Decimal("1"), "t": Decimal("1000"), "lb": Decimal("0.45359237")}


def price_per_kg(price: Decimal, unit: str, currency: str, target_currency: str = "EUR") -> tuple[Decimal | None, str]:
    """Return (price in target_currency per kg, rule applied or reason it cannot be converted)."""
    u = unit.lower()
    if currency.upper() != target_currency:
        return None, f"prices in {currency} are not converted to {target_currency} (no FX rule)"
    if u not in KG_PER_UNIT:
        return None, f"unit '{unit}' is not a mass unit; volume units need a product-specific density"
    factor = KG_PER_UNIT[u]
    rule = "no conversion" if factor == 1 else f"price per {u} / {factor} = price per kg"
    return price / factor, rule


def quantity_in_kg(quantity: Decimal, unit: str) -> Decimal | None:
    factor = KG_PER_UNIT.get(unit.lower())
    return None if factor is None else quantity * factor
