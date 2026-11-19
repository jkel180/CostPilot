from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import ObservationDataType, Role

# ISO 4217 codes accepted at organization level for the MVP.
SUPPORTED_CURRENCIES = {"EUR", "USD", "GBP", "CHF"}


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- users / orgs


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str | None


class MembershipSummary(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    role: Role


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipSummary]
    is_platform_admin: bool = False


def _clean_name(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.strip()
    if len(v) < 2:
        raise ValueError("Name must have at least 2 characters")
    return v


def _clean_country(v: str | None) -> str | None:
    if v is None:
        return v
    if not v.isalpha():
        raise ValueError("Country must be an ISO 3166-1 alpha-2 code")
    return v.upper()


def _clean_currency(v: str | None) -> str | None:
    if v is None:
        return v
    v = v.upper()
    if v not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Currency must be one of {sorted(SUPPORTED_CURRENCIES)}")
    return v


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    currency: str = Field(default="EUR", min_length=3, max_length=3, description="ISO 4217")

    _name = field_validator("name")(_clean_name)
    _country = field_validator("country")(_clean_country)
    _currency = field_validator("currency")(_clean_currency)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    currency: str | None = Field(default=None, min_length=3, max_length=3)

    _name = field_validator("name")(_clean_name)
    _country = field_validator("country")(_clean_country)
    _currency = field_validator("currency")(_clean_currency)


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    country: str | None
    currency: str
    created_at: datetime


class OrganizationWithRole(OrganizationOut):
    role: Role


class MemberOut(BaseModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str | None
    role: Role
    joined_at: datetime


class MemberAdd(BaseModel):
    email: EmailStr
    role: Role = Role.viewer


class MemberRoleUpdate(BaseModel):
    role: Role


# --------------------------------------------------------------------------- reference data


class CommodityOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    category: str
    default_unit: str
    default_currency: str
    description: str | None


# --------------------------------------------------------------------------- dashboard

KpiStatus = Literal["available", "not_available"]


class Provenance(BaseModel):
    source_id: uuid.UUID
    source_name: str
    data_type: ObservationDataType
    observation_date: date
    collected_at: datetime
    is_synthetic: bool


class Kpi(BaseModel):
    key: str
    label: str
    status: KpiStatus
    value: Decimal | None = None
    unit: str | None = None
    currency: str | None = None
    # observed | forecast | calculated | assumption — keeps the three kinds of numbers apart in the UI
    value_kind: Literal["observed", "forecast", "calculated"] | None = None
    provenance: Provenance | None = None
    reason: str | None = None
    note: str | None = None  # scope or caveat shown under the value


class DataStatus(BaseModel):
    market_observations: int
    latest_observation_date: date | None
    latest_collected_at: datetime | None
    active_sources: int
    synthetic_data_present: bool
    customer_purchases: int
    latest_purchase_date: date | None


class DashboardSummary(BaseModel):
    commodity: CommodityOut
    organization_currency: str
    kpis: list[Kpi]
    data_status: DataStatus
    active_alerts: int
    benchmark_series: list["SeriesPoint"] = []
    benchmark_label: str | None = None


# --------------------------------------------------------------------------- market data


class SeriesPoint(BaseModel):
    date: date
    value: Decimal
    quality_status: str
    quality_note: str | None = None
    quantity_kg: Decimal | None = None


class Series(BaseModel):
    geography: str
    label: str
    points: list[SeriesPoint]


class SourceInfo(BaseModel):
    id: uuid.UUID
    name: str
    source_type: str
    source_url: str | None
    license_reference: str | None
    update_frequency: str | None
    is_synthetic: bool
    observations: int
    latest_observation_date: date | None
    last_collected_at: datetime | None
    last_run_status: str | None
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_data_version: str | None
    last_error: str | None


class SeriesResponse(BaseModel):
    commodity: str
    data_type: ObservationDataType
    unit: str | None
    currency: str | None
    scope: str | None  # product specification the series refers to
    series: list[Series]


class OriginRow(BaseModel):
    geography: str
    label: str
    month: date
    unit_value: Decimal | None
    unit_value_quality: str | None
    quantity_kg: Decimal | None
    volume_share_pct: Decimal | None
    mom_pct: Decimal | None


class MarketOverview(BaseModel):
    commodity: str
    benchmark_label: str
    scope: str | None
    latest_month: date | None
    benchmark_value: Decimal | None
    benchmark_mom_pct: Decimal | None
    benchmark_yoy_pct: Decimal | None
    benchmark_12m_avg: Decimal | None
    import_volume_kg: Decimal | None
    import_volume_yoy_pct: Decimal | None
    origins: list[OriginRow]
    sources: list[SourceInfo]


class IngestionRunOut(ORMModel):
    id: uuid.UUID
    connector: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    rows_fetched: int
    rows_saved: int
    rows_rejected: int
    data_version: str | None
    error: str | None
    parameters: dict


# --------------------------------------------------------------------------- purchases


class PreviewRow(BaseModel):
    line: int
    values: dict[str, str] | None
    errors: list[str]


class ImportPreview(BaseModel):
    filename: str
    columns: list[str]
    delimiter: str
    number_format: str  # how numbers were read, e.g. "1.234,56"
    mapping: dict[str, str | None]
    required_fields: list[str]
    optional_fields: list[str]
    mapping_errors: list[str]
    rows_total: int
    rows_valid: int
    rows_invalid: int
    preview: list[PreviewRow]
    errors: list[PreviewRow]


class PurchaseImportOut(ORMModel):
    id: uuid.UUID
    filename: str
    rows_total: int
    rows_imported: int
    rows_skipped: int
    column_mapping: dict
    created_at: datetime


class PurchaseOut(ORMModel):
    id: uuid.UUID
    purchase_date: date
    supplier: str
    product_description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    currency: str
    brix: Decimal | None
    country_of_origin: str | None
    quality_grade: str | None
    incoterm: str | None
    delivery_location: str | None
    contract_type: str | None
    packaging: str | None
    certification: str | None
    import_batch_id: uuid.UUID | None


class PurchaseList(BaseModel):
    total: int
    items: list[PurchaseOut]


class WappGroup(BaseModel):
    key: str
    unit: str
    currency: str
    purchases: int
    total_quantity: Decimal
    total_spend: Decimal
    weighted_avg_price: Decimal | None
    min_price: Decimal
    max_price: Decimal
    first_purchase: date
    last_purchase: date


class PurchaseAnalysis(BaseModel):
    date_from: date | None
    date_to: date | None
    overall: list[WappGroup]
    by_supplier: list[WappGroup]
    by_product: list[WappGroup]
    by_month: list[WappGroup]


DashboardSummary.model_rebuild()
