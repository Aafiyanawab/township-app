"""Pure billing rules (no database), so they are easy to unit test.

ASSUMPTIONS (see docs/ASSUMPTIONS.md): rate, late-fee rate and allocation order
are not given in the brief except the Rs 6.50/sq ft rate.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

RATE_PER_SQFT = Decimal("6.50")           # from the brief's sample data
LATE_FEE_ANNUAL_RATE = Decimal("0.18")    # ASSUMPTION A1: 18% p.a. simple interest
GRACE_DAYS = 0                            # ASSUMPTION A2: interest starts the day after the due date
DAYS_IN_YEAR = Decimal("365")


def money(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def bill_amount(area_sqft: int, rate: Decimal = RATE_PER_SQFT) -> Decimal:
    if area_sqft <= 0:
        raise ValueError("area_sqft must be positive")
    return money(Decimal(area_sqft) * rate)


def days_overdue(due_on: date, today: date, grace_days: int = GRACE_DAYS) -> int:
    return max(0, (today - due_on).days - grace_days)


def late_fee(outstanding: Decimal, due_on: date, today: date,
             annual_rate: Decimal = LATE_FEE_ANNUAL_RATE) -> Decimal:
    """Simple interest on the outstanding principal for the days overdue.

    ASSUMPTION A3: interest is computed on today's outstanding balance, not on
    each past day's balance. Simple and explainable; noted as a limit in the TDD.
    """
    if outstanding <= 0:
        return Decimal("0.00")
    d = days_overdue(due_on, today)
    return money(outstanding * annual_rate * d / DAYS_IN_YEAR)


def allocate_payment(amount: Decimal, outstanding_oldest_first: list[Decimal]):
    """Apply a payment to bills oldest-first (ASSUMPTION A4).

    Returns (allocations, advance): one amount per bill, plus any money left
    over that becomes an advance credit on the flat's ledger.
    """
    remaining = money(amount)
    if remaining <= 0:
        raise ValueError("payment amount must be positive")
    allocations = []
    for owed in outstanding_oldest_first:
        take = min(remaining, max(owed, Decimal("0")))
        allocations.append(money(take))
        remaining -= take
    return allocations, money(remaining)
