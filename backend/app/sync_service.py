import asyncio
import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.credential_cipher import CredentialCipher
from app.aggregates import refresh_attendance_aggregates
from app.db import SessionLocal
from app.integrations.school_id import SchoolIdClient
from app.models_multitenant import (
    SchoolConnection,
    SchoolYearSource,
    SyncCheckpoint,
    SyncError,
    SyncRun,
    SyncedClass,
    SyncedClassAttendance,
    SyncedSchedule,
    SyncedStudent,
    SyncedSubject,
    SyncedTeacher,
    SyncedDomainRecord,
    SyncedStudentAttendance,
)


DOMAIN_MODELS = {
    "students": SyncedStudent,
    "teachers": SyncedTeacher,
    "classes": SyncedClass,
    "subjects": SyncedSubject,
}


def parse_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def nested_value(value, key: str):
    return value.get(key) if isinstance(value, dict) else None


def fingerprint(row: dict) -> str:
    canonical = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def normalize(domain: str, row: dict, school_id: str, school_year_uuid: str | None = None) -> dict:
    common = {
        "school_id": school_id,
        "source_uuid": str(row["uuid"]),
        "source_updated_at": parse_datetime(row.get("updated_at")),
        "fingerprint": fingerprint(row),
        "is_deleted": False,
        "last_synced_at": datetime.now(timezone.utc),
    }
    if domain == "students":
        class_data = row.get("class")
        return common | {
            "school_year_uuid": school_year_uuid,
            "nis": row.get("nis"), "nisn": row.get("nisn"), "name": row.get("name") or "-",
            "dob": parse_date(row.get("dob")), "gender": str(row.get("gender")) if row.get("gender") is not None else None,
            "status": str(row.get("status_description") or row.get("status") or ""),
            "class_source_uuid": nested_value(class_data, "uuid"),
            "class_name": nested_value(class_data, "name") or (class_data if isinstance(class_data, str) else None),
        }
    if domain == "teachers":
        # Unlike student rows, a teacher's "class" field is a plain name string
        # (e.g. "X.7"), not a {uuid, name} object - so there's no uuid to join
        # against SyncedClass here. homeroom_class_id is a legacy numeric id that
        # doesn't match any uuid we store elsewhere either. We store the class
        # name directly since that's the only usable value the source gives us.
        return common | {
            "nuptk": row.get("nuptk"), "name": row.get("name") or "-", "dob": parse_date(row.get("dob")),
            "gender": str(row.get("gender")) if row.get("gender") is not None else None,
            "is_active": bool(row.get("active", True)),
            "homeroom_class_source_id": str(row.get("class") or "") or None,
        }
    if domain == "classes":
        return common | {
            "name": row.get("name") or "-", "level": str(row.get("level") or "") or None,
            "is_active": bool(row.get("is_active", True)),
            "homeroom_teacher_source_id": str(row.get("homeroom_teacher_id") or "") or None,
            "students_count": int(row.get("students_count") or 0),
        }
    if domain == "subjects":
        return common | {"name": row.get("name") or "-"}
    raise ValueError(f"Domain belum didukung: {domain}")


class SyncService:
    def __init__(self) -> None:
        self._clients: dict[str, SchoolIdClient] = {}

    async def _connection(self, school_id: str) -> tuple[str, str, str]:
        async with SessionLocal() as db:
            connection = await db.get(SchoolConnection, school_id)
            if not connection or not connection.enabled:
                raise ValueError("Koneksi sekolah tidak aktif")
            cipher = CredentialCipher()
            return (
                connection.base_url,
                cipher.decrypt(connection.username_ciphertext),
                cipher.decrypt(connection.password_ciphertext),
            )

    async def sync(self, school_id: str, domain: str, scope: dict | None = None) -> str:
        run = SyncRun(school_id=school_id, domain=domain, status="running")
        async with SessionLocal() as db:
            db.add(run)
            await db.commit()
            await db.refresh(run)

        try:
            client = self._clients.get(school_id)
            if client is None:
                base_url, username, password = await self._connection(school_id)
                client = SchoolIdClient(base_url, username, password)
                await asyncio.to_thread(client.login)
                self._clients[school_id] = client
            if domain == "school_years":
                years = await asyncio.to_thread(client.school_years)
                counts = await self._upsert_years(school_id, years)
            elif domain == "student_attendance_summary":
                counts = await self._sync_attendance_summary(client, school_id, scope or {})
            elif domain == "student_attendance_daily":
                counts = await self._sync_daily_attendance(client, school_id, scope or {})
            elif domain == "class_attendances":
                counts = await self._sync_class_attendances(client, school_id, scope or {})
            elif domain == "schedules":
                counts = await self._sync_schedules(client, school_id, scope or {})
            else:
                school_year_uuid = (scope or {}).get("school_year_uuid")
                if domain == "students" and not school_year_uuid:
                    school_year_uuid = await self._active_year(school_id)
                counts = await self._sync_pages(client, school_id, domain, school_year_uuid)
            await self._finish_run(run.id, "success", counts)
        except Exception as exc:
            failed_client = self._clients.pop(school_id, None)
            if failed_client:
                failed_client.close()
            elif "client" in locals():
                client.close()
            safe_message = str(exc).replace(username if 'username' in locals() else "", "<redacted>")[:500]
            await self._fail_run(run.id, school_id, domain, exc.__class__.__name__, safe_message)
            raise
        return run.id

    async def _year(self, school_id: str, source_uuid: str | None = None) -> SchoolYearSource:
        async with SessionLocal() as db:
            stmt = select(SchoolYearSource).where(SchoolYearSource.school_id == school_id)
            stmt = stmt.where(SchoolYearSource.source_uuid == source_uuid) if source_uuid else stmt.where(SchoolYearSource.is_active.is_(True))
            year = (await db.execute(stmt)).scalar_one_or_none()
            if not year:
                raise ValueError("Tahun ajaran belum disinkronkan")
            if not year.source_id:
                raise ValueError("ID numerik tahun ajaran belum disinkronkan")
            return year

    async def _sync_daily_attendance(self, client, school_id: str, scope: dict) -> dict:
        year = await self._year(school_id, scope.get("school_year_uuid"))
        start_date = parse_date(scope.get("start_date")) or max(year.odd_start, datetime.now(timezone.utc).date() - timedelta(days=7))
        end_date = parse_date(scope.get("end_date")) or min(datetime.now(timezone.utc).date(), year.even_end or year.odd_end)
        totals = {"seen": 0, "inserted": 0, "updated": 0, "unchanged": 0}
        current = start_date
        while current <= end_date:
            summary = await asyncio.to_thread(
                client.fetch_attendance_summary_page,
                start_date=current.isoformat(), end_date=current.isoformat(),
                school_year_uuid=year.source_id, page=1, per_page=100,
            )
            active_classes = [
                row for row in summary.rows
                if sum(int(row.get(key) or 0) for key in ("total_clock_in", "total_present", "total_leave_days", "total_sick_days")) > 0
            ]
            for class_row in active_classes:
                source_rows = await asyncio.to_thread(
                    client.fetch_daily_attendance,
                    attendance_date=current.isoformat(), class_uuid=str(class_row["uuid"]), school_year_id=year.source_id,
                )
                normalized = [self._normalize_attendance(school_id, year.source_uuid, current, class_row, row) for row in source_rows]
                counts = await self._upsert_attendance(school_id, normalized)
                for key in totals:
                    totals[key] += counts[key]
                await asyncio.sleep(0.1)
            current += timedelta(days=1)
        await self._checkpoint(school_id, "student_attendance_daily", year.source_uuid, totals)
        await refresh_attendance_aggregates(school_id, start_date, end_date)
        return totals

    def _normalize_attendance(self, school_id: str, year_uuid: str, attendance_date: date, class_row: dict, row: dict) -> dict:
        student_id = row.get("user_id") or row.get("class_student_id") or row.get("id")
        if student_id is None:
            student_id = hashlib.sha256(f"{class_row['uuid']}:{row.get('user_name', '')}".encode()).hexdigest()[:32]
        approved = {
            "date": attendance_date.isoformat(), "class_uuid": class_row["uuid"],
            "student_id": str(student_id), "status": row.get("status"),
            "clock_in_time": row.get("clock_in_time"), "clock_out_time": row.get("clock_out_time"),
            "clock_in_status": row.get("clock_in_status"), "clock_out_status": row.get("clock_out_status"),
            "reason": row.get("clock_in_reason") or row.get("clock_out_reason"),
        }
        return {
            "school_id": school_id, "school_year_uuid": year_uuid, "attendance_date": attendance_date,
            "class_source_uuid": str(class_row["uuid"]), "class_name": class_row.get("class_name"),
            "student_source_id": str(student_id), "student_name": row.get("user_name") or "-",
            "status": row.get("status") or "Alpha",
            "clock_in_time": str(row.get("clock_in_time"))[:16] if row.get("clock_in_time") else None,
            "clock_out_time": str(row.get("clock_out_time"))[:16] if row.get("clock_out_time") else None,
            "clock_in_status": str(row.get("clock_in_status")) if row.get("clock_in_status") is not None else None,
            "clock_out_status": str(row.get("clock_out_status")) if row.get("clock_out_status") is not None else None,
            "reason": (row.get("clock_in_reason") or row.get("clock_out_reason") or None),
            "fingerprint": fingerprint(approved), "source_updated_at": parse_datetime(row.get("updated_at")),
            "last_synced_at": datetime.now(timezone.utc),
        }

    async def _sync_class_attendances(self, client, school_id: str, scope: dict) -> dict:
        """Sesi mengajar per mapel/kelas (fitur 'absensi per mapel' School ID).

        Sengaja tidak requires_school_year (lihat contracts.py) - dipaging generik
        seperti students/teachers, difilter rentang tanggal lewat extra_params.
        """
        end_date = parse_date(scope.get("end_date")) or datetime.now(timezone.utc).date()
        start_date = parse_date(scope.get("start_date")) or (end_date - timedelta(days=30))
        totals = {"seen": 0, "inserted": 0, "updated": 0, "unchanged": 0}
        iterator = client.iter_pages(
            "class_attendances", page_size=100,
            extra_params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        )
        while True:
            page = await asyncio.to_thread(lambda: next(iterator, None))
            if page is None:
                break
            rows = [self._normalize_class_attendance(school_id, row) for row in page.rows if parse_date(row.get("date"))]
            counts = await self._upsert_class_attendances(school_id, rows)
            for key in totals:
                totals[key] += counts[key]
        await self._checkpoint(school_id, "class_attendances", f"{start_date}:{end_date}", totals)
        return totals

    def _normalize_class_attendance(self, school_id: str, row: dict) -> dict:
        approved = dict(row)
        return {
            "school_id": school_id, "source_uuid": str(row["uuid"]),
            "attendance_date": parse_date(row.get("date")),
            "class_name": str(row.get("class") or "") or None,
            "subject_name": str(row.get("subject") or "") or None,
            "teacher_name": str(row.get("teacher_name") or row.get("teacher") or "") or None,
            "session_label": str(row.get("session") or row.get("session_number") or "") or None,
            "start_time": str(row.get("start_time"))[:8] if row.get("start_time") else None,
            "end_time": str(row.get("end_time"))[:8] if row.get("end_time") else None,
            "present_count": int(row.get("present_count") or 0),
            "absent_count": int(row.get("absent_count") or 0),
            "source_updated_at": parse_datetime(row.get("updated_at")),
            "fingerprint": fingerprint(approved), "is_deleted": False,
            "last_synced_at": datetime.now(timezone.utc),
        }

    async def _upsert_class_attendances(self, school_id: str, rows: list[dict]) -> dict:
        counts = {"seen": len(rows), "inserted": 0, "updated": 0, "unchanged": 0}
        if not rows:
            return counts
        uuids = [row["source_uuid"] for row in rows]
        async with SessionLocal() as db:
            existing = dict((await db.execute(select(
                SyncedClassAttendance.source_uuid, SyncedClassAttendance.fingerprint
            ).where(SyncedClassAttendance.school_id == school_id, SyncedClassAttendance.source_uuid.in_(uuids)))).all())
            changed = []
            for row in rows:
                old = existing.get(row["source_uuid"])
                if old is None: counts["inserted"] += 1; changed.append(row)
                elif old != row["fingerprint"]: counts["updated"] += 1; changed.append(row)
                else: counts["unchanged"] += 1
            if changed:
                stmt = pg_insert(SyncedClassAttendance).values(changed)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_synced_class_attendance_source",
                    set_={c: getattr(stmt.excluded, c) for c in changed[0] if c not in {"id", "school_id", "source_uuid"}},
                )
                await db.execute(stmt)
                await db.commit()
        return counts

    async def _sync_schedules(self, client, school_id: str, scope: dict) -> dict:
        """Jadwal pelajaran, per kelas (endpoint School ID discovered to be
        per-class, not a flat paginated list - see client.fetch_schedules)."""
        year = await self._year(school_id, scope.get("school_year_uuid"))
        async with SessionLocal() as db:
            classes = (await db.execute(select(SyncedClass.source_uuid, SyncedClass.name).where(
                SyncedClass.school_id == school_id, SyncedClass.is_deleted.is_(False)
            ))).all()
        totals = {"seen": 0, "inserted": 0, "updated": 0, "unchanged": 0}
        incomplete_years = 0
        for class_uuid, class_name in classes:
            rows, is_complete = await asyncio.to_thread(
                client.fetch_schedules, class_uuid=class_uuid, school_year_id=year.source_id
            )
            if not is_complete:
                incomplete_years += 1
            normalized = [self._normalize_schedule(school_id, year.source_uuid, class_uuid, class_name, row) for row in rows]
            counts = await self._upsert_schedules(school_id, normalized)
            for key in totals:
                totals[key] += counts[key]
            await asyncio.sleep(0.05)
        if incomplete_years == len(classes) and classes:
            raise ValueError("Tahun ajaran belum lengkap menurut School ID (school_year_status.is_data_complete=false) untuk semua kelas")
        await self._checkpoint(school_id, "schedules", year.source_uuid, totals)
        return totals

    def _normalize_schedule(self, school_id: str, year_uuid: str, class_uuid: str, class_name: str, row: dict) -> dict:
        approved = dict(row)
        return {
            "school_id": school_id, "source_uuid": str(row.get("uuid") or f"{class_uuid}:{row.get('day') or row.get('day_of_week')}:{row.get('session') or row.get('session_number')}"),
            "school_year_uuid": year_uuid,
            "day_of_week": str(row.get("day") or row.get("day_of_week") or "") or None,
            "session_label": str(row.get("session") or row.get("session_number") or "") or None,
            "start_time": str(row.get("start_time"))[:8] if row.get("start_time") else None,
            "end_time": str(row.get("end_time"))[:8] if row.get("end_time") else None,
            "class_source_uuid": class_uuid, "class_name": class_name,
            "subject_name": str(row.get("subject") or "") or None,
            "teacher_name": str(row.get("teacher_name") or row.get("teacher") or "") or None,
            "source_updated_at": parse_datetime(row.get("updated_at")),
            "fingerprint": fingerprint(approved), "is_deleted": False,
            "last_synced_at": datetime.now(timezone.utc),
        }

    async def _upsert_schedules(self, school_id: str, rows: list[dict]) -> dict:
        counts = {"seen": len(rows), "inserted": 0, "updated": 0, "unchanged": 0}
        if not rows:
            return counts
        uuids = [row["source_uuid"] for row in rows]
        async with SessionLocal() as db:
            existing = dict((await db.execute(select(
                SyncedSchedule.source_uuid, SyncedSchedule.fingerprint
            ).where(SyncedSchedule.school_id == school_id, SyncedSchedule.source_uuid.in_(uuids)))).all())
            changed = []
            for row in rows:
                old = existing.get(row["source_uuid"])
                if old is None: counts["inserted"] += 1; changed.append(row)
                elif old != row["fingerprint"]: counts["updated"] += 1; changed.append(row)
                else: counts["unchanged"] += 1
            if changed:
                stmt = pg_insert(SyncedSchedule).values(changed)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_synced_schedule_source",
                    set_={c: getattr(stmt.excluded, c) for c in changed[0] if c not in {"id", "school_id", "source_uuid"}},
                )
                await db.execute(stmt)
                await db.commit()
        return counts

    async def _upsert_attendance(self, school_id: str, rows: list[dict]) -> dict:
        counts = {"seen": len(rows), "inserted": 0, "updated": 0, "unchanged": 0}
        if not rows:
            return counts
        keys = [(row["attendance_date"], row["class_source_uuid"], row["student_source_id"]) for row in rows]
        async with SessionLocal() as db:
            existing_rows = (await db.execute(select(
                SyncedStudentAttendance.attendance_date, SyncedStudentAttendance.class_source_uuid,
                SyncedStudentAttendance.student_source_id, SyncedStudentAttendance.fingerprint,
            ).where(
                SyncedStudentAttendance.school_id == school_id,
                SyncedStudentAttendance.attendance_date.in_({key[0] for key in keys}),
            ))).all()
            existing = {(r[0], r[1], r[2]): r[3] for r in existing_rows}
            changed = []
            for row in rows:
                key = (row["attendance_date"], row["class_source_uuid"], row["student_source_id"])
                old = existing.get(key)
                if old is None: counts["inserted"] += 1; changed.append(row)
                elif old != row["fingerprint"]: counts["updated"] += 1; changed.append(row)
                else: counts["unchanged"] += 1
            if changed:
                stmt = pg_insert(SyncedStudentAttendance).values(changed)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_synced_student_attendance",
                    set_={c: getattr(stmt.excluded, c) for c in changed[0] if c not in {"id", "school_id", "attendance_date", "class_source_uuid", "student_source_id"}},
                )
                await db.execute(stmt); await db.commit()
        return counts

    async def _sync_attendance_summary(self, client, school_id: str, scope: dict) -> dict:
        year_uuid = scope.get("school_year_uuid") or await self._active_year(school_id)
        year = await self._year(school_id, year_uuid)
        today = datetime.now(timezone.utc).date()
        end_date = min(today, year.even_end or year.odd_end or today)
        start_date = parse_date(scope.get("start_date")) or max(year.odd_start or end_date, end_date - timedelta(days=29))
        end_date = parse_date(scope.get("end_date")) or end_date
        page_number = 1
        totals = {"seen": 0, "inserted": 0, "updated": 0, "unchanged": 0}
        while True:
            page = await asyncio.to_thread(
                client.fetch_attendance_summary_page,
                start_date=start_date.isoformat(), end_date=end_date.isoformat(),
                school_year_uuid=year.source_id, page=page_number, per_page=100,
            )
            if page.missing_required_fields:
                raise ValueError("Field wajib ringkasan presensi hilang")
            rows = []
            for row in page.rows:
                approved = dict(row)
                rows.append({
                    "school_id": school_id, "domain": "student_attendance_summary",
                    "source_uuid": str(row["uuid"]), "source_updated_at": None,
                    "fingerprint": fingerprint(approved), "is_deleted": False,
                    "last_synced_at": datetime.now(timezone.utc), "event_date": end_date,
                    "school_year_uuid": year_uuid, "student_source_uuid": None,
                    "teacher_source_uuid": None, "class_source_uuid": str(row["uuid"]),
                    "subject_source_uuid": None, "data": approved,
                })
            counts = await self._upsert_generic(school_id, "student_attendance_summary", rows)
            for key in totals:
                totals[key] += counts[key]
            if not page.rows or totals["seen"] >= page.total:
                break
            page_number += 1
        await self._checkpoint(school_id, "student_attendance_summary", year_uuid, totals)
        return totals

    async def _upsert_generic(self, school_id: str, domain: str, rows: list[dict]) -> dict:
        counts = {"seen": len(rows), "inserted": 0, "updated": 0, "unchanged": 0}
        if not rows:
            return counts
        uuids = [row["source_uuid"] for row in rows]
        async with SessionLocal() as db:
            existing = dict((await db.execute(select(
                SyncedDomainRecord.source_uuid, SyncedDomainRecord.fingerprint
            ).where(
                SyncedDomainRecord.school_id == school_id,
                SyncedDomainRecord.domain == domain,
                SyncedDomainRecord.source_uuid.in_(uuids),
            ))).all())
            changed = []
            for row in rows:
                old = existing.get(row["source_uuid"])
                if old is None:
                    counts["inserted"] += 1; changed.append(row)
                elif old != row["fingerprint"]:
                    counts["updated"] += 1; changed.append(row)
                else:
                    counts["unchanged"] += 1
            if changed:
                stmt = pg_insert(SyncedDomainRecord).values(changed)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_synced_domain_source",
                    set_={c: getattr(stmt.excluded, c) for c in changed[0] if c not in {"id", "school_id", "domain", "source_uuid"}},
                )
                await db.execute(stmt)
                await db.commit()
        return counts

    async def _active_year(self, school_id: str) -> str:
        async with SessionLocal() as db:
            result = await db.execute(
                select(SchoolYearSource.source_uuid).where(
                    SchoolYearSource.school_id == school_id, SchoolYearSource.is_active.is_(True)
                )
            )
            value = result.scalar_one_or_none()
            if not value:
                raise ValueError("Tahun ajaran aktif belum disinkronkan")
            return value

    async def _sync_pages(self, client, school_id: str, domain: str, school_year_uuid: str | None) -> dict:
        if domain not in DOMAIN_MODELS:
            raise ValueError(f"Domain belum didukung worker: {domain}")
        totals = {"seen": 0, "inserted": 0, "updated": 0, "unchanged": 0}
        seen_uuids: set[str] = set()
        iterator = client.iter_pages(domain, page_size=100, school_year_uuid=school_year_uuid)
        while True:
            page = await asyncio.to_thread(lambda: next(iterator, None))
            if page is None:
                break
            if page.missing_required_fields:
                raise ValueError(f"Field wajib hilang pada {domain}: {','.join(page.missing_required_fields)}")
            rows = [normalize(domain, row, school_id, school_year_uuid) for row in page.rows]
            seen_uuids.update(row["source_uuid"] for row in rows)
            counts = await self._upsert_entities(domain, school_id, rows)
            for key in totals:
                totals[key] += counts[key]
        if seen_uuids:
            model = DOMAIN_MODELS[domain]
            async with SessionLocal() as db:
                await db.execute(update(model).where(
                    model.school_id == school_id, model.source_uuid.not_in(seen_uuids)
                ).values(is_deleted=True, last_synced_at=datetime.now(timezone.utc)))
                await db.commit()
        await self._checkpoint(school_id, domain, school_year_uuid or "default", totals)
        return totals

    async def _upsert_entities(self, domain: str, school_id: str, rows: list[dict]) -> dict:
        counts = {"seen": len(rows), "inserted": 0, "updated": 0, "unchanged": 0}
        if not rows:
            return counts
        model = DOMAIN_MODELS[domain]
        uuids = [row["source_uuid"] for row in rows]
        async with SessionLocal() as db:
            existing_result = await db.execute(
                select(model.source_uuid, model.fingerprint).where(model.school_id == school_id, model.source_uuid.in_(uuids))
            )
            existing = dict(existing_result.all())
            changed = []
            for row in rows:
                old = existing.get(row["source_uuid"])
                if old is None:
                    counts["inserted"] += 1
                    changed.append(row)
                elif old != row["fingerprint"]:
                    counts["updated"] += 1
                    changed.append(row)
                else:
                    counts["unchanged"] += 1
            if changed:
                stmt = pg_insert(model).values(changed)
                update_columns = {
                    column.name: getattr(stmt.excluded, column.name)
                    for column in model.__table__.columns
                    if column.name not in {"id", "school_id", "source_uuid"}
                }
                stmt = stmt.on_conflict_do_update(
                    index_elements=["school_id", "source_uuid"], set_=update_columns
                )
                await db.execute(stmt)
                await db.commit()
        return counts

    async def _upsert_years(self, school_id: str, years: list[dict]) -> dict:
        values = []
        for row in years:
            values.append({
                "school_id": school_id, "source_uuid": row["uuid"], "name": row.get("name") or "-",
                "source_id": str(row.get("id")) if row.get("id") is not None else None,
                "is_active": bool(row.get("is_active")), "odd_start": parse_date(row.get("odd_semester_start_date")),
                "odd_end": parse_date(row.get("odd_semester_end_date")),
                "even_start": parse_date(row.get("even_semester_start_date")),
                "even_end": parse_date(row.get("even_semester_end_date")),
                "source_updated_at": parse_datetime(row.get("updated_at")),
                "last_synced_at": datetime.now(timezone.utc),
            })
        counts = {"seen": len(values), "inserted": 0, "updated": 0, "unchanged": 0}
        async with SessionLocal() as db:
            existing_rows = (await db.execute(
                select(SchoolYearSource.source_uuid, SchoolYearSource.source_updated_at).where(
                    SchoolYearSource.school_id == school_id
                )
            )).all()
            existing = dict(existing_rows)
            for value in values:
                old = existing.get(value["source_uuid"])
                if old is None:
                    counts["inserted"] += 1
                elif old != value["source_updated_at"]:
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
            if values:
                stmt = pg_insert(SchoolYearSource).values(values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["school_id", "source_uuid"],
                    set_={c: getattr(stmt.excluded, c) for c in values[0] if c not in {"school_id", "source_uuid"}},
                )
                await db.execute(stmt)
            await db.commit()
        await self._checkpoint(school_id, "school_years", "default", counts)
        return counts

    async def _checkpoint(self, school_id: str, domain: str, scope: str, counts: dict) -> None:
        now = datetime.now(timezone.utc)
        async with SessionLocal() as db:
            stmt = pg_insert(SyncCheckpoint).values(
                school_id=school_id, domain=domain, scope=scope,
                cursor={"last_counts": counts}, last_success_at=now, updated_at=now,
            ).on_conflict_do_update(
                constraint="uq_sync_checkpoint",
                set_={"cursor": {"last_counts": counts}, "last_success_at": now, "updated_at": now},
            )
            await db.execute(stmt)
            await db.commit()

    async def _finish_run(self, run_id: str, status: str, counts: dict) -> None:
        async with SessionLocal() as db:
            run = await db.get(SyncRun, run_id)
            run.status = status
            run.finished_at = datetime.now(timezone.utc)
            run.rows_seen, run.rows_inserted = counts["seen"], counts["inserted"]
            run.rows_updated, run.rows_unchanged = counts["updated"], counts["unchanged"]
            await db.commit()

    async def _fail_run(self, run_id: str, school_id: str, domain: str, error_type: str, message: str) -> None:
        async with SessionLocal() as db:
            run = await db.get(SyncRun, run_id)
            run.status, run.finished_at, run.error_summary = "failed", datetime.now(timezone.utc), message
            db.add(SyncError(sync_run_id=run_id, school_id=school_id, domain=domain, error_type=error_type, message=message))
            await db.commit()
