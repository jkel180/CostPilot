"""Comext connector with a fake HTTP layer, run logging, market endpoints and admin permissions."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.ingestion import EurostatComextConnector
from app.ingestion.base import run_connector
from app.ingestion.eurostat_comext import parse_jsonstat
from app.models import Commodity, IngestionRun, MarketObservation, QualityStatus, RunStatus

MONTHS = [f"2026-{m:02d}" for m in range(1, 8)]


def jsonstat(cells: dict[tuple[str, str, str], float]) -> dict:
    """Build a JSON-stat doc from {(partner, indicator, month): value}."""
    partners = sorted({p for p, _, _ in cells})
    inds = ["VALUE_IN_EUROS", "QUANTITY_IN_100KG"]
    dims = {
        "freq": ["M"], "reporter": ["EU27_2020"], "partner": partners, "product": ["20093939"],
        "flow": ["1"], "indicators": inds, "time": MONTHS,
    }
    ids = list(dims)
    size = [len(dims[d]) for d in ids]
    value = {}
    for (p, ind, t), v in cells.items():
        coord = {"freq": "M", "reporter": "EU27_2020", "partner": p, "product": "20093939", "flow": "1",
                 "indicators": ind, "time": t}
        pos = 0
        for d, n in zip(ids, size):
            pos = pos * n + dims[d].index(coord[d])
        value[str(pos)] = v
    labels = {"EXT_EU27_2020": "Extra-EU27", "AR": "Argentina", "MX": "Mexico"}
    return {
        "id": ids, "size": size, "updated": "2026-11-13T11:00:00+0100", "value": value,
        "dimension": {
            d: {"category": {"index": {c: i for i, c in enumerate(dims[d])},
                             "label": {c: labels.get(c, c) for c in dims[d]}}}
            for d in ids
        },
    }


def fixture_cells(scale: float = 1.0) -> dict:
    cells = {}
    for i, t in enumerate(MONTHS):
        # extra-EU total: 2,000 t/month at 2.00 -> 2.60 EUR/kg
        cells[("EXT_EU27_2020", "QUANTITY_IN_100KG", t)] = 20_000
        cells[("EXT_EU27_2020", "VALUE_IN_EUROS", t)] = 20_000 * 100 * (2.0 + 0.1 * i) * scale
        # Argentina: 1,000 t/month at 1.80; month 7 is an outlier (x5)
        cells[("AR", "QUANTITY_IN_100KG", t)] = 10_000
        cells[("AR", "VALUE_IN_EUROS", t)] = 10_000 * 100 * (1.8 if i < 6 else 9.0)
        # Mexico: tiny volumes (2 t)
        cells[("MX", "QUANTITY_IN_100KG", t)] = 20
        cells[("MX", "VALUE_IN_EUROS", t)] = 20 * 100 * 30.0
    del cells[("MX", "QUANTITY_IN_100KG", "2026-07")]  # value without quantity -> rejected
    return cells


def fake_get(cells):
    calls = []

    def get(url, params):
        calls.append(params)
        return jsonstat(cells)

    get.calls = calls
    return get


@pytest.fixture
def lemon(db):
    return db.scalar(select(Commodity))


def test_parse_jsonstat_roundtrip():
    doc = jsonstat({("AR", "VALUE_IN_EUROS", "2026-03"): 5.0})
    (cell,) = parse_jsonstat(doc)
    assert (cell["partner"], cell["indicators"], cell["time"], cell["value"]) == ("AR", "VALUE_IN_EUROS", "2026-03", 5.0)
    assert cell["partner_label"] == "Argentina"


def test_comext_quality_rules_and_provenance(db, lemon):
    get = fake_get(fixture_cells())
    run = run_connector(db, EurostatComextConnector(lemon, http_get=get))
    assert run.status == RunStatus.success, run.error
    assert ("product", "20093939") in get.calls[0] and ("reporter", "EU27_2020") in get.calls[0]

    obs = db.scalars(select(MarketObservation).where(MarketObservation.data_type == "customs_unit_value")).all()
    by = {(o.geography, o.observation_date.month): o for o in obs}
    ext = by[("EXT_EU27_2020", 1)]
    assert float(ext.value) == pytest.approx(2.0) and ext.quality_status == QualityStatus.validated
    assert (ext.currency, ext.unit) == ("EUR", "kg")
    assert ext.attributes["cn_code"] == "20093939" and ext.attributes["quantity_kg"] == 2_000_000
    assert ext.ingestion_run_id == run.id
    assert by[("AR", 7)].quality_status == QualityStatus.rejected  # 5x the series median
    assert by[("MX", 1)].quality_status == QualityStatus.unvalidated and "low volume" in by[("MX", 1)].quality_note
    assert ("MX", 7) not in by  # no quantity -> not stored
    assert run.rows_rejected == 1 and run.data_version and len(run.data_version) == 64


def test_rerun_is_idempotent_and_updates_values(db, lemon):
    run_connector(db, EurostatComextConnector(lemon, http_get=fake_get(fixture_cells())))
    n = db.scalar(select(func.count(MarketObservation.id)))
    run2 = run_connector(db, EurostatComextConnector(lemon, http_get=fake_get(fixture_cells(scale=1.1))))
    assert db.scalar(select(func.count(MarketObservation.id))) == n
    assert run2.parameters["inserted"] == 0 and run2.parameters["updated"] == n
    ext = db.scalar(select(MarketObservation).where(MarketObservation.geography == "EXT_EU27_2020",
                                                    MarketObservation.data_type == "customs_unit_value")
                    .order_by(MarketObservation.observation_date))
    assert float(ext.value) == pytest.approx(2.2)


def test_failed_fetch_is_logged(db, lemon):
    def boom(url, params):
        raise ConnectionError("Eurostat unreachable")

    run = run_connector(db, EurostatComextConnector(lemon, http_get=boom))
    assert run.status == RunStatus.failed and "unreachable" in run.error
    assert db.scalar(select(func.count(IngestionRun.id))) == 1
    assert db.scalar(select(func.count(MarketObservation.id))) == 0


# ------------------------------------------------------------------ endpoints


@pytest.fixture
def ingested(db, lemon):
    run_connector(db, EurostatComextConnector(lemon, http_get=fake_get(fixture_cells())))


def test_market_series_excludes_unvalidated_by_default(actor, ingested):
    u = actor("u@x.com")
    body = u.get("/api/v1/market/series").json()
    geos = [s["geography"] for s in body["series"]]
    assert geos[0] == "EXT_EU27_2020" and "MX" not in geos
    assert body["scope"].startswith("CN 20093939") and (body["unit"], body["currency"]) == ("kg", "EUR")
    ar = next(s for s in body["series"] if s["geography"] == "AR")
    assert len(ar["points"]) == 6 and ar["label"] == "Argentina"  # outlier month excluded
    with_all = u.get("/api/v1/market/series?include_unvalidated=true&geography=MX").json()
    assert with_all["series"][0]["points"][0]["quality_status"] == "unvalidated"


def test_market_overview(actor, ingested):
    body = actor("u@x.com").get("/api/v1/market/overview").json()
    assert body["latest_month"] == "2026-07-01"
    assert float(body["benchmark_value"]) == pytest.approx(2.6)
    assert float(body["benchmark_mom_pct"]) == pytest.approx((2.6 - 2.5) / 2.5 * 100)
    assert body["benchmark_yoy_pct"] is None  # no year-ago month in the fixture
    ar = next(o for o in body["origins"] if o["geography"] == "AR")
    assert float(ar["volume_share_pct"]) == pytest.approx(50) and ar["unit_value_quality"] == "rejected"
    src = body["sources"][0]
    assert src["name"].startswith("Eurostat Comext") and src["last_run_status"] == "success"
    assert src["license_reference"] and src["last_data_version"]


def test_dashboard_benchmark_kpis(actor, ingested):
    u = actor("u@x.com")
    org = u.create_org()
    body = u.get("/api/v1/dashboard/summary", org=org).json()
    k = {x["key"]: x for x in body["kpis"]}
    bench = k["current_market_benchmark"]
    assert bench["status"] == "available" and float(bench["value"]) == pytest.approx(2.6)
    assert bench["value_kind"] == "observed" and bench["provenance"]["source_name"].startswith("Eurostat")
    assert "not a spot price" in bench["note"]
    assert k["monthly_price_change"]["unit"] == "%" and k["monthly_price_change"]["value_kind"] == "calculated"
    assert len(body["benchmark_series"]) == 7


# ------------------------------------------------------------------ admin permissions


def test_only_platform_admins_manage_market_data(actor):
    u = actor("customer@x.com")
    assert u.post("/api/v1/admin/ingestion/eurostat_comext").status_code == 403
    files = {"file": ("m.csv", b"observation_date,geography,value,unit,data_type\n", "text/csv")}
    assert u.post("/api/v1/admin/market-observations/upload", files=files,
                  data={"original_source": "x"}).status_code == 403
    assert actor("ops@costpilot.test").get("/api/v1/me").json()["is_platform_admin"] is True
    assert u.get("/api/v1/me").json()["is_platform_admin"] is False


def test_scheduled_ingestion_requires_token(client):
    assert client.post("/api/v1/admin/scheduled-ingestion/eurostat_comext").status_code == 401
    r = client.post("/api/v1/admin/scheduled-ingestion/eurostat_comext", headers={"X-Ingestion-Token": "wrong"})
    assert r.status_code == 401


def test_manual_market_upload(actor):
    ops = actor("ops@costpilot.test")
    content = (
        "observation_date,geography,value,currency,unit,data_type,quality_status\n"
        "2026-05,AR,2.35,USD,kg,contract_price,validated\n"
        "2026-06,AR,2.40,,kg,contract_price,\n"  # missing currency -> rejected
        "2026-06,AR,abc,USD,kg,spot_price,\n"
    ).encode()
    r = ops.post("/api/v1/admin/market-observations/upload", files={"file": ("m.csv", content, "text/csv")},
                 data={"original_source": "Broker report, May 2026"})
    assert r.status_code == 200, r.text
    assert (r.json()["rows_saved"], r.json()["rows_rejected"]) == (1, 2)
    series = ops.get("/api/v1/market/series?data_type=contract_price").json()["series"]
    assert series[0]["points"][0]["value"] in ("2.350000", "2.35")
    r = ops.post("/api/v1/admin/market-observations/upload", files={"file": ("m.csv", content, "text/csv")},
                 data={"original_source": ""})
    assert r.status_code == 422
