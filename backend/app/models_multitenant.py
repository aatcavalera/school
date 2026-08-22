import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_uuid() -> str:
    return str(uuid.uuid4())


SCHOOL_CATEGORIES = ("SMA", "SMK", "SMP", "SD", "Lainnya")


class School(Base):
    __tablename__ = "schools"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(16), index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Makassar")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Jam masuk & batas terlambat khusus sekolah ini - dipakai untuk menurunkan
    # status "Terlambat" dari jam clock-in, karena School ID tidak selalu
    # mengirim status telat sebagai nilai terpisah (hanya Hadir/Absen/dst).
    school_start_time: Mapped[str | None] = mapped_column(String(5))
    late_cutoff_time: Mapped[str | None] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserDiknasScope(Base):
    """A diknas user's oversight scope: every active school in these categories."""

    __tablename__ = "user_diknas_scopes"
    __table_args__ = (UniqueConstraint("user_id", "category", name="uq_user_diknas_scope"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(16), index=True)


class SchoolConnection(Base):
    __tablename__ = "school_connections"
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="school_id")
    base_url: Mapped[str] = mapped_column(String(500))
    username_ciphertext: Mapped[str] = mapped_column(Text)
    password_ciphertext: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))


class SchoolSyncSetting(Base):
    __tablename__ = "school_sync_settings"
    __table_args__ = (UniqueConstraint("school_id", "domain", name="uq_school_sync_setting"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=21600)
    page_size: Mapped[int] = mapped_column(Integer, default=100)
    priority: Mapped[int] = mapped_column(Integer, default=100)


class SchoolYearSource(Base):
    __tablename__ = "school_years_source"
    __table_args__ = (UniqueConstraint("school_id", "source_uuid", name="uq_school_year_source"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    source_uuid: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    odd_start: Mapped[date | None] = mapped_column(Date)
    odd_end: Mapped[date | None] = mapped_column(Date)
    even_start: Mapped[date | None] = mapped_column(Date)
    even_end: Mapped[date | None] = mapped_column(Date)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceEntityMixin:
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    source_uuid: Mapped[str] = mapped_column(String(64))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncedStudent(SourceEntityMixin, Base):
    __tablename__ = "synced_students"
    __table_args__ = (
        UniqueConstraint("school_id", "source_uuid", name="uq_synced_student_source"),
        Index("ix_synced_students_school_year", "school_id", "school_year_uuid"),
    )
    school_year_uuid: Mapped[str | None] = mapped_column(String(64))
    nis: Mapped[str | None] = mapped_column(String(32), index=True)
    nisn: Mapped[str | None] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str | None] = mapped_column(String(32), index=True)
    class_source_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    class_name: Mapped[str | None] = mapped_column(String(64))


class SyncedTeacher(SourceEntityMixin, Base):
    __tablename__ = "synced_teachers"
    __table_args__ = (UniqueConstraint("school_id", "source_uuid", name="uq_synced_teacher_source"),)
    nuptk: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    dob: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    homeroom_class_source_id: Mapped[str | None] = mapped_column(String(64))


class GenderOverride(Base):
    """Manual gender correction by an admin, keyed to a synced entity.

    Kept separate from SyncedStudent/SyncedTeacher.gender because that column
    is fully overwritten on every sync from School ID - a value written
    directly onto it would be silently discarded on the next sync run.
    """

    __tablename__ = "gender_overrides"
    __table_args__ = (
        UniqueConstraint("school_id", "entity_type", "source_uuid", name="uq_gender_override_entity"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(16))
    source_uuid: Mapped[str] = mapped_column(String(64))
    gender: Mapped[str] = mapped_column(String(16))
    set_by: Mapped[str] = mapped_column(String(64))
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncedClass(SourceEntityMixin, Base):
    __tablename__ = "synced_classes"
    __table_args__ = (UniqueConstraint("school_id", "source_uuid", name="uq_synced_class_source"),)
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    homeroom_teacher_source_id: Mapped[str | None] = mapped_column(String(64))
    students_count: Mapped[int] = mapped_column(Integer, default=0)


class SyncedSubject(SourceEntityMixin, Base):
    __tablename__ = "synced_subjects"
    __table_args__ = (UniqueConstraint("school_id", "source_uuid", name="uq_synced_subject_source"),)
    name: Mapped[str] = mapped_column(String(255))


class SyncedDomainRecord(SourceEntityMixin, Base):
    """Sanitized records for secondary domains whose upstream contract varies."""

    __tablename__ = "synced_domain_records"
    __table_args__ = (
        UniqueConstraint("school_id", "domain", "source_uuid", name="uq_synced_domain_source"),
        Index("ix_synced_domain_school_date", "school_id", "domain", "event_date"),
    )
    domain: Mapped[str] = mapped_column(String(64), index=True)
    event_date: Mapped[date | None] = mapped_column(Date, index=True)
    school_year_uuid: Mapped[str | None] = mapped_column(String(64))
    student_source_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    teacher_source_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    class_source_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    subject_source_uuid: Mapped[str | None] = mapped_column(String(64), index=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)


class SyncedStudentAttendance(Base):
    __tablename__ = "synced_student_attendances"
    __table_args__ = (
        UniqueConstraint("school_id", "attendance_date", "class_source_uuid", "student_source_id", name="uq_synced_student_attendance"),
        Index("ix_synced_attendance_school_date", "school_id", "attendance_date"),
        Index("ix_synced_attendance_school_class_date", "school_id", "class_source_uuid", "attendance_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    school_year_uuid: Mapped[str] = mapped_column(String(64), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    class_source_uuid: Mapped[str] = mapped_column(String(64), index=True)
    class_name: Mapped[str | None] = mapped_column(String(64))
    student_source_id: Mapped[str] = mapped_column(String(64), index=True)
    student_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), index=True)
    clock_in_time: Mapped[str | None] = mapped_column(String(16))
    clock_out_time: Mapped[str | None] = mapped_column(String(16))
    clock_in_status: Mapped[str | None] = mapped_column(String(32))
    clock_out_status: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(255))
    fingerprint: Mapped[str] = mapped_column(String(64))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AttendanceDailyAggregate(Base):
    __tablename__ = "attendance_daily_aggregates"
    __table_args__ = (
        UniqueConstraint("school_id", "attendance_date", "class_source_uuid", "status", name="uq_attendance_daily_aggregate"),
        Index("ix_attendance_aggregate_school_date", "school_id", "attendance_date"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    class_source_uuid: Mapped[str] = mapped_column(String(64))
    class_name: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    student_count: Mapped[int] = mapped_column(Integer, default=0)
    with_clock_in: Mapped[int] = mapped_column(Integer, default=0)
    with_clock_out: Mapped[int] = mapped_column(Integer, default=0)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSchoolAccess(Base):
    __tablename__ = "user_school_access"
    __table_args__ = (UniqueConstraint("user_id", "school_id", name="uq_user_school_access"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="viewer")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    school_id: Mapped[str | None] = mapped_column(ForeignKey("schools.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = (Index("ix_sync_runs_school_started", "school_id", "started_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_seen: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(String(500))


class SyncCheckpoint(Base):
    __tablename__ = "sync_checkpoints"
    __table_args__ = (UniqueConstraint("school_id", "domain", "scope", name="uq_sync_checkpoint"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(64))
    scope: Mapped[str] = mapped_column(String(128), default="default")
    cursor: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SyncError(Base):
    __tablename__ = "sync_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    sync_run_id: Mapped[str | None] = mapped_column(ForeignKey("sync_runs.id", ondelete="CASCADE"), index=True)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(64))
    error_type: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("ix_sync_jobs_claim", "status", "run_after", "priority"),
        Index("ix_sync_jobs_school_domain", "school_id", "domain", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    school_id: Mapped[str] = mapped_column(ForeignKey("schools.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(64))
    scope: Mapped[dict] = mapped_column(JSONB, default=dict)
    dedup_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
