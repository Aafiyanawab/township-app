# Project context
Take-home: gated township resident app (brief 5). Stack: FastAPI + SQLAlchemy (backend/), React + TypeScript + Vite + Tailwind (frontend/), PostgreSQL in prod, SQLite in dev.

## Rules
- Roles: resident, helpdesk, accounts, committee. Check role and ownership on the SERVER for every endpoint (a resident can only see their own flat).
- Money is Decimal, never float. Rates and late-fee logic live in backend/app/services/billing.py. Do not change those rules.
- Validate all input with Pydantic. No secrets in code; read config from app/config.py.
- OTP login is mocked: OTP is always 123456 when OTP_MODE=mock. Issue a JWT with a role claim.
- Bank rows are never posted to a flat automatically unless status == "matched". Unclear rows go to the accounts queue.
- Complaint safety words (fire, gas, lift stuck, shock) always escalate by rule, whatever the AI says. Duplicates are linked, never closed.
- Write pytest tests for new logic. Run `pytest -q` in backend/ before finishing.
- Design: minimal, white space, restrained palette, mobile-first, with loading, empty and error states.
- Small commits with clear messages.