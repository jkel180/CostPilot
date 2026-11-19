"""Customer purchase CSV import and purchase analytics.

Import flow: the client uploads the file to ``preview`` (nothing is stored), adjusts the
column mapping, then uploads it again to ``commit``. Both run the same validation.

Analytics never mix units or currencies: weighted averages are computed per
(unit, currency) group, and per product description when asked.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.csvutil import infer_decimal_comma, parse_date, parse_decimal, read_rows

REQUIRED_FIELDS = ("purchase_date", "supplier", "product_description", "quantity", "unit", "unit_price", "currency")
OPTIONAL_FIELDS = (
    "brix", "country_of_origin", "quality_grade", "incoterm", "delivery_location",
    "contract_type", "packaging", "certification",
)
ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS

# header synonyms (normalized: lowercase, accents stripped, non-alphanumerics removed)
SYNONYMS: dict[str, tuple[str, ...]] = {
    "purchase_date": ("purchasedate", "date", "data", "dataacquisto", "datafattura", "invoicedate", "orderdate", "datadocumento"),
    "supplier": ("supplier", "fornitore", "vendor", "ragionesociale", "seller"),
    "product_description": ("productdescription", "product", "description", "descrizione", "prodotto", "articolo", "item", "materiale"),
    "quantity": ("quantity", "qty", "quantita", "qta", "volume"),
    "unit": ("unit", "uom", "unitofmeasure", "um", "unita", "unitadimisura"),
    "unit_price": ("unitprice", "price", "prezzo", "prezzounitario", "priceperunit", "costounitario"),
    "currency": ("currency", "valuta", "divisa", "ccy"),
    "brix": ("brix", "gradobrix"),
    "country_of_origin": ("countryoforigin", "origin", "origine", "paesediorigine", "paese"),
    "quality_grade": ("qualitygrade", "grade", "qualita"),
    "incoterm": ("incoterm", "incoterms", "resa"),
    "delivery_location": ("deliverylocation", "delivery", "luogodiconsegna", "destinazione"),
    "contract_type": ("contracttype", "contract", "contratto", "tipocontratto"),
    "packaging": ("packaging", "imballo", "confezione"),
    "certification": ("certification", "certificazione", "certifications"),
}

UNIT_ALIASES = {"kgs": "kg", "kilo": "kg", "kilogram": "kg", "kilograms": "kg", "chilogrammi": "kg",
                "t": "t", "ton": "t", "tonne": "t", "tonnes": "t", "mt": "t", "tonnellate": "t",
                "l": "l", "lt": "l", "litre": "l", "liter": "l", "litri": "l", "lb": "lb", "lbs": "lb"}
INCOTERMS = {"EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def suggest_mapping(header: list[str]) -> dict[str, str | None]:
    """field -> column name (or None)."""
    normalized = {_norm(h): h for h in header if h}
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for f in ALL_FIELDS:
        mapping[f] = None
        for syn in SYNONYMS[f]:
            col = normalized.get(syn)
            if col and col not in used:
                mapping[f] = col
                used.add(col)
                break
    return mapping


@dataclass
class RowResult:
    line: int
    values: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedFile:
    header: list[str]
    delimiter: str
    mapping: dict[str, str | None]
    rows: list[RowResult]
    mapping_errors: list[str]
    decimal_comma: bool = False

    @property
    def number_format(self) -> str:
        return "1.234,56" if self.decimal_comma else "1,234.56"

    @property
    def valid(self) -> list[RowResult]:
        return [r for r in self.rows if not r.errors]

    @property
    def invalid(self) -> list[RowResult]:
        return [r for r in self.rows if r.errors]


def _parse_row(raw: dict[str, str], mapping: dict[str, str | None], decimal_comma: bool) -> tuple[dict[str, Any], list[str]]:
    get = lambda f: (raw.get(mapping[f]) or "").strip() if mapping.get(f) else ""  # noqa: E731
    out: dict[str, Any] = {}
    errors: list[str] = []

    def take(f: str, fn):
        try:
            out[f] = fn(get(f))
        except ValueError as exc:
            errors.append(f"{f}: {exc}")

    take("purchase_date", parse_date)
    num = lambda v: parse_decimal(v, decimal_comma)  # noqa: E731
    take("quantity", num)
    take("unit_price", num)
    for f in ("supplier", "product_description"):
        v = get(f)
        if not v:
            errors.append(f"{f}: required")
        out[f] = v[:500 if f == "product_description" else 200]
    unit = get("unit").lower().strip(".")
    if not unit:
        errors.append("unit: required")
    out["unit"] = UNIT_ALIASES.get(unit, unit)[:20]
    cur = get("currency").upper()
    if cur == "€":
        cur = "EUR"
    if not re.fullmatch(r"[A-Z]{3}", cur):
        errors.append("currency: use a 3-letter ISO code such as EUR")
    out["currency"] = cur

    if "quantity" in out and out["quantity"] <= 0:
        errors.append("quantity: must be greater than 0")
    if "unit_price" in out and out["unit_price"] < 0:
        errors.append("unit_price: must not be negative")
    if "purchase_date" in out and out["purchase_date"] > date.today():
        errors.append("purchase_date: is in the future")

    if get("brix"):
        try:
            b = num(get("brix"))
            if not (0 < b <= 100):
                raise ValueError("must be between 0 and 100")
            out["brix"] = b
        except ValueError as exc:
            errors.append(f"brix: {exc}")
    inc = get("incoterm").upper()
    if inc:
        if inc[:3] not in INCOTERMS:
            errors.append(f"incoterm: '{inc}' is not an Incoterms 2020 rule")
        out["incoterm"] = inc[:3]
    for f, limit in (("country_of_origin", 100), ("quality_grade", 100), ("delivery_location", 200),
                     ("contract_type", 50), ("packaging", 100), ("certification", 200)):
        v = get(f)
        if v:
            out[f] = v[:limit]
    return out, errors


def parse_purchase_file(content: bytes, mapping: dict[str, str | None] | None = None) -> ParsedFile:
    header, rows, delimiter = read_rows(content)
    mapping = {**suggest_mapping(header), **(mapping or {})}
    mapping = {f: (mapping.get(f) or None) for f in ALL_FIELDS}
    mapping_errors = []
    for f, col in mapping.items():
        if col and col not in header:
            mapping_errors.append(f"Column '{col}' mapped to {f} is not in the file")
    for f in REQUIRED_FIELDS:
        if not mapping[f]:
            mapping_errors.append(f"Map a column to the required field '{f}'")
    cols = [c for c in mapping.values() if c]
    if len(cols) != len(set(cols)):
        mapping_errors.append("Each column can be mapped to one field only")

    results = []
    decimal_comma = False
    if not mapping_errors:
        samples = [r.get(mapping[f], "") for r in rows[:500] for f in ("quantity", "unit_price")]
        decimal_comma = infer_decimal_comma(delimiter, samples)
        for i, raw in enumerate(rows, start=2):
            values, errors = _parse_row(raw, mapping, decimal_comma)
            results.append(RowResult(line=i, values=values if not errors else None, errors=errors, raw=raw))
    return ParsedFile(header=header, delimiter=delimiter, mapping=mapping, rows=results,
                      mapping_errors=mapping_errors, decimal_comma=decimal_comma)


# --------------------------------------------------------------------------- analytics


def weighted_average_price(items: list[tuple[Decimal, Decimal]]) -> Decimal | None:
    """WAPP = sum(quantity * price) / sum(quantity). ``items`` are (quantity, unit_price)."""
    total_q = sum((q for q, _ in items), Decimal(0))
    if total_q <= 0:
        return None
    return sum((q * p for q, p in items), Decimal(0)) / total_q


def group_wapp(purchases: list[Any], key) -> list[dict[str, Any]]:
    """Weighted average by ``key(purchase)`` plus (unit, currency); groups never mix units or currencies."""
    groups: dict[tuple, list[Any]] = defaultdict(list)
    for p in purchases:
        groups[(key(p), p.unit, p.currency)].append(p)
    out = []
    for (k, unit, currency), ps in groups.items():
        wapp = weighted_average_price([(p.quantity, p.unit_price) for p in ps])
        out.append(
            {
                "key": k,
                "unit": unit,
                "currency": currency,
                "purchases": len(ps),
                "total_quantity": sum((p.quantity for p in ps), Decimal(0)),
                "total_spend": sum((p.quantity * p.unit_price for p in ps), Decimal(0)),
                "weighted_avg_price": wapp,
                "min_price": min(p.unit_price for p in ps),
                "max_price": max(p.unit_price for p in ps),
                "first_purchase": min(p.purchase_date for p in ps),
                "last_purchase": max(p.purchase_date for p in ps),
            }
        )
    return sorted(out, key=lambda g: g["total_spend"], reverse=True)
