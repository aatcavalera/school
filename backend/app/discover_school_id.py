"""Print a PII-free School ID contract summary for the configured school."""

import json
import os

from app.integrations.school_id import SchoolIdClient
from app.integrations.school_id.contracts import CONTRACTS


def main() -> None:
    required = ("URL_SCHOOL_ID", "USERNAME_SCHOOL_ID", "PASSWORD_SCHOOL_ID")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"Environment belum lengkap: {', '.join(missing)}")

    summary: dict[str, object] = {}
    with SchoolIdClient(
        os.environ["URL_SCHOOL_ID"],
        os.environ["USERNAME_SCHOOL_ID"],
        os.environ["PASSWORD_SCHOOL_ID"],
    ) as client:
        client.login()
        years = client.school_years()
        active_year = next((year for year in years if year.get("is_active")), years[0] if years else None)
        summary["school_years"] = {"count": len(years), "has_active": active_year is not None}

        for name, contract in CONTRACTS.items():
            try:
                page = client.fetch_page(
                    name,
                    length=2,
                    school_year_uuid=active_year.get("uuid") if contract.requires_school_year and active_year else None,
                )
                summary[name] = {
                    "status": "ok",
                    "total": page.total,
                    "approved_fields_returned": sorted(page.rows[0]) if page.rows else [],
                    "unexpected_field_count": len(page.unexpected_fields),
                    "missing_required_fields": list(page.missing_required_fields),
                }
            except Exception as exc:
                # Never include response bodies or credentials in discovery output.
                summary[name] = {"status": "error", "error_type": type(exc).__name__}

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
