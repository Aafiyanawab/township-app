from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_role
from ..db import get_db
from ..models import Bill, LedgerEntry, Payment, User
from ..services.billing import days_overdue, late_fee

router = APIRouter(tags=["resident"])


class BillSummary(BaseModel):
    id: int
    period: str
    amount: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    late_fee: Decimal
    days_overdue: int
    due_on: date


class LedgerSummary(BaseModel):
    id: int
    kind: str
    amount: Decimal
    note: str | None
    entry_date: date
    bill_id: int | None
    payment_id: int | None


class TestPaymentRequest(BaseModel):
    amount: Annotated[Decimal, Field(max_digits=12, decimal_places=2)]


@router.get("/me/bills", response_model=list[BillSummary])
def my_bills(
    user: Annotated[User, Depends(require_role("resident"))],
    db: Annotated[Session, Depends(get_db)],
):
    if user.flat_id is None:
        return []
    today = date.today()
    bills = db.query(Bill).filter(Bill.flat_id == user.flat_id).order_by(Bill.period.desc()).all()
    return [
        BillSummary(
            id=bill.id,
            period=bill.period,
            amount=bill.amount,
            paid_amount=bill.paid_amount,
            outstanding=bill.outstanding,
            late_fee=late_fee(bill.outstanding, bill.due_on, today),
            days_overdue=days_overdue(bill.due_on, today),
            due_on=bill.due_on,
        )
        for bill in bills
    ]


@router.get("/me/ledger", response_model=list[LedgerSummary])
def my_ledger(
    user: Annotated[User, Depends(require_role("resident"))],
    db: Annotated[Session, Depends(get_db)],
):
    if user.flat_id is None:
        return []
    return (
        db.query(LedgerEntry)
        .filter(LedgerEntry.flat_id == user.flat_id)
        .order_by(LedgerEntry.entry_date.desc(), LedgerEntry.id.desc())
        .all()
    )


@router.post("/bills/{bill_id}/pay-test")
def pay_bill_test(
    bill_id: int,
    payload: TestPaymentRequest,
    user: Annotated[User, Depends(require_role("resident"))],
    db: Annotated[Session, Depends(get_db)],
):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

    try:
        bill = (
            db.query(Bill)
            .filter(Bill.id == bill_id, Bill.flat_id == user.flat_id)
            .with_for_update()
            .first()
        )
        if bill is None:
            raise HTTPException(status_code=404, detail="Bill not found")

        today = date.today()
        outstanding = bill.outstanding
        fee = late_fee(outstanding, bill.due_on, today)
        if payload.amount > outstanding + fee:
            raise HTTPException(status_code=400, detail="Payment exceeds amount due")

        # Bill.paid_amount tracks principal; any remainder pays the fee and is
        # still recorded in full in the payment and flat ledger.
        bill.paid_amount += min(payload.amount, outstanding)
        payment = Payment(
            flat_id=user.flat_id,
            bill_id=bill.id,
            amount=payload.amount,
            method="online_test",
            source="online",
            received_on=today,
        )
        db.add(payment)
        db.flush()
        db.add(
            LedgerEntry(
                flat_id=user.flat_id,
                kind="payment",
                amount=-payload.amount,
                note=f"Mock online payment for bill {bill.id}",
                entry_date=today,
                bill_id=bill.id,
                payment_id=payment.id,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"payment_id": payment.id, "bill_id": bill.id, "amount": payment.amount}
