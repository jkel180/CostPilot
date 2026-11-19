"""Common interface for market-data connectors.

Every connector implements the five steps from the spec:
``fetch_data -> validate_data -> normalize_data -> save_data -> log_execution``.
:func:`run_connector` drives them and records an :class:`IngestionRun`, so each
saved observation can be traced back to the run, its parameters and a hash of the
exact data that was stored (``data_version``).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Commodity,
    DataSource,
    IngestionRun,
    MarketObservation,
    ObservationDataType,
    QualityStatus,
    RunStatus,
)


@dataclass(frozen=True)
class NormalizedObservation:
    observation_date: date
    geography: str
    value: Decimal
    currency: str | None
    unit: str
    data_type: ObservationDataType
    quality_status: QualityStatus
    product_spec_id: uuid.UUID | None = None
    quality_note: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def key(self) -> tuple:
        return (self.product_spec_id, self.geography, self.observation_date, self.data_type)


@dataclass
class Rejected:
    reason: str
    record: dict[str, Any]


@dataclass
class ValidationResult:
    valid: list[Any]
    rejected: list[Rejected]


@dataclass
class SaveResult:
    inserted: int = 0
    updated: int = 0

    @property
    def saved(self) -> int:
        return self.inserted + self.updated


class Connector(ABC):
    """A market-data source. Subclasses must not write to the database outside ``save_data``."""

    #: stable identifier stored on ingestion runs
    name: str
    #: ``data_sources.name`` this connector writes to
    source_name: str

    def __init__(self, commodity: Commodity, params: dict[str, Any] | None = None) -> None:
        self.commodity = commodity
        self.params = params or {}

    def prepare(self, db: Session) -> None:
        """Resolve reference data (e.g. product specs) before fetching. Optional."""

    @abstractmethod
    def fetch_data(self) -> Any: ...

    @abstractmethod
    def validate_data(self, raw: Any) -> ValidationResult: ...

    @abstractmethod
    def normalize_data(self, valid: list[Any]) -> list[NormalizedObservation]: ...

    def save_data(
        self, db: Session, source: DataSource, run: IngestionRun, rows: list[NormalizedObservation]
    ) -> SaveResult:
        """Upsert by (source, commodity, spec, geography, date, data_type). Re-running is idempotent."""
        existing = {
            (o.product_spec_id, o.geography, o.observation_date, o.data_type): o
            for o in db.scalars(
                select(MarketObservation).where(
                    MarketObservation.source_id == source.id, MarketObservation.commodity_id == self.commodity.id
                )
            )
        }
        result = SaveResult()
        for r in rows:
            obs = existing.get(r.key())
            if obs is None:
                obs = MarketObservation(
                    commodity_id=self.commodity.id, source_id=source.id, ingestion_run_id=run.id, **asdict(r)
                )
                db.add(obs)
                existing[r.key()] = obs  # a repeated key later in the batch updates this row
                result.inserted += 1
            else:
                for f in ("value", "currency", "unit", "quality_status", "quality_note", "attributes"):
                    setattr(obs, f, getattr(r, f))
                obs.ingestion_run_id = run.id
                obs.collected_at = datetime.now(UTC)
                result.updated += 1
        return result

    def log_execution(self, db: Session, run: IngestionRun) -> None:
        db.add(run)
        db.flush()


def data_version(rows: list[NormalizedObservation]) -> str:
    payload = sorted(
        json.dumps(
            {k: (str(v) if not isinstance(v, (dict, type(None))) else v) for k, v in asdict(r).items()},
            sort_keys=True,
        )
        for r in rows
    )
    return hashlib.sha256("\n".join(payload).encode()).hexdigest()


def run_connector(db: Session, connector: Connector, triggered_by: uuid.UUID | None = None) -> IngestionRun:
    """Execute a connector end to end. The run is always recorded, also when it fails."""
    source = db.scalar(select(DataSource).where(DataSource.name == connector.source_name))
    if source is None:
        raise LookupError(f"Data source '{connector.source_name}' is not registered")
    if not source.active:
        raise LookupError(f"Data source '{connector.source_name}' is inactive")

    run = IngestionRun(
        id=uuid.uuid4(),
        source_id=source.id,
        commodity_id=connector.commodity.id,
        connector=connector.name,
        status=RunStatus.running,
        started_at=datetime.now(UTC),
        parameters={k: v for k, v in connector.params.items() if k != "content"},
        triggered_by=triggered_by,
    )
    connector.log_execution(db, run)
    db.commit()

    try:
        connector.prepare(db)
        raw = connector.fetch_data()
        checked = connector.validate_data(raw)
        rows = connector.normalize_data(checked.valid)
        saved = connector.save_data(db, source, run, rows)
        run.rows_fetched = len(checked.valid) + len(checked.rejected)
        run.rows_rejected = len(checked.rejected)
        run.rows_saved = saved.saved
        run.data_version = data_version(rows)
        run.parameters = {
            **run.parameters,
            "inserted": saved.inserted,
            "updated": saved.updated,
            "rejected_sample": [{"reason": r.reason, **r.record} for r in checked.rejected[:20]],
        }
        run.status = RunStatus.success
    except Exception as exc:  # noqa: BLE001 - the failure itself is the logged outcome
        db.rollback()
        run = db.get(IngestionRun, run.id)
        run.status = RunStatus.failed
        run.error = f"{type(exc).__name__}: {exc}"[:2000]
    run.finished_at = datetime.now(UTC)
    db.commit()
    return run
