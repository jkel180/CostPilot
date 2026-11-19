import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None,
    user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None,
    details: dict[str, Any] | None = None,
) -> None:
    """Add an audit entry to the current transaction. Never put purchase data in ``details``."""
    db.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            user_id=user_id,
            organization_id=organization_id,
            details=details or {},
        )
    )
