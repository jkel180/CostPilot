import uuid
from datetime import timedelta

from tests.conftest import make_token


def test_health_is_public(client):
    assert client.get("/health").json()["status"] == "ok"


def test_missing_token_is_rejected(client):
    assert client.get("/api/v1/me").status_code == 401


def test_token_with_wrong_signature_is_rejected(client):
    token = make_token(uuid.uuid4(), "a@example.com", secret="another-secret-that-is-long-enough-xx")
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_token_is_rejected(client):
    token = make_token(uuid.uuid4(), "a@example.com", expires_in=timedelta(seconds=-10))
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_for_wrong_audience_is_rejected(client):
    token = make_token(uuid.uuid4(), "a@example.com", aud="anon")
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_unsigned_token_is_rejected(client):
    import jwt

    token = jwt.encode({"sub": str(uuid.uuid4()), "email": "a@example.com", "aud": "authenticated"}, None, algorithm="none")
    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_concurrent_first_calls_do_not_fail(actor, session_factory, monkeypatch):
    """Two parallel first requests: the second insert hits the PK and must still return 200."""
    from sqlalchemy.orm import Session

    from app.models import User

    alice = actor("alice@example.com")
    # Another request has already created the profile...
    with session_factory() as s:
        s.add(User(id=alice.id, email=alice.email))
        s.commit()
    # ...but this request looked before that happened.
    real_get = Session.get
    calls = {"n": 0}

    def stale_first_get(self, entity, ident, *a, **kw):
        calls["n"] += 1
        if entity is User and calls["n"] == 1:
            return None
        return real_get(self, entity, ident, *a, **kw)

    monkeypatch.setattr(Session, "get", stale_first_get)
    r = alice.get("/api/v1/me")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["id"] == str(alice.id)


def test_email_reused_by_new_auth_account_gets_conflict(actor):
    actor("bob@example.com").signup()
    bob_again = actor("bob@example.com")  # same email, new Supabase user id
    assert bob_again.get("/api/v1/me").status_code == 409


def test_first_call_provisions_user_profile(actor):
    alice = actor("Alice@Example.com")
    r = alice.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["id"] == str(alice.id)
    assert body["user"]["email"] == "alice@example.com"
    assert body["memberships"] == []
