"""Row Level Security policies and reference data.

Security model
--------------
* The FastAPI backend connects with the database owner role and enforces organization
  isolation in code (every customer query filters on ``organization_id``).
* RLS is the second layer, protecting against direct access through Supabase's
  PostgREST API with the public ``anon`` / ``authenticated`` keys:
    - RLS is enabled on every table; ``anon`` gets no privileges at all.
    - ``authenticated`` users may only SELECT rows of organizations they belong to,
      plus shared reference / market tables. All writes go through the backend.
    - ``audit_logs`` is not readable through PostgREST.
* Policies need Supabase's ``auth.uid()``. On a plain PostgreSQL without the ``auth``
  schema (local development) RLS is still enabled, and the policies are skipped.

Revision ID: 0002
Revises: 0001
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALL_TABLES = (
    "organizations", "users", "memberships",
    "commodities", "product_specs", "data_sources", "market_observations",
    "forecasts", "forecast_backtests",
    "customer_purchases", "cost_models", "alerts", "ai_reports", "audit_logs",
)
REFERENCE_TABLES = (
    "commodities", "product_specs", "data_sources", "market_observations", "forecasts", "forecast_backtests",
)
TENANT_READ_TABLES = ("memberships", "customer_purchases", "cost_models", "alerts", "ai_reports")

LEMON_ID = "6c1b1a52-3f43-4b8e-9d0e-6f3c1d1a0001"


def _role_exists(bind: sa.Connection, role: str) -> bool:
    return bool(bind.scalar(sa.text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}))


def _supabase_auth_available(bind: sa.Connection) -> bool:
    return bool(
        bind.scalar(
            sa.text(
                "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'auth' AND p.proname = 'uid'"
            )
        )
    )


def upgrade() -> None:
    bind = op.get_bind()

    op.bulk_insert(
        sa.table(
            "commodities",
            sa.column("id", sa.Uuid), sa.column("code", sa.String), sa.column("name", sa.String),
            sa.column("category", sa.String), sa.column("default_unit", sa.String),
            sa.column("default_currency", sa.String), sa.column("description", sa.Text),
            sa.column("active", sa.Boolean),
        ),
        [
            {
                "id": uuid.UUID(LEMON_ID),
                "code": "lemon_juice_concentrate",
                "name": "Lemon Juice Concentrate",
                "category": "Fruit juice concentrates",
                "default_unit": "kg",
                "default_currency": "EUR",
                "description": "Concentrated lemon juice (HS 2009.39 sub-headings). Specification "
                "(Brix / GPL acidity, cloudy or clear, origin) must be stated before prices are compared.",
                "active": True,
            }
        ],
    )

    if bind.dialect.name != "postgresql":
        return

    for t in ALL_TABLES:
        op.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY")

    for role in ("anon", "authenticated"):
        if _role_exists(bind, role):
            op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")

    if not (_supabase_auth_available(bind) and _role_exists(bind, "authenticated")):
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.is_org_member(org uuid)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
        AS $$
          SELECT EXISTS (
            SELECT 1 FROM public.memberships m
            WHERE m.organization_id = org AND m.user_id = auth.uid()
          );
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.is_org_member(uuid) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.is_org_member(uuid) TO authenticated")

    op.execute("GRANT SELECT ON public.organizations, public.users TO authenticated")
    op.execute(
        "CREATE POLICY org_member_read ON public.organizations FOR SELECT TO authenticated "
        "USING (public.is_org_member(id))"
    )
    op.execute(
        "CREATE POLICY own_profile_read ON public.users FOR SELECT TO authenticated USING (id = auth.uid())"
    )
    for t in TENANT_READ_TABLES:
        op.execute(f"GRANT SELECT ON public.{t} TO authenticated")
        op.execute(
            f"CREATE POLICY org_member_read ON public.{t} FOR SELECT TO authenticated "
            "USING (public.is_org_member(organization_id))"
        )
    for t in REFERENCE_TABLES:
        op.execute(f"GRANT SELECT ON public.{t} TO authenticated")
        op.execute(f"CREATE POLICY reference_read ON public.{t} FOR SELECT TO authenticated USING (true)")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for t in ALL_TABLES:
            for policy in ("org_member_read", "own_profile_read", "reference_read"):
                op.execute(f"DROP POLICY IF EXISTS {policy} ON public.{t}")
            op.execute(f"ALTER TABLE public.{t} DISABLE ROW LEVEL SECURITY")
        op.execute("DROP FUNCTION IF EXISTS public.is_org_member(uuid)")
    op.execute("DELETE FROM commodities WHERE code = 'lemon_juice_concentrate'")
