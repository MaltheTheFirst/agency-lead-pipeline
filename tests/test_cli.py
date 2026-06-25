import pytest
from typer.testing import CliRunner

from agency_lead_pipeline.cli import _print_directory_error, app
from agency_lead_pipeline.clutch import DirectoryAccessError
from agency_lead_pipeline.logging_utils import console


@pytest.mark.parametrize("command", ["discover", "extract", "run", "dedupe", "validate"])
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
