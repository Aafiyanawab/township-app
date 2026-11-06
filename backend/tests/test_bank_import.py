from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as m
from app.db import Base
from app.services import bank_import as bi

TODAY = date(2026, 11, 6)
SAMPLE = (Path(__file__).parent.parent / "seed" / "sample_bank_statement.csv").read_text()


@pytest.fixture
def bank_db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for code, area, upi, amt, paid, due, period in [
        ("T12-0408", 980, "swati@okbank", "6370", "0", date(2026, 9, 20), "2026-09"),
        ("T21-1601", 1640, "aamir@okbank", "10660", "5000", date(2026, 10, 19), "2026-10"),
        ("T07-1203", 1150, "neeraj@okbank", "7475", "7475", date(2026, 11, 10), "2026-11"),
    ]:
        f = m.Flat(code=code, tower=code[:3], area_sqft=area, upi_id=upi)
        db.add(f)
        db.flush()
        db.add(m.Bill(flat_id=f.id, period=period, amount=Decimal(amt), paid_amount=Decimal(paid),
                      issued_on=date.fromisoformat(period + "-01"), due_on=due))
    db.commit()
    yield db
    db.close()


def paid(db, code):
    flat = db.scalars(select(m.Flat).where(m.Flat.code == code)).one()
    return db.scalars(select(m.Bill).where(m.Bill.flat_id == flat.id)).one().paid_amount


def test_sample_statement_outcomes(bank_db):
    s = bi.import_statement(bank_db, SAMPLE, TODAY)
    assert (s["posted"], s["queued"], s["unmatched"], s["ignored"]) == (2, 3, 2, 1)
    assert paid(bank_db, "T12-0408") == Decimal("6370.00")
    assert paid(bank_db, "T21-1601") == Decimal("10660.00")


def test_unclear_rows_never_create_payments(bank_db):
    bi.import_statement(bank_db, SAMPLE, TODAY)
    assert bank_db.scalar(select(func.count()).select_from(m.Payment)) == 2
    assert bank_db.scalar(select(func.count()).select_from(m.BankRow)
                          .where(m.BankRow.status.in_(["queued", "unmatched"]))) == 5


def test_reupload_is_idempotent(bank_db):
    bi.import_statement(bank_db, SAMPLE, TODAY)
    again = bi.import_statement(bank_db, SAMPLE, TODAY)
    assert again["duplicates_skipped"] == 8 and again["posted"] == 0
    assert bank_db.scalar(select(func.count()).select_from(m.BankRow)) == 8
    assert bank_db.scalar(select(func.count()).select_from(m.Payment)) == 2


def test_two_identical_rows_in_one_file_are_both_kept(bank_db):
    line = "2026-11-06,CASH,,,100.00\n"
    s = bi.import_statement(bank_db, "date,description,reference,upi_id,amount\n" + line + line, TODAY)
    assert s["total_rows"] == 2 and s["unmatched"] == 2


def test_invalid_csv_stores_nothing(bank_db):
    bad = "date,description,reference,upi_id,amount\n2026-11-06,OK,,,100\nnot-a-date,X,,,5\n2026-11-06,Y,,,abc\n"
    with pytest.raises(bi.CsvError) as e:
        bi.import_statement(bank_db, bad, TODAY)
    assert len(e.value.errors) == 2
    assert bank_db.scalar(select(func.count()).select_from(m.BankRow)) == 0


def test_missing_column_rejected(bank_db):
    with pytest.raises(bi.CsvError):
        bi.import_statement(bank_db, "date,amount\n2026-11-06,100\n", TODAY)


def test_accounts_can_resolve_queued_row_once(bank_db):
    bi.import_statement(bank_db, SAMPLE, TODAY)
    row = bank_db.scalars(select(m.BankRow).where(m.BankRow.amount == Decimal("1000.00"))).one()
    assert row.status == "queued"
    flat = bank_db.get(m.Flat, row.matched_flat_id)
    bi.resolve_row(bank_db, row.id, flat.id)
    assert row.status == "posted"
    pay = bank_db.scalars(select(m.Payment).where(m.Payment.bank_row_id == row.id)).one()
    assert pay.source == "manual" and pay.amount == Decimal("1000.00")
    with pytest.raises(ValueError):
        bi.resolve_row(bank_db, row.id, flat.id)


def test_ignore_row(bank_db):
    bi.import_statement(bank_db, SAMPLE, TODAY)
    row = bank_db.scalars(select(m.BankRow).where(m.BankRow.status == "unmatched")).first()
    assert bi.ignore_row(bank_db, row.id).status == "ignored"
