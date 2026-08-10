from datetime import date, datetime

from sqlalchemy import (
    String,
    Integer,
    Date,
    Time,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Student(Base):
    __tablename__ = "students"

    nis: Mapped[str] = mapped_column(String(32), primary_key=True)
    nisn: Mapped[str] = mapped_column(String(32), nullable=True)
    nama: Mapped[str] = mapped_column(String(255))
    jenis_kelamin: Mapped[str] = mapped_column(String(1), nullable=True)
    tanggal_lahir: Mapped[date] = mapped_column(Date, nullable=True)
    jenjang: Mapped[str] = mapped_column(String(16), nullable=True)
    kelas: Mapped[str] = mapped_column(String(16), index=True, nullable=True)
    wali_kelas: Mapped[str] = mapped_column(String(255), nullable=True)
    tahun_ajaran: Mapped[str] = mapped_column(String(16), nullable=True)
    status_siswa: Mapped[str] = mapped_column(String(16), default="Aktif")


class AttendanceDaily(Base):
    __tablename__ = "attendance_daily"
    __table_args__ = (UniqueConstraint("tanggal", "nis", name="uq_attendance_tanggal_nis"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tanggal: Mapped[date] = mapped_column(Date, index=True)
    nis: Mapped[str] = mapped_column(String(32), ForeignKey("students.nis"), index=True)
    nama_siswa: Mapped[str] = mapped_column(String(255))
    jenjang: Mapped[str] = mapped_column(String(16), nullable=True)
    kelas: Mapped[str] = mapped_column(String(16), index=True, nullable=True)
    wali_kelas: Mapped[str] = mapped_column(String(255), nullable=True)
    jam_masuk: Mapped[str] = mapped_column(String(8), nullable=True)
    jam_pulang: Mapped[str] = mapped_column(String(8), nullable=True)
    status_kehadiran: Mapped[str] = mapped_column(String(16), index=True)
    keterangan: Mapped[str] = mapped_column(String(255), nullable=True)
    menit_terlambat: Mapped[int] = mapped_column(Integer, default=0)
    sudah_absen_masuk: Mapped[bool] = mapped_column(Boolean, default=False)
    belum_absen_masuk: Mapped[bool] = mapped_column(Boolean, default=False)
    sudah_absen_pulang: Mapped[bool] = mapped_column(Boolean, default=False)
    belum_absen_pulang: Mapped[bool] = mapped_column(Boolean, default=False)
    durasi_menit: Mapped[int] = mapped_column(Integer, nullable=True)
    sumber_data: Mapped[str] = mapped_column(String(64), nullable=True)


class SchoolCalendar(Base):
    __tablename__ = "calendar"

    tanggal: Mapped[date] = mapped_column(Date, primary_key=True)
    hari: Mapped[str] = mapped_column(String(16), nullable=True)
    bulan: Mapped[str] = mapped_column(String(16), nullable=True)
    tahun: Mapped[str] = mapped_column(String(8), nullable=True)
    semester: Mapped[str] = mapped_column(String(16), nullable=True)
    tahun_ajaran: Mapped[str] = mapped_column(String(16), nullable=True)
    jenis_hari: Mapped[str] = mapped_column(String(32), nullable=True)
    hari_sekolah: Mapped[str] = mapped_column(String(8), nullable=True)


class Parameter(Base):
    __tablename__ = "parameters"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    keterangan: Mapped[str] = mapped_column(String(255), nullable=True)


class ImportLog(Base):
    __tablename__ = "import_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rows_students: Mapped[int] = mapped_column(Integer, default=0)
    rows_attendance: Mapped[int] = mapped_column(Integer, default=0)
    rows_calendar: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="success")
    message: Mapped[str] = mapped_column(String(500), nullable=True)
