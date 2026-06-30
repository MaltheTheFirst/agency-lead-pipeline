import pytest
from typer.testing import CliRunner

from agency_lead_pipeline.cli import _print_directory_error, _write_valid_email_leads, app
from agency_lead_pipeline.clutch import DirectoryAccessError
from agency_lead_pipeline.logging_utils import console
from agency_lead_pipeline.models import AgencyRecord, Status
from agency_lead_pipeline.storage import read_records


@pytest.mark.parametrize("command", ["discover", "discover-websites", "extract", "run", "dedupe", "validate"])
def test_command_help_smoke(command):
    result = CliRunner().invoke(app, [command, "--help"])
    assert result.exit_code == 0, result.output


def test_directory_error_is_rendered_without_traceback():
    with console.capture() as capture:
        _print_directory_error(DirectoryAccessError("challenge at page 2"))
    output = capture.get()
    assert "Discovery stopped" in output
    assert "challenge at page 2" in output
    assert "Traceback" not in output


def test_write_valid_email_leads_filters_and_limits_rows(tmp_path):
    output = tmp_path / "valid.csv"
    written = _write_valid_email_leads(
        output,
        [
            AgencyRecord(agency="A", email="hello@a.com", status=Status.EMAIL_FOUND),
            AgencyRecord(agency="B", status=Status.NO_EMAIL),
            AgencyRecord(agency="C", email="hello@c.com", status=Status.EMAIL_FOUND),
        ],
        limit=1,
    )

    assert written == 1
    rows = read_records(output)
    assert len(rows) == 1
    assert rows[0].agency == "A"


def test_write_valid_email_leads_can_export_homepage_websites(tmp_path):
    output = tmp_path / "valid.csv"
    _write_valid_email_leads(
        output,
        [
            AgencyRecord(
                agency="A",
                website="https://agency.com/services/web?utm_source=test",
                email="hello@agency.com",
                status=Status.EMAIL_FOUND,
            )
        ],
    )

    assert read_records(output)[0].website == "https://agency.com"
