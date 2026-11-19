"""Manual CSV upload of market observations (fallback when no API connector exists).

Required columns: observation_date, geography, value, unit, data_type
Optional columns: currency, quality_status, note

Every upload must name where the figures come from (``original_source``), stored with
each observation for provenance. Rows are stored as ``unvalidated`` unless the file
says otherwise.
"""

from __future__ import annotations

from typing import Any

from app.csvutil import infer_decimal_comma, parse_date, parse_decimal, read_rows
from app.ingestion.base import Connector, NormalizedObservation, Rejected, ValidationResult
from app.models import ObservationDataType, QualityStatus

REQUIRED = ("observation_date", "geography", "value", "unit", "data_type")
MONETARY = {
    ObservationDataType.customs_unit_value,
    ObservationDataType.spot_price,
    ObservationDataType.contract_price,
}


class ManualCsvConnector(Connector):
    name = "manual_csv"
    source_name = "Manual upload"

    def __init__(self, commodity, params: dict[str, Any]) -> None:
        super().__init__(commodity, params)
        if not str(params.get("original_source") or "").strip():
            raise ValueError("original_source is required for manual uploads")
        self.content: bytes = params["content"]

    def fetch_data(self) -> list[dict[str, str]]:
        header, rows, delimiter = read_rows(self.content)
        lowered = {h.lower() for h in header}
        missing = [c for c in REQUIRED if c not in lowered]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        out = [{k.lower(): v for k, v in r.items()} for r in rows]
        self.decimal_comma = infer_decimal_comma(delimiter, [r.get("value", "") for r in out[:500]])
        return out

    def validate_data(self, raw: list[dict[str, str]]) -> ValidationResult:
        valid, rejected = [], []
        for i, r in enumerate(raw, start=2):
            try:
                dtype = ObservationDataType(r["data_type"].strip().lower())
                currency = (r.get("currency") or "").strip().upper() or None
                if dtype in MONETARY and (not currency or len(currency) != 3):
                    raise ValueError("a 3-letter currency is required for prices")
                quality = QualityStatus((r.get("quality_status") or "unvalidated").strip().lower())
                value = parse_decimal(r["value"], self.decimal_comma)
                if dtype in MONETARY and value <= 0:
                    raise ValueError("prices must be positive")
                if not r["geography"].strip() or not r["unit"].strip():
                    raise ValueError("geography and unit are required")
                valid.append(
                    {
                        "date": parse_date(r["observation_date"]),
                        "geography": r["geography"].strip()[:100],
                        "value": value,
                        "currency": currency,
                        "unit": r["unit"].strip()[:30],
                        "data_type": dtype,
                        "quality": quality,
                        "note": (r.get("note") or "").strip()[:200] or None,
                        "line": i,
                    }
                )
            except (ValueError, KeyError) as exc:
                rejected.append(Rejected(str(exc), {"line": i}))
        return ValidationResult(valid=valid, rejected=rejected)

    def normalize_data(self, valid: list[dict[str, Any]]) -> list[NormalizedObservation]:
        attrs = {"original_source": str(self.params["original_source"]).strip()[:300],
                 "filename": self.params.get("filename")}
        return [
            NormalizedObservation(
                observation_date=v["date"],
                geography=v["geography"],
                value=v["value"],
                currency=v["currency"],
                unit=v["unit"],
                data_type=v["data_type"],
                quality_status=v["quality"],
                quality_note=v["note"],
                product_spec_id=self.params.get("product_spec_id"),
                attributes={**attrs, "line": v["line"]},
            )
            for v in valid
        ]
