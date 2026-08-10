import unittest
import datetime as dt

from app.sync_service import fingerprint, normalize
from app.routers.dashboard_synced import normalize_status


class SyncNormalizationTests(unittest.TestCase):
    def test_fingerprint_is_stable_across_key_order(self):
        self.assertEqual(fingerprint({"a": 1, "b": 2}), fingerprint({"b": 2, "a": 1}))

    def test_student_normalization_keeps_tenant_and_relationship(self):
        row = {
            "uuid": "student-1", "name": "Siswa Contoh", "nis": "001",
            "class": {"uuid": "class-1", "name": "VII-A"}, "updated_at": "2026-08-01T01:00:00Z",
        }
        result = normalize("students", row, "school-1", "year-1")
        self.assertEqual(result["school_id"], "school-1")
        self.assertEqual(result["class_source_uuid"], "class-1")
        self.assertEqual(result["school_year_uuid"], "year-1")
        self.assertNotIn("class", result)

    def test_upstream_absen_maps_to_alpha(self):
        self.assertEqual(normalize_status("Absen"), "Alpha")

    def test_pending_clock_in_is_not_alpha(self):
        self.assertEqual(normalize_status("Belum Clock In"), "Belum Absen Masuk")
        before_cutoff = dt.datetime(2026, 8, 10, 6, 0, tzinfo=dt.timezone.utc)
        after_cutoff = dt.datetime(2026, 8, 10, 10, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(normalize_status("Belum Clock In", dt.date(2026, 8, 10), "Asia/Makassar", before_cutoff), "Belum Absen Masuk")
        self.assertEqual(normalize_status("Belum Clock In", dt.date(2026, 8, 10), "Asia/Makassar", after_cutoff), "Alpha")
        self.assertEqual(normalize_status("Belum Clock In", dt.date(2026, 8, 9), "Asia/Makassar", before_cutoff), "Alpha")
        self.assertEqual(normalize_status("Hadir"), "Hadir")
