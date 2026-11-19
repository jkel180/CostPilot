"""Harden privileges: RLS on alembic_version, no automatic grants on future objects.

Supabase grants anon/authenticated full privileges on every new table, sequence and
function in ``public`` by default. That would expose any table a later migration adds
and forgets to protect. This migration:

* enables RLS on ``alembic_version`` and revokes direct access to it;
* removes those default grants for objects created by the migration role, so a new
  table is closed until a migration explicitly grants and adds policies;
* revokes ``anon``'s EXECUTE on ``is_org_member`` (it was granted by the defaults).

No-op on databases other than PostgreSQL.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("anon", "authenticated")


def _existing_roles(bind: sa.Connection) -> list[str]:
    return [
        r for r in ROLES if bind.scalar(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": r})
    ]


def _function_exists(bind: sa.Connection) -> bool:
    return bool(bind.scalar(sa.text("SELECT to_regprocedure('public.is_org_member(uuid)') IS NOT NULL")))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY")
    roles = _existing_roles(bind)
    if not roles:
        return
    targets = ", ".join(roles)
    op.execute(f"REVOKE ALL ON public.alembic_version FROM {targets}")
    for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON {kind} FROM {targets}")
    if "anon" in roles and _function_exists(bind):
        op.execute("REVOKE EXECUTE ON FUNCTION public.is_org_member(uuid) FROM anon")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    roles = _existing_roles(bind)
    if roles:
        targets = ", ".join(roles)
        # Restores Supabase's stock defaults.
        for kind in ("TABLES", "SEQUENCES", "FUNCTIONS"):
            op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON {kind} TO {targets}")
    op.execute("ALTER TABLE public.alembic_version DISABLE ROW LEVEL SECURITY")
