from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.job_queue import DEFAULT_INTERVALS, enqueue
from app.models_multitenant import School, SyncJob, SyncRun
from app.security import get_current_username
from app.access import CurrentUser, accessible_school_ids, get_current_user, require_school_access
from app.models_multitenant import AuditLog

router = APIRouter(prefix="/api/sync", tags=["sync"])


class EnqueueRequest(BaseModel):
    school_id: str
    domain: str
    scope: dict = Field(default_factory=dict)


@router.get("/schools")
async def schools(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed = await accessible_school_ids(db, user)
    rows = (await db.execute(select(School).where(School.id.in_(allowed)).order_by(School.name))).scalars().all()
    return [{"id": row.id, "code": row.code, "name": row.name, "is_active": row.is_active} for row in rows]


@router.post("/enqueue")
async def enqueue_sync(payload: EnqueueRequest, user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if payload.domain not in DEFAULT_INTERVALS:
        raise HTTPException(status_code=400, detail="Domain sinkronisasi belum didukung")
    if await db.get(School, payload.school_id) is None:
        raise HTTPException(status_code=404, detail="Sekolah tidak ditemukan")
    await require_school_access(db, user, payload.school_id)
    job_id = await enqueue(payload.school_id, payload.domain, payload.scope, priority=20)
    db.add(AuditLog(user_id=user.id, school_id=payload.school_id, action="sync.enqueue", details={"domain": payload.domain, "job_id": job_id}))
    await db.commit()
    return {"ok": True, "job_id": job_id}


@router.get("/jobs")
async def jobs(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed = await accessible_school_ids(db, user)
    rows = (await db.execute(select(SyncJob).where(SyncJob.school_id.in_(allowed)).order_by(desc(SyncJob.created_at)).limit(100))).scalars().all()
    return [
        {
            "id": row.id, "school_id": row.school_id, "domain": row.domain, "status": row.status,
            "attempts": row.attempts, "run_after": row.run_after.isoformat(),
            "created_at": row.created_at.isoformat(), "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "last_error": row.last_error,
        }
        for row in rows
    ]


@router.get("/runs")
async def runs(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed = await accessible_school_ids(db, user)
    rows = (await db.execute(select(SyncRun).where(SyncRun.school_id.in_(allowed)).order_by(desc(SyncRun.started_at)).limit(100))).scalars().all()
    return [
        {
            "id": row.id, "school_id": row.school_id, "domain": row.domain, "status": row.status,
            "started_at": row.started_at.isoformat(), "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "rows_seen": row.rows_seen, "rows_inserted": row.rows_inserted,
            "rows_updated": row.rows_updated, "rows_unchanged": row.rows_unchanged,
            "error_summary": row.error_summary,
        }
        for row in rows
    ]
