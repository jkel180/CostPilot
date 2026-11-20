"""Forecast runs and cost model fields (Sprint 3).

* ``forecast_runs``: one row per pipeline execution (inputs hash, versions, settings).
* ``forecasts`` / ``forecast_backtests`` link to their run; backtests record whether
  the model is a baseline and whether it was selected.
* ``cost_models``: pass-through and cost-share assumptions, one model per
  organization and commodity.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "forecast_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("commodity_id", sa.Uuid(), nullable=False),
        sa.Column("product_spec_id", sa.Uuid(), nullable=True),
        sa.Column("series_geography", sa.String(length=100), nullable=False),
        sa.Column("series_data_type", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("input_data_version", sa.String(length=64), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=False),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("first_date", sa.Date(), nullable=True),
        sa.Column("last_date", sa.Date(), nullable=True),
        sa.Column("last_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("settings", JSON, nullable=False),
        sa.Column("notes", JSON, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_spec_id"], ["product_specs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecast_run_commodity_generated", "forecast_runs", ["commodity_id", "generated_at"])

    with op.batch_alter_table("forecasts") as b:
        b.add_column(sa.Column("run_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("interval_level", sa.Numeric(4, 2), nullable=True))
        b.create_foreign_key("fk_forecasts_run_id", "forecast_runs", ["run_id"], ["id"], ondelete="CASCADE")
        b.create_index("ix_forecasts_run_id", ["run_id"])

    with op.batch_alter_table("forecast_backtests") as b:
        b.add_column(sa.Column("run_id", sa.Uuid(), nullable=True))
        b.add_column(sa.Column("n_origins", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("is_baseline", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.create_foreign_key("fk_forecast_backtests_run_id", "forecast_runs", ["run_id"], ["id"], ondelete="CASCADE")
        b.create_index("ix_forecast_backtests_run_id", ["run_id"])

    with op.batch_alter_table("cost_models") as b:
        b.add_column(sa.Column("pass_through_pct", sa.Numeric(6, 2), nullable=False, server_default="100"))
        b.add_column(sa.Column("commodity_cost_share_pct", sa.Numeric(6, 2), nullable=True))
        b.drop_index("ix_cost_model_org")
        b.create_check_constraint("ck_cost_model_price", "current_purchase_price >= 0")
        b.create_check_constraint("ck_cost_model_pass_through", "pass_through_pct >= 0 AND pass_through_pct <= 200")
        b.create_unique_constraint("uq_cost_model_org_commodity", ["organization_id", "commodity_id"])

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE public.forecast_runs ENABLE ROW LEVEL SECURITY")
    has_auth = bind.scalar(
        sa.text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'auth' AND p.proname = 'uid'"
        )
    ) and bind.scalar(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'authenticated'"))
    if has_auth:
        op.execute("GRANT SELECT ON public.forecast_runs TO authenticated")
        op.execute("CREATE POLICY reference_read ON public.forecast_runs FOR SELECT TO authenticated USING (true)")


def downgrade() -> None:
    with op.batch_alter_table("cost_models") as b:
        b.drop_constraint("uq_cost_model_org_commodity", type_="unique")
        b.drop_constraint("ck_cost_model_pass_through", type_="check")
        b.drop_constraint("ck_cost_model_price", type_="check")
        b.create_index("ix_cost_model_org", ["organization_id", "commodity_id"])
        b.drop_column("commodity_cost_share_pct")
        b.drop_column("pass_through_pct")
    with op.batch_alter_table("forecast_backtests") as b:
        b.drop_index("ix_forecast_backtests_run_id")
        b.drop_constraint("fk_forecast_backtests_run_id", type_="foreignkey")
        b.drop_column("selected")
        b.drop_column("is_baseline")
        b.drop_column("n_origins")
        b.drop_column("run_id")
    with op.batch_alter_table("forecasts") as b:
        b.drop_index("ix_forecasts_run_id")
        b.drop_constraint("fk_forecasts_run_id", type_="foreignkey")
        b.drop_column("interval_level")
        b.drop_column("run_id")
    op.drop_index("ix_forecast_run_commodity_generated", table_name="forecast_runs")
    op.drop_table("forecast_runs")
