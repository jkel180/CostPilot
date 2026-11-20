"""Eurostat Comext connector (dataset DS-045409, EU trade by CN8, monthly).

What it produces
----------------
For each partner country and month: the **import unit value** (EUR/kg = value / quantity)
stored as ``customs_unit_value``, and the imported quantity as ``trade_volume`` (kg).
Customs unit values are border values of declared trade, not spot or contract prices,
and are labelled as such everywhere.

Product scope
-------------
Lemon juice concentrate at market prices (well above 30 EUR/100 kg) is declared under
CN 20093939: "single citrus fruit juice, unfermented, Brix > 20 but <= 67, value > 30 EUR
per 100 kg, no added sugar". The code is not lemon-only: it covers every single citrus
juice except orange and grapefruit (lemon, lime, mandarin...). The CN codes that name
lemon explicitly exist only for the <= 30 EUR/100 kg band, which does not match
concentrate prices. The benchmark is therefore labelled with its exact CN scope.

Quality rules (documented, deterministic)
-----------------------------------------
* no value or no/zero quantity -> rejected (not stored)
* quantity below ``min_validated_kg`` -> stored as ``unvalidated`` ("low volume")
* unit value outside [median / 3, median * 3] of that partner's series -> ``rejected``
* otherwise -> ``validated``
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Any

import httpx

from app.ingestion.base import Connector, NormalizedObservation, Rejected, ValidationResult
from app.models import ObservationDataType, QualityStatus

API_BASE = "https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/DS-045409"

#: Per-commodity configuration: adding a commodity means adding an entry here.
COMEXT_CONFIG: dict[str, dict[str, Any]] = {
    "lemon_juice_concentrate": {
        "reporter": "EU27_2020",
        "flow": "1",  # imports
        "products": {"20093939": "CN 20093939 - single citrus juice, Brix 20-67, > 30 EUR/100 kg, no added sugar"},
        "partners": ["EXT_EU27_2020", "AR", "ZA", "BR", "US", "MX", "TR", "UY", "CL", "PE", "IL"],
        "since": "2019-01",
        "min_validated_kg": 50_000,
        # Support series for the pooled forecast model: the same product imported by the main
        # EU importers. Stored as "<reporter>:<partner>" unit values, not shown as market origins.
        "panel_reporters": ["IT", "DE", "NL", "ES", "FR", "BE", "PL", "AT"],
        "panel_partners": ["EXT_EU27_2020", "INT_EU27_2020"],
    }
}

PANEL_SEPARATOR = ":"


def is_panel_geography(geography: str) -> bool:
    return PANEL_SEPARATOR in geography

VALUE = "VALUE_IN_EUROS"
QUANTITY = "QUANTITY_IN_100KG"


def parse_jsonstat(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a JSON-stat 2.0 dataset into one dict per non-empty cell."""
    ids: list[str] = doc["id"]
    sizes: list[int] = doc["size"]
    dims = doc["dimension"]
    positions = [
        sorted(dims[d]["category"]["index"].items(), key=lambda kv: kv[1]) for d in ids
    ]
    labels = {d: dims[d]["category"].get("label", {}) for d in ids}
    out = []
    for flat, value in doc.get("value", {}).items():
        n = int(flat)
        coords: dict[str, Any] = {}
        for d, size, pos in zip(reversed(ids), reversed(sizes), reversed(positions)):
            code = pos[n % size][0]
            coords[d] = code
            coords[f"{d}_label"] = labels[d].get(code, code)
            n //= size
        coords["value"] = value
        out.append(coords)
    return out


class EurostatComextConnector(Connector):
    name = "eurostat_comext"
    source_name = "Eurostat Comext (DS-045409)"

    def __init__(self, commodity, params=None, http_get=None) -> None:
        super().__init__(commodity, params)
        cfg = COMEXT_CONFIG.get(commodity.code)
        if cfg is None:
            raise LookupError(f"No Comext configuration for commodity '{commodity.code}'")
        self.cfg = {**cfg, **{k: v for k, v in self.params.items() if k in ("since", "partners")}}
        self.params = {"since": self.cfg["since"], "partners": self.cfg["partners"], "products": list(cfg["products"])}
        self._http_get = http_get or self._default_get
        self.spec_ids: dict[str, Any] = {}

    def prepare(self, db) -> None:
        from sqlalchemy import select

        from app.models import ProductSpec

        for cn, spec_name in self.cfg["products"].items():
            spec_id = db.scalar(
                select(ProductSpec.id).where(
                    ProductSpec.commodity_id == self.commodity.id, ProductSpec.specification_name == spec_name
                )
            )
            if spec_id is None:
                raise LookupError(f"Product specification '{spec_name}' is missing")
            self.spec_ids[cn] = spec_id

    @staticmethod
    def _default_get(url: str, params: list[tuple[str, str]]) -> dict[str, Any]:
        r = httpx.get(url, params=params, timeout=90)
        r.raise_for_status()
        return r.json()

    def _request(self, reporters: list[str], partners: list[str]) -> list[dict[str, Any]]:
        params = [
            ("format", "JSON"), ("lang", "en"), ("freq", "M"), ("flow", self.cfg["flow"]),
            ("indicators", VALUE), ("indicators", QUANTITY), ("sinceTimePeriod", self.cfg["since"]),
        ]
        params += [("reporter", r) for r in reporters]
        params += [("partner", p) for p in partners]
        params += [("product", p) for p in self.cfg["products"]]
        doc = self._http_get(API_BASE, params)
        self.dataset_updated = doc.get("updated")
        return parse_jsonstat(doc)

    def fetch_data(self) -> list[dict[str, Any]]:
        cells = [{**c, "panel": False} for c in self._request([self.cfg["reporter"]], self.cfg["partners"])]
        if self.cfg.get("panel_reporters"):
            cells += [{**c, "panel": True}
                      for c in self._request(self.cfg["panel_reporters"], self.cfg["panel_partners"])]
        # pivot value + quantity into one record per (reporter, partner, product, month)
        records: dict[tuple, dict[str, Any]] = {}
        for c in cells:
            reporter = c.get("reporter", self.cfg["reporter"])
            key = (reporter, c["partner"], c["product"], c["time"])
            rec = records.setdefault(
                key,
                {"reporter": reporter, "panel": c["panel"], "partner": c["partner"],
                 "partner_label": c["partner_label"], "product": c["product"],
                 "period": c["time"], "value_eur": None, "quantity_kg": None},
            )
            if c["indicators"] == VALUE:
                rec["value_eur"] = c["value"]
            elif c["indicators"] == QUANTITY:
                rec["quantity_kg"] = None if c["value"] is None else c["value"] * 100
        return list(records.values())

    def validate_data(self, raw: list[dict[str, Any]]) -> ValidationResult:
        valid, rejected = [], []
        for rec in raw:
            if not rec["value_eur"] or rec["value_eur"] <= 0:
                rejected.append(Rejected("missing or non-positive value", rec))
            elif not rec["quantity_kg"] or rec["quantity_kg"] <= 0:
                rejected.append(Rejected("missing or zero quantity", rec))
            else:
                valid.append({**rec, "unit_value": rec["value_eur"] / rec["quantity_kg"]})

        # outliers against each partner's own series (median of adequately sized months)
        by_series: dict[tuple, list[float]] = {}
        for rec in valid:
            if rec["quantity_kg"] >= self.cfg["min_validated_kg"]:
                by_series.setdefault((rec["reporter"], rec["partner"], rec["product"]), []).append(rec["unit_value"])
        medians = {k: median(v) for k, v in by_series.items() if len(v) >= 3}
        for rec in valid:
            m = medians.get((rec["reporter"], rec["partner"], rec["product"]))
            rec["series_median"] = m
            if rec["quantity_kg"] < self.cfg["min_validated_kg"]:
                rec["quality"] = (QualityStatus.unvalidated, f"low volume (< {self.cfg['min_validated_kg'] // 1000} t)")
            elif m is not None and not (m / 3 <= rec["unit_value"] <= m * 3):
                rec["quality"] = (QualityStatus.rejected, "unit value outlier vs series median (x3)")
            elif m is None:
                rec["quality"] = (QualityStatus.unvalidated, "series too short to validate")
            else:
                rec["quality"] = (QualityStatus.validated, None)
        return ValidationResult(valid=valid, rejected=rejected)

    def normalize_data(self, valid: list[dict[str, Any]]) -> list[NormalizedObservation]:
        rows = []
        for rec in valid:
            y, m = rec["period"].split("-")
            obs_date = date(int(y), int(m), 1)
            spec_id = self.spec_ids.get(rec["product"])
            geography = (f"{rec['reporter']}{PANEL_SEPARATOR}{rec['partner']}" if rec["panel"]
                         else rec["partner"])
            attrs = {
                "reporter": rec["reporter"],
                "role": "panel" if rec["panel"] else "market",
                "flow": "import",
                "cn_code": rec["product"],
                "partner_label": rec["partner_label"],
                "value_eur": rec["value_eur"],
                "quantity_kg": rec["quantity_kg"],
                "dataset": "DS-045409",
                "dataset_updated": getattr(self, "dataset_updated", None),
            }
            status, note = rec["quality"]
            rows.append(
                NormalizedObservation(
                    observation_date=obs_date,
                    geography=geography,
                    value=Decimal(str(rec["unit_value"])).quantize(Decimal("0.000001"), ROUND_HALF_UP),
                    currency="EUR",
                    unit="kg",
                    data_type=ObservationDataType.customs_unit_value,
                    quality_status=status,
                    quality_note=note,
                    product_spec_id=spec_id,
                    attributes=attrs,
                )
            )
            if rec["panel"]:
                continue
            rows.append(
                NormalizedObservation(
                    observation_date=obs_date,
                    geography=rec["partner"],
                    value=Decimal(str(rec["quantity_kg"])).quantize(Decimal("0.0001")),
                    currency=None,
                    unit="kg",
                    data_type=ObservationDataType.trade_volume,
                    quality_status=QualityStatus.validated,
                    product_spec_id=spec_id,
                    attributes=attrs,
                )
            )
        return rows
