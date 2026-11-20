"""Forecasts: read for any signed-in user; runs are started by platform admins or after ingestion."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app import audit
from app.db import get_session_factory
from app.deps import CurrentUser, DbSession, PlatformAdmin
from app.forecasting import run_forecast_in_background, start_run
from app.forecasting.read import bundle, is_running
from app.routers.market import get_commodity
from app.schemas import ForecastBundle, ForecastRunOut

router = APIRouter(tags=["forecasts"])


@router.get("/forecasts/latest", response_model=ForecastBundle)
def latest(_: CurrentUser, db: DbSession, commodity: str = Query("lemon_juice_concentrate", max_length=64)) -> ForecastBundle:
    return bundle(db, get_commodity(db, commodity))


def schedule_forecast(db, commodity, background: BackgroundTasks, session_factory, triggered_by=None):
    """Start a run (unless one is already in progress) and complete it after the response."""
    if is_running(db, commodity):
        return None
    run = start_run(db, commodity, triggered_by)
    background.add_task(run_forecast_in_background, run.id, session_factory)
    return run


@router.post("/admin/forecasts/run", response_model=ForecastRunOut, status_code=status.HTTP_202_ACCEPTED)
def trigger(
    admin: PlatformAdmin,
    db: DbSession,
    background: BackgroundTasks,
    session_factory: Annotated[object, Depends(get_session_factory)],
    commodity: str = Query("lemon_juice_concentrate", max_length=64),
):
    com = get_commodity(db, commodity)
    run = schedule_forecast(db, com, background, session_factory, admin.id)
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A forecast run is already in progress")
    audit.record(db, action="forecast.run", entity_type="forecast_run", entity_id=run.id, user_id=admin.id,
                 organization_id=None, details={})
    db.commit()
    return run
