from datetime import date, datetime, timezone

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import SessionLocal
from app.models_multitenant import AttendanceDailyAggregate, SyncedStudentAttendance


async def refresh_attendance_aggregates(school_id: str, start_date: date, end_date: date) -> int:
    async with SessionLocal() as db:
        grouped = (await db.execute(select(
            SyncedStudentAttendance.attendance_date,
            SyncedStudentAttendance.class_source_uuid,
            SyncedStudentAttendance.class_name,
            SyncedStudentAttendance.status,
            func.count(),
            func.sum(case((SyncedStudentAttendance.clock_in_time.isnot(None), 1), else_=0)),
            func.sum(case((SyncedStudentAttendance.clock_out_time.isnot(None), 1), else_=0)),
        ).where(
            SyncedStudentAttendance.school_id == school_id,
            SyncedStudentAttendance.attendance_date.between(start_date, end_date),
        ).group_by(
            SyncedStudentAttendance.attendance_date, SyncedStudentAttendance.class_source_uuid,
            SyncedStudentAttendance.class_name, SyncedStudentAttendance.status,
        ))).all()
        await db.execute(delete(AttendanceDailyAggregate).where(
            AttendanceDailyAggregate.school_id == school_id,
            AttendanceDailyAggregate.attendance_date.between(start_date, end_date),
        ))
        values = [{
            "school_id": school_id, "attendance_date": row[0], "class_source_uuid": row[1],
            "class_name": row[2], "status": row[3], "student_count": row[4],
            "with_clock_in": row[5] or 0, "with_clock_out": row[6] or 0,
            "refreshed_at": datetime.now(timezone.utc),
        } for row in grouped]
        if values:
            await db.execute(pg_insert(AttendanceDailyAggregate).values(values))
        await db.commit()
        return len(values)
