import csv
import io
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import case, desc, distinct, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from app.access import CurrentUser, get_current_user, require_school_access, resolve_school_id
from app.cache import analytics_cache
from app.db import get_db
from app.models_multitenant import (
    AttendanceDailyAggregate,
    AuditLog,
    GenderOverride,
    School,
    SchoolYearSource,
    SyncCheckpoint,
    SyncError,
    SyncRun,
    SyncedClass,
    SyncedStudent,
    SyncedStudentAttendance,
    SyncedSubject,
    SyncedTeacher,
)
from app.routers.dashboard_synced import normalize_status
from app.name_gender import AdaptiveGenderClassifier, operator_samples

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def percentage(value: int, total: int) -> float:
    return round(100 * value / total, 1) if total else 0.0


def gender_label(value: str | None) -> str:
    labels = {"1": "Laki-laki", "2": "Perempuan", "L": "Laki-laki", "P": "Perempuan"}
    return labels.get((value or "").strip(), "Belum terisi")


@router.get("")
async def school_analytics(
    school_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    selected = await resolve_school_id(db, user, school_id)
    cache_key = f"school-analytics:{selected}"
    if cached := analytics_cache.get(cache_key):
        return cached

    school = await db.get(School, selected)
    active_student = (SyncedStudent.school_id == selected, SyncedStudent.is_deleted.is_(False))
    active_teacher = (SyncedTeacher.school_id == selected, SyncedTeacher.is_deleted.is_(False))
    active_class = (SyncedClass.school_id == selected, SyncedClass.is_deleted.is_(False))
    active_subject = (SyncedSubject.school_id == selected, SyncedSubject.is_deleted.is_(False))

    total_students = int((await db.execute(select(func.count()).select_from(SyncedStudent).where(*active_student))).scalar_one())
    total_teachers = int((await db.execute(select(func.count()).select_from(SyncedTeacher).where(*active_teacher))).scalar_one())
    total_classes = int((await db.execute(select(func.count()).select_from(SyncedClass).where(*active_class))).scalar_one())
    total_subjects = int((await db.execute(select(func.count()).select_from(SyncedSubject).where(*active_subject))).scalar_one())

    override_rows = (await db.execute(
        select(GenderOverride.entity_type, GenderOverride.source_uuid, GenderOverride.gender).where(
            GenderOverride.school_id == selected
        )
    )).all()
    overrides: dict[tuple[str, str], str] = {(etype, uuid_): gender for etype, uuid_, gender in override_rows}
    student_overrides = {uuid_: gender for (etype, uuid_), gender in overrides.items() if etype == "student"}
    teacher_overrides = {uuid_: gender for (etype, uuid_), gender in overrides.items() if etype == "teacher"}

    gender_rows = (await db.execute(
        select(SyncedStudent.gender, func.count()).where(*active_student).group_by(SyncedStudent.gender)
    )).all()
    student_gender: dict[str, int] = {}
    for value, count in gender_rows:
        label = gender_label(value)
        student_gender[label] = student_gender.get(label, 0) + int(count)
    verified_names = []
    for model, filters in ((SyncedStudent, active_student), (SyncedTeacher, active_teacher)):
        labelled = (await db.execute(select(model.name, model.gender).where(
            *filters, func.nullif(model.gender, "").is_not(None)
        ))).all()
        verified_names.extend((name, gender_label(gender)) for name, gender in labelled)
    gender_classifier = AdaptiveGenderClassifier(verified_names + operator_samples())
    missing_students = (await db.execute(select(SyncedStudent.source_uuid, SyncedStudent.name).where(
        *active_student, func.nullif(SyncedStudent.gender, "").is_(None)
    ))).all()
    inferred_student_gender = {"Laki-laki": 0, "Perempuan": 0, "Belum dapat ditentukan": 0}
    confidence_total = 0.0
    inferred_count = 0
    overridden_student_count = 0
    for source_uuid, name in missing_students:
        override = student_overrides.get(source_uuid)
        if override:
            # Sudah dikoreksi manual oleh admin - hitung sebagai data resmi, bukan estimasi.
            student_gender[override] = student_gender.get(override, 0) + 1
            overridden_student_count += 1
            continue
        estimate = gender_classifier.predict(name)
        if estimate.label:
            inferred_student_gender[estimate.label] += 1
            confidence_total += estimate.confidence
            inferred_count += 1
        else:
            inferred_student_gender["Belum dapat ditentukan"] += 1

    status_rows = (await db.execute(
        select(SyncedStudent.status, func.count()).where(*active_student).group_by(SyncedStudent.status)
    )).all()
    teacher_gender_rows = (await db.execute(
        select(SyncedTeacher.gender, func.count()).where(*active_teacher).group_by(SyncedTeacher.gender)
    )).all()
    teacher_gender: dict[str, int] = {}
    for value, count in teacher_gender_rows:
        label = gender_label(value)
        teacher_gender[label] = teacher_gender.get(label, 0) + int(count)
    missing_teachers = (await db.execute(select(SyncedTeacher.source_uuid, SyncedTeacher.name).where(
        *active_teacher, func.nullif(SyncedTeacher.gender, "").is_(None)
    ))).all()
    inferred_teacher_gender = {"Laki-laki": 0, "Perempuan": 0, "Belum dapat ditentukan": 0}
    for source_uuid, name in missing_teachers:
        override = teacher_overrides.get(source_uuid)
        if override:
            teacher_gender[override] = teacher_gender.get(override, 0) + 1
            continue
        estimate = gender_classifier.predict(name)
        inferred_teacher_gender[estimate.label or "Belum dapat ditentukan"] += 1

    completeness_row = (await db.execute(select(
        func.count(SyncedStudent.nisn),
        func.count(SyncedStudent.dob),
        func.count(case((func.nullif(SyncedStudent.gender, "").is_not(None), 1))),
        func.count(case((func.nullif(SyncedStudent.class_name, "").is_not(None), 1))),
    ).where(*active_student))).one()
    gender_filled = int(completeness_row[2]) + overridden_student_count
    completeness = [
        {"field": "NISN", "filled": int(completeness_row[0]), "percent": percentage(int(completeness_row[0]), total_students)},
        {"field": "Tanggal lahir", "filled": int(completeness_row[1]), "percent": percentage(int(completeness_row[1]), total_students)},
        {"field": "Jenis kelamin", "filled": gender_filled, "percent": percentage(gender_filled, total_students)},
        {"field": "Kelas", "filled": int(completeness_row[3]), "percent": percentage(int(completeness_row[3]), total_students)},
    ]

    actual_class_rows = (await db.execute(select(
        SyncedStudent.class_source_uuid, func.count()
    ).where(*active_student, SyncedStudent.class_source_uuid.is_not(None)).group_by(SyncedStudent.class_source_uuid))).all()
    actual_by_class = {source_uuid: int(count) for source_uuid, count in actual_class_rows}
    class_rows = (await db.execute(select(SyncedClass).where(*active_class).order_by(SyncedClass.level, SyncedClass.name))).scalars().all()
    classes = [{
        "id": row.source_uuid,
        "name": row.name,
        "level": row.level or "-",
        "students": actual_by_class.get(row.source_uuid, 0),
        "source_students": row.students_count,
        "has_homeroom_teacher": bool(row.homeroom_teacher_source_id),
    } for row in class_rows]
    level_map: dict[str, dict] = {}
    for row in classes:
        level = row["level"]
        item = level_map.setdefault(level, {"level": level, "classes": 0, "students": 0})
        item["classes"] += 1
        item["students"] += row["students"]

    subject_names = list((await db.execute(
        select(SyncedSubject.name).where(*active_subject).order_by(SyncedSubject.name)
    )).scalars())
    years = (await db.execute(
        select(SchoolYearSource).where(SchoolYearSource.school_id == selected).order_by(desc(SchoolYearSource.is_active), desc(SchoolYearSource.name))
    )).scalars().all()

    latest_attendance_date = (await db.execute(select(func.max(AttendanceDailyAggregate.attendance_date)).where(
        AttendanceDailyAggregate.school_id == selected
    ))).scalar_one_or_none()
    attendance_dates = int((await db.execute(select(func.count(distinct(SyncedStudentAttendance.attendance_date))).where(
        SyncedStudentAttendance.school_id == selected
    ))).scalar_one())
    attendance_records = int((await db.execute(select(func.count()).select_from(SyncedStudentAttendance).where(
        SyncedStudentAttendance.school_id == selected
    ))).scalar_one())
    attendance_unique_students = int((await db.execute(select(func.count(distinct(SyncedStudentAttendance.student_source_id))).where(
        SyncedStudentAttendance.school_id == selected
    ))).scalar_one())
    latest_status_rows = []
    if latest_attendance_date:
        latest_status_rows = (await db.execute(select(
            AttendanceDailyAggregate.status, func.sum(AttendanceDailyAggregate.student_count)
        ).where(
            AttendanceDailyAggregate.school_id == selected,
            AttendanceDailyAggregate.attendance_date == latest_attendance_date,
        ).group_by(AttendanceDailyAggregate.status))).all()
    attendance_status: dict[str, int] = {}
    for value, count in latest_status_rows:
        label = normalize_status(value, latest_attendance_date, school.timezone)
        attendance_status[label] = attendance_status.get(label, 0) + int(count or 0)
    latest_observed = sum(attendance_status.values())
    latest_present = attendance_status.get("Hadir", 0) + attendance_status.get("Terlambat", 0)

    checkpoints = (await db.execute(select(SyncCheckpoint).where(
        SyncCheckpoint.school_id == selected
    ).order_by(SyncCheckpoint.domain, SyncCheckpoint.scope))).scalars().all()
    recent_runs = (await db.execute(select(SyncRun).where(
        SyncRun.school_id == selected
    ).order_by(desc(SyncRun.started_at)).limit(8))).scalars().all()
    error_count = int((await db.execute(select(func.count()).select_from(SyncError).where(
        SyncError.school_id == selected
    ))).scalar_one())
    last_success = max((row.last_success_at for row in checkpoints if row.last_success_at), default=None)

    response = {
        "school": {"id": school.id, "code": school.code, "name": school.name, "timezone": school.timezone},
        "executive": {
            "students": total_students, "teachers": total_teachers, "classes": total_classes, "subjects": total_subjects,
            "student_teacher_ratio": round(total_students / total_teachers, 1) if total_teachers else 0,
            "average_class_size": round(total_students / total_classes, 1) if total_classes else 0,
            "active_year": next((row.name for row in years if row.is_active), None),
            "last_sync_at": last_success.isoformat() if last_success else None,
        },
        "students": {
            "by_gender": [{"name": key, "value": value} for key, value in student_gender.items()],
            "gender_estimate": {
                "counts": [{"name": key, "value": value} for key, value in inferred_student_gender.items()],
                "estimated": inferred_count,
                "unresolved": inferred_student_gender["Belum dapat ditentukan"],
                "average_confidence": round(confidence_total / inferred_count, 2) if inferred_count else 0,
                "method": "Classifier adaptif sekolah: data resmi + koreksi operator",
            },
            "by_status": [{"name": status or "Belum terisi", "value": int(count)} for status, count in status_rows],
            "by_level": sorted(level_map.values(), key=lambda row: row["level"]),
            "completeness": completeness,
        },
        "teachers": {
            "active": int((await db.execute(select(func.count()).select_from(SyncedTeacher).where(*active_teacher, SyncedTeacher.is_active.is_(True)))).scalar_one()),
            "homeroom_assignments": sum(1 for row in classes if row["has_homeroom_teacher"]),
            "by_gender": [{"name": key, "value": value} for key, value in teacher_gender.items()],
            "gender_estimate": [{"name": key, "value": value} for key, value in inferred_teacher_gender.items()],
        },
        "academic": {
            "classes": classes,
            "subjects": subject_names,
            "school_years": [{"name": row.name, "active": row.is_active} for row in years],
        },
        "attendance": {
            "latest_date": latest_attendance_date.isoformat() if latest_attendance_date else None,
            "dates_available": attendance_dates,
            "records": attendance_records,
            "unique_students": attendance_unique_students,
            "historical_coverage_percent": percentage(attendance_unique_students, total_students),
            "latest_observed": latest_observed,
            "coverage_percent": percentage(latest_observed, total_students),
            "attendance_rate": percentage(latest_present, latest_observed),
            "pending_check_in": attendance_status.get("Belum Absen Masuk", 0),
            "status": [{"name": key, "value": value} for key, value in attendance_status.items()],
        },
        "operations": {
            "last_success_at": last_success.isoformat() if last_success else None,
            "domains": [{"domain": row.domain, "scope": row.scope, "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None} for row in checkpoints],
            "error_count": error_count,
            "recent_runs": [{
                "domain": row.domain, "status": row.status, "started_at": row.started_at.isoformat(),
                "rows_seen": row.rows_seen, "rows_changed": row.rows_inserted + row.rows_updated,
            } for row in recent_runs],
        },
    }
    analytics_cache.set(cache_key, response)
    return response


ENTITY_MODELS = {"student": SyncedStudent, "teacher": SyncedTeacher}


@router.get("/gender-review")
async def gender_review(
    school_id: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Nama siswa/guru yang jenis kelaminnya kosong di sumber School ID dan belum
    dikoreksi manual, lengkap dengan tebakan heuristik supaya admin tinggal konfirmasi."""
    selected = await resolve_school_id(db, user, school_id)

    override_rows = (await db.execute(
        select(GenderOverride.entity_type, GenderOverride.source_uuid).where(GenderOverride.school_id == selected)
    )).all()
    already_overridden = {(etype, uuid_) for etype, uuid_ in override_rows}

    verified_names = []
    for model, entity_type in ((SyncedStudent, "student"), (SyncedTeacher, "teacher")):
        labelled = (await db.execute(select(model.name, model.gender).where(
            model.school_id == selected, model.is_deleted.is_(False), func.nullif(model.gender, "").is_not(None)
        ))).all()
        verified_names.extend((name, gender_label(gender)) for name, gender in labelled)
    classifier = AdaptiveGenderClassifier(verified_names + operator_samples())

    items = []
    for entity_type, model, extra_col in (
        ("student", SyncedStudent, SyncedStudent.class_name),
        ("teacher", SyncedTeacher, None),
    ):
        cols = [model.source_uuid, model.name] + ([extra_col] if extra_col is not None else [])
        rows = (await db.execute(select(*cols).where(
            model.school_id == selected, model.is_deleted.is_(False), func.nullif(model.gender, "").is_(None)
        ))).all()
        for row in rows:
            source_uuid, name = row[0], row[1]
            if (entity_type, source_uuid) in already_overridden:
                continue
            detail = row[2] if extra_col is not None else None
            estimate = classifier.predict(name)
            items.append({
                "entity_type": entity_type,
                "source_uuid": source_uuid,
                "name": name,
                "detail": detail,
                "suggested_gender": estimate.label,
                "confidence": estimate.confidence,
            })

    items.sort(key=lambda item: (item["confidence"] is None, -(item["confidence"] or 0)))
    return {"total_unresolved": len(items), "items": items[:limit]}


class GenderOverrideIn(BaseModel):
    entity_type: str
    source_uuid: str
    gender: str


@router.put("/gender-override")
async def set_gender_override(
    payload: GenderOverrideIn,
    school_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    selected = await resolve_school_id(db, user, school_id)
    await require_school_access(db, user, selected)

    if payload.entity_type not in ENTITY_MODELS:
        raise HTTPException(status_code=400, detail="entity_type harus 'student' atau 'teacher'")
    if payload.gender not in {"Laki-laki", "Perempuan"}:
        raise HTTPException(status_code=400, detail="gender harus 'Laki-laki' atau 'Perempuan'")

    model = ENTITY_MODELS[payload.entity_type]
    exists = (await db.execute(select(model.source_uuid).where(
        model.school_id == selected, model.source_uuid == payload.source_uuid, model.is_deleted.is_(False)
    ))).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="Data siswa/guru tidak ditemukan di sekolah ini")

    stmt = pg_insert(GenderOverride).values(
        school_id=selected,
        entity_type=payload.entity_type,
        source_uuid=payload.source_uuid,
        gender=payload.gender,
        set_by=user.username,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_gender_override_entity",
        set_={"gender": stmt.excluded.gender, "set_by": stmt.excluded.set_by, "set_at": func.now()},
    )
    await db.execute(stmt)
    db.add(AuditLog(
        user_id=user.id, school_id=selected, action="gender_override.set",
        details={"entity_type": payload.entity_type, "source_uuid": payload.source_uuid, "gender": payload.gender},
    ))
    await db.commit()
    analytics_cache.set(f"school-analytics:{selected}", None)
    return {"ok": True}


@router.get("/insights")
async def analytics_insights(
    school_id: str | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    selected = await resolve_school_id(db, user, school_id)
    insight_school = await db.get(School, selected)
    dates = list((await db.execute(select(distinct(SyncedStudentAttendance.attendance_date)).where(
        SyncedStudentAttendance.school_id == selected
    ).order_by(desc(SyncedStudentAttendance.attendance_date)).limit(2))).scalars())
    comparisons = []
    for attendance_date in dates:
        rows = (await db.execute(select(
            SyncedStudentAttendance.status, func.count()
        ).where(
            SyncedStudentAttendance.school_id == selected,
            SyncedStudentAttendance.attendance_date == attendance_date,
        ).group_by(SyncedStudentAttendance.status))).all()
        counts: dict[str, int] = {}
        for status_name, count in rows:
            label = normalize_status(status_name, attendance_date, insight_school.timezone)
            counts[label] = counts.get(label, 0) + int(count)
        observed = sum(counts.values())
        present = counts.get("Hadir", 0) + counts.get("Terlambat", 0)
        comparisons.append({"date": attendance_date.isoformat(), "observed": observed, "attendance_rate": percentage(present, observed)})

    risk_rows = (await db.execute(select(
        SyncedStudentAttendance.student_source_id,
        func.max(SyncedStudentAttendance.student_name),
        func.max(SyncedStudentAttendance.class_name),
        func.count().filter(SyncedStudentAttendance.status.in_(["Alpha", "Absen"])),
        func.count().filter(SyncedStudentAttendance.status == "Terlambat"),
        func.count(),
    ).where(
        SyncedStudentAttendance.school_id == selected
    ).group_by(SyncedStudentAttendance.student_source_id).having(
        func.count().filter(SyncedStudentAttendance.status.in_(["Alpha", "Absen"])) > 0
    ).order_by(desc(func.count().filter(SyncedStudentAttendance.status.in_(["Alpha", "Absen"])))).limit(20))).all()
    risks = [{
        "student_id": row[0], "name": row[1], "class_name": row[2], "alpha": int(row[3]),
        "late": int(row[4]), "observations": int(row[5]),
        "risk_score": min(100, int(row[3]) * 25 + int(row[4]) * 10),
    } for row in risk_rows]

    class_anomalies = []
    if dates:
        class_rows = (await db.execute(select(
            SyncedStudentAttendance.class_name,
            func.count(),
            func.count().filter(SyncedStudentAttendance.status.in_(["Hadir", "Terlambat"])),
        ).where(
            SyncedStudentAttendance.school_id == selected,
            SyncedStudentAttendance.attendance_date == dates[0],
        ).group_by(SyncedStudentAttendance.class_name))).all()
        rates = [(name or "-", int(total), percentage(int(present), int(total))) for name, total, present in class_rows]
        average = sum(rate for _, _, rate in rates) / len(rates) if rates else 0
        class_anomalies = [{"class_name": name, "observed": total, "attendance_rate": rate, "gap_from_average": round(rate - average, 1)} for name, total, rate in rates if rate < average - 15]

    change = None
    if len(comparisons) == 2:
        change = round(comparisons[0]["attendance_rate"] - comparisons[1]["attendance_rate"], 1)
    return {"period_comparison": comparisons, "attendance_change_points": change, "at_risk_students": risks, "class_anomalies": class_anomalies}


@router.get("/attendance.csv")
async def attendance_csv(
    school_id: str | None = Query(default=None),
    days: int = Query(default=31, ge=1, le=366),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    selected = await resolve_school_id(db, user, school_id)
    export_school = await db.get(School, selected)
    latest = (await db.execute(select(func.max(SyncedStudentAttendance.attendance_date)).where(
        SyncedStudentAttendance.school_id == selected
    ))).scalar_one_or_none()
    rows = []
    if latest:
        rows = (await db.execute(select(SyncedStudentAttendance).where(
            SyncedStudentAttendance.school_id == selected,
            SyncedStudentAttendance.attendance_date >= latest - timedelta(days=days - 1),
        ).order_by(SyncedStudentAttendance.attendance_date, SyncedStudentAttendance.class_name, SyncedStudentAttendance.student_name))).scalars().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["tanggal", "kelas", "siswa", "status", "jam_masuk", "jam_pulang", "alasan"])
    for row in rows:
        writer.writerow([row.attendance_date.isoformat(), row.class_name or "", row.student_name, normalize_status(row.status, row.attendance_date, export_school.timezone), row.clock_in_time or "", row.clock_out_time or "", row.reason or ""])
    return Response(
        content=output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="presensi-{selected}-{latest or "kosong"}.csv"', "Cache-Control": "no-store"},
    )
