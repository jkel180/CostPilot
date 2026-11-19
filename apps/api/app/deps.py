"""FastAPI dependencies: authentication, organization context and role checks.

Every endpoint that touches customer data depends on :func:`get_org_context`, which
resolves the organization from the ``X-Organization-Id`` header and verifies that the
caller is a member. Queries must then filter on ``ctx.organization.id``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthError, verify_access_token
from app.config import Settings, get_settings
from app.db import get_db
from app.models import Membership, Organization, Role, User

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        token_user = verify_access_token(credentials.credentials, settings)
    except AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    # Provision the application profile on first sight of a Supabase user.
    now = datetime.now(UTC)
    user = db.get(User, token_user.id)
    if user is None:
        db.add(User(id=token_user.id, email=token_user.email, last_seen_at=now))
        try:
            db.commit()
        except IntegrityError:
            # A parallel request (e.g. two calls on first page load) created it first.
            db.rollback()
        user = db.get(User, token_user.id)
        if user is None:
            # The email belongs to a different auth id (account deleted and re-created in Supabase).
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This email is linked to another CostPilot profile. Contact your administrator.",
            )
        return user

    user.email = token_user.email
    user.last_seen_at = now
    db.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True)
class OrgContext:
    user: User
    organization: Organization
    membership: Membership

    @property
    def role(self) -> Role:
        return self.membership.role


def get_org_context(
    db: DbSession,
    user: CurrentUser,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> OrgContext:
    if not x_organization_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organization-Id header is required")
    try:
        org_id = uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Organization-Id is not a valid id") from exc

    membership = db.scalar(
        select(Membership).where(Membership.organization_id == org_id, Membership.user_id == user.id)
    )
    # 404 rather than 403: do not reveal whether another organization exists.
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    return OrgContext(user=user, organization=membership.organization, membership=membership)


OrgCtx = Annotated[OrgContext, Depends(get_org_context)]


def require_role(*roles: Role) -> Callable[[OrgContext], OrgContext]:
    allowed = set(roles)

    def checker(ctx: OrgCtx) -> OrgContext:
        if ctx.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role for this action")
        return ctx

    return checker


AdminCtx = Annotated[OrgContext, Depends(require_role(Role.admin))]
EditorCtx = Annotated[OrgContext, Depends(require_role(Role.admin, Role.analyst))]
