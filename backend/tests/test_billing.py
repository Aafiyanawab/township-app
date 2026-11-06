from datetime import date
from decimal import Decimal

import pytest

from app.services.billing import (allocate_payment, bill_amount, days_overdue,
                                  late_fee)

TODAY = date(2026, 11, 6)


# Sample rows from the brief (rate Rs 6.50 per sq ft)
@pytest.mark.parametrize("area,expected", [(1150, "7475.00"), (980, "6370.00"), (1640, "10660.00")])
def test_bill_amount_matches_brief_samples(area, expected):
    assert bill_amount(area) == Decimal(expected)


def test_bill_amount_rejects_bad_area():
    with pytest.raises(ValueError):
        bill_amount(0)


def test_days_overdue_matches_brief_samples():
    assert days_overdue(date(2026, 9, 20), TODAY) == 47   # T12-0408
    assert days_overdue(date(2026, 10, 19), TODAY) == 18  # T21-1601


def test_not_overdue_has_no_late_fee():
    assert late_fee(Decimal("7475"), date(2026, 11, 10), TODAY) == Decimal("0.00")


def test_fully_paid_has_no_late_fee():
    assert late_fee(Decimal("0"), date(2026, 9, 20), TODAY) == Decimal("0.00")


def test_late_fee_on_partial_payment_sample():
    # T21-1601: 10660 billed, 5000 paid -> 5660 outstanding, 18 days overdue
    assert late_fee(Decimal("5660"), date(2026, 10, 19), TODAY) == Decimal("50.24")


def test_allocation_oldest_first_and_partial():
    allocs, advance = allocate_payment(Decimal("8000"), [Decimal("6370"), Decimal("7475")])
    assert allocs == [Decimal("6370.00"), Decimal("1630.00")]
    assert advance == Decimal("0.00")


def test_overpayment_becomes_advance():
    allocs, advance = allocate_payment(Decimal("10000"), [Decimal("7475")])
    assert allocs == [Decimal("7475.00")]
    assert advance == Decimal("2525.00")


def test_zero_payment_rejected():
    with pytest.raises(ValueError):
        allocate_payment(Decimal("0"), [Decimal("100")])
