"""Seed demo data. DEV ONLY: drops and recreates all tables.

Run from the backend/ folder:  python -m seed.seed
All names and phone numbers are fictional. Demo OTP in mock mode: 123456.
"""
import random
from datetime import date, datetime, timedelta
from decimal import Decimal

from app import models as m
from app.db import Base, SessionLocal, engine
from app.services.billing import bill_amount

TODAY = date(2026, 11, 6)  # fixed so "days overdue" matches the brief's sample rows
random.seed(42)

FIRST = ["Rohan", "Priya", "Anil", "Sunita", "Vikram", "Meera", "Kiran", "Deepa", "Sanjay", "Pooja",
         "Rahul", "Anita", "Manish", "Kavita", "Nitin", "Shweta", "Amit", "Rekha", "Suresh", "Nisha"]
LAST = ["Patil", "Deshmukh", "Kulkarni", "Joshi", "Shaikh", "Pawar", "Gokhale", "Iyer", "Singh", "More"]

SAMPLE = [  # (flat code, resident, area, tenant, paid, due_on, period) from the brief
    ("T07-1203", "Neeraj Kulkarni", 1150, False, Decimal("7475"), date(2026, 11, 10), "2026-11"),
    ("T12-0408", "Swati Joshi", 980, True, Decimal("0"), TODAY - timedelta(days=47), "2026-09"),
    ("T21-1601", "Aamir Shaikh", 1640, False, Decimal("5000"), TODAY - timedelta(days=18), "2026-10"),
]


def add_flat_with_bill(db, code, name, area, tenant, paid, due_on, period, phone, upi):
    flat = m.Flat(code=code, tower=code[:3], area_sqft=area, upi_id=upi)
    db.add(flat)
    db.flush()
    db.add(m.User(phone=phone, name=name, role="resident", flat_id=flat.id, is_tenant=tenant))
    amount = bill_amount(area)
    bill = m.Bill(flat_id=flat.id, period=period, amount=amount, paid_amount=paid,
                  issued_on=date.fromisoformat(period + "-01"), due_on=due_on)
    db.add(bill)
    db.flush()
    db.add(m.LedgerEntry(flat_id=flat.id, kind="bill", amount=amount, entry_date=bill.issued_on,
                         bill_id=bill.id, note=f"Maintenance {period}"))
    if paid > 0:
        pay = m.Payment(flat_id=flat.id, bill_id=bill.id, amount=paid, method="upi", source="manual",
                        reference=f"SEED-{code}", received_on=min(TODAY, due_on))
        db.add(pay)
        db.flush()
        db.add(m.LedgerEntry(flat_id=flat.id, kind="payment", amount=-paid, entry_date=pay.received_on,
                             payment_id=pay.id, note="Payment received"))
    return flat


def run():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()

    # staff (demo accounts)
    staff = [("9000010001", "Help Desk Demo", "helpdesk"), ("9000010002", "Accounts Demo", "accounts"),
             ("9000010003", "Committee Demo", "committee")]
    for phone, name, role in staff:
        db.add(m.User(phone=phone, name=name, role=role))

    flats = {}
    for i, (code, name, area, tenant, paid, due_on, period) in enumerate(SAMPLE, start=1):
        flats[code] = add_flat_with_bill(db, code, name, area, tenant, paid, due_on, period,
                                         phone=f"900002000{i}", upi=f"{name.split()[0].lower()}@okbank")

    # generated flats: mix of paid, partly paid and overdue
    used = set(flats)
    n = 0
    while n < 40:
        tower = 7 if n < 3 else random.randint(1, 28)  # first 3 generated flats sit in Tower 7 (lift complaint cluster)
        floor, unit = random.randint(1, 16), random.randint(1, 4)
        code = f"T{tower:02d}-{floor:02d}{unit:02d}"
        if code in used:
            continue
        used.add(code)
        n += 1
        area = random.choice([850, 920, 980, 1050, 1150, 1280, 1450, 1640])
        name = f"{random.choice(FIRST)} {random.choice(LAST)}"
        amount = bill_amount(area)
        roll = random.random()
        if roll < 0.55:      # paid in full, current month
            paid, due_on, period = amount, date(2026, 11, 10), "2026-11"
        elif roll < 0.75:    # current month, not yet paid
            paid, due_on, period = Decimal("0"), date(2026, 11, 10), "2026-11"
        elif roll < 0.9:     # October, partly paid, overdue
            paid, due_on, period = (amount / 2).quantize(Decimal("1")), date(2026, 10, 10), "2026-10"
        else:                # October, unpaid, overdue
            paid, due_on, period = Decimal("0"), date(2026, 10, 10), "2026-10"
        flats[code] = add_flat_with_bill(db, code, name, area, False, paid, due_on, period,
                                         phone=f"90003{n:05d}", upi=f"{name.split()[0].lower()}{n}@okbank")
    db.flush()

    # complaints: the brief's water leak, a lift cluster (duplicates), and a mix
    helpdesk = db.query(m.User).filter_by(role="helpdesk").one()
    swati = db.query(m.User).filter_by(phone="9000020002").one()
    now = datetime(2026, 11, 6, 9, 0)

    def complaint(flat_code, user, text, category, urgency, status, hours_ago, **kw):
        c = m.Complaint(flat_id=flats[flat_code].id, raised_by=user.id, text=text, category=category,
                        urgency=urgency, status=status, created_at=now - timedelta(hours=hours_ago),
                        respond_by=now - timedelta(hours=hours_ago) + timedelta(hours=4), **kw)
        db.add(c)
        db.flush()
        db.add(m.ComplaintEvent(complaint_id=c.id, actor_id=user.id, kind="created", detail=text[:200]))
        return c

    complaint("T12-0408", swati, "Water leaking from the bathroom ceiling since yesterday", "plumbing",
              "high", "open", 20, ai_category="plumbing", ai_confidence=92)
    lift = complaint("T07-1203", db.query(m.User).filter_by(phone="9000020001").one(),
                     "Lift stuck between floors in Tower 7", "lift", "critical", "assigned", 5,
                     ai_category="lift", ai_confidence=95, safety_escalated=True, assigned_to=helpdesk.id)
    others = [f for f in flats if f.startswith("T07") and f != "T07-1203"][:3]
    for code in others:
        u = db.query(m.User).filter_by(flat_id=flats[code].id).first()
        if u:
            complaint(code, u, "Lift not working in tower 7", "lift", "high", "open", 4,
                      ai_category="lift", ai_confidence=88, duplicate_of_id=lift.id)
    db.commit()
    db.close()
    print(f"Seeded {len(flats)} flats. Staff logins: 9000010001 (helpdesk), 9000010002 (accounts), "
          "9000010003 (committee). Demo OTP: 123456")


if __name__ == "__main__":
    run()
