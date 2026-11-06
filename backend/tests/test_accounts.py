from datetime import date, timedelta, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import BankRow, Bill, Flat, Payment, User

MATCH_CSV_HEADER = "date,description,reference,upi_id,amount\n"


@pytest.fixture
def accounts_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)
    with TestSession() as db:
        flat = Flat(code="T55-0101", tower="T55", area_sqft=800, upi_id="unit55@upi")
        db.add(flat)
        db.flush()
        accounts = User(phone="9000000011", name="Accounts", role="accounts")
        resident = User(phone="9000000012", name="Resident", role="resident", flat_id=flat.id)
        db.add_all([accounts, resident])
        db.flush()
        bill = Bill(
            flat_id=flat.id,
            period="2026-11",
            amount=Decimal("500.00"),
            paid_amount=Decimal("0.00"),
            issued_on=date.today(),
            due_on=date.today() + timedelta(days=10),
        )
        db.add(bill)
        db.commit()
        accounts_id, resident_id, flat_id = accounts.id, resident.id, flat.id

    def override_get_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    def bearer(user_id, role):
        token = jwt.encode(
            {"sub": str(user_id), "role": role, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            settings.jwt_secret,
            algorithm="HS256",
        )
        return f"Bearer {token}"

    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client, TestSession, bearer(accounts_id, "accounts"), bearer(resident_id, "resident"), flat_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


def _matched_csv():
    return MATCH_CSV_HEADER + f"{date.today().isoformat()},Maintenance,T55-0101,unit55@upi,500.00\n"


def test_resident_gets_403(accounts_api):
    client, _, _, resident_token, _ = accounts_api
    response = client.get("/accounts/bank-rows?status=queued", headers={"Authorization": resident_token})
    assert response.status_code == 403


def test_upload_posts_matched_rows(accounts_api):
    client, Session, accounts_token, _, _ = accounts_api
    response = client.post(
        "/accounts/bank-statements",
        headers={"Authorization": accounts_token},
        files={"file": ("statement.csv", _matched_csv(), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["posted"] == 1
    with Session() as db:
        row = db.query(BankRow).one()
        assert row.status == "posted"
        assert db.query(Payment).filter_by(source="bank_match").count() == 1


def test_reupload_is_a_noop(accounts_api):
    client, Session, accounts_token, _, _ = accounts_api
    files = {"file": ("statement.csv", _matched_csv(), "text/csv")}
    first = client.post("/accounts/bank-statements", headers={"Authorization": accounts_token}, files=files)
    second = client.post("/accounts/bank-statements", headers={"Authorization": accounts_token}, files=files)
    assert first.status_code == second.status_code == 200
    assert second.json()["duplicates_skipped"] == 1
    assert second.json()["posted"] == 0
    with Session() as db:
        assert db.query(BankRow).count() == 1
        assert db.query(Payment).count() == 1


def test_resolve_posts_once_and_second_resolve_conflicts(accounts_api):
    client, Session, accounts_token, _, flat_id = accounts_api
    with Session() as db:
        row = BankRow(
            row_hash="queued-test-row-hash",
            batch_id="batch-test",
            txn_date=date.today(),
            description="Unclear transfer",
            amount=Decimal("50.00"),
            reference="REF-50",
            status="queued",
            confidence=60,
            match_reason="Partial evidence",
        )
        db.add(row)
        db.commit()
        row_id = row.id

    path = f"/accounts/bank-rows/{row_id}/resolve"
    first = client.post(path, headers={"Authorization": accounts_token}, json={"flat_id": flat_id})
    second = client.post(path, headers={"Authorization": accounts_token}, json={"flat_id": flat_id})
    assert first.status_code == 200
    assert first.json()["status"] == "posted"
    assert second.status_code == 409
    with Session() as db:
        assert db.query(Payment).filter_by(bank_row_id=row_id).count() == 1


def test_resolve_missing_row_or_flat_returns_404(accounts_api):
    client, Session, accounts_token, _, _ = accounts_api
    with Session() as db:
        row = BankRow(
            row_hash="missing-flat-test-row-hash",
            batch_id="batch-missing",
            txn_date=date.today(),
            description="Needs review",
            amount=Decimal("20.00"),
            status="queued",
        )
        db.add(row)
        db.commit()
        row_id = row.id

    missing_row = client.post(
        "/accounts/bank-rows/999999/resolve",
        headers={"Authorization": accounts_token},
        json={"flat_id": 1},
    )
    missing_flat = client.post(
        f"/accounts/bank-rows/{row_id}/resolve",
        headers={"Authorization": accounts_token},
        json={"flat_id": 999999},
    )
    assert missing_row.status_code == 404
    assert missing_flat.status_code == 404


def test_ignore_changes_queued_row_to_ignored(accounts_api):
    client, Session, accounts_token, _, _ = accounts_api
    with Session() as db:
        row = BankRow(
            row_hash="ignore-test-row-hash",
            batch_id="batch-ignore",
            txn_date=date.today(),
            description="Ignore me",
            amount=Decimal("20.00"),
            status="queued",
        )
        db.add(row)
        db.commit()
        row_id = row.id

    response = client.post(
        f"/accounts/bank-rows/{row_id}/ignore", headers={"Authorization": accounts_token}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_bank_row_list_paginates_in_pages_of_50(accounts_api):
    client, Session, accounts_token, _, _ = accounts_api
    with Session() as db:
        db.add_all([
            BankRow(
                row_hash=f"pagination-row-{index}",
                batch_id="batch-pagination",
                txn_date=date.today(),
                description=f"row {index}",
                amount=Decimal("1.00"),
                status="queued",
            )
            for index in range(51)
        ])
        db.commit()

    first = client.get("/accounts/bank-rows?status=queued&page=1", headers={"Authorization": accounts_token})
    second = client.get("/accounts/bank-rows?status=queued&page=2", headers={"Authorization": accounts_token})
    assert first.status_code == second.status_code == 200
    assert len(first.json()["items"]) == 50
    assert len(second.json()["items"]) == 1
    assert first.json()["total"] == 51


def test_bad_csv_returns_422_errors_list(accounts_api):
    client, _, accounts_token, _, _ = accounts_api
    response = client.post(
        "/accounts/bank-statements",
        headers={"Authorization": accounts_token},
        files={"file": ("invalid.csv", "date,amount\n2026-01-01,10\n", "text/csv")},
    )
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert "Missing column(s)" in response.json()["detail"][0]


def test_non_csv_and_oversized_uploads_are_rejected(accounts_api):
    client, _, accounts_token, _, _ = accounts_api
    non_csv = client.post(
        "/accounts/bank-statements",
        headers={"Authorization": accounts_token},
        files={"file": ("statement.txt", "not csv", "text/plain")},
    )
    oversized = client.post(
        "/accounts/bank-statements",
        headers={"Authorization": accounts_token},
        files={"file": ("large.csv", "x" * (1_048_577), "text/csv")},
    )
    assert non_csv.status_code == 400
    assert oversized.status_code == 400


def test_bank_row_list_includes_suggested_flat_code(accounts_api):
    client, Session, accounts_token, _, flat_id = accounts_api
    with Session() as db:
        db.add(BankRow(
            row_hash="queued-list-row-hash",
            batch_id="batch-list",
            txn_date=date.today(),
            description="Needs review",
            amount=Decimal("25.00"),
            reference="REF-25",
            status="queued",
            matched_flat_id=flat_id,
            confidence=60,
            match_reason="Possible match",
        ))
        db.commit()

    response = client.get("/accounts/bank-rows?status=queued", headers={"Authorization": accounts_token})
    assert response.status_code == 200
    assert response.json()["items"][0]["suggested_flat_code"] == "T55-0101"
    assert response.json()["page_size"] == 50


def test_invalid_status_is_rejected(accounts_api):
    client, _, accounts_token, _, _ = accounts_api
    response = client.get("/accounts/bank-rows?status=matched", headers={"Authorization": accounts_token})
    assert response.status_code == 422
