"""SQLAlchemy models.

Money is Numeric(12, 2) in rupees (Decimal in Python, never float).
Status/role fields are plain strings; allowed values live in the constants below.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, Numeric,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# ---- allowed values -------------------------------------------------------
ROLES = ("resident", "helpdesk", "accounts", "committee")
COMPLAINT_STATUSES = ("open", "assigned", "in_progress", "resolved", "closed")
BANK_ROW_STATUSES = ("matched", "queued", "unmatched", "posted", "ignored")


class Flat(Base):
    __tablename__ = "flats"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # e.g. T07-1203
    tower: Mapped[str] = mapped_column(String(4))
    area_sqft: Mapped[int] = mapped_column(Integer)
    upi_id: Mapped[str | None] = mapped_column(String(80))  # registered UPI ID, used by matching

    users = relationship("User", back_populates="flat")
    bills = relationship("Bill", back_populates="flat")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(15), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    flat_id: Mapped[int | None] = mapped_column(ForeignKey("flats.id"))
    is_tenant: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    flat = relationship("Flat", back_populates="users")


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (UniqueConstraint("flat_id", "period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    flat_id: Mapped[int] = mapped_column(ForeignKey("flats.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))  # "2026-11"
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    issued_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)

    flat = relationship("Flat", back_populates="bills")

    @property
    def outstanding(self) -> Decimal:
        return self.amount - self.paid_amount


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    flat_id: Mapped[int] = mapped_column(ForeignKey("flats.id"), index=True)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(String(20))  # upi | cheque | transfer | online_test
    reference: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20), default="online")  # online | bank_match | manual
    received_on: Mapped[date] = mapped_column(Date)
    bank_row_id: Mapped[int | None] = mapped_column(ForeignKey("bank_rows.id"))


class BankRow(Base):
    """One line of an uploaded bank statement CSV.

    row_hash is unique, so re-uploading the same CSV never creates duplicates.
    A row is only ever posted to a flat automatically when status == 'matched'
    (high confidence). Everything else waits in the accounts queue.
    """
    __tablename__ = "bank_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    row_hash: Mapped[str] = mapped_column(String(64), unique=True)
    batch_id: Mapped[str] = mapped_column(String(40), index=True)
    txn_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(100))
    upi_id: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="unmatched")
    matched_flat_id: Mapped[int | None] = mapped_column(ForeignKey("flats.id"))
    confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100
    match_reason: Mapped[str | None] = mapped_column(Text)


class LedgerEntry(Base):
    """Per-flat ledger. Bills are positive (debit), payments negative (credit)."""
    __tablename__ = "ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    flat_id: Mapped[int] = mapped_column(ForeignKey("flats.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # bill | payment | adjustment
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(String(200))
    entry_date: Mapped[date] = mapped_column(Date)
    bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"))
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))


class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[int] = mapped_column(primary_key=True)
    flat_id: Mapped[int] = mapped_column(ForeignKey("flats.id"), index=True)
    raised_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), default="general")
    urgency: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | high | critical
    status: Mapped[str] = mapped_column(String(20), default="open")
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # AI / rule metadata
    ai_category: Mapped[str | None] = mapped_column(String(30))
    ai_confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100
    category_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_escalated: Mapped[bool] = mapped_column(Boolean, default=False)  # set by keyword rule, not AI
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"))  # linked, never closed
    rating: Mapped[int | None] = mapped_column(Integer)  # 1-5, on closure
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    respond_by: Mapped[datetime | None] = mapped_column(DateTime)  # response timer
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    events = relationship("ComplaintEvent", back_populates="complaint")


class ComplaintEvent(Base):
    """Status/assignment/category history so residents can see where a complaint stands."""
    __tablename__ = "complaint_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))  # created | assigned | status | category_changed | linked_duplicate
    detail: Mapped[str | None] = mapped_column(String(300))
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    complaint = relationship("Complaint", back_populates="events")
