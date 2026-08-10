import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import AttendanceDaily, Student, Parameter
from app.security import get_current_username
from app.models_multitenant import AttendanceDailyAggregate, School, SyncCheckpoint, SyncedStudent
from app.routers.dashboard_synced import build_synced_dashboard, normalize_status, synced_filters
from app.access import CurrentUser, accessible_school_ids, get_current_user, resolve_school_id
from app.cache import dashboard_cache

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

STATUS_LIST = ["Hadir", "Terlambat", "Izin", "Sakit", "Alpha"]
STATUS_COLOR = {
    "Hadir": "#22c55e",
    "Terlambat": "#f59e0b",
    "Izin": "#eab308",
    "Sakit": "#3b82f6",
    "Alpha": "#ef4444",
}


@router.get("/overview")
async def overview(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    allowed = await accessible_school_ids(db, user)
    schools = (await db.execute(select(School).where(School.id.in_(allowed)).order_by(School.name))).scalars().all()
    result = []
    for school in schools:
        latest_date = (await db.execute(select(func.max(AttendanceDailyAggregate.attendance_date)).where(
            AttendanceDailyAggregate.school_id == school.id
        ))).scalar_one_or_none()
        status_rows = []
        if latest_date:
            status_rows = (await db.execute(select(
                AttendanceDailyAggregate.status, func.sum(AttendanceDailyAggregate.student_count)
            ).where(
                AttendanceDailyAggregate.school_id == school.id,
                AttendanceDailyAggregate.attendance_date == latest_date,
            ).group_by(AttendanceDailyAggregate.status))).all()
        counts = {"Hadir": 0, "Terlambat": 0, "Izin": 0, "Sakit": 0, "Alpha": 0, "Belum Absen Masuk": 0}
        for status_name, count in status_rows:
            counts[normalize_status(status_name, latest_date, school.timezone)] += int(count or 0)
        observed = sum(counts.values())
        total_students = (await db.execute(select(func.count()).select_from(SyncedStudent).where(
            SyncedStudent.school_id == school.id, SyncedStudent.is_deleted.is_(False)
        ))).scalar_one()
        last_sync = (await db.execute(select(func.max(SyncCheckpoint.last_success_at)).where(
            SyncCheckpoint.school_id == school.id
        ))).scalar_one_or_none()
        result.append({
            "id": school.id, "code": school.code, "name": school.name,
            "latest_attendance_date": latest_date.isoformat() if latest_date else None,
            "last_sync_at": last_sync.isoformat() if last_sync else None,
            "total_students": total_students, "observed_students": observed,
            "present": counts["Hadir"] + counts["Terlambat"], "absent": counts["Alpha"],
            "pending_check_in": counts["Belum Absen Masuk"],
            "attendance_rate": round(100 * (counts["Hadir"] + counts["Terlambat"]) / observed, 1) if observed else 0,
            "sync_status": "healthy" if last_sync else "pending",
        })
    return {"schools": result, "total_schools": len(result)}


def _apply_filters(stmt, jenjang, kelas, wali_kelas, tahun_ajaran, tanggal=None, tanggal_col=None):
    if jenjang and jenjang != "Semua":
        stmt = stmt.where(AttendanceDaily.jenjang == jenjang)
    if kelas and kelas != "Semua":
        stmt = stmt.where(AttendanceDaily.kelas == kelas)
    if wali_kelas and wali_kelas != "Semua":
        stmt = stmt.where(AttendanceDaily.wali_kelas == wali_kelas)
    if tanggal is not None and tanggal_col is not None:
        stmt = stmt.where(tanggal_col == tanggal)
    return stmt


def _time_bucket(value: Optional[str], buckets: list[tuple[str, Optional[str], Optional[str]]]) -> Optional[str]:
    if not value:
        return None
    for label, lo, hi in buckets:
        if lo and value < lo:
            continue
        if hi and value >= hi:
            continue
        return label
    return buckets[-1][0]


ARRIVAL_BUCKETS = [
    ("< 06:45", None, "06:45"),
    ("06:45 - 07:00", "06:45", "07:01"),
    ("07:01 - 07:15", "07:01", "07:16"),
    ("07:16 - 07:30", "07:16", "07:31"),
    ("07:31 - 08:00", "07:31", "08:01"),
    ("> 08:00", "08:01", None),
]
DEPARTURE_BUCKETS = [
    ("< 15:00", None, "15:00"),
    ("15:00 - 15:15", "15:00", "15:16"),
    ("15:16 - 15:30", "15:16", "15:31"),
    ("15:31 - 16:00", "15:31", "16:01"),
    ("16:01 - 16:30", "16:01", "16:31"),
    ("> 16:30", "16:31", None),
]


@router.get("/filters")
async def get_filters(
    school_id: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if (await db.execute(select(func.count()).select_from(School))).scalar_one() > 0:
        selected_school = await resolve_school_id(db, user, school_id)
        return await synced_filters(db, selected_school)
    async def distinct_values(col):
        res = await db.execute(select(distinct(col)).where(col.isnot(None)).order_by(col))
        return [r[0] for r in res.all() if r[0]]

    return {
        "jenjang": await distinct_values(Student.jenjang),
        "kelas": await distinct_values(Student.kelas),
        "wali_kelas": await distinct_values(Student.wali_kelas),
        "tahun_ajaran": await distinct_values(Student.tahun_ajaran),
    }


@router.get("")
async def get_dashboard(
    tanggal: Optional[dt.date] = Query(default=None),
    jenjang: Optional[str] = Query(default="Semua"),
    kelas: Optional[str] = Query(default="Semua"),
    wali_kelas: Optional[str] = Query(default="Semua"),
    tahun_ajaran: Optional[str] = Query(default="Semua"),
    school_id: Optional[str] = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if (await db.execute(select(func.count()).select_from(School))).scalar_one() > 0:
        selected_school = await resolve_school_id(db, user, school_id)
        cache_key = "|".join(map(str, [selected_school, tanggal, jenjang, kelas, wali_kelas, tahun_ajaran]))
        if cached := dashboard_cache.get(cache_key):
            return cached
        response = await build_synced_dashboard(db, tanggal, jenjang, kelas, wali_kelas, tahun_ajaran, selected_school)
        dashboard_cache.set(cache_key, response)
        return response
    if tanggal is None:
        result = await db.execute(select(func.max(AttendanceDaily.tanggal)))
        tanggal = result.scalar_one_or_none() or dt.date.today()

    params_result = await db.execute(select(Parameter))
    params = {p.key: p.value for p in params_result.scalars().all()}

    total_siswa_stmt = select(func.count(distinct(Student.nis))).where(Student.status_siswa == "Aktif")
    if jenjang and jenjang != "Semua":
        total_siswa_stmt = total_siswa_stmt.where(Student.jenjang == jenjang)
    if kelas and kelas != "Semua":
        total_siswa_stmt = total_siswa_stmt.where(Student.kelas == kelas)
    if wali_kelas and wali_kelas != "Semua":
        total_siswa_stmt = total_siswa_stmt.where(Student.wali_kelas == wali_kelas)
    if tahun_ajaran and tahun_ajaran != "Semua":
        total_siswa_stmt = total_siswa_stmt.where(Student.tahun_ajaran == tahun_ajaran)
    total_siswa = (await db.execute(total_siswa_stmt)).scalar_one()

    status_stmt = (
        select(AttendanceDaily.status_kehadiran, func.count())
        .where(AttendanceDaily.tanggal == tanggal)
        .group_by(AttendanceDaily.status_kehadiran)
    )
    status_stmt = _apply_filters(status_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    status_rows = (await db.execute(status_stmt)).all()
    status_counts = {s: 0 for s in STATUS_LIST}
    for status_name, cnt in status_rows:
        if status_name in status_counts:
            status_counts[status_name] = cnt

    belum_masuk_stmt = select(func.count()).where(
        and_(AttendanceDaily.tanggal == tanggal, AttendanceDaily.belum_absen_masuk.is_(True))
    )
    belum_masuk_stmt = _apply_filters(belum_masuk_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    belum_absen_masuk = (await db.execute(belum_masuk_stmt)).scalar_one()

    belum_pulang_stmt = select(func.count()).where(
        and_(AttendanceDaily.tanggal == tanggal, AttendanceDaily.belum_absen_pulang.is_(True))
    )
    belum_pulang_stmt = _apply_filters(belum_pulang_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    belum_absen_pulang = (await db.execute(belum_pulang_stmt)).scalar_one()

    denom = max(total_siswa, 1)
    hadir = status_counts["Hadir"]
    tingkat_kehadiran = round(100 * hadir / denom, 1) if total_siswa else 0.0

    komposisi = [
        {
            "status": s,
            "jumlah": status_counts[s],
            "persen": round(100 * status_counts[s] / denom, 1) if total_siswa else 0.0,
            "color": STATUS_COLOR[s],
        }
        for s in STATUS_LIST
    ]
    komposisi.append(
        {
            "status": "Belum Pulang",
            "jumlah": belum_absen_pulang,
            "persen": round(100 * belum_absen_pulang / denom, 1) if total_siswa else 0.0,
            "color": "#8b5cf6",
        }
    )
    komposisi.append(
        {
            "status": "Belum Masuk",
            "jumlah": belum_absen_masuk,
            "persen": round(100 * belum_absen_masuk / denom, 1) if total_siswa else 0.0,
            "color": "#6b7280",
        }
    )

    trend_start = tanggal - dt.timedelta(days=29)
    trend_stmt = select(
        AttendanceDaily.tanggal,
        func.count().filter(AttendanceDaily.status_kehadiran == "Hadir"),
        func.count(),
    ).where(and_(AttendanceDaily.tanggal >= trend_start, AttendanceDaily.tanggal <= tanggal))
    trend_stmt = _apply_filters(trend_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    trend_stmt = trend_stmt.group_by(AttendanceDaily.tanggal).order_by(AttendanceDaily.tanggal)
    trend_rows = (await db.execute(trend_stmt)).all()
    trend = [
        {
            "tanggal": t.isoformat(),
            "persentase": round(100 * h / c, 1) if c else 0.0,
        }
        for t, h, c in trend_rows
    ]

    jenjang_stmt = select(
        Student.jenjang,
        func.count(distinct(AttendanceDaily.nis)).filter(AttendanceDaily.status_kehadiran == "Hadir"),
        func.count(distinct(Student.nis)),
    ).select_from(Student).outerjoin(
        AttendanceDaily, and_(AttendanceDaily.nis == Student.nis, AttendanceDaily.tanggal == tanggal)
    ).where(Student.status_siswa == "Aktif").group_by(Student.jenjang)
    jenjang_rows = (await db.execute(jenjang_stmt)).all()
    per_jenjang = [
        {
            "jenjang": j,
            "persentase": round(100 * h / t, 1) if t else 0.0,
            "total_siswa": t,
        }
        for j, h, t in jenjang_rows
        if j
    ]

    kelas_stmt = select(
        Student.kelas,
        func.count(distinct(AttendanceDaily.nis)).filter(AttendanceDaily.status_kehadiran == "Hadir"),
        func.count(distinct(Student.nis)),
    ).select_from(Student).outerjoin(
        AttendanceDaily, and_(AttendanceDaily.nis == Student.nis, AttendanceDaily.tanggal == tanggal)
    ).where(Student.status_siswa == "Aktif").group_by(Student.kelas)
    kelas_rows = (await db.execute(kelas_stmt)).all()
    per_kelas = sorted(
        [
            {"kelas": k, "persentase": round(100 * h / t, 1) if t else 0.0}
            for k, h, t in kelas_rows
            if k
        ],
        key=lambda x: x["persentase"],
        reverse=True,
    )

    top_terlambat_stmt = (
        select(AttendanceDaily.nama_siswa, AttendanceDaily.kelas, AttendanceDaily.menit_terlambat)
        .where(and_(AttendanceDaily.tanggal == tanggal, AttendanceDaily.status_kehadiran == "Terlambat"))
        .order_by(AttendanceDaily.menit_terlambat.desc())
        .limit(10)
    )
    top_terlambat_stmt = _apply_filters(top_terlambat_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    top_terlambat = [
        {"nama": n, "kelas": k, "menit": m} for n, k, m in (await db.execute(top_terlambat_stmt)).all()
    ]

    semester_start = dt.date(tanggal.year if tanggal.month >= 7 else tanggal.year - 1, 7, 1)
    top_alpha_stmt = (
        select(AttendanceDaily.nama_siswa, AttendanceDaily.kelas, func.count().label("hari"))
        .where(
            and_(
                AttendanceDaily.status_kehadiran == "Alpha",
                AttendanceDaily.tanggal >= semester_start,
                AttendanceDaily.tanggal <= tanggal,
            )
        )
        .group_by(AttendanceDaily.nama_siswa, AttendanceDaily.kelas)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_alpha_stmt = _apply_filters(top_alpha_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    top_alpha = [{"nama": n, "kelas": k, "hari": h} for n, k, h in (await db.execute(top_alpha_stmt)).all()]

    belum_masuk_list_stmt = (
        select(AttendanceDaily.nama_siswa, AttendanceDaily.kelas)
        .where(and_(AttendanceDaily.tanggal == tanggal, AttendanceDaily.belum_absen_masuk.is_(True)))
        .order_by(AttendanceDaily.nama_siswa)
    )
    belum_masuk_list_stmt = _apply_filters(belum_masuk_list_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    siswa_belum_masuk = [{"nama": n, "kelas": k} for n, k in (await db.execute(belum_masuk_list_stmt)).all()]

    belum_pulang_list_stmt = (
        select(AttendanceDaily.nama_siswa, AttendanceDaily.kelas)
        .where(and_(AttendanceDaily.tanggal == tanggal, AttendanceDaily.belum_absen_pulang.is_(True)))
        .order_by(AttendanceDaily.nama_siswa)
    )
    belum_pulang_list_stmt = _apply_filters(belum_pulang_list_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    siswa_belum_pulang = [{"nama": n, "kelas": k} for n, k in (await db.execute(belum_pulang_list_stmt)).all()]

    jam_stmt = select(AttendanceDaily.jam_masuk, AttendanceDaily.jam_pulang).where(
        AttendanceDaily.tanggal == tanggal
    )
    jam_stmt = _apply_filters(jam_stmt, jenjang, kelas, wali_kelas, tahun_ajaran)
    jam_rows = (await db.execute(jam_stmt)).all()

    arrival_hist = {label: 0 for label, _, _ in ARRIVAL_BUCKETS}
    departure_hist = {label: 0 for label, _, _ in DEPARTURE_BUCKETS}
    for jm, jp in jam_rows:
        b = _time_bucket(jm, ARRIVAL_BUCKETS)
        if b:
            arrival_hist[b] += 1
        b2 = _time_bucket(jp, DEPARTURE_BUCKETS)
        if b2:
            departure_hist[b2] += 1

    if tingkat_kehadiran >= 95:
        rating = "Sangat Baik"
    elif tingkat_kehadiran >= 90:
        rating = "Baik"
    elif tingkat_kehadiran >= 80:
        rating = "Cukup"
    else:
        rating = "Perlu Tindak Lanjut"

    perlu_perhatian = []
    if belum_absen_masuk:
        perlu_perhatian.append(f"{belum_absen_masuk} siswa belum melakukan absen masuk.")
    if belum_absen_pulang:
        perlu_perhatian.append(f"{belum_absen_pulang} siswa belum melakukan absen pulang.")
    if per_kelas:
        terendah = per_kelas[-1]
        perlu_perhatian.append(
            f"Kelas {terendah['kelas']} memiliki persentase kehadiran terendah ({terendah['persentase']}%)."
        )
    if status_counts["Alpha"]:
        perlu_perhatian.append(f"{status_counts['Alpha']} siswa tidak hadir (Alpha).")
    lebih_15 = sum(1 for row in top_terlambat if row["menit"] and row["menit"] > 15)
    if status_counts["Terlambat"]:
        perlu_perhatian.append(
            f"{status_counts['Terlambat']} siswa terlambat, {lebih_15} di antaranya terlambat lebih dari 15 menit."
        )

    return {
        "tanggal": tanggal.isoformat(),
        "ringkasan": {
            "jam_masuk_sekolah": params.get("Jam Masuk Sekolah", "-"),
            "batas_terlambat": params.get("Batas Terlambat", "-"),
            "jam_pulang_sekolah": params.get("Jam Pulang Sekolah", "-"),
            "tingkat_kehadiran": tingkat_kehadiran,
            "siswa_masih_di_sekolah": belum_absen_pulang,
            "total_siswa_hadir": hadir,
        },
        "kartu": {
            "total_siswa": total_siswa,
            "hadir": hadir,
            "terlambat": status_counts["Terlambat"],
            "izin": status_counts["Izin"],
            "sakit": status_counts["Sakit"],
            "alpha": status_counts["Alpha"],
            "belum_absen_pulang": belum_absen_pulang,
            "belum_absen_masuk": belum_absen_masuk,
        },
        "komposisi_kehadiran": komposisi,
        "tingkat_kehadiran": {"persen": tingkat_kehadiran, "rating": rating},
        "trend_30_hari": trend,
        "per_jenjang": per_jenjang,
        "per_kelas": per_kelas,
        "top_terlambat": top_terlambat,
        "top_alpha": top_alpha,
        "siswa_belum_absen_masuk": siswa_belum_masuk,
        "siswa_belum_absen_pulang": siswa_belum_pulang,
        "distribusi_jam_kedatangan": [{"label": k, "jumlah": v} for k, v in arrival_hist.items()],
        "distribusi_jam_pulang": [{"label": k, "jumlah": v} for k, v in departure_hist.items()],
        "perlu_perhatian": perlu_perhatian,
    }
