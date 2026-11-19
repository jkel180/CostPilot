"""Role-based authorization: admin manages, analyst/viewer cannot."""

import pytest


@pytest.fixture
def team(actor):
    admin, analyst, viewer = actor("admin@acme.com"), actor("analyst@acme.com"), actor("viewer@acme.com")
    for u in (analyst, viewer):
        u.signup()
    org = admin.create_org()
    ids = {}
    for u, role in ((analyst, "analyst"), (viewer, "viewer")):
        r = admin.post("/api/v1/organizations/current/members", org=org, json={"email": u.email, "role": role})
        assert r.status_code == 201, r.text
        ids[role] = r.json()["membership_id"]
    admin_mid = next(
        m["membership_id"]
        for m in admin.get("/api/v1/organizations/current/members", org=org).json()
        if m["role"] == "admin"
    )
    ids["admin"] = admin_mid
    return {"org": org, "admin": admin, "analyst": analyst, "viewer": viewer, "ids": ids}


def test_all_members_can_read_org_and_members(team):
    for who in ("admin", "analyst", "viewer"):
        u = team[who]
        assert u.get("/api/v1/organizations/current", org=team["org"]).json()["role"] == who
        assert len(u.get("/api/v1/organizations/current/members", org=team["org"]).json()) == 3


@pytest.mark.parametrize("who", ["analyst", "viewer"])
def test_non_admins_cannot_manage_organization(team, actor, who):
    u, org = team[who], team["org"]
    outsider = actor("new@acme.com")
    outsider.signup()
    assert u.patch("/api/v1/organizations/current", org=org, json={"name": "Hacked"}).status_code == 403
    assert u.post("/api/v1/organizations/current/members", org=org, json={"email": outsider.email}).status_code == 403
    mid = team["ids"]["viewer"]
    assert u.patch(f"/api/v1/organizations/current/members/{mid}", org=org, json={"role": "admin"}).status_code == 403
    assert u.delete(f"/api/v1/organizations/current/members/{mid}", org=org).status_code == 403


def test_adding_member_requires_existing_account_and_no_duplicates(team):
    admin, org = team["admin"], team["org"]
    r = admin.post("/api/v1/organizations/current/members", org=org, json={"email": "ghost@acme.com"})
    assert r.status_code == 404
    r = admin.post("/api/v1/organizations/current/members", org=org, json={"email": "VIEWER@acme.com"})
    assert r.status_code == 409


def test_admin_changes_role_and_removes_member(team):
    admin, org, ids = team["admin"], team["org"], team["ids"]
    r = admin.patch(f"/api/v1/organizations/current/members/{ids['viewer']}", org=org, json={"role": "analyst"})
    assert r.status_code == 200 and r.json()["role"] == "analyst"
    assert admin.delete(f"/api/v1/organizations/current/members/{ids['viewer']}", org=org).status_code == 204
    # the removed user loses access immediately
    assert team["viewer"].get("/api/v1/organizations/current", org=org).status_code == 404


def test_last_admin_cannot_be_demoted_or_removed(team):
    admin, org, ids = team["admin"], team["org"], team["ids"]
    assert admin.patch(
        f"/api/v1/organizations/current/members/{ids['admin']}", org=org, json={"role": "viewer"}
    ).status_code == 409
    assert admin.delete(f"/api/v1/organizations/current/members/{ids['admin']}", org=org).status_code == 409
    # with a second admin, the first may step down
    admin.patch(f"/api/v1/organizations/current/members/{ids['analyst']}", org=org, json={"role": "admin"})
    assert admin.patch(
        f"/api/v1/organizations/current/members/{ids['admin']}", org=org, json={"role": "viewer"}
    ).status_code == 200
