import datetime as dt
import re
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models_multitenant import School, SchoolYearSource, SyncedClassAttendance, SyncedStudent, SyncedStudentAttendance, SyncedSubject, SyncedTeacher
from app.config import settings

_JENJANG_PREFIX = re.compile(r"^[A-Za-z]+")


def jenjang_from_class(name: str | None) -> str:
    """Level prefix of a class name, e.g. 'XI.7' -> 'XI', 'XII-A' -> 'XII'.

    Class names vary by school ('X.1', 'VII-A', 'XII IPA 2', ...) - only the
    leading run of letters is the level, whatever separator follows it.
    """
    if not name:
        return "-"
    match = _JENJANG_PREFIX.match(name.strip())
    return match.group(0).upper() if match else name.strip()


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


def _hhmm(value: str | None) -> str | None:
    if not value:
        return None
    return value[-8:-3] if "T" in value else value[:5]


def classify_status(
    raw_status: str | None,
    clock_in_time: str | None,
    attendance_date: dt.date | None,
    timezone_name: str,
    late_cutoff_time: str | None,
) -> str:
    """normalize_status(), then upgrade Hadir -> Terlambat by clock-in time.

    School ID rarely sends a distinct "terlambat" status - most schools only
    report Hadir/Absen/Belum Clock In. Lateness has to be derived from
    clock_in_time against the school's configured cutoff (Settings). Without
    a cutoff configured, everyone present stays "Hadir" - we cannot guess.
    """
    label = normalize_status(raw_status, attendance_date, timezone_name)
    if label == "Hadir" and late_cutoff_time:
        clock_in = _hhmm(clock_in_time)
        if clock_in and clock_in > late_cutoff_time:
            return "Terlambat"
    return label


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
    late_cutoff = school.late_cutoff_time if school else None
    counts = Counter(classify_status(row.status, row.clock_in_time, row.attendance_date, school_timezone, late_cutoff) for row in rows)
    for key in ("Hadir", "Terlambat", "Izin", "Sakit", "Alpha", "Belum Absen Masuk"): counts.setdefault(key, 0)
    hadir = counts["Hadir"] + counts["Terlambat"]
    denom = max(len(rows), 1)
    tingkat = round(100 * hadir / denom, 1) if rows else 0.0

    trend_start = tanggal - dt.timedelta(days=29)
    trend_rows = (await db.execute(select(
        SyncedStudentAttendance.attendance_date, SyncedStudentAttendance.status, SyncedStudentAttendance.clock_in_time
    ).where(
        SyncedStudentAttendance.school_id == school_id,
        SyncedStudentAttendance.attendance_date.between(trend_start, tanggal),
        SyncedStudentAttendance.class_name.in_(allowed_classes) if allowed_classes else False,
    ))).all()
    daily = defaultdict(Counter)
    for day, status, clock_in_time in trend_rows:
        daily[day][classify_status(status, clock_in_time, day, school_timezone, late_cutoff)] += 1
    trend = []
    for day in sorted(daily):
        day_total = sum(daily[day].values()); day_present = daily[day]["Hadir"] + daily[day]["Terlambat"]
        trend.append({"tanggal": day.isoformat(), "persentase": round(100 * day_present / day_total, 1) if day_total else 0})

    student_totals = Counter(s.class_name for s in students if s.class_name)
    class_status = defaultdict(Counter)
    for row in rows: class_status[row.class_name][classify_status(row.status, row.clock_in_time, row.attendance_date, school_timezone, late_cutoff)] += 1
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

    top_terlambat: list[dict] = []
    if late_cutoff:
        # Terlambat tidak selalu jadi status tersendiri di sumber - harus
        # dihitung per baris dari clock_in_time, jadi tidak bisa GROUP BY di SQL.
        hadir_rows = (await db.execute(select(
            SyncedStudentAttendance.student_name, SyncedStudentAttendance.class_name,
            SyncedStudentAttendance.attendance_date, SyncedStudentAttendance.clock_in_time,
        ).where(
            SyncedStudentAttendance.school_id == school_id,
            func.lower(SyncedStudentAttendance.status).in_(["hadir", "present"]),
            SyncedStudentAttendance.clock_in_time.isnot(None),
        ))).all()
        late_counter: Counter = Counter()
        for name, class_name, attendance_date, clock_in_time in hadir_rows:
            if classify_status("hadir", clock_in_time, attendance_date, school_timezone, late_cutoff) == "Terlambat":
                late_counter[(name, class_name)] += 1
        top_terlambat = [
            {"nama": name, "kelas": class_name, "hari": count}
            for (name, class_name), count in late_counter.most_common(10)
        ]
    belum_masuk = [{"nama": row.student_name, "kelas": row.class_name} for row in rows if classify_status(row.status, row.clock_in_time, row.attendance_date, school_timezone, late_cutoff) == "Belum Absen Masuk"]
    belum_pulang = [{"nama": row.student_name, "kelas": row.class_name} for row in rows if classify_status(row.status, row.clock_in_time, row.attendance_date, school_timezone, late_cutoff) in {"Hadir", "Terlambat"} and not row.clock_out_time]

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
    if not late_cutoff: attention.append("Batas jam terlambat belum diatur di Settings - status Terlambat belum bisa dihitung.")
    return {
        "tanggal": tanggal.isoformat(),
        "ringkasan": {
            "jam_masuk_sekolah": (school.school_start_time if school else None) or "-",
            "batas_terlambat": late_cutoff or "-",
            "jam_pulang_sekolah": "-",
            "tingkat_kehadiran": tingkat, "siswa_masih_di_sekolah": len(belum_pulang), "total_siswa_hadir": hadir,
        },
        "kartu": {"total_siswa": total_siswa, "record_teramati": len(rows), "hadir": counts["Hadir"], "terlambat": counts["Terlambat"], "izin": counts["Izin"], "sakit": counts["Sakit"], "alpha": counts["Alpha"], "belum_absen_pulang": len(belum_pulang), "belum_absen_masuk": len(belum_masuk)},
        "komposisi_kehadiran": composition, "tingkat_kehadiran": {"persen": tingkat, "rating": rating},
        "trend_30_hari": trend, "per_jenjang": per_jenjang, "per_kelas": per_kelas,
        "top_terlambat": top_terlambat, "top_alpha": top_alpha,
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


async def build_guru_dashboard(db: AsyncSession, school_id: str | None = None) -> dict:
    """Dashboard guru versi minimal: hanya data master yang tersedia dari School ID
    (nama, gender, aktif/nonaktif, wali kelas). School ID tidak menyediakan absensi
    masuk-pulang guru, dan absensi mengajar per mapel/kelas belum terisi di sumbernya
    untuk sekolah manapun yang terdaftar saat ini - jadi belum bisa ditampilkan."""
    if not school_id:
        school_id = (await db.execute(select(School.id).where(School.is_active.is_(True)).order_by(School.created_at))).scalar_one()

    active_teacher = (SyncedTeacher.school_id == school_id, SyncedTeacher.is_deleted.is_(False))
    teachers = (await db.execute(select(SyncedTeacher).where(*active_teacher).order_by(SyncedTeacher.name))).scalars().all()

    gender_counts = Counter()
    daftar_guru = []
    for teacher in teachers:
        gender_label = {"1": "Laki-laki", "2": "Perempuan", "L": "Laki-laki", "P": "Perempuan"}.get((teacher.gender or "").upper(), "Belum terisi")
        gender_counts[gender_label] += 1
        daftar_guru.append({
            "nama": teacher.name,
            "jenis_kelamin": gender_label,
            "status": "Aktif" if teacher.is_active else "Nonaktif",
            # homeroom_class_source_id sebenarnya menyimpan nama kelas (lihat sync_service.normalize),
            # bukan uuid - sumbernya memang cuma memberi nama string, bukan objek {uuid,name}.
            "wali_kelas": teacher.homeroom_class_source_id or None,
        })

    total_guru = len(teachers)
    guru_aktif = sum(1 for t in teachers if t.is_active)
    wali_kelas_terpetakan = sum(1 for g in daftar_guru if g["wali_kelas"])
    colors = {"Laki-laki": "#3b82f6", "Perempuan": "#ec4899", "Belum terisi": "#94a3b8"}
    komposisi_gender = [
        {"status": label, "jumlah": gender_counts[label], "persen": round(100 * gender_counts[label] / total_guru, 1) if total_guru else 0, "color": colors[label]}
        for label in ("Laki-laki", "Perempuan", "Belum terisi") if gender_counts[label] > 0
    ]

    return {
        "kartu": {
            "total_guru": total_guru, "guru_aktif": guru_aktif,
            "guru_nonaktif": total_guru - guru_aktif, "wali_kelas_terpetakan": wali_kelas_terpetakan,
        },
        "komposisi_gender": komposisi_gender,
        "daftar_guru": sorted(daftar_guru, key=lambda g: g["nama"]),
        "catatan": (
            "Absensi masuk-pulang guru dan absensi mengajar per mapel/kelas belum tersedia dari School ID "
            "untuk sekolah ini - dashboard menampilkan data master guru yang tersedia."
        ),
    }


async def guru_siswa_filters(db: AsyncSession, school_id: str) -> dict:
    classes = (await db.execute(select(distinct(SyncedStudent.class_name)).where(
        SyncedStudent.school_id == school_id, SyncedStudent.is_deleted.is_(False), SyncedStudent.class_name.isnot(None)
    ).order_by(SyncedStudent.class_name))).scalars().all()
    subjects = (await db.execute(select(distinct(SyncedSubject.name)).where(
        SyncedSubject.school_id == school_id, SyncedSubject.is_deleted.is_(False)
    ).order_by(SyncedSubject.name))).scalars().all()
    teachers = (await db.execute(select(distinct(SyncedTeacher.name)).where(
        SyncedTeacher.school_id == school_id, SyncedTeacher.is_deleted.is_(False), SyncedTeacher.is_active.is_(True)
    ).order_by(SyncedTeacher.name))).scalars().all()
    return {
        "jenjang": sorted({jenjang_from_class(name) for name in classes}),
        "kelas": classes, "mata_pelajaran": subjects, "guru": teachers,
    }


async def build_guru_siswa_dashboard(
    db: AsyncSession, start: dt.date, end: dt.date,
    jenjang: str, kelas: str, mapel: str, guru: str, school_id: str | None = None,
) -> dict:
    """Dashboard gabungan kehadiran guru mengajar + siswa per sesi (per gambar
    contoh). Kehadiran guru disimpulkan dari sesi (SyncedClassAttendance) yang
    tercatat lewat fitur 'absensi per mapel' School ID, BUKAN dari clock-in/out
    guru terpisah (sumbernya tidak punya itu). Guru Terjadwal / Belum Terdeteksi
    butuh data Jadwal Pelajaran yang saat ini tidak tersedia sama sekali dari
    School ID untuk sekolah manapun yang terdaftar (schedules_count = 0 di semua
    kelas) - keduanya dikembalikan null sampai sumber jadwal itu ada.
    """
    if not school_id:
        school_id = (await db.execute(select(School.id).where(School.is_active.is_(True)).order_by(School.created_at))).scalar_one()
    school = await db.get(School, school_id)
    school_timezone = school.timezone if school else "Asia/Makassar"
    late_cutoff = school.late_cutoff_time if school else None

    active_student = (SyncedStudent.school_id == school_id, SyncedStudent.is_deleted.is_(False))
    student_stmt = select(SyncedStudent.name, SyncedStudent.class_name).where(*active_student)
    if kelas and kelas != "Semua":
        student_stmt = student_stmt.where(SyncedStudent.class_name == kelas)
    students = (await db.execute(student_stmt)).all()
    if jenjang and jenjang != "Semua":
        students = [(name, class_name) for name, class_name in students if jenjang_from_class(class_name) == jenjang]
    allowed_classes = {class_name for _, class_name in students if class_name}
    total_siswa = len(students)

    session_stmt = select(SyncedClassAttendance).where(
        SyncedClassAttendance.school_id == school_id,
        SyncedClassAttendance.attendance_date.between(start, end),
        SyncedClassAttendance.is_deleted.is_(False),
    )
    if allowed_classes:
        session_stmt = session_stmt.where(SyncedClassAttendance.class_name.in_(allowed_classes))
    if mapel and mapel != "Semua":
        session_stmt = session_stmt.where(SyncedClassAttendance.subject_name == mapel)
    if guru and guru != "Semua":
        session_stmt = session_stmt.where(SyncedClassAttendance.teacher_name == guru)
    sessions = (await db.execute(session_stmt.order_by(
        SyncedClassAttendance.attendance_date, SyncedClassAttendance.start_time
    ))).scalars().all()

    monitoring_sesi = []
    subject_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    class_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    teachers_with_session = set()
    daily_session_counts: dict[dt.date, int] = defaultdict(int)
    for s in sessions:
        observed = s.present_count + s.absent_count
        persen = round(100 * s.present_count / observed, 1) if observed else 0.0
        monitoring_sesi.append({
            "tanggal": s.attendance_date.isoformat(),
            "jam": s.start_time, "sesi": s.session_label, "kelas": s.class_name,
            "mata_pelajaran": s.subject_name, "guru": s.teacher_name,
            "status_guru": "Hadir Mengajar" if s.present_count > 0 or s.absent_count > 0 else "Belum Terdeteksi",
            "siswa_hadir": s.present_count, "siswa_alpha": s.absent_count,
            "kehadiran_persen": persen,
        })
        if s.subject_name:
            subject_totals[s.subject_name][0] += s.present_count
            subject_totals[s.subject_name][1] += observed
        if s.class_name:
            class_totals[s.class_name][0] += s.present_count
            class_totals[s.class_name][1] += observed
        if s.teacher_name:
            teachers_with_session.add(s.teacher_name)
        daily_session_counts[s.attendance_date] += 1

    kehadiran_per_mapel = sorted(
        [{"mapel": name, "persen": round(100 * present / total, 1) if total else 0} for name, (present, total) in subject_totals.items()],
        key=lambda item: item["persen"], reverse=True,
    )
    kehadiran_per_kelas = sorted(
        [{"kelas": name, "persen": round(100 * present / total, 1) if total else 0} for name, (present, total) in class_totals.items()],
        key=lambda item: item["persen"], reverse=True,
    )
    trend_guru = [{"tanggal": d.isoformat(), "jumlah_sesi": c} for d, c in sorted(daily_session_counts.items())]

    attendance_stmt = select(SyncedStudentAttendance).where(
        SyncedStudentAttendance.school_id == school_id,
        SyncedStudentAttendance.attendance_date.between(start, end),
    )
    if allowed_classes:
        attendance_stmt = attendance_stmt.where(SyncedStudentAttendance.class_name.in_(allowed_classes))
    student_rows = (await db.execute(attendance_stmt)).scalars().all()
    status_counts = Counter(
        classify_status(row.status, row.clock_in_time, row.attendance_date, school_timezone, late_cutoff)
        for row in student_rows
    )
    daily_student: dict[dt.date, Counter] = defaultdict(Counter)
    for row in student_rows:
        label = classify_status(row.status, row.clock_in_time, row.attendance_date, school_timezone, late_cutoff)
        daily_student[row.attendance_date][label] += 1
    trend_siswa = []
    for day in sorted(daily_student):
        day_total = sum(daily_student[day].values())
        day_present = daily_student[day]["Hadir"] + daily_student[day]["Terlambat"]
        trend_siswa.append({"tanggal": day.isoformat(), "persentase": round(100 * day_present / day_total, 1) if day_total else 0})

    hadir_total = status_counts["Hadir"] + status_counts["Terlambat"]
    observed_total = sum(status_counts.values())
    colors = {"Hadir": "#22c55e", "Terlambat": "#f59e0b", "Izin": "#eab308", "Sakit": "#3b82f6", "Alpha": "#ef4444"}
    ringkasan_siswa = [
        {"status": status, "jumlah": status_counts[status], "persen": round(100 * status_counts[status] / observed_total, 1) if observed_total else 0, "color": colors[status]}
        for status in colors if status_counts[status] > 0
    ]

    perlu_perhatian = []
    belum_terdeteksi = sum(1 for s in monitoring_sesi if s["status_guru"] == "Belum Terdeteksi")
    if belum_terdeteksi:
        perlu_perhatian.append(f"{belum_terdeteksi} sesi belum terdeteksi (guru belum melakukan absensi siswa pada sesi yang sudah berjalan).")
    if status_counts["Alpha"]:
        perlu_perhatian.append(f"{status_counts['Alpha']} siswa Alpha tanpa keterangan pada periode ini.")
    if kehadiran_per_kelas:
        terendah = kehadiran_per_kelas[-1]
        perlu_perhatian.append(f"Kelas {terendah['kelas']} memiliki kehadiran terendah ({terendah['persen']}%).")
    if kehadiran_per_mapel:
        terendah_mapel = kehadiran_per_mapel[-1]
        perlu_perhatian.append(f"Mata pelajaran {terendah_mapel['mapel']} memiliki kehadiran siswa terendah ({terendah_mapel['persen']}%).")
    if not sessions:
        perlu_perhatian.append(
            "Belum ada sesi mengajar tercatat pada periode ini - sekolah belum mengisi Jadwal Pelajaran dan/atau "
            "belum memakai fitur absensi per mata pelajaran di School ID."
        )

    return {
        "periode": {"start": start.isoformat(), "end": end.isoformat()},
        "kartu": {
            "guru_terjadwal": None,
            "guru_hadir_mengajar": len(teachers_with_session),
            "guru_belum_terdeteksi": None,
            "total_sesi_pelajaran": len(sessions),
            "siswa_terdaftar": total_siswa,
            "kehadiran_siswa": {"jumlah": hadir_total, "persen": round(100 * hadir_total / observed_total, 1) if observed_total else 0},
            "izin": status_counts["Izin"], "sakit": status_counts["Sakit"], "alpha": status_counts["Alpha"],
        },
        "monitoring_sesi": monitoring_sesi,
        "trend_guru": trend_guru,
        "trend_siswa": trend_siswa,
        "kehadiran_per_mapel": kehadiran_per_mapel,
        "kehadiran_per_kelas": kehadiran_per_kelas,
        "ringkasan_siswa": ringkasan_siswa,
        "perlu_perhatian": perlu_perhatian,
        "catatan": (
            "Kehadiran guru dihitung berdasarkan absensi siswa yang dilakukan guru pada setiap sesi mata pelajaran "
            "(fitur 'absensi per mapel' School ID). \"Guru Terjadwal\" dan \"Guru Belum Terdeteksi\" butuh data "
            "Jadwal Pelajaran yang belum diisi sekolah di School ID, jadi belum bisa ditampilkan."
        ),
    }
