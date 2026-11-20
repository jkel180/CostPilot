from decimal import Decimal

import pytest

from app.simulator import SimulationInput, monthly_quantity, scenario, target_savings
from app.units import price_per_kg
from tests.test_forecasting import FAST, seed_benchmark

D = Decimal


# ------------------------------------------------------------------ formulas (spec 3.4)


def test_scenario_math():
    inp = SimulationInput(monthly_quantity=D(1000), current_price=D("2.00"), months=3, pass_through=D(1))
    s = scenario(inp, D(10))
    assert s["scenario_price"] == D("2.200000")
    assert s["period_quantity"] == D("3000.00")
    assert s["baseline_spend"] == D("6000.00") and s["expected_spend"] == D("6600.00")
    assert s["period_impact"] == D("600.00")       # price change x quantity
    assert s["annualized_impact"] == D("2400.00")  # monthly impact x 12


def test_pass_through_scales_the_change_and_savings_are_negative():
    inp = SimulationInput(monthly_quantity=D(1000), current_price=D("2.00"), months=1, pass_through=D("0.5"))
    s = scenario(inp, D(-10))
    assert s["price_change_pct"] == D("-5.00") and s["period_impact"] == D("-100.00")


def test_monthly_quantity():
    assert monthly_quantity(D(120000), "annual") == D(10000)
    assert monthly_quantity(D(5000), "monthly") == D(5000)
    with pytest.raises(ValueError):
        monthly_quantity(D(1), "weekly")


def test_target_savings():
    assert target_savings(D("2.50"), D("2.30"), D(1000)) == D("2400.00")
    assert target_savings(D("2.50"), None, D(1000)) is None


def test_unit_rules_are_explicit():
    assert price_per_kg(D(2500), "t", "EUR")[0] == D("2.5")
    assert price_per_kg(D("2.5"), "kg", "EUR")[1] == "no conversion"
    assert price_per_kg(D("2.5"), "kg", "USD")[0] is None
    assert price_per_kg(D("2.5"), "l", "EUR")[0] is None  # volume needs a density


# ------------------------------------------------------------------ API

MODEL = {"expected_volume": "120000", "volume_period": "annual", "current_purchase_price": "2.50",
         "target_purchase_price": "2.30", "currency": "EUR", "unit": "kg", "pass_through_pct": "100"}


@pytest.fixture
def team(actor):
    admin, viewer = actor("admin@a.com"), actor("viewer@a.com")
    viewer.signup()
    org = admin.create_org("Org A")
    admin.post("/api/v1/organizations/current/members", org=org, json={"email": viewer.email, "role": "viewer"})
    return {"org": org, "admin": admin, "viewer": viewer}


def test_cost_model_roles_and_isolation(team, actor):
    org = team["org"]
    assert team["admin"].get("/api/v1/cost-model", org=org).json() is None
    assert team["viewer"].put("/api/v1/cost-model", org=org, json=MODEL).status_code == 403
    r = team["admin"].put("/api/v1/cost-model", org=org, json=MODEL)
    assert r.status_code == 200 and r.json()["current_purchase_price"] in ("2.500000", "2.5", "2.50")
    r = team["admin"].put("/api/v1/cost-model", org=org, json={**MODEL, "current_purchase_price": "2.40"})
    assert r.json()["id"] == team["admin"].get("/api/v1/cost-model", org=org).json()["id"]  # one model, updated
    bob = actor("bob@b.com")
    org_b = bob.create_org("Org B")
    assert bob.get("/api/v1/cost-model", org=org_b).json() is None
    assert bob.get("/api/v1/cost-model", org=org).status_code == 404


def test_cost_model_validation(team):
    bad = {**MODEL, "pass_through_pct": "250"}
    assert team["admin"].put("/api/v1/cost-model", org=team["org"], json=bad).status_code == 422
    assert team["admin"].put("/api/v1/cost-model", org=team["org"], json={**MODEL, "currency": "XXX"}).status_code == 422


def test_simulator_without_model_or_forecast(team):
    org = team["org"]
    assert team["viewer"].post("/api/v1/simulator", org=org, json={}).status_code == 422
    team["admin"].put("/api/v1/cost-model", org=org, json=MODEL)
    body = team["viewer"].post("/api/v1/simulator", org=org, json={"months": 3}).json()
    assert body["inputs_source"] == "cost_model" and body["forecast_horizon_used"] is None
    assert "No forecast" in body["forecast_note"]
    keys = [s["key"] for s in body["scenarios"]]
    assert keys == ["custom_-10", "custom_10"]
    up = body["scenarios"][1]
    # 10,000 kg/month x 3 months x 2.50 x 10% = 7,500
    assert float(up["period_impact"]) == pytest.approx(7500) and float(up["annualized_impact"]) == pytest.approx(30000)
    assert float(body["target_annual_savings"]) == pytest.approx(24000)
    assert body["market_gap"]["available"] is False  # no benchmark yet


def test_simulator_with_forecast_and_dashboard_exposure(team, db, monkeypatch):
    from app.forecasting import models as registry
    from app.forecasting.pipeline import run_forecast

    monkeypatch.setattr(registry, "MODELS", FAST)
    com = seed_benchmark(db)
    run_forecast(db, com)
    org = team["org"]
    team["admin"].put("/api/v1/cost-model", org=org, json=MODEL)
    body = team["viewer"].post("/api/v1/simulator", org=org, json={"months": 3}).json()
    assert body["forecast_horizon_used"] == 3
    fc = {s["key"]: s for s in body["scenarios"] if s["source"] == "forecast"}
    assert set(fc) == {"downside", "base", "upside"}
    assert float(fc["downside"]["period_impact"]) <= float(fc["base"]["period_impact"]) <= float(fc["upside"]["period_impact"])
    gap = body["market_gap"]
    assert gap["available"] and gap["gap_pct"] is not None and "customs benchmark" in gap["rule"]

    long = team["viewer"].post("/api/v1/simulator", org=org, json={"months": 12}).json()
    assert long["forecast_horizon_used"] == 6 and "applied to the whole 12-month period" in long["forecast_note"]

    dash = team["viewer"].get("/api/v1/dashboard/summary", org=org).json()
    k = {x["key"]: x for x in dash["kpis"]}["estimated_cost_exposure"]
    assert k["status"] == "available" and k["value_kind"] == "calculated" and k["unit"] == "3 months"
    assert float(k["value"]) == pytest.approx(float(fc["base"]["period_impact"]))
    assert len(dash["forecast_points"]) == 3 and len(dash["cost_scenarios"]) == 5
