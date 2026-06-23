from agency_lead_pipeline.models import FINALIZED_STATUSES, Status


def test_finalized_statuses_are_exact():
    assert FINALIZED_STATUSES == {
        Status.EMAIL_FOUND, Status.NO_EMAIL, Status.WEBSITE_UNREACHABLE,
        Status.TIMEOUT, Status.SKIPPED,
    }

