import asyncio
import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models_multitenant import School
from app.sync_service import SyncService


async def main() -> None:
    code = os.environ.get("SCHOOL_CODE", "pilot-001")
    async with SessionLocal() as db:
        school_id = (await db.execute(select(School.id).where(School.code == code))).scalar_one_or_none()
    if not school_id:
        raise SystemExit("Sekolah tidak ditemukan")
    scope = {key: value for key, value in {
        "start_date": os.environ.get("SYNC_START_DATE"), "end_date": os.environ.get("SYNC_END_DATE")
    }.items() if value}
    run_id = await SyncService().sync(school_id, "student_attendance_daily", scope)
    print(f"Backfill selesai: run_id={run_id}")


if __name__ == "__main__":
    asyncio.run(main())
