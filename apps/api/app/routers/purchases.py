"""Customer purchases: CSV import (preview -> commit), history and supplier analysis.

All queries are scoped to the caller's organization. Importing and deleting require
the admin or analyst role; viewers can read.
"""

from __future__ import annotations

import json
import uuid
from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app import audit
from app.csvutil import MAX_BYTES, CsvError
from app.deps import DbSession, EditorCtx, OrgCtx
from app.models import CustomerPurchase, PurchaseImport
from app.purchases import ALL_FIELDS, OPTIONAL_FIELDS, REQUIRED_FIELDS, group_wapp, parse_purchase_file
from app.routers.market import get_commodity
from app.schemas import (
    ImportPreview,
    PreviewRow,
    PurchaseAnalysis,
    PurchaseImportOut,
    PurchaseList,
    PurchaseOut,
    WappGroup,
)

router = APIRouter(prefix="/purchases", tags=["purchases"])


async def _read_upload(file: UploadFile) -> bytes:
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".txt")):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .csv file")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File is larger than 5 MB")
    return content


def _mapping(raw: str | None) -> dict[str, str | None] | None:
    if not raw:
        return None
    try:
        m = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "mapping must be JSON") from exc
    if not isinstance(m, dict) or any(k not in ALL_FIELDS for k in m):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"mapping keys must be among {list(ALL_FIELDS)}")
    return {k: (str(v) if v else None) for k, v in m.items()}


def _parse(content: bytes, mapping):
    try:
        return parse_purchase_file(content, mapping)
    except CsvError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _row_out(r) -> PreviewRow:
    vals = {k: str(v) for k, v in (r.values or {}).items()} if r.values else None
    return PreviewRow(line=r.line, values=vals, errors=r.errors)


@router.post("/imports/preview", response_model=ImportPreview)
async def preview_import(
    ctx: EditorCtx,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
) -> ImportPreview:
    """Validate a file without storing anything."""
    parsed = _parse(await _read_upload(file), _mapping(mapping))
    return ImportPreview(
        filename=file.filename or "upload.csv",
        columns=parsed.header,
        delimiter=parsed.delimiter,
        number_format=parsed.number_format,
        mapping=parsed.mapping,
        required_fields=list(REQUIRED_FIELDS),
        optional_fields=list(OPTIONAL_FIELDS),
        mapping_errors=parsed.mapping_errors,
        rows_total=len(parsed.rows),
        rows_valid=len(parsed.valid),
        rows_invalid=len(parsed.invalid),
        preview=[_row_out(r) for r in parsed.rows[:20]],
        errors=[_row_out(r) for r in parsed.invalid[:200]],
    )


@router.post("/imports", response_model=PurchaseImportOut, status_code=status.HTTP_201_CREATED)
async def commit_import(
    ctx: EditorCtx,
    db: DbSession,
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    skip_invalid: bool = Form(False),
    commodity: str = Form("lemon_juice_concentrate"),
) -> PurchaseImport:
    com = get_commodity(db, commodity)
    parsed = _parse(await _read_upload(file), _mapping(mapping))
    if parsed.mapping_errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(parsed.mapping_errors))
    if parsed.invalid and not skip_invalid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"{len(parsed.invalid)} rows have errors. Fix them or import only the valid rows.",
        )
    if not parsed.valid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file has no valid rows")

    batch = PurchaseImport(
        id=uuid.uuid4(),
        organization_id=ctx.organization.id,
        commodity_id=com.id,
        filename=(file.filename or "upload.csv")[:255],
        rows_total=len(parsed.rows),
        rows_imported=len(parsed.valid),
        rows_skipped=len(parsed.invalid),
        column_mapping=parsed.mapping,
        created_by=ctx.user.id,
    )
    db.add(batch)
    db.flush()
    db.add_all(
        CustomerPurchase(
            organization_id=ctx.organization.id,
            commodity_id=com.id,
            import_batch_id=batch.id,
            created_by=ctx.user.id,
            **r.values,
        )
        for r in parsed.valid
    )
    audit.record(
        db, action="purchases.imported", entity_type="purchase_import", entity_id=batch.id,
        user_id=ctx.user.id, organization_id=ctx.organization.id,
        details={"rows_imported": batch.rows_imported, "rows_skipped": batch.rows_skipped},
    )
    db.commit()
    db.refresh(batch)
    return batch


@router.get("/imports", response_model=list[PurchaseImportOut])
def list_imports(ctx: OrgCtx, db: DbSession) -> list[PurchaseImport]:
    return list(
        db.scalars(
            select(PurchaseImport)
            .where(PurchaseImport.organization_id == ctx.organization.id)
            .order_by(PurchaseImport.created_at.desc())
        )
    )


@router.delete("/imports/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_import(import_id: uuid.UUID, ctx: EditorCtx, db: DbSession) -> None:
    batch = db.scalar(
        select(PurchaseImport).where(
            PurchaseImport.id == import_id, PurchaseImport.organization_id == ctx.organization.id
        )
    )
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    removed = db.query(CustomerPurchase).filter(
        CustomerPurchase.import_batch_id == batch.id, CustomerPurchase.organization_id == ctx.organization.id
    ).delete(synchronize_session=False)
    audit.record(
        db, action="purchases.import_deleted", entity_type="purchase_import", entity_id=batch.id,
        user_id=ctx.user.id, organization_id=ctx.organization.id, details={"rows_removed": removed},
    )
    db.delete(batch)
    db.commit()


def _filtered(ctx, commodity_id, supplier, date_from, date_to):
    q = select(CustomerPurchase).where(
        CustomerPurchase.organization_id == ctx.organization.id, CustomerPurchase.commodity_id == commodity_id
    )
    if supplier:
        q = q.where(CustomerPurchase.supplier == supplier)
    if date_from:
        q = q.where(CustomerPurchase.purchase_date >= date_from)
    if date_to:
        q = q.where(CustomerPurchase.purchase_date <= date_to)
    return q


@router.get("", response_model=PurchaseList)
def list_purchases(
    ctx: OrgCtx,
    db: DbSession,
    commodity: str = Query("lemon_juice_concentrate", max_length=64),
    supplier: str | None = Query(None, max_length=200),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> PurchaseList:
    com = get_commodity(db, commodity)
    q = _filtered(ctx, com.id, supplier, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = db.scalars(
        q.order_by(CustomerPurchase.purchase_date.desc(), CustomerPurchase.supplier).limit(limit).offset(offset)
    ).all()
    return PurchaseList(total=total, items=[PurchaseOut.model_validate(p) for p in items])


@router.get("/analysis", response_model=PurchaseAnalysis)
def analysis(
    ctx: OrgCtx,
    db: DbSession,
    commodity: str = Query("lemon_juice_concentrate", max_length=64),
    date_from: date | None = None,
    date_to: date | None = None,
) -> PurchaseAnalysis:
    com = get_commodity(db, commodity)
    ps = db.scalars(_filtered(ctx, com.id, None, date_from, date_to)).all()

    def groups(key) -> list[WappGroup]:
        return [WappGroup(**{**g, "key": str(g["key"])}) for g in group_wapp(ps, key)]

    by_month = sorted(groups(lambda p: p.purchase_date.strftime("%Y-%m")), key=lambda g: g.key)
    return PurchaseAnalysis(
        date_from=date_from,
        date_to=date_to,
        overall=groups(lambda p: "all"),
        by_supplier=groups(lambda p: p.supplier),
        by_product=groups(lambda p: p.product_description),
        by_month=by_month,
    )
