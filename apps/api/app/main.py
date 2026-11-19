from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import admin, commodities, dashboard, market, me, organizations, purchases


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CostPilot AI API",
        version="0.1.0",
        # Interactive docs only outside production.
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.environment == "production" else "/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Organization-Id"],
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str | int | bool]:
        # configuration presence only (counts/flags), never values
        return {
            "status": "ok",
            "environment": settings.environment,
            "platform_admins_configured": len(settings.platform_admin_emails),
            "scheduled_ingestion_enabled": bool(settings.ingestion_token),
        }

    for r in (me.router, organizations.router, commodities.router, dashboard.router, market.router,
              purchases.router, admin.router):
        app.include_router(r, prefix="/api/v1")
    return app


app = create_app()
