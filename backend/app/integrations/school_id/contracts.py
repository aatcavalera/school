from dataclasses import dataclass


@dataclass(frozen=True)
class DataContract:
    name: str
    endpoint: str
    fields: frozenset[str]
    required_fields: frozenset[str]
    requires_school_year: bool = False


# Explicit allowlists prevent accidental persistence of credentials, device
# tokens, login IPs, coordinates, or other fields exposed by the upstream UI.
CONTRACTS: dict[str, DataContract] = {
    "students": DataContract(
        name="students",
        endpoint="/administration/students/data",
        fields=frozenset(
            {
                "uuid", "nis", "nisn", "name", "dob", "gender",
                "gender_description", "status", "status_description", "class",
                "created_at", "updated_at",
            }
        ),
        required_fields=frozenset({"uuid", "name"}),
        requires_school_year=True,
    ),
    "teachers": DataContract(
        name="teachers",
        endpoint="/ajax/get/teachers",
        fields=frozenset(
            {
                "uuid", "nuptk", "name", "dob", "gender", "active",
                "homeroom_class_id", "class", "created_at", "updated_at",
            }
        ),
        required_fields=frozenset({"uuid", "name"}),
    ),
    "parents": DataContract(
        name="parents",
        endpoint="/ajax/get/parents",
        fields=frozenset({"uuid", "name", "dob", "gender", "class", "students", "created_at", "updated_at"}),
        required_fields=frozenset({"uuid", "name"}),
    ),
    "classes": DataContract(
        name="classes",
        endpoint="/administration/classes/data",
        fields=frozenset(
            {
                "uuid", "name", "level", "is_active", "homeroom_teacher_id",
                "homeroom_teacher", "students_count", "schedules_count",
                "created_at", "updated_at",
            }
        ),
        required_fields=frozenset({"uuid", "name"}),
    ),
    "subjects": DataContract(
        name="subjects",
        endpoint="/ajax/get/subjects",
        fields=frozenset({"uuid", "name", "icon", "created_at", "updated_at"}),
        required_fields=frozenset({"uuid", "name"}),
    ),
    "student_permits": DataContract(
        name="student_permits",
        endpoint="/ajax/get/izins",
        fields=frozenset(
            {"uuid", "date", "student", "class", "type", "description", "status", "created_at", "updated_at"}
        ),
        required_fields=frozenset({"uuid"}),
    ),
    "teacher_permits": DataContract(
        name="teacher_permits",
        endpoint="/ajax/get/guru_izins",
        fields=frozenset(
            {"uuid", "date", "teacher", "type", "description", "status", "created_at", "updated_at"}
        ),
        required_fields=frozenset({"uuid"}),
    ),
    "class_attendances": DataContract(
        name="class_attendances",
        endpoint="/school/class-attendances/index-datatable",
        fields=frozenset(
            {
                "uuid", "date", "class", "subject", "present_count",
                "absent_count", "created_at", "updated_at",
                # Belum pernah teramati di data nyata (kedua sekolah belum pakai fitur ini),
                # nama field ditambahkan mendahului supaya kalau nanti sekolah mulai isi
                "teacher", "teacher_uuid", "teacher_name", "session", "session_number",
                "start_time", "end_time", "class_uuid", "subject_uuid",
            }
        ),
        required_fields=frozenset(),
    ),
    "student_attendance_summary": DataContract(
        name="student_attendance_summary",
        endpoint="/school/attendance/re-student-attendance-group-per-class",
        fields=frozenset(
            {
                "uuid", "class_name", "class_is_active", "students_count",
                "total_absent", "total_clock_in", "total_clock_in_pending",
                "total_clock_out", "total_clock_out_pending", "total_leave_days",
                "total_present", "total_sick_days",
            }
        ),
        required_fields=frozenset({"uuid", "class_name"}),
        requires_school_year=True,
    ),
}


SENSITIVE_FIELDS = frozenset(
    {
        "password", "remember_token", "fcm_token", "email_verify_token",
        "last_login_ip", "latitude", "longitude", "phone", "phone_raw",
        "phone_index", "user_phone", "whatsapp_number", "address",
        "address_raw", "address_index", "email", "email_raw", "email_index",
    }
)


def sanitize_row(contract: DataContract, row: dict) -> dict:
    """Return only explicitly approved top-level fields from an upstream row."""
    return {key: row[key] for key in contract.fields if key in row}


def inspect_schema(contract: DataContract, row: dict) -> tuple[set[str], set[str]]:
    actual = set(row)
    return actual - contract.fields, contract.required_fields - actual
