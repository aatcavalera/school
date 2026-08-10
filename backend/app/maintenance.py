import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, text

from app.config import settings
from app.db import SessionLocal, engine
from app.models_multitenant import SyncError, SyncJob, SyncRun


async def run() -> None:
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        removed_runs = (await db.execute(delete(SyncRun).where(
            SyncRun.status == "success", SyncRun.finished_at < now - timedelta(days=settings.sync_success_retention_days)
        ))).rowcount
        removed_jobs = (await db.execute(delete(SyncJob).where(
            SyncJob.status.in_(["success", "dead"]), SyncJob.finished_at < now - timedelta(days=settings.sync_job_retention_days)
        ))).rowcount
        removed_errors = (await db.execute(delete(SyncError).where(
            SyncError.created_at < now - timedelta(days=settings.sync_error_retention_days)
        ))).rowcount
        await db.commit()
    async with engine.connect() as connection:
        await connection.execution_options(isolation_level="AUTOCOMMIT")
        for table in ("synced_student_attendances", "attendance_daily_aggregates", "sync_jobs", "sync_runs"):
            await connection.execute(text(f"ANALYZE {table}"))
    print(f"Maintenance selesai: runs={removed_runs} jobs={removed_jobs} errors={removed_errors}")


if __name__ == "__main__":
    asyncio.run(run())
