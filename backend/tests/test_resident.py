from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as SQLAlchemySession, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Bill, Flat, LedgerEntry, Payment, User


@pytest.fixture
def resident_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)
    with TestSession() as db:
        flat_a = Flat(code="T01-0101", tower="T01", area_sqft=1000)
        flat_b = Flat(code="T02-0101", tower="T02", area_sqft=1000)
        db.add_all([flat_a, flat_b])
        db.flush()
        resident_a = User(phone="9000000001", name="Resident A", role="resident", flat_id=flat_a.id)
        resident_b = User(phone="9000000002", name="Resident B", role="resident", flat_id=flat_b.id)
        db.add_all([resident_a, resident_b])
        db.flush()
        bill_a = Bill(
            flat_id=flat_a.id,
            period="2026-11",
            amount=Decimal("100.00"),
            paid_amount=Decimal("0.00"),
            issued_on=date.today(),
            due_on=date.today() + timedelta(days=10),
        )
        bill_b = Bill(
            flat_id=flat_b.id,
            period="2026-11",
            amount=Decimal("200.00"),
            paid_amount=Decimal("0.00"),
            issued_on=date.today(),
            due_on=date.today() + timedelta(days=10),
        )
        db.add_all([bill_a, bill_b])
        db.flush()
        db.add_all([
            LedgerEntry(flat_id=flat_a.id, kind="bill", amount=Decimal("100.00"),
                        note="own bill", entry_date=date.today(), bill_id=bill_a.id),
            LedgerEntry(flat_id=flat_b.id, kind="bill", amount=Decimal("200.00"),
                        note="other bill", entry_date=date.today(), bill_id=bill_b.id),
        ])
        db.commit()
        resident_id, other_bill_id, own_bill_id = resident_a.id, bill_b.id, bill_a.id

    def override_get_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    token = jwt.encode(
        {"sub": str(resident_id), "role": "resident", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        settings.jwt_secret,
        algorithm="HS256",
    )
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, TestSession, f"Bearer {token}", own_bill_id, other_bill_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_resident_sees_only_own_bills(resident_api):
    client, _, token, _, _ = resident_api
    response = client.get("/me/bills", headers={"Authorization": token})
    assert response.status_code == 200
    assert [bill["amount"] for bill in response.json()] == ["100.00"]
    assert response.json()[0]["outstanding"] == "100.00"
    assert response.json()[0]["late_fee"] == "0.00"
    assert response.json()[0]["days_overdue"] == 0


def test_resident_ledger_is_flat_scoped_and_newest_first(resident_api):
    client, _, token, _, _ = resident_api
    response = client.get("/me/ledger", headers={"Authorization": token})
    assert response.status_code == 200
    assert [entry["note"] for entry in response.json()] == ["own bill"]


def test_payment_above_owed_is_rejected(resident_api):
    client, _, token, own_bill_id, _ = resident_api
    response = client.post(
        f"/bills/{own_bill_id}/pay-test", headers={"Authorization": token}, json={"amount": "100.01"}
    )
    assert response.status_code == 400


@pytest.mark.parametrize("amount", ["0", "-1.00"])
def test_non_positive_payment_is_rejected(resident_api, amount):
    client, _, token, own_bill_id, _ = resident_api
    response = client.post(
        f"/bills/{own_bill_id}/pay-test", headers={"Authorization": token}, json={"amount": amount}
    )
    assert response.status_code == 400


def test_paying_another_flat_bill_returns_404(resident_api):
    client, _, token, _, other_bill_id = resident_api
    response = client.post(
        f"/bills/{other_bill_id}/pay-test", headers={"Authorization": token}, json={"amount": "10.00"}
    )
    assert response.status_code == 404


def test_partial_payment_updates_balance_and_records_rows(resident_api):
    client, Session, token, own_bill_id, _ = resident_api
    response = client.post(
        f"/bills/{own_bill_id}/pay-test", headers={"Authorization": token}, json={"amount": "25.00"}
    )
    assert response.status_code == 200
    with Session() as db:
        bill = db.get(Bill, own_bill_id)
        payment = db.query(Payment).one()
        entry = db.query(LedgerEntry).filter_by(kind="payment").one()
        assert bill.paid_amount == Decimal("25.00")
        assert payment.amount == Decimal("25.00")
        assert entry.amount == Decimal("-25.00")
        assert entry.payment_id == payment.id


def test_failed_payment_leaves_no_partial_rows(resident_api):
    client, Session, token, own_bill_id, _ = resident_api

    def fail_payment_ledger(session, flush_context, instances):
        if any(isinstance(obj, LedgerEntry) and obj.kind == "payment" for obj in session.new):
            raise RuntimeError("simulated ledger write failure")

    event.listen(SQLAlchemySession, "before_flush", fail_payment_ledger)
    try:
        response = client.post(
            f"/bills/{own_bill_id}/pay-test", headers={"Authorization": token}, json={"amount": "25.00"}
        )
    finally:
        event.remove(SQLAlchemySession, "before_flush", fail_payment_ledger)

    assert response.status_code == 500
    with Session() as db:
        assert db.get(Bill, own_bill_id).paid_amount == Decimal("0.00")
        assert db.query(Payment).count() == 0
        assert db.query(LedgerEntry).filter_by(kind="payment").count() == 0
