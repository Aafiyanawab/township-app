from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..auth import require_role
from ..db import get_db
from ..models import Bill, Complaint, ComplaintEvent, Payment, User
from ..services import complaints as complaint_service

router = APIRouter(tags=["complaints"])
ComplaintCategory = Literal[
    "plumbing", "electrical", "lift", "cleaning", "security", "parking",
    "noise", "lighting", "safety", "general",
]
ComplaintStatus = Literal["open", "assigned", "in_progress", "resolved", "closed"]


class CreateComplaintRequest(BaseModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=1000)]


class RateComplaintRequest(BaseModel):
    rating: Annotated[StrictInt, Field(ge=1, le=5)]


class CategoryRequest(BaseModel):
    category: ComplaintCategory


class AssignRequest(BaseModel):
    assignee_id: int = Field(gt=0)


class StatusRequest(BaseModel):
    status: ComplaintStatus


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ComplaintEventResponse(ORMResponse):
    id: int
    kind: str
    detail: str | None
    at: datetime


class ResidentComplaintResponse(ORMResponse):
    id: int
    text: str
    status: str
    category: str
    urgency: str
    created_at: datetime
    respond_by: datetime | None
    events: list[ComplaintEventResponse]


class HelpdeskComplaintResponse(ORMResponse):
    id: int
    text: str
    flat_id: int
    status: str
    category: str
    urgency: str
    created_at: datetime
    respond_by: datetime | None
    first_response_at: datetime | None
    assigned_to: int | None
    duplicate_of_id: int | None
    overdue: bool
    duplicates_count: int


class CommitteeSummaryResponse(BaseModel):
    period: str
    collections: Decimal
    billed: Decimal
    dues_ageing: dict[str, Decimal]
    complaints_by_status: dict[str, int]
    average_hours_to_first_response: Decimal | None
    reopened_count: int
    reopened_percentage: Decimal
    average_rating: Decimal | None


def _get_complaint_or_404(db: Session, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


def _resident_complaint_or_404(db: Session, complaint_id: int, user: User) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None or complaint.flat_id != user.flat_id:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@router.post("/complaints", response_model=ResidentComplaintResponse)
def create_resident_complaint(
    payload: CreateComplaintRequest,
    user: Annotated[User, Depends(require_role("resident"))],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        complaint = complaint_service.create_complaint(db, user, payload.text, datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return complaint


@router.get("/me/complaints", response_model=list[ResidentComplaintResponse])
def my_complaints(
    user: Annotated[User, Depends(require_role("resident"))],
    db: Annotated[Session, Depends(get_db)],
):
    if user.flat_id is None:
        return []
    complaints = db.scalars(
        select(Complaint)
        .where(Complaint.flat_id == user.flat_id)
        .order_by(Complaint.created_at.desc(), Complaint.id.desc())
    ).all()
    return [
        ResidentComplaintResponse(
            id=item.id,
            text=item.text,
            status=item.status,
            category=item.category,
            urgency=item.urgency,
            created_at=item.created_at,
            respond_by=item.respond_by,
            events=sorted(item.events, key=lambda event: (event.at, event.id)),
        )
        for item in complaints
    ]


@router.post("/complaints/{complaint_id}/rate", response_model=ResidentComplaintResponse)
def rate_resident_complaint(
    complaint_id: int,
    payload: RateComplaintRequest,
    user: Annotated[User, Depends(require_role("resident"))],
    db: Annotated[Session, Depends(get_db)],
):
    complaint = _resident_complaint_or_404(db, complaint_id, user)
    try:
        return complaint_service.rate_and_close(db, complaint, payload.rating, user, datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/complaints/{complaint_id}/reopen", response_model=ResidentComplaintResponse)
def reopen_resident_complaint(
    complaint_id: int,
    user: Annotated[User, Depends(require_role("resident"))],
    db: Annotated[Session, Depends(get_db)],
):
    complaint = _resident_complaint_or_404(db, complaint_id, user)
    try:
        return complaint_service.set_status(db, complaint, "open", user, datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/helpdesk/complaints", response_model=list[HelpdeskComplaintResponse])
def helpdesk_complaints(
    _user: Annotated[User, Depends(require_role("helpdesk"))],
    db: Annotated[Session, Depends(get_db)],
    status: ComplaintStatus | None = Query(default=None),
    category: ComplaintCategory | None = Query(default=None),
):
    query = select(Complaint)
    if status is not None:
        query = query.where(Complaint.status == status)
    if category is not None:
        query = query.where(Complaint.category == category)
    urgency_rank = case(
        (Complaint.urgency == "critical", 0),
        (Complaint.urgency == "high", 1),
        (Complaint.urgency == "normal", 2),
        (Complaint.urgency == "low", 3),
        else_=4,
    )
    records = db.scalars(query.order_by(urgency_rank, Complaint.created_at, Complaint.id)).all()
    now = datetime.utcnow()
    duplicate_counts = dict(
        db.execute(
            select(Complaint.duplicate_of_id, func.count(Complaint.id))
            .where(Complaint.duplicate_of_id.is_not(None))
            .group_by(Complaint.duplicate_of_id)
        ).all()
    )
    return [
        HelpdeskComplaintResponse(
            id=item.id,
            text=item.text,
            flat_id=item.flat_id,
            status=item.status,
            category=item.category,
            urgency=item.urgency,
            created_at=item.created_at,
            respond_by=item.respond_by,
            first_response_at=item.first_response_at,
            assigned_to=item.assigned_to,
            duplicate_of_id=item.duplicate_of_id,
            overdue=bool(item.respond_by and item.respond_by < now and item.first_response_at is None),
            duplicates_count=duplicate_counts.get(item.id, 0),
        )
        for item in records
    ]


@router.post("/helpdesk/complaints/{complaint_id}/category", response_model=HelpdeskComplaintResponse)
def helpdesk_change_category(
    complaint_id: int,
    payload: CategoryRequest,
    user: Annotated[User, Depends(require_role("helpdesk"))],
    db: Annotated[Session, Depends(get_db)],
):
    complaint = _get_complaint_or_404(db, complaint_id)
    try:
        complaint_service.change_category(db, complaint, payload.category, user, datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _helpdesk_complaint_response(db, complaint)


@router.post("/helpdesk/complaints/{complaint_id}/assign", response_model=HelpdeskComplaintResponse)
def helpdesk_assign(
    complaint_id: int,
    payload: AssignRequest,
    user: Annotated[User, Depends(require_role("helpdesk"))],
    db: Annotated[Session, Depends(get_db)],
):
    complaint = _get_complaint_or_404(db, complaint_id)
    try:
        complaint_service.assign(db, complaint, payload.assignee_id, user, datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _helpdesk_complaint_response(db, complaint)


@router.post("/helpdesk/complaints/{complaint_id}/status", response_model=HelpdeskComplaintResponse)
def helpdesk_set_status(
    complaint_id: int,
    payload: StatusRequest,
    user: Annotated[User, Depends(require_role("helpdesk"))],
    db: Annotated[Session, Depends(get_db)],
):
    complaint = _get_complaint_or_404(db, complaint_id)
    try:
        complaint_service.set_status(db, complaint, payload.status, user, datetime.utcnow())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _helpdesk_complaint_response(db, complaint)


def _helpdesk_complaint_response(db: Session, complaint: Complaint) -> HelpdeskComplaintResponse:
    duplicate_count = db.scalar(
        select(func.count(Complaint.id)).where(Complaint.duplicate_of_id == complaint.id)
    ) or 0
    now = datetime.utcnow()
    return HelpdeskComplaintResponse(
        id=complaint.id,
        text=complaint.text,
        flat_id=complaint.flat_id,
        status=complaint.status,
        category=complaint.category,
        urgency=complaint.urgency,
        created_at=complaint.created_at,
        respond_by=complaint.respond_by,
        first_response_at=complaint.first_response_at,
        assigned_to=complaint.assigned_to,
        duplicate_of_id=complaint.duplicate_of_id,
        overdue=bool(complaint.respond_by and complaint.respond_by < now and complaint.first_response_at is None),
        duplicates_count=duplicate_count,
    )


@router.get("/committee/summary", response_model=CommitteeSummaryResponse)
def committee_summary(
    _user: Annotated[User, Depends(require_role("committee"))],
    db: Annotated[Session, Depends(get_db)],
):
    today = date.today()
    period = today.strftime("%Y-%m")
    month_start = date(today.year, today.month, 1)
    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)

    collections = db.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.received_on >= month_start, Payment.received_on < next_month
        )
    ) or Decimal("0.00")
    billed = db.scalar(
        select(func.coalesce(func.sum(Bill.amount), 0)).where(Bill.period == period)
    ) or Decimal("0.00")

    buckets = {"0_30": Decimal("0.00"), "31_60": Decimal("0.00"), "61_plus": Decimal("0.00")}
    for bill in db.scalars(select(Bill).where(Bill.amount > Bill.paid_amount)).all():
        if bill.due_on > today:
            continue
        outstanding = bill.outstanding
        overdue_days = max(0, (today - bill.due_on).days)
        bucket = "0_30" if overdue_days <= 30 else "31_60" if overdue_days <= 60 else "61_plus"
        buckets[bucket] += outstanding

    status_rows = db.execute(select(Complaint.status, func.count()).group_by(Complaint.status)).all()
    status_counts = {name: 0 for name in ("open", "assigned", "in_progress", "resolved", "closed")}
    status_counts.update({name: count for name, count in status_rows})

    response_times = db.execute(
        select(Complaint.created_at, Complaint.first_response_at)
        .where(Complaint.first_response_at.is_not(None))
    ).all()
    hours_total_us = sum(
        ((responded - created).days * 86400 + (responded - created).seconds) * 1_000_000
        + (responded - created).microseconds
        for created, responded in response_times
    )
    average_hours = (
        (Decimal(hours_total_us) / Decimal(len(response_times) * 3_600_000_000)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if response_times
        else None
    )

    total_complaints = db.scalar(select(func.count(Complaint.id))) or 0
    reopened_count = db.scalar(
        select(func.count(func.distinct(ComplaintEvent.complaint_id))).where(ComplaintEvent.kind == "reopened")
    ) or 0
    reopened_percentage = (
        (Decimal(reopened_count) * Decimal("100") / Decimal(total_complaints)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if total_complaints
        else Decimal("0.00")
    )
    ratings = db.scalars(select(Complaint.rating).where(Complaint.rating.is_not(None))).all()
    average_rating = (
        (Decimal(sum(ratings)) / Decimal(len(ratings))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if ratings
        else None
    )

    return CommitteeSummaryResponse(
        period=period,
        collections=Decimal(str(collections)),
        billed=Decimal(str(billed)),
        dues_ageing=buckets,
        complaints_by_status=status_counts,
        average_hours_to_first_response=average_hours,
        reopened_count=reopened_count,
        reopened_percentage=reopened_percentage,
        average_rating=average_rating,
    )
