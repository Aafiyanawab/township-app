# Assumptions (each one is also labelled in the TDD)

- A1: Late fee is 18% per year simple interest. The brief says "per bye-laws" but does not give a rate.
- A2: Interest starts the day after the due date (no grace period). Easy to change: `GRACE_DAYS`.
- A3: Interest is calculated on today's outstanding balance, not on each past day's balance.
- A4: A payment is applied to the oldest bill first. Any extra becomes an advance credit.
- A5: Bills are issued on the 1st and due on the 10th ("most bills are paid in the first 10 days").
- A6: Sample "days overdue" values (47 and 18) are reproduced by fixing the seed date to 6 Nov 2026.
- A7: SMS OTP is mocked. In mock mode the OTP is always 123456 (demo only, never in production).
- A8: All names, phone numbers and UPI IDs in the seed data are fictional.
- A9: A payment that clears the principal also settles the accrued late fee. Late fee is not stored separately.
- A10: Matching weights are reference 60, UPI ID 30, amount 20. Auto-post needs a score of 80 or more.
- A11: Rows with a score of 40 to 79, or with conflicting signals, go to the accounts queue. Below 40 they are shown as unmatched.
- A12: Bank CSV columns are date, description, reference, upi_id, amount (credit positive, debit negative).
