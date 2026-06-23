import pytest
from typer.testing import CliRunner

from agency_lead_pipeline.cli import app


@pytest.mark.parametrize("command", ["discover", "extract", "run", "dedupe", "validate"])
def test_command_help_smoke(command):
    result = CliRunner().invoke(app, [command, "--help"])
    assert result.exit_code == 0, result.output

