from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import ensure_demo_data
from .routers import accounts, auth, complaints, health, helpdesk, resident


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_demo_data()
    yield


app = FastAPI(title="Township API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(helpdesk.router)
app.include_router(resident.router)
app.include_router(accounts.router)
app.include_router(complaints.router)
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
