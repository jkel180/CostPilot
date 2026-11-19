import json
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development", description="development | staging | production")
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/costpilot"

    # Supabase Auth. Tokens are verified with the project's JWKS (asymmetric signing keys);
    # SUPABASE_JWT_SECRET is only needed for projects still on the legacy HS256 secret.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    jwt_audience: str = "authenticated"

    # Accepts a JSON list, a comma-separated list or a single URL.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # CostPilot operators who manage shared market data (sources, ingestion, manual uploads).
    platform_admin_emails: Annotated[list[str], NoDecode] = []
    # Shared secret for scheduled ingestion (e.g. a GitHub Actions cron). Empty disables it.
    ingestion_token: str = ""

    @field_validator("cors_origins", "platform_admin_emails", mode="before")
    @classmethod
    def parse_list(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        v = v.strip()
        if v.startswith("["):
            return json.loads(v)
        # trailing slashes never match a browser Origin header
        return [o.strip().strip("\"'").rstrip("/") for o in v.split(",") if o.strip()]

    def is_platform_admin(self, email: str) -> bool:
        return email.lower() in {e.lower() for e in self.platform_admin_emails}

    @property
    def jwt_issuer(self) -> str | None:
        return f"{self.supabase_url.rstrip('/')}/auth/v1" if self.supabase_url else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
