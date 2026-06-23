from agency_lead_pipeline.models import AgencyRecord, CSV_COLUMNS
from agency_lead_pipeline.storage import read_records, write_records_atomic


def test_atomic_csv_round_trip(tmp_path):
    path = tmp_path / "nested" / "leads.csv"
    write_records_atomic(path, [AgencyRecord(agency="A")])
    assert read_records(path)[0].agency == "A"
    assert path.read_text(encoding="utf-8").splitlines()[0].split(",") == CSV_COLUMNS
    assert not list(path.parent.glob("*.tmp"))

