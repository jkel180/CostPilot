from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Commodity
from app.schemas import CommodityOut

router = APIRouter(prefix="/commodities", tags=["commodities"])


@router.get("", response_model=list[CommodityOut])
def list_commodities(_: CurrentUser, db: DbSession) -> list[Commodity]:
    return list(db.scalars(select(Commodity).where(Commodity.active.is_(True)).order_by(Commodity.name)))
