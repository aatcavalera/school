import asyncio
import hashlib
import os
import socket
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select

from app.config import settings
from app.db import SessionLocal
from app.models_multitenant import School, SchoolSyncSetting, SyncJob
from app.sync_service import SyncService


DEFAULT_INTERVALS = {
    "school_years": 21600,
    "classes": 21600,
    "teachers": 21600,
    "subjects": 21600,
    "students": 21600,
    "schedules": 21600,
    "student_attendance_summary": 300,
    "student_attendance_daily": 300,
    "class_attendances": 300,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def attendance_window_open(school: School, now: datetime) -> bool:
    local = now.astimezone(ZoneInfo(school.timezone or "Asia/Makassar"))
    weekdays = {int(value) for value in settings.attendance_sync_weekdays.split(",") if value.strip().isdigit()}
    current = local.strftime("%H:%M")
    return local.weekday() in weekdays and settings.attendance_sync_start_local <= current <= settings.attendance_sync_end_local


async def enqueue(school_id: str, domain: str, scope: dict | None = None, *, priority: int = 100, bucket: str | None = None):
    scope = scope or {}
    identity = json_key(scope)
    dedup_key = f"{school_id}:{domain}:{identity}:{bucket or os.urandom(8).hex()}"
    async with SessionLocal() as db:
        existing = (await db.execute(select(SyncJob.id).where(SyncJob.dedup_key == dedup_key))).scalar_one_or_none()
        if existing:
            return existing
        job = SyncJob(school_id=school_id, domain=domain, scope=scope, dedup_key=dedup_key, priority=priority)
        db.add(job)
        await db.commit()
        return job.id


def json_key(scope: dict) -> str:
    raw = repr(sorted(scope.items())).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


async def schedule_due_jobs() -> int:
    now = utcnow()
    queued = 0
    async with SessionLocal() as db:
        schools = (await db.execute(select(School).where(School.is_active.is_(True)))).scalars().all()
        settings_rows = (await db.execute(select(SchoolSyncSetting).where(SchoolSyncSetting.enabled.is_(True)))).scalars().all()
    settings_map = {(row.school_id, row.domain): row for row in settings_rows}
    for school in schools:
        for domain, default_interval in DEFAULT_INTERVALS.items():
            if domain in {"student_attendance_summary", "student_attendance_daily", "class_attendances"} and not attendance_window_open(school, now):
                continue
            row = settings_map.get((school.id, domain))
            interval = row.interval_seconds if row else default_interval
            priority = row.priority if row else (10 if domain == "school_years" else 100)
            bucket = str(int(now.timestamp()) // max(interval, 60))
            await enqueue(school.id, domain, priority=priority, bucket=bucket)
            queued += 1
    return queued


async def claim(worker_id: str) -> SyncJob | None:
    now = utcnow()
    stale = now - timedelta(minutes=15)
    async with SessionLocal() as db:
        async with db.begin():
            stmt = (
                select(SyncJob)
                .where(
                    or_(
                        and_(SyncJob.status == "queued", SyncJob.run_after <= now),
                        and_(SyncJob.status == "running", SyncJob.locked_at < stale),
                    )
                )
                .order_by(SyncJob.priority, SyncJob.run_after)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            job = (await db.execute(stmt)).scalar_one_or_none()
            if job:
                job.status = "running"
                job.locked_at = now
                job.locked_by = worker_id
                job.attempts += 1
        return job


async def finish(job_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(SyncJob, job_id)
        job.status, job.finished_at, job.locked_at, job.locked_by = "success", utcnow(), None, None
        await db.commit()


async def fail(job_id: str, message: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(SyncJob, job_id)
        job.last_error = message[:500]
        job.locked_at = job.locked_by = None
        if job.attempts >= job.max_attempts:
            job.status, job.finished_at = "dead", utcnow()
        else:
            job.status = "queued"
            job.run_after = utcnow() + timedelta(seconds=min(300, 2 ** job.attempts * 5))
        await db.commit()


async def worker_loop() -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    service = SyncService()
    while True:
        job = await claim(worker_id)
        if job is None:
            await asyncio.sleep(settings.sync_poll_seconds)
            continue
        try:
            await service.sync(job.school_id, job.domain, job.scope)
            await finish(job.id)
        except Exception as exc:
            await fail(job.id, f"{type(exc).__name__}: {exc}")


async def scheduler_loop() -> None:
    while True:
        await schedule_due_jobs()
        await asyncio.sleep(60)


async def main() -> None:
    mode = os.environ.get("SYNC_PROCESS", "worker")
    if mode == "scheduler":
        await scheduler_loop()
    else:
        await worker_loop()


if __name__ == "__main__":
    asyncio.run(main())
