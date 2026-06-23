from agency_lead_pipeline.dedupe import dedupe_records, mark_discovery_duplicates
from agency_lead_pipeline.models import AgencyRecord, Status


def test_canonical_preference_and_duplicate_marking():
    rows = [
        AgencyRecord(agency="First", domain="example.com", source_order=0),
        AgencyRecord(agency="Richer", country="DK", website="https://example.com", domain="example.com", source_order=1),
    ]
    marked = mark_discovery_duplicates(rows)
    assert marked[0].status == Status.DUPLICATE
    assert dedupe_records(marked)[0].agency == "Richer"


def test_earliest_source_wins_tie():
    rows = [
        AgencyRecord(agency="First", website="https://example.com", domain="example.com", source_order=0),
        AgencyRecord(agency="Later", website="https://example.com", domain="example.com", source_order=1),
    ]
    assert dedupe_records(rows)[0].agency == "First"

