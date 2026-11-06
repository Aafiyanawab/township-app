"""Complaint lifecycle. Endpoints stay thin and call these functions."""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .complaints_ai import CATEGORIES, Candidate, classify_complaint, default_llm, find_duplicate

SLA_HOURS = {"critical": 1, "high": 4, "normal": 24, "low": 48}   # ASSUMPTION A13
TRANSITIONS = {
    "open": {"assigned", "in_progress", "resolved"},
    "assigned": {"in_progress", "resolved"},
    "in_progress": {"resolved", "assigned"},
    "resolved": {"closed", "open"},      # resolved -> open is a reopen
    "closed": set(),
}
ACTIVE = ("open", "assigned", "in_progress")


def _event(db, c, actor_id, kind, detail, now):
    db.add(m.ComplaintEvent(complaint_id=c.id, actor_id=actor_id, kind=kind, detail=detail[:300], at=now))


def pick_assignee(db: Session, safety: bool) -> int | None:
    """Safety goes to the duty manager (ASSUMPTION A14: the lowest-id help-desk user).
    Everything else goes to the help-desk user with the fewest active complaints."""
    staff = db.scalars(select(m.User).where(m.User.role == "helpdesk", m.User.is_active.is_(True))
                       .order_by(m.User.id)).all()
    if not staff:
        return None
    if safety:
        return staff[0].id
    load = dict(db.execute(select(m.Complaint.assigned_to, func.count()).where(
        m.Complaint.status.in_(ACTIVE), m.Complaint.assigned_to.isnot(None)).group_by(m.Complaint.assigned_to)).all())
    return min(staff, key=lambda u: (load.get(u.id, 0), u.id)).id


def create_complaint(db: Session, user: m.User, text: str, now: datetime, llm="default",
                     photo_path: str | None = None) -> m.Complaint:
    text = (text or "").strip()
    if not 5 <= len(text) <= 1000:
        raise ValueError("Complaint must be 5 to 1000 characters")
    if user.flat_id is None:
        raise ValueError("Only residents linked to a flat can raise complaints")
    flat = db.get(m.Flat, user.flat_id)
    result = classify_complaint(text, default_llm() if llm == "default" else llm)

    recent = db.execute(select(m.Complaint, m.Flat.tower).join(m.Flat, m.Flat.id == m.Complaint.flat_id)
                        .where(m.Complaint.status.in_(ACTIVE),
                               m.Complaint.created_at >= now - timedelta(hours=48))).all()
    dup = find_duplicate(result.category, flat.id, flat.tower, now,
                         [Candidate(c.id, c.flat_id, t, c.category, c.created_at, c.duplicate_of_id)
                          for c, t in recent])
    assignee = pick_assignee(db, result.safety_escalated)
    c = m.Complaint(flat_id=flat.id, raised_by=user.id, text=text, photo_path=photo_path,
                    category=result.category, urgency=result.urgency,
                    status="assigned" if assignee else "open", assigned_to=assignee,
                    ai_category=result.category, ai_confidence=result.confidence,
                    safety_escalated=result.safety_escalated, duplicate_of_id=dup,
                    created_at=now, respond_by=now + timedelta(hours=SLA_HOURS[result.urgency]))
    db.add(c)
    db.flush()
    _event(db, c, user.id, "created", text, now)
    if result.safety_escalated:
        _event(db, c, None, "safety_escalated", "Escalated to duty manager by safety rule", now)
    if result.needs_review:
        _event(db, c, None, "needs_review", "AI was unsure; help desk please check the category", now)
    if assignee:
        _event(db, c, None, "assigned", f"Auto-assigned to user {assignee}", now)
    if dup:
        _event(db, c, None, "linked_duplicate", f"Linked to complaint #{dup}", now)
    db.commit()
    return c


def change_category(db: Session, c: m.Complaint, new_category: str, actor: m.User, now: datetime) -> m.Complaint:
    if new_category not in CATEGORIES:
        raise ValueError("Unknown category")
    _event(db, c, actor.id, "category_changed", f"{c.category} -> {new_category}", now)
    c.category, c.category_overridden = new_category, True
    db.commit()
    return c


def assign(db: Session, c: m.Complaint, assignee_id: int, actor: m.User, now: datetime) -> m.Complaint:
    target = db.get(m.User, assignee_id)
    if target is None or target.role != "helpdesk" or not target.is_active:
        raise ValueError("Assignee must be an active help-desk user")
    c.assigned_to = assignee_id
    if c.status == "open":
        c.status = "assigned"
    _event(db, c, actor.id, "assigned", f"Assigned to user {assignee_id}", now)
    db.commit()
    return c


def set_status(db: Session, c: m.Complaint, new_status: str, actor: m.User, now: datetime) -> m.Complaint:
    if new_status not in TRANSITIONS.get(c.status, set()):
        raise ValueError(f"Cannot move a complaint from {c.status} to {new_status}")
    reopened = c.status == "resolved" and new_status == "open"
    if actor.role == "helpdesk" and c.first_response_at is None:
        c.first_response_at = now
    _event(db, c, actor.id, "reopened" if reopened else "status", f"{c.status} -> {new_status}", now)
    c.status = new_status
    if new_status == "closed":
        c.closed_at = now
    db.commit()
    return c


def rate_and_close(db: Session, c: m.Complaint, rating: int, actor: m.User, now: datetime) -> m.Complaint:
    if c.status != "resolved":
        raise ValueError("Only a resolved complaint can be rated and closed")
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
        raise ValueError("Rating must be a whole number from 1 to 5")
    c.rating = rating
    _event(db, c, actor.id, "status", f"resolved -> closed (rated {rating}/5)", now)
    c.status, c.closed_at = "closed", now
    db.commit()
    return c
