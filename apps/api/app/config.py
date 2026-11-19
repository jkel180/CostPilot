from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="development", description="development | staging | production")
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/costpilot"

    # Supabase Auth. Tokens are verified with the project's JWKS (asymmetric signing keys);
    # SUPABASE_JWT_SECRET is only needed for projects still on the legacy HS256 secret.
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    jwt_audience: str = "authenticated"

    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def jwt_issuer(self) -> str | None:
        return f"{self.supabase_url.rstrip('/')}/auth/v1" if self.supabase_url else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
