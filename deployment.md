# deployment.md

Township: gated township resident app (client brief 5).

- GitHub: https://github.com/Aafiyanawab/township-app
- Live app: https://township-app-rng1.onrender.com/#/login

> The live app runs on Render's free plan. After inactivity it sleeps, so the first load can take about a minute. Its demo data is re-seeded on every start, so payments and complaints you create may disappear after a restart.

## 1. Run it locally

Requirements: Python 3.12, Node.js 20, Git. Docker is optional (only for local PostgreSQL).

**Backend** (from the repository root):

```bash
cd backend
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env        # Windows: Copy-Item ..\.env.example .env
python -m seed.seed            # creates the demo data (DEV ONLY: it drops and recreates tables)
uvicorn app.main:app --reload  # API on http://localhost:8000
```

With no `DATABASE_URL`, the backend uses a local SQLite file (`dev.db`). To use PostgreSQL instead, run `docker compose up -d db` from the repository root and set `DATABASE_URL` in `.env` (see `.env.example`).

**Frontend** (second terminal):

```bash
cd frontend
npm ci
npm run dev                    # http://localhost:5173
```

In development the frontend calls `http://localhost:8000` (set in `frontend/.env.development`). Open http://localhost:5173 and sign in with a demo login below.

**Tests and checks:**

```bash
cd backend && pytest -q
cd frontend && npm run lint && npm run build
```

The backend tests build their own temporary database, so no manual seeding is needed.

Note: the API docs (`/docs`) require a login token, by design. The route list is in the TDD.

## 2. How it is deployed

One Docker web service on Render (free plan, Singapore region). The root `Dockerfile` is multi-stage: Node builds the frontend, then a Python image runs FastAPI, which serves both the API and the built frontend from one URL, so there is no CORS setup in production. It runs as a non-root user without `--reload`. `render.yaml` describes the service, health check path `/health`, and the environment variable names. Every push to `main` redeploys automatically. GitHub Actions runs the backend tests and the frontend lint and build on every push.

The free plan uses SQLite that resets on restart. With `SEED_ON_START=true`, the app creates the tables and loads the demo data only if the database is empty. The seed on start never drops tables.

## 3. Environment variables (names only)

| Name | Purpose |
|---|---|
| `ENV` | `production` on Render; production refuses to start with a weak JWT secret |
| `JWT_SECRET` | Secret used to sign login tokens (long random string) |
| `JWT_EXPIRE_MINUTES` | Token lifetime in minutes |
| `OTP_MODE` | `mock` (demo OTP is accepted) |
| `DATABASE_URL` | Database connection string; leave empty to use SQLite |
| `SEED_ON_START` | `true` to load demo data when the database is empty |
| `CORS_ORIGINS` | Allowed browser origins (needed only if the frontend is hosted separately) |
| `GEMINI_API_KEY` | Optional. Enables the LLM for complaint classification; without it the keyword rules are used |
| `ANTHROPIC_API_KEY` | Optional alternative LLM provider; leave empty |
| `GEMINI_MODEL` | Optional model name override |
| `VITE_API_URL` | Frontend build setting: `http://localhost:8000` in development, empty in production |

Values are set in the Render dashboard or a local `.env` file. `.env` is git-ignored and no secrets are committed.

## 4. Demo logins for the reviewer

Sign in with a phone number, then the OTP **123456** (mock OTP, demo only). All names and numbers are fictional.

| Role | Phone | What to try |
|---|---|---|
| Resident (tenant, overdue bill and a complaint) | `9000020002` | Dues with late fee, test payment, raise a complaint |
| Resident | `9000020001` | Paid bill, lift complaint |
| Resident (bill still unpaid) | `9000300007` | Pay a bill and see the receipt and ledger |
| Help desk | `9000010001` | Complaint queue, change category, assign, status |
| Accounts | `9000010002` | Upload a bank CSV, review the queue, resolve or ignore |
| Committee | `9000010003` | Collections, dues ageing, complaint times |

Try this: sign in as accounts, download the sample CSV on the Accounts screen and upload it. Expected on fresh data: 2 posted, 3 queued, 2 unmatched, 1 ignored. Uploading the same file again reports 8 duplicates skipped. Then sign in as resident `9000020002` and see the bill paid.

Safety rule: as a resident, raise "Lift stuck between floors" and it shows as Critical.

OTP requests are rate-limited (5 per minute per phone). If you see "too many attempts", wait a minute.