# Township: resident app for maintenance, complaints and visitors

Take-home build (brief 5). Stack: React + Vite + Tailwind (PWA), FastAPI, PostgreSQL.

## Quick start
```bash
docker compose up -d db
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Frontend: see `frontend/` (created with `npm create vite@latest frontend -- --template react-ts`).
