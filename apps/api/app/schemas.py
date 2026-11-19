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
