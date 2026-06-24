import csv

import pytest

from agency_lead_pipeline.models import AgencyRecord, CSV_COLUMNS
from agency_lead_pipeline.storage import read_records, write_records_atomic


def test_atomic_csv_round_trip(tmp_path):
    path = tmp_path / "nested" / "leads.csv"
    write_records_atomic(path, [AgencyRecord(agency="A")])
    assert read_records(path)[0].agency == "A"
    assert path.read_text(encoding="utf-8").splitlines()[0].split(",") == CSV_COLUMNS
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_csv_formula_injection_is_protected_for_every_exported_field(tmp_path, prefix):
    path = tmp_path / "leads.csv"
    value = f"{prefix}dangerous"
    record = AgencyRecord(
        agency=value,
        website=value,
        domain=value,
        country=value,
        email=value,
        email_source_page=value,
        source_url=value,
        clutch_profile=value,
        notes=value,
    )

    write_records_atomic(path, [record])

    with path.open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    for column in set(CSV_COLUMNS) - {"Status"}:
        assert row[column] == f"'{value}"


def test_csv_protection_is_not_decoded_or_reapplied(tmp_path):
    first_path = tmp_path / "first.csv"
    second_path = tmp_path / "second.csv"
    write_records_atomic(first_path, [AgencyRecord(agency="=formula")])

    loaded = read_records(first_path)
    assert loaded[0].agency == "'=formula"
    write_records_atomic(second_path, loaded)

    with second_path.open("r", encoding="utf-8", newline="") as handle:
        assert next(csv.DictReader(handle))["Agency"] == "'=formula"


def test_legitimate_apostrophe_prefixed_value_is_unchanged(tmp_path):
    path = tmp_path / "leads.csv"
    write_records_atomic(path, [AgencyRecord(agency="'+44 20 1234 5678")])
    assert read_records(path)[0].agency == "'+44 20 1234 5678"
