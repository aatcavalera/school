import unittest
import json
from pathlib import Path

from app.integrations.school_id.contracts import CONTRACTS, SENSITIVE_FIELDS, inspect_schema, sanitize_row


class ContractTests(unittest.TestCase):
    def test_sensitive_fields_are_never_approved(self):
        for contract in CONTRACTS.values():
            self.assertFalse(contract.fields & SENSITIVE_FIELDS, contract.name)

    def test_sanitizer_drops_unapproved_personal_and_auth_fields(self):
        source = {
            "uuid": "anonymous-uuid",
            "name": "Siswa Contoh",
            "nis": "0001",
            "password": "must-not-survive",
            "fcm_token": "must-not-survive",
            "phone": "must-not-survive",
            "new_upstream_field": "must-not-survive",
        }
        result = sanitize_row(CONTRACTS["students"], source)
        self.assertEqual(result, {"uuid": "anonymous-uuid", "name": "Siswa Contoh", "nis": "0001"})

    def test_schema_drift_is_reported(self):
        unexpected, missing = inspect_schema(CONTRACTS["students"], {"uuid": "x", "new_field": 1})
        self.assertEqual(unexpected, {"new_field"})
        self.assertEqual(missing, {"name"})

    def test_anonymous_fixture_cannot_leak_sensitive_fields(self):
        fixture = Path(__file__).parent / "fixtures" / "school_id_students_page.json"
        row = json.loads(fixture.read_text())["data"][0]
        result = sanitize_row(CONTRACTS["students"], row)
        self.assertFalse(set(result) & SENSITIVE_FIELDS)
        self.assertEqual(result["uuid"], "00000000-0000-0000-0000-000000000001")


if __name__ == "__main__":
    unittest.main()
