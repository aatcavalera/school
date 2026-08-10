import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.importer import import_workbook
from app.models import ImportLog
from app.security import get_current_username

router = APIRouter(prefix="/api/import", tags=["import"])


@router.post("/upload")
async def upload_and_import(
    file: UploadFile = File(...),
    username: str = Depends(get_current_username),
    db: AsyncSession = Depends(get_db),
):
    if not settings.allow_legacy_import:
        raise HTTPException(status_code=410, detail="Import Excel legacy dinonaktifkan; data berasal dari sinkronisasi School ID")
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="File harus berformat .xlsx")

    os.makedirs(settings.upload_tmp_dir, exist_ok=True)
    tmp_path = os.path.join(settings.upload_tmp_dir, f"{uuid.uuid4().hex}.xlsx")

    try:
        with open(tmp_path, "wb") as f:
            f.write(await file.read())

        counts = await import_workbook(db, tmp_path)

        log = ImportLog(
            filename=file.filename,
            rows_students=counts["students"],
            rows_attendance=counts["attendance"],
            rows_calendar=counts["calendar"],
            status="success",
            message=f"Diimpor oleh {username}",
        )
        db.add(log)
        await db.commit()
        return {"ok": True, "counts": counts}
    except Exception as exc:
        await db.rollback()
        log = ImportLog(filename=file.filename, status="failed", message=str(exc)[:500])
        db.add(log)
        await db.commit()
        raise HTTPException(status_code=400, detail=f"Gagal memproses file: {exc}")
    finally:
        # File sumber tidak pernah disimpan permanen - hanya data hasil parsing yang disimpan di DB.
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.get("/history")
async def import_history(username: str = Depends(get_current_username), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ImportLog).order_by(desc(ImportLog.imported_at)).limit(20))
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "filename": l.filename,
            "imported_at": l.imported_at.isoformat(),
            "rows_students": l.rows_students,
            "rows_attendance": l.rows_attendance,
            "rows_calendar": l.rows_calendar,
            "status": l.status,
            "message": l.message,
        }
        for l in logs
    ]
