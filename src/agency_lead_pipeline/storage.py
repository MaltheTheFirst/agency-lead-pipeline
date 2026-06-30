from __future__ import annotations

import csv
import os
import tempfile
import time
from pathlib import Path

from .models import AgencyRecord, CSV_COLUMNS


FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
REPLACE_RETRIES = 10
REPLACE_RETRY_DELAY_SECONDS = 0.5


def read_archived_domains(directory: Path) -> set[str]:
    """Read only domain identifiers from historical CSVs, regardless of schema."""
    from .http_utils import registrable_domain

    domains: set[str] = set()
    if not directory.is_dir():
        return domains
    for path in sorted(directory.glob("*.csv")):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = {name.strip().lower(): name for name in (reader.fieldnames or []) if name}
            domain_field = headers.get("domain")
            website_field = headers.get("website")
            if not domain_field and not website_field:
                continue
            for row in reader:
                value = (row.get(domain_field or "", "") or row.get(website_field or "", "")).strip()
                domain = registrable_domain(value[1:] if value.startswith("'") else value)
                if domain:
                    domains.add(domain)
    return domains


def protect_csv_field(value: str) -> str:
    """Prevent spreadsheet applications from interpreting exported data as formulas."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def read_records(path: Path) -> list[AgencyRecord]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError(f"Unexpected CSV columns: {reader.fieldnames}; expected {CSV_COLUMNS}")
        return [AgencyRecord.from_csv_row(row, index) for index, row in enumerate(reader)]


def write_records_atomic(path: Path, records: list[AgencyRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(
                {column: protect_csv_field(value) for column, value in record.to_csv_row().items()}
                for record in records
            )
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(REPLACE_RETRIES):
            try:
                os.replace(temp_name, path)
                break
            except PermissionError:
                if attempt == REPLACE_RETRIES - 1:
                    raise PermissionError(
                        f"Could not replace {path}. Close the CSV in Excel, preview panes, "
                        "or other programs that may be locking it, then rerun."
                    )
                time.sleep(REPLACE_RETRY_DELAY_SECONDS)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def validate_csv(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        records = read_records(path)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    from .email_utils import is_valid_email
    from .http_utils import normalize_url, registrable_domain

    for row_number, record in enumerate(records, start=2):
        if not record.agency:
            errors.append(f"row {row_number}: Agency is empty")
        if record.website and not normalize_url(record.website):
            errors.append(f"row {row_number}: malformed Website")
        if record.domain and record.domain != registrable_domain(record.domain):
            errors.append(f"row {row_number}: invalid or non-registrable Domain")
        if record.email and not is_valid_email(record.email):
            errors.append(f"row {row_number}: malformed or filtered Email")
    return errors
