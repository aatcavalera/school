import asyncio
import datetime as dt
import random
import os

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import SessionLocal
from app.models import AttendanceDaily, Parameter, SchoolCalendar, Student

FIRST_NAMES = [
    "Ahmad", "Budi", "Citra", "Dewi", "Eka", "Fajar", "Gita", "Hadi", "Indah", "Joko",
    "Kartika", "Lestari", "Made", "Nur", "Oki", "Putri", "Rangga", "Siti", "Taufik", "Utami",
    "Vina", "Wahyu", "Yuni", "Zaki", "Andi", "Bella", "Cahya", "Dian", "Erlangga", "Farah",
    "Galih", "Hana", "Irfan", "Jihan", "Kevin", "Laila", "Miftah", "Naufal", "Olivia", "Putra",
]
LAST_NAMES = [
    "Santoso", "Pratama", "Wijaya", "Kusuma", "Setiawan", "Ramadhan", "Saputra", "Nugroho",
    "Hidayat", "Suryani", "Maulana", "Fauzan", "Aisyah", "Marlina", "Nurhaliza", "Anggraini",
    "Firmansyah", "Gunawan", "Handayani", "Iskandar", "Juliana", "Kurniawan", "Lubis", "Mahendra",
]
WALI_KELAS_POOL = [
    "Budi Santoso, S.Pd", "Siti Nurhaliza, S.Pd", "Agus Setiawan, S.Pd", "Rina Marlina, S.Pd",
    "Dewi Anggraini, S.Pd", "Hendra Kurniawan, S.Pd", "Fitriani, S.Pd", "Yusuf Iskandar, S.Pd",
    "Lestari Handayani, S.Pd",
]
JENJANG_KELAS = [
    ("VII", "VII-A"), ("VII", "VII-B"), ("VII", "VII-C"),
    ("VIII", "VIII-A"), ("VIII", "VIII-B"), ("VIII", "VIII-C"),
    ("IX", "IX-A"), ("IX", "IX-B"), ("IX", "IX-C"),
]
STUDENTS_PER_KELAS = 143
TAHUN_AJARAN = "2026/2027"
DAYS_OF_HISTORY = 35


def _random_name(used: set) -> str:
    for _ in range(50):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in used:
            used.add(name)
            return name
    # Pool kombinasi nama depan x belakang habis - tambahkan nama tengah agar tetap unik & selalu berhenti.
    while True:
        name = f"{random.choice(FIRST_NAMES)} {random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        if name not in used:
            used.add(name)
            return name


def _school_days(end_date: dt.date, count_calendar_days: int) -> list[dt.date]:
    days = []
    d = end_date
    while len(days) < count_calendar_days:
        if d.weekday() < 5:
            days.append(d)
        d -= dt.timedelta(days=1)
    return sorted(days)


async def main():
    if os.environ.get("ALLOW_DUMMY_SEED") != "yes":
        raise SystemExit("Dummy seed dinonaktifkan. Set ALLOW_DUMMY_SEED=yes hanya pada database development.")
    random.seed(42)
    used_names: set = set()

    students = []
    nis_counter = 240001
    wali_by_kelas = {kelas: random.choice(WALI_KELAS_POOL) for _, kelas in JENJANG_KELAS}

    for jenjang, kelas in JENJANG_KELAS:
        for _ in range(STUDENTS_PER_KELAS):
            nis = str(nis_counter)
            nis_counter += 1
            nama = _random_name(used_names)
            jk = random.choice(["L", "P"])
            usia_hari = random.randint(12 * 365, 15 * 365)
            tanggal_lahir = dt.date.today() - dt.timedelta(days=usia_hari)
            students.append(
                {
                    "nis": nis,
                    "nisn": f"00{nis}",
                    "nama": nama,
                    "jenis_kelamin": jk,
                    "tanggal_lahir": tanggal_lahir,
                    "jenjang": jenjang,
                    "kelas": kelas,
                    "wali_kelas": wali_by_kelas[kelas],
                    "tahun_ajaran": TAHUN_AJARAN,
                    "status_siswa": "Aktif",
                }
            )

    today = dt.date.today()
    calendar_days = _school_days(today, DAYS_OF_HISTORY)
    calendar_rows = []
    hari_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan_id = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
                "September", "Oktober", "November", "Desember"]
    for d in calendar_days:
        calendar_rows.append(
            {
                "tanggal": d,
                "hari": hari_id[d.weekday()],
                "bulan": bulan_id[d.month],
                "tahun": str(d.year),
                "semester": "Ganjil" if d.month >= 7 else "Genap",
                "tahun_ajaran": TAHUN_AJARAN,
                "jenis_hari": "Hari Efektif",
                "hari_sekolah": "Ya",
            }
        )

    # Setiap siswa punya kecenderungan kehadiran sendiri agar top-10 & trend terlihat realistis.
    student_profile = {}
    for s in students:
        roll = random.random()
        if roll < 0.05:
            student_profile[s["nis"]] = "sering_terlambat"
        elif roll < 0.08:
            student_profile[s["nis"]] = "sering_alpha"
        else:
            student_profile[s["nis"]] = "normal"

    attendance_rows = []
    is_last_day = {d: (d == calendar_days[-1]) for d in calendar_days}

    for d in calendar_days:
        last_day = is_last_day[d]
        for s in students:
            profile = student_profile[s["nis"]]
            roll = random.random()

            if profile == "sering_alpha":
                status = random.choices(
                    ["Hadir", "Terlambat", "Izin", "Sakit", "Alpha"],
                    weights=[55, 10, 8, 7, 20],
                )[0]
            elif profile == "sering_terlambat":
                status = random.choices(
                    ["Hadir", "Terlambat", "Izin", "Sakit", "Alpha"],
                    weights=[55, 35, 4, 4, 2],
                )[0]
            else:
                status = random.choices(
                    ["Hadir", "Terlambat", "Izin", "Sakit", "Alpha"],
                    weights=[92, 4, 2, 2, 1] if d.weekday() != 0 else [86, 7, 3, 2, 2],
                )[0]

            jam_masuk = None
            jam_pulang = None
            menit_terlambat = 0
            keterangan = None
            sudah_masuk = False
            belum_masuk = False
            sudah_pulang = False
            belum_pulang = False
            durasi = None

            if status == "Hadir":
                base = 6 * 60 + random.randint(30, 59)
                jam_masuk = f"{base // 60:02d}:{base % 60:02d}"
                sudah_masuk = True
                if last_day and random.random() < 0.02:
                    belum_pulang = True
                else:
                    keluar = 15 * 60 + 30 + random.randint(-20, 70)
                    jam_pulang = f"{keluar // 60:02d}:{keluar % 60:02d}"
                    sudah_pulang = True
                    durasi = keluar - base
            elif status == "Terlambat":
                base = 7 * 60 + random.randint(1, 50)
                jam_masuk = f"{base // 60:02d}:{base % 60:02d}"
                menit_terlambat = base - (7 * 60)
                sudah_masuk = True
                keluar = 15 * 60 + 30 + random.randint(-10, 60)
                jam_pulang = f"{keluar // 60:02d}:{keluar % 60:02d}"
                sudah_pulang = True
                durasi = keluar - base
            elif status == "Izin":
                keterangan = random.choice(["Keperluan keluarga", "Acara keluarga", "Ada urusan penting"])
            elif status == "Sakit":
                keterangan = random.choice(["Demam", "Flu", "Sakit perut", "Pusing"])
            elif status == "Alpha":
                if last_day and random.random() < 0.6:
                    belum_masuk = True

            attendance_rows.append(
                {
                    "tanggal": d,
                    "nis": s["nis"],
                    "nama_siswa": s["nama"],
                    "jenjang": s["jenjang"],
                    "kelas": s["kelas"],
                    "wali_kelas": s["wali_kelas"],
                    "jam_masuk": jam_masuk,
                    "jam_pulang": jam_pulang,
                    "status_kehadiran": status,
                    "keterangan": keterangan,
                    "menit_terlambat": menit_terlambat,
                    "sudah_absen_masuk": sudah_masuk,
                    "belum_absen_masuk": belum_masuk,
                    "sudah_absen_pulang": sudah_pulang,
                    "belum_absen_pulang": belum_pulang,
                    "durasi_menit": durasi,
                    "sumber_data": "Skul.id",
                }
            )

    parameters = [
        {"key": "Jam Masuk Sekolah", "value": "07:00", "keterangan": "Jam mulai sekolah"},
        {"key": "Batas Terlambat", "value": "07:00", "keterangan": "Jam masuk setelah waktu ini dikategorikan terlambat"},
        {"key": "Jam Pulang Sekolah", "value": "15:30", "keterangan": "Untuk menentukan siswa belum absensi pulang"},
        {"key": "Batas Absensi Masuk", "value": "10:00", "keterangan": "Batas monitoring siswa yang belum check-in"},
    ]

    async with SessionLocal() as db:
        print("Menghapus data lama...")
        await db.execute(delete(AttendanceDaily))
        await db.execute(delete(SchoolCalendar))
        await db.execute(delete(Student))
        await db.commit()

        print(f"Menyisipkan {len(students)} siswa...")
        for i in range(0, len(students), 500):
            await db.execute(pg_insert(Student).values(students[i : i + 500]))
        await db.commit()

        print(f"Menyisipkan {len(calendar_rows)} baris kalender...")
        await db.execute(pg_insert(SchoolCalendar).values(calendar_rows))
        await db.commit()

        print(f"Menyisipkan {len(attendance_rows)} baris absensi (ini bisa memakan waktu)...")
        for i in range(0, len(attendance_rows), 1000):
            await db.execute(pg_insert(AttendanceDaily).values(attendance_rows[i : i + 1000]))
            await db.commit()

        for p in parameters:
            stmt = pg_insert(Parameter).values(**p)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Parameter.key], set_={"value": stmt.excluded.value, "keterangan": stmt.excluded.keterangan}
            )
            await db.execute(stmt)
        await db.commit()

    print("Selesai.")
    print(f"Total siswa: {len(students)}")
    print(f"Total baris absensi: {len(attendance_rows)}")
    print(f"Rentang tanggal: {calendar_days[0]} s/d {calendar_days[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
