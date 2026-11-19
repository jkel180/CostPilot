"""Organization-level data isolation (MVP acceptance criterion #2)."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import Alert, Commodity, CustomerPurchase


@pytest.fixture
def two_orgs(actor):
    alice, bob = actor("alice@a.com"), actor("bob@b.com")
    return {"alice": alice, "bob": bob, "org_a": alice.create_org("Org A"), "org_b": bob.create_org("Org B")}


@pytest.mark.parametrize(
    "method,url",
    [
        ("get", "/api/v1/organizations/current"),
        ("patch", "/api/v1/organizations/current"),
        ("get", "/api/v1/organizations/current/members"),
        ("post", "/api/v1/organizations/current/members"),
        ("get", "/api/v1/dashboard/summary"),
    ],
)
def test_non_member_gets_404_for_another_org(two_orgs, method, url):
    bob = two_orgs["bob"]
    kwargs = {"json": {"name": "Pwned", "email": "bob@b.com"}} if method in ("patch", "post") else {}
    r = getattr(bob, method)(url, org=two_orgs["org_a"], **kwargs)
    assert r.status_code == 404


def test_unknown_org_id_looks_the_same_as_foreign_org(two_orgs):
    r = two_orgs["bob"].get("/api/v1/organizations/current", org=str(uuid.uuid4()))
    assert r.status_code == 404


def test_admin_cannot_touch_memberships_of_another_org(two_orgs):
    alice, bob = two_orgs["alice"], two_orgs["bob"]
    alice_mid = alice.get("/api/v1/organizations/current/members", org=two_orgs["org_a"]).json()[0]["membership_id"]
    # Bob is admin of org B and addresses Alice's membership through his own org context
    url = f"/api/v1/organizations/current/members/{alice_mid}"
    assert bob.patch(url, org=two_orgs["org_b"], json={"role": "viewer"}).status_code == 404
    assert bob.delete(url, org=two_orgs["org_b"]).status_code == 404


def test_me_lists_only_own_memberships(two_orgs):
    memberships = two_orgs["bob"].get("/api/v1/me").json()["memberships"]
    assert [m["organization_name"] for m in memberships] == ["Org B"]


def test_dashboard_counts_only_own_customer_data(two_orgs, db):
    lemon = db.scalar(select(Commodity))
    org_a = uuid.UUID(two_orgs["org_a"])
    for i in range(3):
        db.add(
            CustomerPurchase(
                organization_id=org_a, commodity_id=lemon.id, supplier="Citrus SA", purchase_date=date(2026, i + 1, 15),
                product_description="Lemon juice concentrate 400 GPL", quantity=Decimal("1000"), unit="kg",
                unit_price=Decimal("3.10"), currency="EUR",
            )
        )
    db.add(Alert(organization_id=org_a, commodity_id=lemon.id, alert_type="pct_change", threshold=Decimal("5")))
    db.commit()

    a = two_orgs["alice"].get("/api/v1/dashboard/summary", org=two_orgs["org_a"]).json()
    b = two_orgs["bob"].get("/api/v1/dashboard/summary", org=two_orgs["org_b"]).json()
    assert (a["data_status"]["customer_purchases"], a["active_alerts"]) == (3, 1)
    assert a["data_status"]["latest_purchase_date"] == "2026-03-15"
    assert (b["data_status"]["customer_purchases"], b["active_alerts"]) == (0, 0)
    assert b["data_status"]["latest_purchase_date"] is None
