from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import CurrentUser, accessible_school_ids, get_current_user
from app.db import get_db
from app.models_multitenant import (
    School, SyncCheckpoint, SyncError, SyncJob, SyncRun, SyncedClass,
    SyncedDomainRecord, SyncedStudent, SyncedStudentAttendance, SyncedSubject, SyncedTeacher,
)
from app.telemetry import telemetry

router = APIRouter(prefix="/api/operations", tags=["operations"])


@router.get("/status")
async def status(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed = await accessible_school_ids(db, user)
    now = datetime.now(timezone.utc)
    queue_rows = (await db.execute(select(SyncJob.status, func.count()).where(
        SyncJob.school_id.in_(allowed)
    ).group_by(SyncJob.status))).all()
    queue = {name: int(count) for name, count in queue_rows}
    checkpoints = (await db.execute(select(SyncCheckpoint).where(
        SyncCheckpoint.school_id.in_(allowed)
    ))).scalars().all()
    alerts = []
    for row in checkpoints:
        if not row.last_success_at or now - row.last_success_at > timedelta(hours=12):
            alerts.append({
                "severity": "warning", "school_id": row.school_id, "domain": row.domain,
                "message": "Sinkronisasi terlambat lebih dari 12 jam",
            })
    dead = queue.get("dead", 0)
    queued = queue.get("queued", 0)
    if dead:
        alerts.append({"severity": "critical", "message": f"{dead} job masuk dead-letter"})
    if queued > 50:
        alerts.append({"severity": "warning", "message": f"Antrean menumpuk: {queued} job"})
    recent_errors = int((await db.execute(select(func.count()).select_from(SyncError).where(
        SyncError.school_id.in_(allowed), SyncError.created_at >= now - timedelta(hours=24)
    ))).scalar_one())
    if recent_errors >= 5:
        alerts.append({"severity": "critical", "message": f"{recent_errors} sync error dalam 24 jam"})

    db_size = int((await db.execute(text("select pg_database_size(current_database())"))).scalar_one())
    return {
        "generated_at": now.isoformat(), "telemetry": telemetry.snapshot(),
        "queue": queue, "recent_sync_errors": recent_errors,
        "database_bytes": db_size, "alerts": alerts,
    }


@router.get("/storage")
async def storage(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed = await accessible_school_ids(db, user)
    schools = (await db.execute(select(School).where(School.id.in_(allowed)).order_by(School.name))).scalars().all()
    models = [SyncedStudent, SyncedTeacher, SyncedClass, SyncedSubject, SyncedStudentAttendance, SyncedDomainRecord, SyncRun, SyncJob, SyncError]
    rows = []
    for school in schools:
        counts = {}
        for model in models:
            counts[model.__tablename__] = int((await db.execute(select(func.count()).select_from(model).where(model.school_id == school.id))).scalar_one())
        rows.append({"school_id": school.id, "school_name": school.name, "row_counts": counts, "total_rows": sum(counts.values())})
    relation_rows = (await db.execute(text("""
        select relname, pg_total_relation_size(quote_ident(relname)::regclass)
        from pg_stat_user_tables
        where relname like 'synced_%' or relname in ('sync_runs','sync_jobs','sync_errors','attendance_daily_aggregates')
        order by 2 desc
    """))).all()
    return {"tenants": rows, "relations": [{"name": name, "bytes": int(size)} for name, size in relation_rows]}
