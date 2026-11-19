"""Market-data queries shared by the market endpoints and the dashboard."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Commodity,
    DataSource,
    IngestionRun,
    MarketObservation,
    ObservationDataType,
    ProductSpec,
    QualityStatus,
    RunStatus,
)

#: The benchmark series: EU imports from all non-EU countries, customs unit value.
BENCHMARK_GEOGRAPHY = "EXT_EU27_2020"
BENCHMARK_LABEL = "EU imports from outside the EU (customs unit value)"


@dataclass
class Point:
    observation_date: date
    value: Decimal
    quality_status: QualityStatus
    quality_note: str | None
    attributes: dict
    source_id: uuid.UUID
    collected_at: object
    product_spec_id: uuid.UUID | None


def series(
    db: Session,
    commodity: Commodity,
    data_type: ObservationDataType,
    geographies: list[str] | None = None,
    include_unvalidated: bool = False,
    since: date | None = None,
    include_rejected: bool = False,
) -> dict[str, list[MarketObservation]]:
    q = select(MarketObservation).where(
        MarketObservation.commodity_id == commodity.id, MarketObservation.data_type == data_type
    )
    if geographies:
        q = q.where(MarketObservation.geography.in_(geographies))
    allowed = [QualityStatus.validated] + ([QualityStatus.unvalidated] if include_unvalidated else [])
    if include_rejected:
        allowed.append(QualityStatus.rejected)
    q = q.where(MarketObservation.quality_status.in_(allowed))
    if since:
        q = q.where(MarketObservation.observation_date >= since)
    out: dict[str, list[MarketObservation]] = {}
    for o in db.scalars(q.order_by(MarketObservation.geography, MarketObservation.observation_date)):
        out.setdefault(o.geography, []).append(o)
    return out


def pct_change(new: Decimal | None, old: Decimal | None) -> Decimal | None:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / old * 100


def month_offset(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


def find(points: list[MarketObservation], d: date) -> MarketObservation | None:
    return next((p for p in points if p.observation_date == d), None)


def benchmark(db: Session, commodity: Commodity) -> dict | None:
    """Latest validated benchmark point with month-on-month and year-on-year changes."""
    pts = series(db, commodity, ObservationDataType.customs_unit_value, [BENCHMARK_GEOGRAPHY]).get(
        BENCHMARK_GEOGRAPHY, []
    )
    if not pts:
        return None
    last = pts[-1]
    prev = find(pts, month_offset(last.observation_date, -1))
    year_ago = find(pts, month_offset(last.observation_date, -12))
    source = db.get(DataSource, last.source_id)
    spec = db.get(ProductSpec, last.product_spec_id) if last.product_spec_id else None
    return {
        "observation": last,
        "previous": prev,
        "mom_pct": pct_change(last.value, prev.value if prev else None),
        "yoy_pct": pct_change(last.value, year_ago.value if year_ago else None),
        "source": source,
        "spec": spec,
    }


def latest_runs(db: Session, commodity: Commodity) -> dict[uuid.UUID, IngestionRun]:
    runs = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.commodity_id == commodity.id)
        .order_by(IngestionRun.started_at.desc())
        .limit(50)
    ).all()
    latest: dict[uuid.UUID, IngestionRun] = {}
    for r in runs:
        latest.setdefault(r.source_id, r)
    return latest


def last_success(db: Session, source_id: uuid.UUID, commodity: Commodity) -> IngestionRun | None:
    return db.scalar(
        select(IngestionRun)
        .where(
            IngestionRun.source_id == source_id,
            IngestionRun.commodity_id == commodity.id,
            IngestionRun.status == RunStatus.success,
        )
        .order_by(IngestionRun.started_at.desc())
        .limit(1)
    )


def observation_stats(db: Session, commodity: Commodity) -> dict[uuid.UUID, tuple[int, date | None, object]]:
    rows = db.execute(
        select(
            MarketObservation.source_id,
            func.count(MarketObservation.id),
            func.max(MarketObservation.observation_date),
            func.max(MarketObservation.collected_at),
        )
        .where(MarketObservation.commodity_id == commodity.id)
        .group_by(MarketObservation.source_id)
    ).all()
    return {sid: (n, last, collected) for sid, n, last, collected in rows}
