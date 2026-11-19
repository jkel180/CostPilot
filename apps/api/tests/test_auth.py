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


def test_first_call_provisions_user_profile(actor):
    alice = actor("Alice@Example.com")
    r = alice.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["id"] == str(alice.id)
    assert body["user"]["email"] == "alice@example.com"
    assert body["memberships"] == []
