from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Bill, Complaint, ComplaintEvent, Flat, Payment, User
from app.services import complaints as complaint_service


@pytest.fixture
def complaints_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False)
    now = datetime.utcnow()
    today = date.today()

    with TestSession() as db:
        flat_a = Flat(code="T31-0101", tower="T31", area_sqft=1000)
        flat_b = Flat(code="T32-0101", tower="T32", area_sqft=900)
        flat_c = Flat(code="T33-0101", tower="T33", area_sqft=850)
        flat_d = Flat(code="T34-0101", tower="T34", area_sqft=700)
        db.add_all([flat_a, flat_b, flat_c, flat_d])
        db.flush()
        resident_a = User(phone="9000000031", name="Resident A", role="resident", flat_id=flat_a.id)
        resident_b = User(phone="9000000032", name="Resident B", role="resident", flat_id=flat_b.id)
        helpdesk_a = User(phone="9000000033", name="Helpdesk A", role="helpdesk")
        helpdesk_b = User(phone="9000000034", name="Helpdesk B", role="helpdesk")
        accounts = User(phone="9000000035", name="Accounts", role="accounts")
        committee = User(phone="9000000036", name="Committee", role="committee")
        db.add_all([resident_a, resident_b, helpdesk_a, helpdesk_b, accounts, committee])
        db.flush()

        bill_data = [
            (flat_a.id, Decimal("1000.00"), Decimal("0.00"), 10),
            (flat_b.id, Decimal("2000.00"), Decimal("500.00"), 40),
            (flat_c.id, Decimal("500.00"), Decimal("0.00"), 70),
        ]
        bills = [
            Bill(
                flat_id=flat_id,
                period=today.strftime("%Y-%m"),
                amount=amount,
                paid_amount=paid,
                issued_on=today.replace(day=1),
                due_on=today - timedelta(days=age),
            )
            for flat_id, amount, paid, age in bill_data
        ]
        db.add_all(bills)
        db.flush()
        db.add(Bill(
            flat_id=flat_d.id,
            period=(today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"),
            amount=Decimal("100.00"),
            paid_amount=Decimal("0.00"),
            issued_on=today.replace(day=1) - timedelta(days=1),
            due_on=today + timedelta(days=10),
        ))
        db.add_all([
            Payment(flat_id=flat_a.id, bill_id=bills[0].id, amount=Decimal("300.00"), method="upi",
                    source="online", received_on=today),
            Payment(flat_id=flat_b.id, bill_id=bills[1].id, amount=Decimal("200.00"), method="upi",
                    source="online", received_on=today),
            Payment(flat_id=flat_b.id, bill_id=bills[1].id, amount=Decimal("900.00"), method="upi",
                    source="online", received_on=today - timedelta(days=40)),
        ])

        original = Complaint(
            flat_id=flat_a.id, raised_by=resident_a.id, text="Tap is leaking in the bathroom",
            category="plumbing", urgency="normal", status="open", created_at=now - timedelta(hours=4),
            respond_by=now - timedelta(hours=1),
        )
        duplicate = Complaint(
            flat_id=flat_b.id, raised_by=resident_b.id, text="Lift issue in the lobby",
            category="lift", urgency="critical", status="open", created_at=now - timedelta(hours=3),
            respond_by=now + timedelta(hours=1),
        )
        resolved_rate = Complaint(
            flat_id=flat_a.id, raised_by=resident_a.id, text="Resolved electrical issue",
            category="electrical", urgency="low", status="resolved", created_at=now - timedelta(hours=10),
            respond_by=now - timedelta(hours=8), first_response_at=now - timedelta(hours=8),
        )
        resolved_reopen = Complaint(
            flat_id=flat_a.id, raised_by=resident_a.id, text="Resolved parking issue",
            category="parking", urgency="normal", status="resolved", created_at=now - timedelta(hours=20),
            respond_by=now - timedelta(hours=19), first_response_at=now - timedelta(hours=19),
        )
        closed_rated = Complaint(
            flat_id=flat_b.id, raised_by=resident_b.id, text="Closed cleaning issue",
            category="cleaning", urgency="normal", status="closed", created_at=now - timedelta(hours=30),
            respond_by=now - timedelta(hours=27), first_response_at=now - timedelta(hours=27), rating=4,
        )
        db.add_all([original, duplicate, resolved_rate, resolved_reopen, closed_rated])
        db.flush()
        duplicate.duplicate_of_id = original.id
        db.add_all([
            ComplaintEvent(complaint_id=item.id, actor_id=item.raised_by, kind="created", detail="Created",
                           at=item.created_at)
            for item in (original, duplicate, resolved_rate, resolved_reopen, closed_rated)
        ])
        db.add(ComplaintEvent(complaint_id=resolved_reopen.id, actor_id=resident_a.id,
                              kind="reopened", detail="resolved -> open", at=now - timedelta(hours=18)))
        db.commit()
        ids = {
            "resident_a": resident_a.id,
            "resident_b": resident_b.id,
            "helpdesk_a": helpdesk_a.id,
            "helpdesk_b": helpdesk_b.id,
            "accounts": accounts.id,
            "committee": committee.id,
            "original": original.id,
            "duplicate": duplicate.id,
            "resolved_rate": resolved_rate.id,
            "resolved_reopen": resolved_reopen.id,
        }

    def override_get_db():
        with TestSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    def token(user_id, role):
        encoded = jwt.encode(
            {"sub": str(user_id), "role": role, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            settings.jwt_secret,
            algorithm="HS256",
        )
        return f"Bearer {encoded}"

    client = TestClient(app)
    tokens = {
        "resident_a": token(ids["resident_a"], "resident"),
        "resident_b": token(ids["resident_b"], "resident"),
        "helpdesk_a": token(ids["helpdesk_a"], "helpdesk"),
        "helpdesk_b": token(ids["helpdesk_b"], "helpdesk"),
        "accounts": token(ids["accounts"], "accounts"),
        "committee": token(ids["committee"], "committee"),
    }
    try:
        yield client, TestSession, tokens, ids
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()


_ACCESS_CASES = [
    ("post", "/complaints", {"text": "Water is leaking here"}, role)
    for role in ("helpdesk_a", "accounts", "committee")
] + [
    ("get", "/me/complaints", None, role) for role in ("helpdesk_a", "accounts", "committee")
] + [
    ("post", "/complaints/{id}/rate", {"rating": 5}, role)
    for role in ("helpdesk_a", "accounts", "committee")
] + [
    ("post", "/complaints/{id}/reopen", None, role)
    for role in ("helpdesk_a", "accounts", "committee")
] + [
    ("get", "/helpdesk/complaints", None, role) for role in ("resident_a", "accounts", "committee")
] + [
    ("post", "/helpdesk/complaints/{id}/category", {"category": "security"}, role)
    for role in ("resident_a", "accounts", "committee")
] + [
    ("post", "/helpdesk/complaints/{id}/assign", {"assignee_id": 1}, role)
    for role in ("resident_a", "accounts", "committee")
] + [
    ("post", "/helpdesk/complaints/{id}/status", {"status": "in_progress"}, role)
    for role in ("resident_a", "accounts", "committee")
] + [
    ("get", "/committee/summary", None, role) for role in ("resident_a", "helpdesk_a", "accounts")
]


@pytest.mark.parametrize(("method", "path", "body", "wrong_role"), _ACCESS_CASES)
def test_role_access_is_enforced(complaints_api, method, path, body, wrong_role):
    client, _, tokens, ids = complaints_api
    path = path.format(id=ids["original"] if "reopen" not in path and "rate" not in path else ids["resolved_rate"])
    response = client.request(method.upper(), path, headers={"Authorization": tokens[wrong_role]}, json=body)
    assert response.status_code == 403


def test_resident_can_create_and_list_only_own_flat_complaints(complaints_api, monkeypatch):
    client, _, tokens, _ = complaints_api
    monkeypatch.setattr(complaint_service, "default_llm", lambda: None)
    created = client.post(
        "/complaints", headers={"Authorization": tokens["resident_a"]}, json={"text": "Water is leaking here"}
    )
    listed = client.get("/me/complaints", headers={"Authorization": tokens["resident_a"]})
    assert created.status_code == 200
    assert created.json()["status"] == "assigned"
    assert created.json()["events"][0]["kind"] == "created"
    assert listed.status_code == 200
    assert all(item["text"] != "Lift issue in the lobby" for item in listed.json())
    assert listed.json()[0]["id"] == created.json()["id"]


def test_resident_cannot_discover_other_flats_complaint(complaints_api):
    client, _, tokens, ids = complaints_api
    response = client.post(
        f"/complaints/{ids['duplicate']}/rate",
        headers={"Authorization": tokens["resident_a"]},
        json={"rating": 5},
    )
    assert response.status_code == 404


def test_resident_service_validation_errors_map_to_expected_statuses(complaints_api):
    client, _, tokens, ids = complaints_api
    invalid_text = client.post(
        "/complaints", headers={"Authorization": tokens["resident_a"]}, json={"text": "bad"}
    )
    unrated = client.post(
        f"/complaints/{ids['original']}/rate",
        headers={"Authorization": tokens["resident_a"]},
        json={"rating": 5},
    )
    assert invalid_text.status_code == 422
    assert unrated.status_code == 409


def test_resident_can_rate_resolved_complaint(complaints_api):
    client, _, tokens, ids = complaints_api
    response = client.post(
        f"/complaints/{ids['resolved_rate']}/rate",
        headers={"Authorization": tokens["resident_a"]},
        json={"rating": 5},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_resident_can_reopen_resolved_complaint(complaints_api):
    client, _, tokens, ids = complaints_api
    response = client.post(
        f"/complaints/{ids['resolved_reopen']}/reopen", headers={"Authorization": tokens["resident_a"]}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "open"
    assert any(event["kind"] == "reopened" for event in response.json()["events"])


def test_helpdesk_queue_filters_orders_and_shows_sla_and_duplicate_fields(complaints_api):
    client, _, tokens, ids = complaints_api
    response = client.get(
        "/helpdesk/complaints?status=open", headers={"Authorization": tokens["helpdesk_a"]}
    )
    assert response.status_code == 200
    results = response.json()
    assert [item["urgency"] for item in results] == ["critical", "normal"]
    original = next(item for item in results if item["id"] == ids["original"])
    assert original["overdue"] is True
    assert original["duplicates_count"] == 1
    category_filtered = client.get(
        "/helpdesk/complaints?category=plumbing", headers={"Authorization": tokens["helpdesk_a"]}
    )
    assert [item["id"] for item in category_filtered.json()] == [ids["original"]]


def test_helpdesk_can_change_category_assign_and_set_status(complaints_api):
    client, _, tokens, ids = complaints_api
    headers = {"Authorization": tokens["helpdesk_a"]}
    complaint_id = ids["original"]
    category = client.post(
        f"/helpdesk/complaints/{complaint_id}/category", headers=headers, json={"category": "security"}
    )
    assigned = client.post(
        f"/helpdesk/complaints/{complaint_id}/assign", headers=headers, json={"assignee_id": ids["helpdesk_b"]}
    )
    status = client.post(
        f"/helpdesk/complaints/{complaint_id}/status", headers=headers, json={"status": "in_progress"}
    )
    assert category.status_code == assigned.status_code == status.status_code == 200
    assert category.json()["category"] == "security"
    assert assigned.json()["assigned_to"] == ids["helpdesk_b"]
    assert status.json()["status"] == "in_progress"


def test_helpdesk_missing_complaint_is_404_and_invalid_changes_are_409(complaints_api):
    client, _, tokens, ids = complaints_api
    headers = {"Authorization": tokens["helpdesk_a"]}
    missing_id = 999999
    missing_responses = [
        client.post(f"/helpdesk/complaints/{missing_id}/category", headers=headers,
                    json={"category": "security"}),
        client.post(f"/helpdesk/complaints/{missing_id}/assign", headers=headers,
                    json={"assignee_id": ids["helpdesk_b"]}),
        client.post(f"/helpdesk/complaints/{missing_id}/status", headers=headers,
                    json={"status": "in_progress"}),
    ]
    invalid_responses = [
        client.post(f"/helpdesk/complaints/{ids['original']}/category", headers=headers,
                    json={"category": "not-a-category"}),
        client.post(f"/helpdesk/complaints/{ids['original']}/assign", headers=headers,
                    json={"assignee_id": ids["resident_b"]}),
        client.post(f"/helpdesk/complaints/{ids['original']}/status", headers=headers,
                    json={"status": "closed"}),
    ]
    assert [response.status_code for response in missing_responses] == [404, 404, 404]
    assert [response.status_code for response in invalid_responses] == [422, 409, 409]


def test_committee_summary_reports_finance_and_complaint_metrics(complaints_api):
    client, _, tokens, _ = complaints_api
    response = client.get("/committee/summary", headers={"Authorization": tokens["committee"]})
    assert response.status_code == 200
    summary = response.json()
    assert summary["collections"] == "500.00"
    assert summary["billed"] == "3500.00"
    assert summary["dues_ageing"] == {"0_30": "1000.00", "31_60": "1500.00", "61_plus": "500.00"}
    assert summary["complaints_by_status"]["open"] == 2
    assert summary["reopened_count"] == 1
    assert summary["reopened_percentage"] == "20.00"
    assert summary["average_hours_to_first_response"] == "2.00"
    assert summary["average_rating"] == "4.00"
