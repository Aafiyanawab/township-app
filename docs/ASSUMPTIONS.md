# Assumptions (each one is also labelled in the TDD)

- A1: Late fee is 18% per year simple interest. The brief says "per bye-laws" but does not give a rate.
- A2: Interest starts the day after the due date (no grace period). Easy to change: `GRACE_DAYS`.
- A3: Interest is calculated on today's outstanding balance, not on each past day's balance.
- A4: A payment is applied to the oldest bill first. Any extra becomes an advance credit.
- A5: Bills are issued on the 1st and due on the 10th ("most bills are paid in the first 10 days").
- A6: Sample "days overdue" values (47 and 18) are reproduced by fixing the seed date to 6 Nov 2026.
- A7: SMS OTP is mocked. In mock mode the OTP is always 123456 (demo only, never in production).
- A8: All names, phone numbers and UPI IDs in the seed data are fictional.
