"""Bank statement row -> flat matching. Pure logic, no database, easy to test.

Signals and weights (ASSUMPTIONS A10-A12 in docs/ASSUMPTIONS.md):
  reference/description names the flat code   +60
  UPI ID equals the flat's registered UPI ID  +30
  amount equals something the flat owes       +20

Decision rules (conservative on purpose: unclear money is never posted automatically):
  * credits only; debits and zero rows are 'ignored'
  * best score < 40                           -> 'unmatched'
  * a second, different flat scores >= 30     -> 'queued' (conflicting signals)
  * best score >= 80                          -> 'matched' (auto-post), unless the amount
                                                 is more than the flat still owes -> 'queued'
  * otherwise                                 -> 'queued' with the best flat as a suggestion
"""
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .billing import money

REF_WEIGHT = 60
UPI_WEIGHT = 30
AMOUNT_WEIGHT = 20
AUTO_POST_MIN = 80
QUEUE_MIN = 40
CONFLICT_MIN = 30

# T12-0408, T120408, "T12 0408" all normalise to T12-0408
_FLAT_CODE = re.compile(r"(?<![A-Za-z0-9])T\s?(\d{2})\s?-?\s?(\d{4})(?!\d)", re.I)


def extract_flat_codes(text: str) -> set[str]:
    return {f"T{a}-{b}" for a, b in _FLAT_CODE.findall(text or "")}


@dataclass(frozen=True)
class BankRowIn:
    txn_date: date
    description: str
    reference: str
    upi_id: str
    amount: Decimal


@dataclass(frozen=True)
class FlatInfo:
    id: int
    code: str
    upi_id: str | None = None
    outstanding_by_bill: tuple = ()          # unpaid principal of each open bill
    late_fee_total: Decimal = Decimal("0")   # accrued late fee as of the import date

    @property
    def principal_total(self) -> Decimal:
        return sum(self.outstanding_by_bill, Decimal("0"))

    @property
    def dues(self) -> Decimal:
        return self.principal_total + self.late_fee_total

    def amount_ok(self, amount: Decimal) -> bool:
        if self.principal_total <= 0:
            return False
        candidates = {money(x) for x in self.outstanding_by_bill}
        candidates |= {money(self.principal_total), money(self.dues)}
        return money(amount) in candidates


@dataclass(frozen=True)
class MatchResult:
    status: str                 # matched | queued | unmatched | ignored
    flat_id: int | None
    confidence: int
    reason: str


def score_flat(row: BankRowIn, flat: FlatInfo) -> tuple[int, list[str]]:
    score, why = 0, []
    if flat.code in extract_flat_codes(f"{row.reference} {row.description}"):
        score += REF_WEIGHT
        why.append(f"reference names {flat.code}")
    if row.upi_id and flat.upi_id and row.upi_id.strip().casefold() == flat.upi_id.strip().casefold():
        score += UPI_WEIGHT
        why.append("UPI ID matches")
    if flat.amount_ok(row.amount):
        score += AMOUNT_WEIGHT
        why.append("amount matches what the flat owes")
    return min(score, 100), why  # signals can sum to 110; confidence is capped at 100


def match_batch(rows: list[BankRowIn], flats: list[FlatInfo]) -> list[MatchResult]:
    """Match rows in file order. Scores use the dues snapshot, and an auto-post
    is only allowed while the flat still owes at least that amount, so two
    payments for the same bill in one file cannot both be auto-posted."""
    remaining = {f.id: f.dues for f in flats}
    results: list[MatchResult] = []

    for row in rows:
        if row.amount <= 0:
            results.append(MatchResult("ignored", None, 0, "Debit or zero amount, not a payment received"))
            continue

        scored = []
        for f in flats:
            s, why = score_flat(row, f)
            if s > 0:
                scored.append((s, f, why))
        scored.sort(key=lambda t: (-t[0], t[1].code))

        if not scored or scored[0][0] < QUEUE_MIN:
            best = f" (weak hint: {scored[0][1].code}, score {scored[0][0]})" if scored else ""
            results.append(MatchResult("unmatched", None, scored[0][0] if scored else 0,
                                       "No reliable reference or UPI ID" + best))
            continue

        top_s, top_f, top_why = scored[0]
        reason = f"{top_f.code}: " + ", ".join(top_why)

        if len(scored) > 1 and scored[1][0] >= CONFLICT_MIN and scored[1][1].id != top_f.id:
            results.append(MatchResult(
                "queued", top_f.id, top_s,
                f"Conflicting signals: {top_f.code} (score {top_s}) vs {scored[1][1].code} (score {scored[1][0]})"))
        elif top_s >= AUTO_POST_MIN:
            if row.amount > remaining[top_f.id]:
                results.append(MatchResult("queued", top_f.id, top_s,
                                           f"{reason}; but amount is more than the flat owes"))
            else:
                remaining[top_f.id] -= row.amount
                results.append(MatchResult("matched", top_f.id, top_s, reason))
        else:
            results.append(MatchResult("queued", top_f.id, top_s,
                                       f"Partial evidence, needs review. {reason}"))
    return results
