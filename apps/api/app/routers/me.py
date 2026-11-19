from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Membership, Organization
from app.schemas import MembershipSummary, MeOut, UserOut

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeOut)
def read_me(user: CurrentUser, db: DbSession) -> MeOut:
    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.name)
    ).all()
    return MeOut(
        user=UserOut.model_validate(user),
        memberships=[
            MembershipSummary(organization_id=o.id, organization_name=o.name, role=m.role) for m, o in rows
        ],
    )
