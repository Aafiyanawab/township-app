"""Bank statement CSV import: parse, de-duplicate, match, post, and accounts resolve.

CSV columns (header required): date, description, reference, upi_id, amount
  date = YYYY-MM-DD, amount = credit positive / debit negative.
Re-uploading the same file is safe: every row has a stable hash and is skipped if seen.
"""
import csv
import hashlib
import io
import uuid
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .billing import allocate_payment, late_fee, money
from .matching import BankRowIn, FlatInfo, match_batch

REQUIRED = ["date", "description", "reference", "upi_id", "amount"]
MAX_ROWS = 5000
MAX_FIELD = 300


class CsvError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def parse_csv(text: str) -> list[BankRowIn]:
    """All-or-nothing: if any line is invalid nothing is imported."""
    reader = csv.DictReader(io.StringIO(text))
    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        raise CsvError([f"Missing column(s): {', '.join(missing)}"])

    rows, errors = [], []
    for line_no, raw in enumerate(reader, start=2):
        if line_no - 1 > MAX_ROWS:
            raise CsvError([f"Too many rows (maximum {MAX_ROWS})"])
        rec = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if any(len(rec.get(c, "")) > MAX_FIELD for c in REQUIRED):
            errors.append(f"Line {line_no}: a field is longer than {MAX_FIELD} characters")
            continue
        try:
            d = date.fromisoformat(rec["date"])
        except ValueError:
            errors.append(f"Line {line_no}: date must be YYYY-MM-DD")
            continue
        try:
            amt = Decimal(rec["amount"].replace(",", ""))
            if not amt.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            errors.append(f"Line {line_no}: amount is not a number")
            continue
        rows.append(BankRowIn(d, rec["description"], rec["reference"], rec["upi_id"], money(amt)))
    if errors:
        raise CsvError(errors)
    return rows


def _hashes(rows: list[BankRowIn]) -> list[str]:
    """Stable per-row hash. Identical rows in one file get an occurrence number,
    so two genuine identical payments both survive, yet re-uploading is a no-op."""
    seen, out = Counter(), []
    for r in rows:
        key = "|".join([r.txn_date.isoformat(), r.description, r.reference, r.upi_id, str(money(r.amount))])
        seen[key] += 1
        out.append(hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest())
    return out


def build_flat_infos(db: Session, today: date) -> list[FlatInfo]:
    flats = db.scalars(select(m.Flat)).all()
    open_bills = db.scalars(select(m.Bill).where(m.Bill.amount > m.Bill.paid_amount)).all()
    by_flat = defaultdict(list)
    for b in open_bills:
        by_flat[b.flat_id].append(b)
    infos = []
    for f in flats:
        fb = by_flat.get(f.id, [])
        fee = sum((late_fee(b.outstanding, b.due_on, today) for b in fb), Decimal("0"))
        infos.append(FlatInfo(id=f.id, code=f.code, upi_id=f.upi_id,
                              outstanding_by_bill=tuple(b.outstanding for b in fb),
                              late_fee_total=money(fee)))
    return infos


def post_payment(db: Session, flat_id: int, amount: Decimal, method: str, reference: str | None,
                 received_on: date, source: str, bank_row_id: int | None = None) -> m.Payment:
    """Apply a payment oldest-bill-first and write Payment + LedgerEntry. Caller commits."""
    bills = db.scalars(select(m.Bill).where(m.Bill.flat_id == flat_id, m.Bill.amount > m.Bill.paid_amount)
                       .order_by(m.Bill.due_on, m.Bill.id)).all()
    allocations, _advance = allocate_payment(amount, [b.outstanding for b in bills])
    first = None
    for bill, part in zip(bills, allocations):
        if part > 0:
            bill.paid_amount = bill.paid_amount + part
            first = first or bill
    pay = m.Payment(flat_id=flat_id, bill_id=first.id if first else None, amount=money(amount),
                    method=method, reference=reference, source=source, received_on=received_on,
                    bank_row_id=bank_row_id)
    db.add(pay)
    db.flush()
    db.add(m.LedgerEntry(flat_id=flat_id, kind="payment", amount=-money(amount), entry_date=received_on,
                         payment_id=pay.id, note=f"Payment via {source}"))
    return pay


def import_statement(db: Session, csv_text: str, today: date, batch_id: str | None = None) -> dict:
    rows = parse_csv(csv_text)
    batch_id = batch_id or uuid.uuid4().hex[:12]
    hashes = _hashes(rows)
    existing = set(db.scalars(select(m.BankRow.row_hash).where(m.BankRow.row_hash.in_(hashes))))
    fresh = [(r, h) for r, h in zip(rows, hashes) if h not in existing]
    results = match_batch([r for r, _ in fresh], build_flat_infos(db, today))

    summary = Counter(total_rows=len(rows), duplicates_skipped=len(rows) - len(fresh))
    try:
        for (r, h), res in zip(fresh, results):
            row = m.BankRow(row_hash=h, batch_id=batch_id, txn_date=r.txn_date, description=r.description,
                            amount=money(r.amount), reference=r.reference or None, upi_id=r.upi_id or None,
                            status=res.status, matched_flat_id=res.flat_id, confidence=res.confidence,
                            match_reason=res.reason)
            db.add(row)
            db.flush()
            if res.status == "matched":
                post_payment(db, res.flat_id, r.amount, "transfer", r.reference or r.description,
                             r.txn_date, "bank_match", bank_row_id=row.id)
                row.status = "posted"
                summary["posted"] += 1
            else:
                summary[res.status] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    out = {k: summary.get(k, 0) for k in ("total_rows", "duplicates_skipped", "posted", "queued", "unmatched", "ignored")}
    out["batch_id"] = batch_id
    return out


def resolve_row(db: Session, row_id: int, flat_id: int, today: date | None = None) -> m.BankRow:
    """Accounts staff assign a queued/unmatched row to a flat. Only this path posts unclear money."""
    row = db.get(m.BankRow, row_id)
    if row is None:
        raise LookupError("Bank row not found")
    if row.status not in ("queued", "unmatched"):
        raise ValueError("This row has already been handled")
    if db.get(m.Flat, flat_id) is None:
        raise LookupError("Flat not found")
    post_payment(db, flat_id, row.amount, "transfer", row.reference or row.description,
                 row.txn_date, "manual", bank_row_id=row.id)
    row.status, row.matched_flat_id = "posted", flat_id
    row.match_reason = (row.match_reason or "") + " | Posted manually by accounts"
    db.commit()
    return row


def ignore_row(db: Session, row_id: int) -> m.BankRow:
    row = db.get(m.BankRow, row_id)
    if row is None:
        raise LookupError("Bank row not found")
    if row.status not in ("queued", "unmatched"):
        raise ValueError("This row has already been handled")
    row.status = "ignored"
    db.commit()
    return row
