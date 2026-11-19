def test_dashboard_skeleton_never_fabricates_values(actor):
    alice = actor("alice@example.com")
    org = alice.create_org()
    r = alice.get("/api/v1/dashboard/summary", org=org)
    assert r.status_code == 200
    body = r.json()
    assert body["commodity"]["code"] == "lemon_juice_concentrate"
    assert [k["key"] for k in body["kpis"]] == [
        "current_market_benchmark",
        "monthly_price_change",
        "forecast_3m",
        "forecast_6m",
        "customer_avg_purchase_price",
        "estimated_cost_exposure",
    ]
    for kpi in body["kpis"]:
        assert kpi["status"] == "not_available"
        assert kpi["value"] is None
        assert kpi["reason"]
    assert body["data_status"]["market_observations"] == 0
    assert body["data_status"]["synthetic_data_present"] is False


def test_dashboard_unknown_commodity(actor):
    alice = actor("alice@example.com")
    org = alice.create_org()
    assert alice.get("/api/v1/dashboard/summary?commodity=coffee", org=org).status_code == 404
