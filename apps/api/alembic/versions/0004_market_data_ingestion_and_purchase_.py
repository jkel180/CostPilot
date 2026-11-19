"""Market data ingestion and purchase imports (Sprint 2).

* ``ingestion_runs``: execution log of every connector run.
* ``purchase_imports``: one row per customer CSV upload; purchases reference it.
* ``market_observations`` gains provenance fields (quality note, source attributes,
  ingestion run).
* Reference data: Eurostat Comext and manual-upload sources, and the product
  specification matching the Comext benchmark code.
* RLS on the new tables (0003 removed automatic grants, so access is explicit).

Revision ID: 0004
Revises: 0003
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

LEMON_ID = uuid.UUID("6c1b1a52-3f43-4b8e-9d0e-6f3c1d1a0001")
COMEXT_SOURCE_ID = uuid.UUID("6c1b1a52-3f43-4b8e-9d0e-6f3c1d1a0101")
MANUAL_SOURCE_ID = uuid.UUID("6c1b1a52-3f43-4b8e-9d0e-6f3c1d1a0102")
SPEC_CN_20093939_ID = uuid.UUID("6c1b1a52-3f43-4b8e-9d0e-6f3c1d1a0201")


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("commodity_id", sa.Uuid(), nullable=False),
        sa.Column("connector", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "success", "failed", name="run_status", native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_fetched", sa.Integer(), nullable=False),
        sa.Column("rows_saved", sa.Integer(), nullable=False),
        sa.Column("rows_rejected", sa.Integer(), nullable=False),
        sa.Column("parameters", JSON, nullable=False),
        sa.Column("data_version", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingestion_run_source_started", "ingestion_runs", ["source_id", "started_at"])

    op.create_table(
        "purchase_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("commodity_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("rows_total", sa.Integer(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("rows_skipped", sa.Integer(), nullable=False),
        sa.Column("column_mapping", JSON, nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["commodity_id"], ["commodities.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_import_org_created", "purchase_imports", ["organization_id", "created_at"])

    with op.batch_alter_table("customer_purchases") as batch_op:
        batch_op.create_foreign_key(
            "fk_customer_purchases_import_batch_id", "purchase_imports", ["import_batch_id"], ["id"], ondelete="CASCADE"
        )

    with op.batch_alter_table("market_observations") as batch_op:
        batch_op.add_column(sa.Column("quality_note", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("attributes", JSON, nullable=False, server_default=sa.text("'{}'")))
        batch_op.add_column(sa.Column("ingestion_run_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_market_observations_ingestion_run_id", "ingestion_runs", ["ingestion_run_id"], ["id"], ondelete="SET NULL"
        )

    # ---- reference data
    sources = sa.table(
        "data_sources",
        sa.column("id", sa.Uuid), sa.column("name", sa.String), sa.column("source_type", sa.String),
        sa.column("source_url", sa.String), sa.column("license_reference", sa.Text),
        sa.column("update_frequency", sa.String), sa.column("active", sa.Boolean), sa.column("is_synthetic", sa.Boolean),
    )
    op.bulk_insert(
        sources,
        [
            {
                "id": COMEXT_SOURCE_ID,
                "name": "Eurostat Comext (DS-045409)",
                "source_type": "official_statistics",
                "source_url": "https://ec.europa.eu/eurostat/comext/newxtweb/",
                "license_reference": "© European Union, Eurostat. Reuse authorised with acknowledgement of the source "
                "(Commission Decision 2011/833/EU).",
                "update_frequency": "monthly",
                "active": True,
                "is_synthetic": False,
            },
            {
                "id": MANUAL_SOURCE_ID,
                "name": "Manual upload",
                "source_type": "manual_upload",
                "source_url": None,
                "license_reference": "Uploaded by a CostPilot platform administrator; the file's own licence applies.",
                "update_frequency": "ad hoc",
                "active": True,
                "is_synthetic": False,
            },
        ],
    )
    specs = sa.table(
        "product_specs",
        sa.column("id", sa.Uuid), sa.column("commodity_id", sa.Uuid), sa.column("specification_name", sa.String),
        sa.column("brix", sa.Numeric), sa.column("origin", sa.String), sa.column("quality_grade", sa.String),
        sa.column("unit_of_measure", sa.String),
    )
    op.bulk_insert(
        specs,
        [
            {
                "id": SPEC_CN_20093939_ID,
                "commodity_id": LEMON_ID,
                "specification_name": "CN 20093939 - single citrus juice, Brix 20-67, > 30 EUR/100 kg, no added sugar",
                "brix": None,
                "origin": None,
                "quality_grade": None,
                "unit_of_measure": "kg",
            }
        ],
    )

    # ---- row level security (PostgreSQL / Supabase only)
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for t in ("ingestion_runs", "purchase_imports"):
        op.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY")
    has_auth = bind.scalar(
        sa.text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'auth' AND p.proname = 'uid'"
        )
    ) and bind.scalar(sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'authenticated'"))
    if not has_auth:
        return
    op.execute("GRANT SELECT ON public.ingestion_runs, public.purchase_imports TO authenticated")
    op.execute("CREATE POLICY reference_read ON public.ingestion_runs FOR SELECT TO authenticated USING (true)")
    op.execute(
        "CREATE POLICY org_member_read ON public.purchase_imports FOR SELECT TO authenticated "
        "USING (public.is_org_member(organization_id))"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM product_specs WHERE specification_name LIKE 'CN 20093939%'")
    op.execute("DELETE FROM data_sources WHERE name IN ('Eurostat Comext (DS-045409)', 'Manual upload')")
    with op.batch_alter_table("market_observations") as batch_op:
        batch_op.drop_constraint("fk_market_observations_ingestion_run_id", type_="foreignkey")
        batch_op.drop_column("ingestion_run_id")
        batch_op.drop_column("attributes")
        batch_op.drop_column("quality_note")
    with op.batch_alter_table("customer_purchases") as batch_op:
        batch_op.drop_constraint("fk_customer_purchases_import_batch_id", type_="foreignkey")
    op.drop_index("ix_purchase_import_org_created", table_name="purchase_imports")
    op.drop_table("purchase_imports")
    op.drop_index("ix_ingestion_run_source_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
