import asyncio
from sqlalchemy import func, select

from app.aggregates import refresh_attendance_aggregates
from app.db import SessionLocal
from app.models_multitenant import School, SyncedStudentAttendance


async def main() -> None:
    async with SessionLocal() as db:
        schools = (await db.execute(select(School.id).where(School.is_active.is_(True)))).scalars().all()
        for school_id in schools:
            bounds = (await db.execute(select(
                func.min(SyncedStudentAttendance.attendance_date), func.max(SyncedStudentAttendance.attendance_date)
            ).where(SyncedStudentAttendance.school_id == school_id))).one()
            if bounds[0] and bounds[1]:
                count = await refresh_attendance_aggregates(school_id, bounds[0], bounds[1])
                print(f"Agregat diperbarui: school_id={school_id} rows={count}")


if __name__ == "__main__":
    asyncio.run(main())
