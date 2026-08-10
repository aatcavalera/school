import datetime as dt
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_multitenant import School, SchoolYearSource, SyncedStudent, SyncedStudentAttendance
from app.config import settings


def jenjang_from_class(name: str | None) -> str:
    if not name:
        return "-"
    return name.split("-")[0].strip()


def normalize_status(
    value: str | None,
    attendance_date: dt.date | None = None,
    timezone_name: str = "Asia/Makassar",
    now: dt.datetime | None = None,
) -> str:
    value = (value or "").strip().lower()
    if value in {"belum clock in", "belum absen masuk", "not clocked in"}:
        if attendance_date is not None:
            local_now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(timezone_name))
            cutoff = dt.time.fromisoformat(settings.attendance_sync_end_local)
            if attendance_date < local_now.date() or (attendance_date == local_now.date() and local_now.time() >= cutoff):
                return "Alpha"
        return "Belum Absen Masuk"
    return {
        "hadir": "Hadir", "present": "Hadir", "absen": "Alpha", "alpha": "Alpha",
        "izin": "Izin", "leave": "Izin", "sakit": "Sakit", "sick": "Sakit",
        "terlambat": "Terlambat",
    }.get(value, "Alpha")


async def synced_filters(db: AsyncSession, school_id: str) -> dict:
    classes = (await db.execute(select(distinct(SyncedStudent.class_name)).where(
        SyncedStudent.school_id == school_id, SyncedStudent.is_deleted.is_(False), SyncedStudent.class_name.isnot(None)
    ).order_by(SyncedStudent.class_name))).scalars().all()
    years = (await db.execute(select(distinct(SchoolYearSource.name)).where(
        SchoolYearSource.school_id == school_id
    ).order_by(SchoolYearSource.name))).scalars().all()
    return {
        "jenjang": sorted({jenjang_from_class(name) for name in classes}),
        "kelas": classes, "wali_kelas": [], "tahun_ajaran": years,
    }


async def build_synced_dashboard(
    db: AsyncSession, tanggal: dt.date | None, jenjang: str, kelas: str,
    _wali_kelas: str, tahun_ajaran: str, school_id: str | None = None,
) -> dict:
    if not school_id:
        school_id = (await db.execute(select(School.id).where(School.is_active.is_(True)).order_by(School.created_at))).scalar_one()
    school = await db.get(School, school_id)
    school_timezone = school.timezone if school else "Asia/Makassar"
    if tanggal is None:
        tanggal = (await db.execute(select(func.max(SyncedStudentAttendance.attendance_date)).where(
            SyncedStudentAttendance.school_id == school_id
        ))).scalar_one_or_none() or dt.date.today()

    student_stmt = select(SyncedStudent).where(
        SyncedStudent.school_id == school_id, SyncedStudent.is_deleted.is_(False)
    )
    if kelas and kelas != "Semua": student_stmt = student_stmt.where(SyncedStudent.class_name == kelas)
    if tahun_ajaran and tahun_ajaran != "Semua":
        selected_year_uuid = (await db.execute(select(SchoolYearSource.source_uuid).where(
            SchoolYearSource.school_id == school_id, SchoolYearSource.name == tahun_ajaran
        ))).scalar_one_or_none()
        student_stmt = student_stmt.where(SyncedStudent.school_year_uuid == selected_year_uuid)
    students = (await db.execute(student_stmt)).scalars().all()
    if jenjang and jenjang != "Semua": students = [s for s in students if jenjang_from_class(s.class_name) == jenjang]
    allowed_classes = {s.class_name for s in students if s.class_name}
    total_siswa = len(students)

    attendance_stmt = select(SyncedStudentAttendance).where(
        SyncedStudentAttendance.school_id == school_id,
        SyncedStudentAttendance.attendance_date == tanggal,
    )
    if allowed_classes: attendance_stmt = attendance_stmt.where(SyncedStudentAttendance.class_name.in_(allowed_classes))
    elif total_siswa == 0: attendance_stmt = attendance_stmt.where(False)
    rows = (await db.execute(attendance_stmt)).scalars().all()
    counts = Counter(normalize_status(row.status, row.attendance_date, school_timezone) for row in rows)
    for key in ("Hadir", "Terlambat", "Izin", "Sakit", "Alpha", "Belum Absen Masuk"): counts.setdefault(key, 0)
    hadir = counts["Hadir"] + counts["Terlambat"]
    denom = max(len(rows), 1)
    tingkat = round(100 * hadir / denom, 1) if rows else 0.0

    trend_start = tanggal - dt.timedelta(days=29)
    trend_rows = (await db.execute(select(
        SyncedStudentAttendance.attendance_date, SyncedStudentAttendance.status, func.count()
    ).where(
        SyncedStudentAttendance.school_id == school_id,
        SyncedStudentAttendance.attendance_date.between(trend_start, tanggal),
        SyncedStudentAttendance.class_name.in_(allowed_classes) if allowed_classes else False,
    ).group_by(SyncedStudentAttendance.attendance_date, SyncedStudentAttendance.status)
    )).all()
    daily = defaultdict(Counter)
    for day, status, count in trend_rows: daily[day][normalize_status(status, day, school_timezone)] += count
    trend = []
    for day in sorted(daily):
        day_total = sum(daily[day].values()); day_present = daily[day]["Hadir"] + daily[day]["Terlambat"]
        trend.append({"tanggal": day.isoformat(), "persentase": round(100 * day_present / day_total, 1) if day_total else 0})

    student_totals = Counter(s.class_name for s in students if s.class_name)
    class_status = defaultdict(Counter)
    for row in rows: class_status[row.class_name][normalize_status(row.status, row.attendance_date, school_timezone)] += 1
    per_kelas = []
    for class_name, total in student_totals.items():
        present = class_status[class_name]["Hadir"] + class_status[class_name]["Terlambat"]
        observed = sum(class_status[class_name].values())
        per_kelas.append({"kelas": class_name, "persentase": round(100 * present / observed, 1) if observed else 0})
    per_kelas.sort(key=lambda item: item["persentase"], reverse=True)
    level_total, level_present = Counter(), Counter()
    for class_name, total in student_totals.items():
        level = jenjang_from_class(class_name); level_total[level] += total
        level_present[level] += class_status[class_name]["Hadir"] + class_status[class_name]["Terlambat"]
    per_jenjang = [{"jenjang": level, "persentase": round(100 * level_present[level] / total, 1) if total else 0, "total_siswa": total} for level, total in sorted(level_total.items())]

    alpha_rows = (await db.execute(select(
        SyncedStudentAttendance.student_name, SyncedStudentAttendance.class_name, func.count()
    ).where(
        SyncedStudentAttendance.school_id == school_id,
        func.lower(SyncedStudentAttendance.status).in_(["absen", "alpha"]),
    ).group_by(SyncedStudentAttendance.student_name, SyncedStudentAttendance.class_name)
     .order_by(func.count().desc()).limit(10))).all()
    top_alpha = [{"nama": name, "kelas": class_name, "hari": count} for name, class_name, count in alpha_rows]
    belum_masuk = [{"nama": row.student_name, "kelas": row.class_name} for row in rows if normalize_status(row.status, row.attendance_date, school_timezone) == "Belum Absen Masuk"]
    belum_pulang = [{"nama": row.student_name, "kelas": row.class_name} for row in rows if normalize_status(row.status, row.attendance_date, school_timezone) in {"Hadir", "Terlambat"} and not row.clock_out_time]

    def bucket_time(value, boundaries):
        if not value: return None
        value = value[-8:-3] if "T" in value else value[:5]
        for label, low, high in boundaries:
            if (low is None or value >= low) and (high is None or value < high): return label
    arrivals = [("< 06:45", None, "06:45"), ("06:45 - 07:00", "06:45", "07:01"), ("07:01 - 07:15", "07:01", "07:16"), ("07:16 - 07:30", "07:16", "07:31"), ("07:31 - 08:00", "07:31", "08:01"), ("> 08:00", "08:01", None)]
    departures = [("< 15:00", None, "15:00"), ("15:00 - 15:15", "15:00", "15:16"), ("15:16 - 15:30", "15:16", "15:31"), ("15:31 - 16:00", "15:31", "16:01"), ("16:01 - 16:30", "16:01", "16:31"), ("> 16:30", "16:31", None)]
    arrival_counts, departure_counts = Counter(), Counter()
    for row in rows:
        if label := bucket_time(row.clock_in_time, arrivals): arrival_counts[label] += 1
        if label := bucket_time(row.clock_out_time, departures): departure_counts[label] += 1

    colors = {"Hadir": "#22c55e", "Terlambat": "#f59e0b", "Izin": "#eab308", "Sakit": "#3b82f6", "Alpha": "#ef4444"}
    composition = [{"status": status, "jumlah": counts[status], "persen": round(100 * counts[status] / denom, 1) if rows else 0, "color": colors[status]} for status in colors]
    composition += [{"status": "Belum Pulang", "jumlah": len(belum_pulang), "persen": round(100 * len(belum_pulang) / denom, 1) if rows else 0, "color": "#8b5cf6"}, {"status": "Belum Masuk", "jumlah": len(belum_masuk), "persen": round(100 * len(belum_masuk) / denom, 1) if rows else 0, "color": "#6b7280"}]
    rating = "Data Berjalan" if belum_masuk else "Sangat Baik" if tingkat >= 95 else "Baik" if tingkat >= 90 else "Cukup" if tingkat >= 80 else "Perlu Tindak Lanjut"
    attention = []
    if belum_masuk: attention.append(f"{len(belum_masuk)} siswa belum memiliki data check-in; status ini belum dianggap Alpha.")
    if belum_pulang: attention.append(f"{len(belum_pulang)} siswa hadir tanpa data absen pulang.")
    if per_kelas: attention.append(f"Kelas {per_kelas[-1]['kelas']} memiliki persentase kehadiran terendah ({per_kelas[-1]['persentase']}%).")
    return {
        "tanggal": tanggal.isoformat(),
        "ringkasan": {"jam_masuk_sekolah": "-", "batas_terlambat": "-", "jam_pulang_sekolah": "-", "tingkat_kehadiran": tingkat, "siswa_masih_di_sekolah": len(belum_pulang), "total_siswa_hadir": hadir},
        "kartu": {"total_siswa": total_siswa, "record_teramati": len(rows), "hadir": counts["Hadir"], "terlambat": counts["Terlambat"], "izin": counts["Izin"], "sakit": counts["Sakit"], "alpha": counts["Alpha"], "belum_absen_pulang": len(belum_pulang), "belum_absen_masuk": len(belum_masuk)},
        "komposisi_kehadiran": composition, "tingkat_kehadiran": {"persen": tingkat, "rating": rating},
        "trend_30_hari": trend, "per_jenjang": per_jenjang, "per_kelas": per_kelas,
        "top_terlambat": [], "top_alpha": top_alpha,
        "siswa_belum_absen_masuk": belum_masuk, "siswa_belum_absen_pulang": belum_pulang,
        "distribusi_jam_kedatangan": [{"label": label, "jumlah": arrival_counts[label]} for label, _, _ in arrivals],
        "distribusi_jam_pulang": [{"label": label, "jumlah": departure_counts[label]} for label, _, _ in departures],
        "perlu_perhatian": attention,
        "metadata": {
            "source": "School ID", "observed_students": len(rows), "total_students": total_siswa,
            "coverage_percent": round(100 * len(rows) / total_siswa, 1) if total_siswa else 0,
            "is_partial": len(rows) < total_siswa, "pending_check_in": len(belum_masuk),
        },
    }
