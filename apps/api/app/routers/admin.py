"""Platform administration of shared market data.

Only CostPilot operators (``PLATFORM_ADMIN_EMAILS``) may run connectors or upload market
observations; customers never write to shared tables. A scheduler can trigger the
API connectors with the ``X-Ingestion-Token`` header instead of a user session.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import select

from app import audit
from app.config import Settings, get_settings
from app.db import get_session_factory
from app.deps import DbSession, PlatformAdmin
from app.ingestion import CONNECTORS, ManualCsvConnector
from app.ingestion.base import run_connector
from app.models import IngestionRun, ProductSpec, RunStatus
from app.routers.forecasts import schedule_forecast
from app.routers.market import get_commodity
from app.routers.purchases import _read_upload
from app.schemas import IngestionRunOut

router = APIRouter(prefix="/admin", tags=["admin"])


def _run_response(db: DbSession, run: IngestionRun) -> IngestionRun:
    if run.status == RunStatus.failed:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Ingestion failed: {run.error}")
    return run


SessionFactory = Annotated[object, Depends(get_session_factory)]


@router.post("/ingestion/{connector}", response_model=IngestionRunOut)
def trigger_connector(connector: str, admin: PlatformAdmin, db: DbSession, background: BackgroundTasks,
                      session_factory: SessionFactory,
                      commodity: str = Query("lemon_juice_concentrate", max_length=64)) -> IngestionRun:
    """Run a connector; on success the forecast is refreshed in the background."""
    cls = CONNECTORS.get(connector)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown connector. Available: {sorted(CONNECTORS)}")
    com = get_commodity(db, commodity)
    run = run_connector(db, cls(com), triggered_by=admin.id)
    if run.status == RunStatus.success:
        schedule_forecast(db, com, background, session_factory, admin.id)
    audit.record(db, action="ingestion.run", entity_type="ingestion_run", entity_id=run.id, user_id=admin.id,
                 organization_id=None, details={"connector": connector, "status": run.status.value})
    db.commit()
    return _run_response(db, run)


@router.post("/scheduled-ingestion/{connector}", response_model=IngestionRunOut)
def scheduled_connector(
    connector: str,
    db: DbSession,
    background: BackgroundTasks,
    session_factory: SessionFactory,
    settings: Annotated[Settings, Depends(get_settings)],
    x_ingestion_token: Annotated[str | None, Header()] = None,
    commodity: str = Query("lemon_juice_concentrate", max_length=64),
) -> IngestionRun:
    if not settings.ingestion_token or not x_ingestion_token or not hmac.compare_digest(
        settings.ingestion_token, x_ingestion_token
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid ingestion token")
    cls = CONNECTORS.get(connector)
    if cls is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown connector")
    com = get_commodity(db, commodity)
    run = run_connector(db, cls(com))
    if run.status == RunStatus.success:
        schedule_forecast(db, com, background, session_factory)
    return _run_response(db, run)


@router.post("/market-observations/upload", response_model=IngestionRunOut)
async def upload_market_csv(
    admin: PlatformAdmin,
    db: DbSession,
    file: UploadFile = File(...),
    original_source: str = Form(..., min_length=3, max_length=300),
    commodity: str = Form("lemon_juice_concentrate"),
    product_spec: str | None = Form(None, max_length=200),
) -> IngestionRun:
    com = get_commodity(db, commodity)
    spec_id = None
    if product_spec:
        spec_id = db.scalar(
            select(ProductSpec.id).where(ProductSpec.commodity_id == com.id, ProductSpec.specification_name == product_spec)
        )
        if spec_id is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Product specification not found")
    content = await _read_upload(file)
    try:
        connector = ManualCsvConnector(com, {"content": content, "original_source": original_source,
                                             "filename": file.filename, "product_spec_id": spec_id})
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    run = run_connector(db, connector, triggered_by=admin.id)
    if run.status == RunStatus.failed:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, run.error or "Upload failed")
    return run


@router.get("/ingestion-runs", response_model=list[IngestionRunOut])
def list_runs(_: PlatformAdmin, db: DbSession, limit: int = Query(20, ge=1, le=100)) -> list[IngestionRun]:
    return list(db.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)))
