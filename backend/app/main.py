from contextlib import asynccontextmanager
from html import escape
import json
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import get_current_user
from .config import settings
from .db import ensure_demo_data
from .models import User
from .routers import accounts, auth, complaints, health, helpdesk, resident


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_demo_data()
    yield


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(status_code=500, content={"detail": "Internal server error"})
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app = FastAPI(title="Township API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityHeadersMiddleware)
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


@app.get("/openapi.json", include_in_schema=False)
def protected_openapi(_user: Annotated[User, Depends(get_current_user)]):
    return app.openapi()


@app.get("/docs", include_in_schema=False, response_class=HTMLResponse)
def protected_docs(_user: Annotated[User, Depends(get_current_user)]):
    spec = escape(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
    return HTMLResponse(
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Township API</title>"
        "<h1>Township API</h1><p>Authenticated API schema</p><pre>" + spec + "</pre></html>"
    )


@app.get("/redoc", include_in_schema=False)
def protected_redoc(_user: Annotated[User, Depends(get_current_user)]):
    return RedirectResponse("/docs", status_code=307)


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
