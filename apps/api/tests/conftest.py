from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import get_db
from app.main import create_app
from app.models import Base, Commodity

TEST_SECRET = "test-secret-at-least-32-bytes-long-for-hs256"


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", database_url="sqlite://", supabase_url="", supabase_jwt_secret=TEST_SECRET)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):  # SQLite does not enforce foreign keys by default
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as s:
        s.add(
            Commodity(
                code="lemon_juice_concentrate", name="Lemon Juice Concentrate",
                category="Fruit juice concentrates", default_unit="kg", default_currency="EUR",
            )
        )
        s.commit()
    yield factory
    engine.dispose()


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as s:
        yield s


@pytest.fixture
def client(settings: Settings, session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def _db() -> Iterator[Session]:
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = _db
    with TestClient(app) as c:
        yield c


def make_token(
    user_id: uuid.UUID,
    email: str,
    *,
    secret: str = TEST_SECRET,
    aud: str = "authenticated",
    expires_in: timedelta = timedelta(hours=1),
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "aud": aud, "iat": now, "exp": now + expires_in, "role": "authenticated"},
        secret,
        algorithm="HS256",
    )


class Actor:
    """A signed-in test user with helpers to call the API."""

    def __init__(self, client: TestClient, email: str) -> None:
        self.client = client
        self.id = uuid.uuid4()
        self.email = email
        self.token = make_token(self.id, email)

    def headers(self, org_id: str | uuid.UUID | None = None) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.token}"}
        if org_id:
            h["X-Organization-Id"] = str(org_id)
        return h

    def get(self, url: str, org: str | None = None, **kw):
        return self.client.get(url, headers=self.headers(org), **kw)

    def post(self, url: str, org: str | None = None, **kw):
        return self.client.post(url, headers=self.headers(org), **kw)

    def patch(self, url: str, org: str | None = None, **kw):
        return self.client.patch(url, headers=self.headers(org), **kw)

    def delete(self, url: str, org: str | None = None, **kw):
        return self.client.delete(url, headers=self.headers(org), **kw)

    def signup(self) -> None:
        assert self.get("/api/v1/me").status_code == 200

    def create_org(self, name: str = "Acme Beverages", **extra) -> str:
        r = self.post("/api/v1/organizations", json={"name": name, "country": "IT", "currency": "EUR", **extra})
        assert r.status_code == 201, r.text
        return r.json()["id"]


@pytest.fixture
def actor(client: TestClient) -> Callable[[str], Actor]:
    return lambda email: Actor(client, email)
