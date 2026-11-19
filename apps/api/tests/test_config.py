import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('["https://a.vercel.app", "http://localhost:3000"]', ["https://a.vercel.app", "http://localhost:3000"]),
        ("https://a.vercel.app", ["https://a.vercel.app"]),
        ("https://a.vercel.app/", ["https://a.vercel.app"]),
        ("https://a.vercel.app, http://localhost:3000", ["https://a.vercel.app", "http://localhost:3000"]),
        ('"https://a.vercel.app"', ["https://a.vercel.app"]),
    ],
)
def test_cors_origins_formats(monkeypatch, raw, expected):
    monkeypatch.setenv("CORS_ORIGINS", raw)
    assert Settings(_env_file=None).cors_origins == expected
