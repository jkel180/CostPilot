"""Market intelligence: shared benchmark data with provenance. Readable by any signed-in user."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app import market
from app.deps import CurrentUser, DbSession
from app.models import Commodity, DataSource, ObservationDataType, ProductSpec
from app.schemas import MarketOverview, OriginRow, Series, SeriesPoint, SeriesResponse, SourceInfo

router = APIRouter(prefix="/market", tags=["market"])


def get_commodity(db: DbSession, code: str) -> Commodity:
    com = db.scalar(select(Commodity).where(Commodity.code == code, Commodity.active.is_(True)))
    if com is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commodity not found")
    return com


def _label(obs) -> str:
    if obs.geography == market.BENCHMARK_GEOGRAPHY:
        return "Extra-EU total"
    label = (obs.attributes or {}).get("partner_label") or obs.geography
    # Eurostat labels carry historical notes, e.g. "South Africa (incl. Namibia 'NA' -> 1989)"
    return label.split(" (")[0].strip() or obs.geography


def source_infos(db: DbSession, com: Commodity) -> list[SourceInfo]:
    stats = market.observation_stats(db, com)
    runs = market.latest_runs(db, com)
    out = []
    for s in db.scalars(select(DataSource).order_by(DataSource.name)):
        n, last_obs, collected = stats.get(s.id, (0, None, None))
        run = runs.get(s.id)
        if n == 0 and run is None:
            continue
        ok = market.last_success(db, s.id, com)
        out.append(
            SourceInfo(
                id=s.id, name=s.name, source_type=s.source_type.value, source_url=s.source_url,
                license_reference=s.license_reference, update_frequency=s.update_frequency,
                is_synthetic=s.is_synthetic, observations=n, latest_observation_date=last_obs,
                last_collected_at=collected,
                last_run_status=run.status.value if run else None,
                last_run_at=run.started_at if run else None,
                last_success_at=ok.finished_at if ok else None,
                last_data_version=ok.data_version if ok else None,
                last_error=run.error if run and run.error else None,
            )
        )
    return out


def _scope(db: DbSession, spec_id) -> str | None:
    spec = db.get(ProductSpec, spec_id) if spec_id else None
    return spec.specification_name if spec else None


@router.get("/series", response_model=SeriesResponse)
def get_series(
    _: CurrentUser,
    db: DbSession,
    commodity: str = Query("lemon_juice_concentrate", max_length=64),
    data_type: ObservationDataType = ObservationDataType.customs_unit_value,
    geography: list[str] | None = Query(None, max_length=20),
    include_unvalidated: bool = False,
    since: date | None = None,
) -> SeriesResponse:
    com = get_commodity(db, commodity)
    data = market.series(db, com, data_type, geography, include_unvalidated, since)
    first = next((pts[0] for pts in data.values() if pts), None)
    order = sorted(data, key=lambda g: (g != market.BENCHMARK_GEOGRAPHY, g))
    return SeriesResponse(
        commodity=com.code,
        data_type=data_type,
        unit=first.unit if first else None,
        currency=first.currency if first else None,
        scope=_scope(db, first.product_spec_id) if first else None,
        series=[
            Series(
                geography=g,
                label=_label(data[g][0]),
                points=[
                    SeriesPoint(
                        date=o.observation_date, value=o.value, quality_status=o.quality_status.value,
                        quality_note=o.quality_note,
                        quantity_kg=(Decimal(str(o.attributes["quantity_kg"])) if (o.attributes or {}).get("quantity_kg") else None),
                    )
                    for o in data[g]
                ],
            )
            for g in order
        ],
    )


@router.get("/overview", response_model=MarketOverview)
def get_overview(
    _: CurrentUser, db: DbSession, commodity: str = Query("lemon_juice_concentrate", max_length=64)
) -> MarketOverview:
    com = get_commodity(db, commodity)
    bench = market.benchmark(db, com)
    sources = source_infos(db, com)
    if bench is None:
        return MarketOverview(
            commodity=com.code, benchmark_label=market.BENCHMARK_LABEL, scope=None, latest_month=None,
            benchmark_value=None, benchmark_mom_pct=None, benchmark_yoy_pct=None, benchmark_12m_avg=None,
            import_volume_kg=None, import_volume_yoy_pct=None, origins=[], sources=sources,
        )

    month = bench["observation"].observation_date
    prices = market.series(db, com, ObservationDataType.customs_unit_value, include_unvalidated=True,
                           since=market.month_offset(month, -12), include_rejected=True)
    volumes = market.series(db, com, ObservationDataType.trade_volume, since=market.month_offset(month, -12))
    bench_pts = [p for p in prices.get(market.BENCHMARK_GEOGRAPHY, [])
                 if p.quality_status.value == "validated" and p.observation_date > market.month_offset(month, -12)]
    avg12 = (sum((p.value for p in bench_pts), Decimal(0)) / len(bench_pts)) if bench_pts else None

    total_vol = market.find(volumes.get(market.BENCHMARK_GEOGRAPHY, []), month)
    total_vol_ya = market.find(volumes.get(market.BENCHMARK_GEOGRAPHY, []), market.month_offset(month, -12))

    origins = []
    for geo, vols in volumes.items():
        if geo == market.BENCHMARK_GEOGRAPHY:
            continue
        v = market.find(vols, month)
        p = market.find(prices.get(geo, []), month)
        prev = market.find(prices.get(geo, []), market.month_offset(month, -1))
        if v is None and p is None:
            continue
        validated = p is not None and p.quality_status.value == "validated"
        origins.append(
            OriginRow(
                geography=geo,
                label=_label(v or p),
                month=month,
                unit_value=p.value if p else None,
                unit_value_quality=p.quality_status.value if p else None,
                quantity_kg=v.value if v else None,
                volume_share_pct=(v.value / total_vol.value * 100) if (v and total_vol and total_vol.value) else None,
                mom_pct=market.pct_change(p.value, prev.value) if (validated and prev and prev.quality_status.value == "validated") else None,
            )
        )
    origins.sort(key=lambda o: o.quantity_kg or 0, reverse=True)
    return MarketOverview(
        commodity=com.code,
        benchmark_label=market.BENCHMARK_LABEL,
        scope=bench["spec"].specification_name if bench["spec"] else None,
        latest_month=month,
        benchmark_value=bench["observation"].value,
        benchmark_mom_pct=bench["mom_pct"],
        benchmark_yoy_pct=bench["yoy_pct"],
        benchmark_12m_avg=avg12,
        import_volume_kg=total_vol.value if total_vol else None,
        import_volume_yoy_pct=market.pct_change(total_vol.value if total_vol else None,
                                                total_vol_ya.value if total_vol_ya else None),
        origins=origins,
        sources=sources,
    )
