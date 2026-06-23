from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

from .models import AgencyRecord, CSV_COLUMNS


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
            writer.writerows(record.to_csv_row() for record in records)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
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

