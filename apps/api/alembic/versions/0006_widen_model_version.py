"""Widen model_version to 100 characters on forecasts and forecast_backtests.

The version string records the pipeline and library versions
(e.g. "costpilot-forecast/1.0 statsmodels/0.15.0 numpy/2.5.5") and exceeded 50.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("forecasts", "forecast_backtests"):
        with op.batch_alter_table(table) as b:
            b.alter_column("model_version", type_=sa.String(100), existing_type=sa.String(50), existing_nullable=False)


def downgrade() -> None:
    for table in ("forecasts", "forecast_backtests"):
        with op.batch_alter_table(table) as b:
            b.alter_column("model_version", type_=sa.String(50), existing_type=sa.String(100), existing_nullable=False)
