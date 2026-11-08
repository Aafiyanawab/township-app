from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..auth import require_role
from ..db import get_db
from ..models import BankRow, Flat, User
from ..services.bank_import import CsvError, ignore_row, import_statement, resolve_row

router = APIRouter(prefix="/accounts", tags=["accounts"])
MAX_UPLOAD_BYTES = 1_048_576


class BankImportSummary(BaseModel):
    total_rows: int
    duplicates_skipped: int
    posted: int
    queued: int
    unmatched: int
    ignored: int
    batch_id: str


class ResolveRequest(BaseModel):
    flat_id: int = Field(gt=0)


class BankRowSummary(BaseModel):
    id: int
    status: str
    description: str
    amount: Decimal
    reference: str | None
    confidence: int | None
    match_reason: str | None
    suggested_flat_code: str | None


class BankRowPage(BaseModel):
    items: list[BankRowSummary]
    page: int
    page_size: int
    total: int


class FlatOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str


@router.get("/flats", response_model=list[FlatOption])
def list_flats_for_resolution(
    _user: Annotated[User, Depends(require_role("accounts"))],
    db: Annotated[Session, Depends(get_db)],
):
    return db.scalars(select(Flat).order_by(Flat.code)).all()


@router.post("/bank-statements", response_model=BankImportSummary)
async def upload_bank_statement(
    file: Annotated[UploadFile, File()],
    _user: Annotated[User, Depends(require_role("accounts"))],
    db: Annotated[Session, Depends(get_db)],
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")
    if file.content_type not in (None, "", "text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Upload a CSV file")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="CSV file must be 1 MB or smaller")
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail=["CSV file must be UTF-8 encoded"])

    try:
        return import_statement(db, csv_text, today=date.today())
    except CsvError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)


@router.get("/bank-rows", response_model=BankRowPage)
def list_bank_rows(
    _user: Annotated[User, Depends(require_role("accounts"))],
    db: Annotated[Session, Depends(get_db)],
    row_status: Annotated[Literal["queued", "unmatched", "posted", "ignored"], Query(alias="status")],
    page: Annotated[int, Query(ge=1)] = 1,
):
    filters = BankRow.status == row_status
    total = db.scalar(select(func.count()).select_from(BankRow).where(filters)) or 0
    rows = db.execute(
        select(BankRow, Flat.code)
        .outerjoin(Flat, Flat.id == BankRow.matched_flat_id)
        .where(filters)
        .order_by(BankRow.id)
        .offset((page - 1) * 50)
        .limit(50)
    ).all()
    return BankRowPage(
        items=[
            BankRowSummary(
                id=row.id,
                status=row.status,
                description=row.description,
                amount=row.amount,
                reference=row.reference,
                confidence=row.confidence,
                match_reason=row.match_reason,
                suggested_flat_code=code,
            )
            for row, code in rows
        ],
        page=page,
        page_size=50,
        total=total,
    )


@router.post("/bank-rows/{row_id}/resolve", status_code=status.HTTP_200_OK)
def resolve_bank_row(
    row_id: int,
    payload: ResolveRequest,
    _user: Annotated[User, Depends(require_role("accounts"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        row = resolve_row(db, row_id, payload.flat_id, today=date.today())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"id": row.id, "status": row.status, "flat_id": row.matched_flat_id}


@router.post("/bank-rows/{row_id}/ignore")
def ignore_bank_row(
    row_id: int,
    _user: Annotated[User, Depends(require_role("accounts"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        row = ignore_row(db, row_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"id": row.id, "status": row.status}
