import pytest
from sqlalchemy import select

from app.models import AuditLog


def test_registering_an_organization_makes_the_caller_admin(actor, db):
    alice = actor("alice@example.com")
    r = alice.post("/api/v1/organizations", json={"name": "  Agrumi Srl ", "country": "it", "currency": "eur"})
    assert r.status_code == 201, r.text
    org = r.json()
    assert (org["name"], org["country"], org["currency"], org["role"]) == ("Agrumi Srl", "IT", "EUR", "admin")

    me = alice.get("/api/v1/me").json()
    assert me["memberships"] == [{"organization_id": org["id"], "organization_name": "Agrumi Srl", "role": "admin"}]

    actions = db.scalars(select(AuditLog.action)).all()
    assert "organization.created" in actions


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "X"},
        {"name": "Valid", "currency": "XYZ"},
        {"name": "Valid", "country": "ITA"},
        {"name": "Valid", "country": "1T"},
    ],
)
def test_invalid_organization_payloads_are_rejected(actor, payload):
    assert actor("a@example.com").post("/api/v1/organizations", json=payload).status_code == 422


def test_user_can_belong_to_several_organizations(actor):
    alice = actor("alice@example.com")
    a = alice.create_org("Beta Foods")
    b = alice.create_org("Alpha Drinks")
    names = [m["organization_name"] for m in alice.get("/api/v1/me").json()["memberships"]]
    assert names == ["Alpha Drinks", "Beta Foods"]
    assert alice.get("/api/v1/organizations/current", org=a).json()["name"] == "Beta Foods"
    assert alice.get("/api/v1/organizations/current", org=b).json()["name"] == "Alpha Drinks"


def test_org_context_header_is_required_and_validated(actor):
    alice = actor("alice@example.com")
    alice.create_org()
    assert alice.get("/api/v1/organizations/current").status_code == 400
    assert alice.get("/api/v1/organizations/current", org="not-a-uuid").status_code == 400


def test_admin_can_update_profile(actor):
    alice = actor("alice@example.com")
    org = alice.create_org()
    r = alice.patch("/api/v1/organizations/current", org=org, json={"name": "Acme Italia", "currency": "usd"})
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["currency"], r.json()["country"]) == ("Acme Italia", "USD", "IT")


def test_commodities_list_includes_lemon_concentrate(actor):
    codes = [c["code"] for c in actor("a@example.com").get("/api/v1/commodities").json()]
    assert codes == ["lemon_juice_concentrate"]
