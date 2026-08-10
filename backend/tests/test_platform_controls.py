import unittest
from datetime import datetime, timezone

from app.cache import TTLCache
from app.login_limiter import LoginRateLimiter
from app.name_gender import AdaptiveGenderClassifier, estimate_gender, operator_samples
from app.job_queue import attendance_window_open
from app.models_multitenant import School


class PlatformControlTests(unittest.TestCase):
    def test_attendance_scheduler_respects_school_local_hours(self):
        school = School(code="test", name="Test", timezone="Asia/Makassar")
        self.assertTrue(attendance_window_open(school, datetime(2026, 8, 10, 0, 0, tzinfo=timezone.utc)))
        self.assertFalse(attendance_window_open(school, datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)))
    def test_login_limiter_blocks_after_threshold(self):
        limiter = LoginRateLimiter(attempts=2, window_seconds=60)
        self.assertTrue(limiter.allowed("client"))
        limiter.fail("client"); limiter.fail("client")
        self.assertFalse(limiter.allowed("client"))
        limiter.success("client")
        self.assertTrue(limiter.allowed("client"))

    def test_ttl_cache_returns_value(self):
        cache = TTLCache(ttl_seconds=10, max_items=2)
        cache.set("school:date", {"ok": True})
        self.assertEqual(cache.get("school:date"), {"ok": True})

    def test_full_name_gender_estimation_is_marked_and_conservative(self):
        self.assertEqual(estimate_gender("Muhammad Fajar Ramadhan").label, "Laki-laki")
        self.assertEqual(estimate_gender("Siti Aisyah Putri").label, "Perempuan")
        self.assertIsNone(estimate_gender("Dwi Cahya").label)
        expected = {
            "Dwi Cahya Pranata": "Laki-laki",
            "Nur Wahyu Ramadhani": "Perempuan",
            "Eka Tri Saputra": "Laki-laki",
            "Dian Cahya Utama": "Perempuan",
            "Rizki Nur Permata": "Perempuan",
            "Tri Agung Lestari": "Perempuan",
            "Nova Dwi Cahyani": "Perempuan",
            "Nurul Fitra Ramadhan": "Perempuan",
        }
        for name, label in expected.items():
            self.assertEqual(estimate_gender(name).label, label)
        verified_operator_labels = {
            "ABD. RAHMAN H. IBRAHIM": "Laki-laki", "ABD. RAHMAN S. ABDULLAH": "Laki-laki",
            "ABD. WAHIT MANTALI": "Laki-laki", "ADAWIYA UI": "Perempuan", "ADELFIN ABAS": "Perempuan",
            "ADELIA OKTAVIANI R. LUITI": "Perempuan", "ADI PRASATYA DUMBI": "Laki-laki",
            "ADI ZULKARNAIN KONIYO": "Laki-laki", "ADITIA WALANGADI": "Laki-laki",
            "AGUSTINA UTI": "Perempuan", "AIDA HABUKE": "Perempuan", "AIRA CAHAYA BINTANG KALUKU": "Perempuan",
        }
        for name, label in verified_operator_labels.items():
            self.assertEqual(estimate_gender(name), type(estimate_gender(name))(label, 1.0))
        classifier = AdaptiveGenderClassifier(operator_samples())
        self.assertEqual(classifier.predict("ADI PRATAMA").label, "Laki-laki")
        self.assertEqual(classifier.predict("ADELIA PUTRI").label, "Perempuan")
