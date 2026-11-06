from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models as m
from app.db import Base
from app.services import complaints as svc

NOW = datetime(2026, 11, 6, 12, 0)
NO_AI = None


@pytest.fixture
def cdb():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    flats = [m.Flat(code=c, tower=c[:3], area_sqft=1000) for c in ("T07-0101", "T07-0202", "T08-0101")]
    db.add_all(flats)
    db.flush()
    db.add_all([m.User(phone=f"90000000{i}", name=f"Res {i}", role="resident", flat_id=f.id) for i, f in enumerate(flats)])
    db.add_all([m.User(phone="9000010001", name="Duty Manager", role="helpdesk"),
                m.User(phone="9000010002", name="Desk 2", role="helpdesk")])
    db.commit()
    yield db
    db.close()


def resident(db, i):
    return db.scalars(select(m.User).where(m.User.role == "resident")).all()[i]


def helpdesk(db, i=0):
    return db.scalars(select(m.User).where(m.User.role == "helpdesk").order_by(m.User.id)).all()[i]


def test_safety_complaint_goes_to_duty_manager_with_one_hour_timer(cdb):
    c = svc.create_complaint(cdb, resident(cdb, 0), "Lift stuck between floors", NOW, llm=NO_AI)
    assert c.urgency == "critical" and c.safety_escalated and c.assigned_to == helpdesk(cdb, 0).id
    assert c.respond_by == NOW + timedelta(hours=1)
    kinds = {e.kind for e in c.events}
    assert {"created", "safety_escalated", "assigned"} <= kinds


def test_normal_complaints_are_balanced_across_help_desk(cdb):
    a = svc.create_complaint(cdb, resident(cdb, 0), "Water leaking in bathroom", NOW, llm=NO_AI)
    b = svc.create_complaint(cdb, resident(cdb, 1), "Water leaking in kitchen", NOW, llm=NO_AI)
    assert a.assigned_to != b.assigned_to


def test_duplicate_lift_complaints_are_linked_and_never_closed(cdb):
    first = svc.create_complaint(cdb, resident(cdb, 0), "Lift not working in tower 7", NOW, llm=NO_AI)
    second = svc.create_complaint(cdb, resident(cdb, 1), "Lift is not working", NOW + timedelta(hours=1), llm=NO_AI)
    other_tower = svc.create_complaint(cdb, resident(cdb, 2), "Lift is not working", NOW + timedelta(hours=1), llm=NO_AI)
    assert second.duplicate_of_id == first.id and other_tower.duplicate_of_id is None
    hd = helpdesk(cdb)
    svc.set_status(cdb, first, "resolved", hd, NOW)
    assert second.status != "closed"          # linked, never auto-closed


def test_help_desk_can_change_category_in_one_call(cdb):
    c = svc.create_complaint(cdb, resident(cdb, 0), "Something is wrong near my door", NOW, llm=NO_AI)
    assert c.category == "general"
    svc.change_category(cdb, c, "security", helpdesk(cdb), NOW)
    assert c.category == "security" and c.category_overridden
    with pytest.raises(ValueError):
        svc.change_category(cdb, c, "made-up", helpdesk(cdb), NOW)


def test_status_flow_reopen_and_rating(cdb):
    c = svc.create_complaint(cdb, resident(cdb, 0), "Tap leaking in bathroom", NOW, llm=NO_AI)
    hd, res = helpdesk(cdb), resident(cdb, 0)
    with pytest.raises(ValueError):
        svc.rate_and_close(cdb, c, 5, res, NOW)          # not resolved yet
    svc.set_status(cdb, c, "in_progress", hd, NOW)
    assert c.first_response_at == NOW
    svc.set_status(cdb, c, "resolved", hd, NOW)
    svc.set_status(cdb, c, "open", res, NOW)             # reopen
    assert any(e.kind == "reopened" for e in c.events)
    svc.set_status(cdb, c, "resolved", hd, NOW)
    for bad in (0, 6, "5", True):
        with pytest.raises(ValueError):
            svc.rate_and_close(cdb, c, bad, res, NOW)
    svc.rate_and_close(cdb, c, 4, res, NOW)
    assert (c.status, c.rating, c.closed_at) == ("closed", 4, NOW)
    with pytest.raises(ValueError):
        svc.set_status(cdb, c, "open", hd, NOW)          # closed is final


def test_invalid_transition_and_bad_text_rejected(cdb):
    c = svc.create_complaint(cdb, resident(cdb, 0), "Tap leaking in bathroom", NOW, llm=NO_AI)
    with pytest.raises(ValueError):
        svc.set_status(cdb, c, "closed", helpdesk(cdb), NOW)
    with pytest.raises(ValueError):
        svc.create_complaint(cdb, resident(cdb, 0), "hi", NOW, llm=NO_AI)
    with pytest.raises(ValueError):
        svc.create_complaint(cdb, resident(cdb, 0), "x" * 1001, NOW, llm=NO_AI)


def test_staff_without_a_flat_cannot_raise_complaints(cdb):
    with pytest.raises(ValueError):
        svc.create_complaint(cdb, helpdesk(cdb), "Water leaking somewhere", NOW, llm=NO_AI)


def test_assign_only_to_helpdesk(cdb):
    c = svc.create_complaint(cdb, resident(cdb, 0), "Tap leaking in bathroom", NOW, llm=NO_AI)
    with pytest.raises(ValueError):
        svc.assign(cdb, c, resident(cdb, 1).id, helpdesk(cdb), NOW)
    svc.assign(cdb, c, helpdesk(cdb, 1).id, helpdesk(cdb), NOW)
    assert c.assigned_to == helpdesk(cdb, 1).id
