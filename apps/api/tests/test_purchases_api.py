import json

import pytest

GOOD = (
    "Data;Fornitore;Descrizione;Quantità;UM;Prezzo unitario;Valuta\n"
    "15/01/2026;Citrus SA;LJC 400 GPL;1000;kg;3,00;EUR\n"
    "20/02/2026;Citrus SA;LJC 400 GPL;3000;kg;2,00;EUR\n"
    "05/03/2026;Agrumi Srl;LJC 400 GPL;500;kg;2,80;EUR\n"
).encode()
WITH_ERROR = GOOD + b"bad-date;X;LJC;10;kg;3;EUR\n"


def upload(user, org, content=GOOD, path="/api/v1/purchases/imports", **data):
    return user.post(path, org=org, files={"file": ("acquisti.csv", content, "text/csv")}, data=data)


@pytest.fixture
def team(actor):
    admin, analyst, viewer = actor("admin@a.com"), actor("analyst@a.com"), actor("viewer@a.com")
    for u in (analyst, viewer):
        u.signup()
    org = admin.create_org("Org A")
    for u, role in ((analyst, "analyst"), (viewer, "viewer")):
        admin.post("/api/v1/organizations/current/members", org=org, json={"email": u.email, "role": role})
    return {"org": org, "admin": admin, "analyst": analyst, "viewer": viewer}


def test_preview_stores_nothing(team):
    r = upload(team["analyst"], team["org"], path="/api/v1/purchases/imports/preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["rows_total"], body["rows_valid"], body["rows_invalid"], body["delimiter"]) == (3, 3, 0, ";")
    assert body["mapping"]["supplier"] == "Fornitore"
    assert team["analyst"].get("/api/v1/purchases", org=team["org"]).json()["total"] == 0


def test_commit_and_wapp_by_supplier(team):
    r = upload(team["analyst"], team["org"])
    assert r.status_code == 201, r.text
    assert r.json()["rows_imported"] == 3
    listing = team["viewer"].get("/api/v1/purchases", org=team["org"]).json()
    assert listing["total"] == 3 and listing["items"][0]["purchase_date"] == "2026-03-05"

    a = team["viewer"].get("/api/v1/purchases/analysis", org=team["org"]).json()
    by_sup = {g["key"]: g for g in a["by_supplier"]}
    # (1000*3 + 3000*2) / 4000 = 2.25
    assert float(by_sup["Citrus SA"]["weighted_avg_price"]) == pytest.approx(2.25)
    assert float(by_sup["Citrus SA"]["total_quantity"]) == 4000
    # overall: (3000 + 6000 + 1400) / 4500
    assert float(a["overall"][0]["weighted_avg_price"]) == pytest.approx(10400 / 4500)
    assert [g["key"] for g in a["by_month"]] == ["2026-01", "2026-02", "2026-03"]


def test_rows_with_errors_block_import_unless_skipped(team):
    r = upload(team["analyst"], team["org"], WITH_ERROR)
    assert r.status_code == 422 and "1 rows have errors" in r.json()["detail"]
    r = upload(team["analyst"], team["org"], WITH_ERROR, skip_invalid="true")
    assert r.status_code == 201
    assert (r.json()["rows_imported"], r.json()["rows_skipped"]) == (3, 1)


def test_custom_mapping(team):
    content = b"when,who,what,how_much,uom,cost,ccy\n2026-01-01,A,LJC,10,kg,3,EUR\n"
    r = upload(team["analyst"], team["org"], content, path="/api/v1/purchases/imports/preview")
    assert r.json()["mapping_errors"]
    mapping = {"purchase_date": "when", "supplier": "who", "product_description": "what", "quantity": "how_much",
               "unit": "uom", "unit_price": "cost", "currency": "ccy"}
    r = upload(team["analyst"], team["org"], content, mapping=json.dumps(mapping))
    assert r.status_code == 201, r.text


def test_viewer_cannot_import_or_delete(team):
    assert upload(team["viewer"], team["org"]).status_code == 403
    imp = upload(team["admin"], team["org"]).json()
    assert team["viewer"].delete(f"/api/v1/purchases/imports/{imp['id']}", org=team["org"]).status_code == 403


def test_delete_import_removes_its_purchases(team):
    imp = upload(team["analyst"], team["org"]).json()
    assert team["analyst"].delete(f"/api/v1/purchases/imports/{imp['id']}", org=team["org"]).status_code == 204
    assert team["analyst"].get("/api/v1/purchases", org=team["org"]).json()["total"] == 0
    assert team["analyst"].get("/api/v1/purchases/imports", org=team["org"]).json() == []


def test_purchases_are_isolated_between_organizations(team, actor):
    imp = upload(team["admin"], team["org"]).json()
    bob = actor("bob@b.com")
    org_b = bob.create_org("Org B")
    assert bob.get("/api/v1/purchases", org=org_b).json()["total"] == 0
    assert bob.get("/api/v1/purchases/analysis", org=org_b).json()["overall"] == []
    assert bob.get("/api/v1/purchases/imports", org=org_b).json() == []
    # cannot reach org A's data through org A's id, nor delete A's import through org B
    assert bob.get("/api/v1/purchases", org=team["org"]).status_code == 404
    assert bob.delete(f"/api/v1/purchases/imports/{imp['id']}", org=org_b).status_code == 404
    assert team["admin"].get("/api/v1/purchases", org=team["org"]).json()["total"] == 3


def test_rejects_non_csv_upload(team):
    r = team["analyst"].post(
        "/api/v1/purchases/imports/preview", org=team["org"],
        files={"file": ("data.xlsx", b"PK\x03\x04", "application/octet-stream")},
    )
    assert r.status_code == 415


def test_dashboard_shows_customer_wapp(team):
    from datetime import date, timedelta

    d1 = (date.today() - timedelta(days=30)).strftime("%d/%m/%Y")
    d2 = (date.today() - timedelta(days=60)).strftime("%d/%m/%Y")
    content = f"Data;Fornitore;Descrizione;Quantità;UM;Prezzo;Valuta\n{d1};A;LJC;1000;kg;3;EUR\n{d2};B;LJC;3000;kg;2;EUR\n"
    upload(team["admin"], team["org"], content.encode())
    kpis = {k["key"]: k for k in team["viewer"].get("/api/v1/dashboard/summary", org=team["org"]).json()["kpis"]}
    k = kpis["customer_avg_purchase_price"]
    assert k["status"] == "available" and float(k["value"]) == pytest.approx(2.25)
    assert (k["unit"], k["currency"], k["value_kind"]) == ("kg", "EUR", "calculated")
