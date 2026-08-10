"""Run a controlled foreground sync for one school (bootstrap/diagnostics)."""

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
        raise SystemExit(f"Sekolah tidak ditemukan: {code}")
    service = SyncService()
    for domain in ("school_years", "classes", "teachers", "subjects", "students", "student_attendance_summary"):
        run_id = await service.sync(school_id, domain)
        print(f"Sync selesai: domain={domain} run_id={run_id}")


if __name__ == "__main__":
    asyncio.run(main())
