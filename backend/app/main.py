import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app.config import settings
from app.db import engine
from app.routers import admin_users, analytics, auth, dashboard, import_data, operations, settings_router, sync_admin
from app.telemetry import telemetry
from app.logging_config import configure_logging

configure_logging(settings.log_level)
logger = logging.getLogger("school.api")

app = FastAPI(title="Portal Analitik School")

app.add_middleware(
    CORSMiddleware,
    # Browser traffic is same-origin through the Next.js /api rewrite. The
    # backend is internal-only, so cross-origin browser access is unnecessary.
    allow_origins=[],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(operations.router)
app.include_router(import_data.router)
app.include_router(settings_router.router)
app.include_router(sync_admin.router)
app.include_router(admin_users.router)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    telemetry.observe_request(request.method, request.url.path, response.status_code, duration_ms)
    logger.info(
        "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/health/live")
async def liveness():
    return {"status": "ok", "service": "backend"}


@app.get("/api/health/ready")
async def readiness():
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
