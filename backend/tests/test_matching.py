from datetime import date
from decimal import Decimal

from app.services.matching import BankRowIn, FlatInfo, extract_flat_codes, match_batch

D = Decimal


def flat(id, code, upi=None, outs=("0",), fee="0"):
    return FlatInfo(id=id, code=code, upi_id=upi, outstanding_by_bill=tuple(D(o) for o in outs),
                    late_fee_total=D(fee))


def row(amount, ref="", desc="", upi=""):
    return BankRowIn(date(2026, 11, 5), desc, ref, upi, D(amount))


A = flat(1, "T12-0408", "swati@okbank", ("6370",), "147.64")
B = flat(2, "T21-1601", "aamir@okbank", ("5660",), "50.24")


def one(r, flats=(A, B)):
    return match_batch([r], list(flats))[0]


def test_reference_normalisation():
    for text in ("T12-0408", "t120408", "pay T12 0408 sep", "T12-0408MAINT"):
        assert extract_flat_codes(text) == {"T12-0408"}
    assert extract_flat_codes("T12-04088") == set()


def test_reference_upi_and_amount_auto_posts():
    r = one(row("6370", ref="T12-0408", upi="swati@okbank"))
    assert (r.status, r.flat_id, r.confidence) == ("matched", 1, 100)


def test_reference_and_amount_auto_posts():
    assert one(row("5660", ref="T21-1601")).status == "matched"


def test_upi_is_case_insensitive():
    assert one(row("6370", ref="T12-0408", upi="SWATI@OKBANK")).confidence == 100


def test_upi_and_amount_only_goes_to_queue_with_suggestion():
    r = one(row("6370", ref="maintenance", upi="swati@okbank"))
    assert (r.status, r.flat_id) == ("queued", 1)


def test_reference_only_goes_to_queue():
    r = one(row("1000", ref="T12-0408"))
    assert (r.status, r.flat_id, r.confidence) == ("queued", 1, 60)


def test_amount_only_is_unmatched_and_never_posted():
    r = one(row("6370"))
    assert r.status == "unmatched" and r.confidence == 20


def test_typo_in_reference_is_unmatched():
    assert one(row("6370", ref="T12-0480")).status == "unmatched"


def test_conflicting_signals_are_queued_not_posted():
    r = one(row("5660", ref="T21-1601", upi="swati@okbank"))
    assert r.status == "queued" and "Conflicting" in r.reason


def test_debit_rows_are_ignored():
    assert one(row("-1200", desc="BANK CHARGES")).status == "ignored"
    assert one(row("0")).status == "ignored"


def test_amount_above_what_flat_owes_is_queued():
    r = one(row("9000", ref="T12-0408", upi="swati@okbank"))
    assert r.status == "queued" and "more than the flat owes" in r.reason


def test_fully_paid_flat_never_auto_posts():
    paid = flat(3, "T07-1203", "neeraj@okbank", outs=())
    assert one(row("7475", ref="T07-1203", upi="neeraj@okbank"), flats=(paid,)).status == "queued"


def test_second_payment_for_same_bill_in_one_file_is_queued():
    rows = [row("6370", ref="T12-0408", upi="swati@okbank"), row("6370", ref="T12-0408", upi="swati@okbank")]
    first, second = match_batch(rows, [A, B])
    assert first.status == "matched" and second.status == "queued"


def test_payment_of_principal_plus_late_fee_is_recognised():
    assert one(row("6517.64", ref="T12-0408")).status == "matched"
