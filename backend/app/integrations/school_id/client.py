import html
import json
import re
import time
import threading
from html.parser import HTMLParser
from dataclasses import dataclass
from urllib.parse import urlsplit
import httpx

from app.integrations.school_id.contracts import CONTRACTS, inspect_schema, sanitize_row


class SchoolIdError(RuntimeError):
    pass


@dataclass(frozen=True)
class PageResult:
    rows: list[dict]
    total: int
    filtered: int
    unexpected_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]


class SchoolIdClient:
    """Minimal read-only client for the web endpoints used by School ID's UI."""

    # The portal rejects non-browser clients at its edge. Keep this stable and
    # identify the integration through its controlled request rate and logs.
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        timeout: float = 20.0,
        verify_tls: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        parsed_url = urlsplit(base_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise SchoolIdError("URL School ID tidak valid")
        # Environment values may point directly at /school/login. API paths are
        # rooted at the portal origin, so discard any configured path/query.
        self.base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        self._username = username
        self._password = password
        self._logged_in = False
        self._last_request_at = 0.0
        self._request_lock = threading.Lock()
        self._client = httpx.Client(
            base_url=self.base_url,
            follow_redirects=True,
            timeout=timeout,
            verify=verify_tls,
            transport=transport,
            headers={"User-Agent": self.USER_AGENT},
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self) -> None:
        self._client.close()

    def login(self) -> None:
        response = None
        for attempt in range(3):
            login_page = self._request("GET", "/", authenticate=False)
            login_page.raise_for_status()
            token_match = re.search(r'name="_token"\s+value="([^"]+)"', login_page.text)
            if not token_match:
                raise SchoolIdError("CSRF token tidak ditemukan pada halaman login")
            response = self._request(
                "POST",
                "/school/login",
                data={
                    "_token": token_match.group(1),
                    "username": self._username,
                    "password": self._password,
                },
                headers={"Referer": str(login_page.url)},
            )
            if response.status_code != 419:
                break
            time.sleep(1.0 * (2**attempt))
        assert response is not None
        response.raise_for_status()
        if "name=\"password\"" in response.text or "403 Forbidden" in response.text:
            raise SchoolIdError("Login School ID gagal")
        self._logged_in = True

    def _request(self, method: str, path: str, *, authenticate: bool = True, **kwargs) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(6):
            try:
                with self._request_lock:
                    elapsed = time.monotonic() - self._last_request_at
                    if elapsed < 0.35:
                        time.sleep(0.35 - elapsed)
                    response = self._client.request(method, path, **kwargs)
                    self._last_request_at = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 5:
                        retry_after = response.headers.get("retry-after")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else min(15.0, 1.0 * (2**attempt))
                        time.sleep(delay)
                        continue
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < 5:
                    time.sleep(min(15.0, 1.0 * (2**attempt)))
        raise SchoolIdError("School ID tidak dapat dihubungi setelah retry") from last_error

    def school_years(self) -> list[dict]:
        response = self._request("GET", "/presensis")
        response.raise_for_status()
        match = re.search(r'data-tajaran="([^"]+)"', response.text)
        if not match:
            raise SchoolIdError("Daftar tahun ajaran tidak ditemukan")
        try:
            source = json.loads(html.unescape(match.group(1)))
        except (TypeError, json.JSONDecodeError) as exc:
            raise SchoolIdError("Format tahun ajaran School ID berubah") from exc

        allowed = {
            "id", "uuid", "name", "is_active", "odd_semester_start_date",
            "odd_semester_end_date", "even_semester_start_date",
            "even_semester_end_date", "created_at", "updated_at",
        }
        return [{key: item[key] for key in allowed if key in item} for item in source]

    def school_name(self) -> str:
        response = self._request("GET", "/profile")
        response.raise_for_status()

        class TextCollector(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.skip = 0
                self.items: list[str] = []

            def handle_starttag(self, tag, _attrs):
                if tag in {"script", "style"}:
                    self.skip += 1

            def handle_endtag(self, tag):
                if tag in {"script", "style"} and self.skip:
                    self.skip -= 1

            def handle_data(self, data):
                value = " ".join(html.unescape(data).split())
                if value and not self.skip:
                    self.items.append(value)

        parser = TextCollector()
        parser.feed(response.text)
        for value in parser.items:
            match = re.fullmatch(r"\d{8}\s*-\s*(.+)", value)
            if match:
                return match.group(1).strip()
        raise SchoolIdError("Nama sekolah tidak ditemukan pada profil School ID")

    def fetch_page(
        self,
        contract_name: str,
        *,
        start: int = 0,
        length: int = 100,
        school_year_uuid: str | None = None,
        extra_params: dict[str, str] | None = None,
    ) -> PageResult:
        if contract_name not in CONTRACTS:
            raise SchoolIdError(f"Kontrak tidak dikenal: {contract_name}")
        contract = CONTRACTS[contract_name]
        if contract.requires_school_year and not school_year_uuid:
            raise SchoolIdError(f"{contract_name} membutuhkan school_year_uuid")

        params: dict[str, str | int] = {"draw": 1, "start": start, "length": min(length, 500)}
        if school_year_uuid:
            params["school_year_uuid"] = school_year_uuid
        if extra_params:
            params.update(extra_params)

        response = self._request(
            "GET",
            contract.endpoint,
            params=params,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise SchoolIdError(f"{contract_name} tidak mengembalikan JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SchoolIdError(f"Envelope response {contract_name} berubah")

        unexpected: set[str] = set()
        missing: set[str] = set()
        rows = []
        for raw_row in payload["data"]:
            if not isinstance(raw_row, dict):
                raise SchoolIdError(f"Row {contract_name} bukan object")
            row_unexpected, row_missing = inspect_schema(contract, raw_row)
            unexpected.update(row_unexpected)
            missing.update(row_missing)
            rows.append(sanitize_row(contract, raw_row))

        return PageResult(
            rows=rows,
            total=int(payload.get("recordsTotal") or len(rows)),
            filtered=int(payload.get("recordsFiltered") or len(rows)),
            unexpected_fields=tuple(sorted(unexpected)),
            missing_required_fields=tuple(sorted(missing)),
        )

    def iter_pages(
        self,
        contract_name: str,
        *,
        page_size: int = 100,
        school_year_uuid: str | None = None,
        extra_params: dict[str, str] | None = None,
    ):
        start = 0
        while True:
            page = self.fetch_page(
                contract_name,
                start=start,
                length=page_size,
                school_year_uuid=school_year_uuid,
                extra_params=extra_params,
            )
            yield page
            start += len(page.rows)
            if not page.rows or start >= page.filtered:
                break

    def fetch_attendance_summary_page(
        self, *, start_date: str, end_date: str, school_year_uuid: str, page: int = 1, per_page: int = 100
    ) -> PageResult:
        contract = CONTRACTS["student_attendance_summary"]
        response = self._request(
            "GET", contract.endpoint,
            params={
                "start_date": start_date, "end_date": end_date, "tahun_ajaran": school_year_uuid,
                "page": page, "per_page": min(per_page, 500),
            },
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise SchoolIdError("Envelope ringkasan presensi berubah")
        unexpected, missing, rows = set(), set(), []
        for raw_row in payload["data"]:
            row_unexpected, row_missing = inspect_schema(contract, raw_row)
            unexpected.update(row_unexpected)
            missing.update(row_missing)
            rows.append(sanitize_row(contract, raw_row))
        return PageResult(
            rows=rows, total=int(payload.get("total") or len(rows)), filtered=int(payload.get("total") or len(rows)),
            unexpected_fields=tuple(sorted(unexpected)), missing_required_fields=tuple(sorted(missing)),
        )

    def fetch_daily_attendance(self, *, attendance_date: str, class_uuid: str, school_year_id: str) -> list[dict]:
        response = self._request(
            "GET", "/school/attendance/re-student-attendance-per-student-and-per-class",
            params={
                "start_date": attendance_date, "end_date": attendance_date,
                "class_uuid": class_uuid, "tahun_ajaran": school_year_id,
            },
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise SchoolIdError("Envelope presensi harian berubah")
        allowed = {
            "id", "user_id", "user_name", "class_student_id", "date", "status",
            "clock_in_time", "clock_out_time", "clock_in_status", "clock_out_status",
            "clock_in_reason", "clock_out_reason", "created_at", "updated_at",
        }
        return [{key: row[key] for key in allowed if key in row} for row in payload if isinstance(row, dict)]
