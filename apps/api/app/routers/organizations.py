"""Organization registration, profile and member management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app import audit
from app.deps import AdminCtx, CurrentUser, DbSession, OrgCtx
from app.models import Membership, Organization, Role, User
from app.schemas import (
    MemberAdd,
    MemberOut,
    MemberRoleUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
    OrganizationWithRole,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _member_out(m: Membership) -> MemberOut:
    return MemberOut(
        membership_id=m.id,
        user_id=m.user_id,
        email=m.user.email,
        full_name=m.user.full_name,
        role=m.role,
        joined_at=m.created_at,
    )


@router.post("", response_model=OrganizationWithRole, status_code=status.HTTP_201_CREATED)
def create_organization(payload: OrganizationCreate, db: DbSession, user: CurrentUser) -> OrganizationWithRole:
    """Register a new organization; the caller becomes its first admin."""
    org = Organization(**payload.model_dump(), created_by=user.id)
    db.add(org)
    db.flush()
    db.add(Membership(organization_id=org.id, user_id=user.id, role=Role.admin, created_by=user.id))
    audit.record(
        db, action="organization.created", entity_type="organization", entity_id=org.id,
        user_id=user.id, organization_id=org.id, details={"name": org.name},
    )
    db.commit()
    db.refresh(org)
    return OrganizationWithRole(**OrganizationOut.model_validate(org).model_dump(), role=Role.admin)


@router.get("/current", response_model=OrganizationWithRole)
def get_current_organization(ctx: OrgCtx) -> OrganizationWithRole:
    return OrganizationWithRole(**OrganizationOut.model_validate(ctx.organization).model_dump(), role=ctx.role)


@router.patch("/current", response_model=OrganizationOut)
def update_current_organization(payload: OrganizationUpdate, ctx: AdminCtx, db: DbSession) -> Organization:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    org = ctx.organization
    for field, value in changes.items():
        setattr(org, field, value)
    audit.record(
        db, action="organization.updated", entity_type="organization", entity_id=org.id,
        user_id=ctx.user.id, organization_id=org.id, details={"fields": sorted(changes)},
    )
    db.commit()
    db.refresh(org)
    return org


@router.get("/current/members", response_model=list[MemberOut])
def list_members(ctx: OrgCtx, db: DbSession) -> list[MemberOut]:
    members = db.scalars(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.organization_id == ctx.organization.id)
        .order_by(User.email)
    ).all()
    return [_member_out(m) for m in members]


@router.post("/current/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(payload: MemberAdd, ctx: AdminCtx, db: DbSession) -> MemberOut:
    """Add an existing CostPilot user (they must have signed up) to this organization."""
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No CostPilot account with this email. Ask the person to sign up first, then add them.",
        )
    exists = db.scalar(
        select(Membership).where(
            Membership.organization_id == ctx.organization.id, Membership.user_id == user.id
        )
    )
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This user is already a member")
    membership = Membership(
        organization_id=ctx.organization.id, user_id=user.id, role=payload.role, created_by=ctx.user.id
    )
    db.add(membership)
    db.flush()
    audit.record(
        db, action="member.added", entity_type="membership", entity_id=membership.id,
        user_id=ctx.user.id, organization_id=ctx.organization.id,
        details={"member_user_id": str(user.id), "role": payload.role.value},
    )
    db.commit()
    db.refresh(membership)
    return _member_out(membership)


def _get_membership(db: DbSession, ctx: AdminCtx, membership_id: uuid.UUID) -> Membership:
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id, Membership.organization_id == ctx.organization.id
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return membership


def _admin_count(db: DbSession, organization_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == organization_id, Membership.role == Role.admin)
    ) or 0


@router.patch("/current/members/{membership_id}", response_model=MemberOut)
def update_member_role(
    membership_id: uuid.UUID, payload: MemberRoleUpdate, ctx: AdminCtx, db: DbSession
) -> MemberOut:
    membership = _get_membership(db, ctx, membership_id)
    if (
        membership.role == Role.admin
        and payload.role != Role.admin
        and _admin_count(db, ctx.organization.id) <= 1
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "An organization must keep at least one admin")
    previous = membership.role
    membership.role = payload.role
    audit.record(
        db, action="member.role_changed", entity_type="membership", entity_id=membership.id,
        user_id=ctx.user.id, organization_id=ctx.organization.id,
        details={"from": previous.value, "to": payload.role.value},
    )
    db.commit()
    db.refresh(membership)
    return _member_out(membership)


@router.delete("/current/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(membership_id: uuid.UUID, ctx: AdminCtx, db: DbSession) -> None:
    membership = _get_membership(db, ctx, membership_id)
    if membership.role == Role.admin and _admin_count(db, ctx.organization.id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "An organization must keep at least one admin")
    audit.record(
        db, action="member.removed", entity_type="membership", entity_id=membership.id,
        user_id=ctx.user.id, organization_id=ctx.organization.id,
        details={"member_user_id": str(membership.user_id)},
    )
    db.delete(membership)
    db.commit()
