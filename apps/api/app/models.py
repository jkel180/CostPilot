"""SQLAlchemy models for CostPilot AI.

Conventions
-----------
* UUID primary keys everywhere.
* Every customer-specific table carries ``organization_id`` (NOT NULL, FK, indexed).
  The API filters on it for every query; in Supabase, Row Level Security adds a
  second layer (see the initial Alembic migration).
* Reference/market tables (commodities, product_specs, data_sources,
  market_observations, forecasts, forecast_backtests) are shared across
  organizations and never hold customer data.
* Audit fields: ``created_at`` / ``updated_at`` and, where a user creates the row,
  ``created_by``. Security-relevant actions also go to ``audit_logs``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    """Portable enum stored as VARCHAR + CHECK constraint (no native PG enum to migrate)."""
    return Enum(
        cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class Base(DeclarativeBase):
    pass


# --------------------------------------------------------------------------- enums


class Role(str, enum.Enum):
    admin = "admin"
    analyst = "analyst"
    viewer = "viewer"


class SourceType(str, enum.Enum):
    official_statistics = "official_statistics"  # Eurostat Comext, UN Comtrade, FAOSTAT
    climate = "climate"  # Copernicus CDS
    commercial = "commercial"  # licensed agrifood data providers
    manual_upload = "manual_upload"
    synthetic = "synthetic"  # development only, never shown as real market data


class ObservationDataType(str, enum.Enum):
    """Kept explicit so customs benchmarks, spot, contract and paid prices are never mixed."""

    customs_unit_value = "customs_unit_value"
    spot_price = "spot_price"
    contract_price = "contract_price"
    trade_volume = "trade_volume"
    production_indicator = "production_indicator"
    climate_indicator = "climate_indicator"
    other_indicator = "other_indicator"


class QualityStatus(str, enum.Enum):
    unvalidated = "unvalidated"
    validated = "validated"
    rejected = "rejected"


class RunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"


class ForecastQualityStatus(str, enum.Enum):
    reliable = "reliable"  # beats the baseline in backtesting
    below_baseline = "below_baseline"  # must not be presented as a reliable forecast
    insufficient_data = "insufficient_data"


# --------------------------------------------------------------------------- mixins


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------- tenancy


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))  # ISO 3166-1 alpha-2
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")  # ISO 4217
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    memberships: Mapped[list[Membership]] = relationship(back_populates="organization")


class User(CreatedAtMixin, Base):
    """Application profile. ``id`` equals the Supabase Auth user id (JWT ``sub``)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", foreign_keys="Membership.user_id"
    )


class Membership(TimestampMixin, Base):
    """A user's role within one organization (a user may belong to several)."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_membership_org_user"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(_enum(Role, "role"), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    organization: Mapped[Organization] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships", foreign_keys=[user_id])


# --------------------------------------------------------------------------- reference data


class Commodity(TimestampMixin, Base):
    __tablename__ = "commodities"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    default_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProductSpec(TimestampMixin, Base):
    __tablename__ = "product_specs"
    __table_args__ = (
        UniqueConstraint("commodity_id", "specification_name", name="uq_product_spec_name"),
        CheckConstraint("brix IS NULL OR (brix > 0 AND brix <= 100)", name="ck_product_spec_brix"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    specification_name: Mapped[str] = mapped_column(String(200), nullable=False)
    brix: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    origin: Mapped[str | None] = mapped_column(String(100))
    quality_grade: Mapped[str | None] = mapped_column(String(100))
    unit_of_measure: Mapped[str] = mapped_column(String(20), nullable=False)


class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    source_type: Mapped[SourceType] = mapped_column(_enum(SourceType, "source_type"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    license_reference: Mapped[str | None] = mapped_column(Text)
    update_frequency: Mapped[str | None] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class MarketObservation(CreatedAtMixin, Base):
    __tablename__ = "market_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "commodity_id",
            "product_spec_id",
            "geography",
            "observation_date",
            "data_type",
            name="uq_market_observation",
        ),
        Index("ix_market_obs_commodity_date", "commodity_id", "observation_date"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    product_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_specs.id", ondelete="RESTRICT")
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    geography: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))  # null for non-monetary indicators
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    data_type: Mapped[ObservationDataType] = mapped_column(
        _enum(ObservationDataType, "observation_data_type"), nullable=False
    )
    quality_status: Mapped[QualityStatus] = mapped_column(
        _enum(QualityStatus, "quality_status"), nullable=False, default=QualityStatus.unvalidated
    )
    quality_note: Mapped[str | None] = mapped_column(String(200))
    # Source-specific provenance, e.g. reporter, CN code, raw value and quantity, geography label.
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )


class ForecastRun(Base):
    """One execution of the forecasting pipeline: inputs, versions and outcome.

    A run is reproducible from ``input_data_version`` (hash of the exact series used)
    and ``model_version`` (pipeline + library versions); ``settings`` holds every
    parameter the pipeline used.
    """

    __tablename__ = "forecast_runs"
    __table_args__ = (Index("ix_forecast_run_commodity_generated", "commodity_id", "generated_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    product_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_specs.id", ondelete="RESTRICT")
    )
    series_geography: Mapped[str] = mapped_column(String(100), nullable=False)
    series_data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | insufficient_data | failed
    input_data_version: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    n_observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_date: Mapped[date | None] = mapped_column(Date)
    last_date: Mapped[date | None] = mapped_column(Date)
    last_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    currency: Mapped[str | None] = mapped_column(String(3))
    unit: Mapped[str | None] = mapped_column(String(30))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    notes: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Forecast(CreatedAtMixin, Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        CheckConstraint("horizon_months IN (1, 3, 6)", name="ck_forecast_horizon"),
        CheckConstraint(
            "lower_bound <= forecast_value AND forecast_value <= upper_bound", name="ck_forecast_bounds"
        ),
        Index("ix_forecast_commodity_generated", "commodity_id", "forecast_date"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    product_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_specs.id", ondelete="RESTRICT")
    )
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)  # generation date
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    lower_bound: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    upper_bound: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_data_version: Mapped[str] = mapped_column(String(100), nullable=False)
    quality_status: Mapped[ForecastQualityStatus] = mapped_column(
        _enum(ForecastQualityStatus, "forecast_quality_status"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    interval_level: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))  # e.g. 0.80


class ForecastBacktest(CreatedAtMixin, Base):
    __tablename__ = "forecast_backtests"
    __table_args__ = (Index("ix_backtest_commodity_model", "commodity_id", "model_name", "horizon_months"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_data_version: Mapped[str] = mapped_column(String(100), nullable=False)
    evaluation_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_months: Mapped[int] = mapped_column(Integer, nullable=False)
    mae: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    wape: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    directional_accuracy: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    interval_coverage: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    benchmark_name: Mapped[str] = mapped_column(String(100), nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    n_origins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# --------------------------------------------------------------------------- customer data


class CustomerPurchase(TimestampMixin, Base):
    __tablename__ = "customer_purchases"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_purchase_price_non_negative"),
        Index("ix_purchase_org_date", "organization_id", "purchase_date"),
        Index("ix_purchase_org_supplier", "organization_id", "supplier"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    product_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_specs.id", ondelete="RESTRICT")
    )
    supplier: Mapped[str] = mapped_column(String(200), nullable=False)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # optional specification fields
    brix: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    country_of_origin: Mapped[str | None] = mapped_column(String(100))
    quality_grade: Mapped[str | None] = mapped_column(String(100))
    incoterm: Mapped[str | None] = mapped_column(String(10))
    delivery_location: Mapped[str | None] = mapped_column(String(200))
    contract_type: Mapped[str | None] = mapped_column(String(50))
    packaging: Mapped[str | None] = mapped_column(String(100))
    certification: Mapped[str | None] = mapped_column(String(200))
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_imports.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class PurchaseImport(CreatedAtMixin, Base):
    """One CSV upload. Deleting it removes the purchases it created."""

    __tablename__ = "purchase_imports"
    __table_args__ = (Index("ix_purchase_import_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_imported: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class IngestionRun(Base):
    """Execution log of a market-data connector (``log_execution``)."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (Index("ix_ingestion_run_source_started", "source_id", "started_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False
    )
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    connector: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_saved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    data_version: Mapped[str | None] = mapped_column(String(64))  # sha256 of the normalized rows
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class CostModel(TimestampMixin, Base):
    __tablename__ = "cost_models"
    __table_args__ = (
        CheckConstraint("expected_volume >= 0", name="ck_cost_model_volume"),
        CheckConstraint("current_purchase_price >= 0", name="ck_cost_model_price"),
        CheckConstraint("pass_through_pct >= 0 AND pass_through_pct <= 200", name="ck_cost_model_pass_through"),
        UniqueConstraint("organization_id", "commodity_id", name="uq_cost_model_org_commodity"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    product_spec_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_specs.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    expected_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume_period: Mapped[str] = mapped_column(String(10), nullable=False, default="annual")
    current_purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    target_purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # share of a benchmark % change passed on to the customer's price (100 = fully proportional)
    pass_through_pct: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal(100))
    commodity_cost_share_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    assumptions_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class Alert(TimestampMixin, Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alert_org_active", "organization_id", "active"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    commodity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commodities.id", ondelete="RESTRICT"), nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AIReport(CreatedAtMixin, Base):
    __tablename__ = "ai_reports"
    __table_args__ = (Index("ix_ai_report_org_generated", "organization_id", "generated_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_data_reference: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AuditLog(CreatedAtMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)


#: Tables that hold customer data and must be isolated per organization.
TENANT_TABLES = (
    "memberships", "customer_purchases", "purchase_imports", "cost_models", "alerts", "ai_reports", "audit_logs",
)
#: Shared reference / market tables (no customer data).
REFERENCE_TABLES = (
    "forecast_runs",
    "commodities",
    "product_specs",
    "data_sources",
    "market_observations",
    "ingestion_runs",
    "forecasts",
    "forecast_backtests",
)
