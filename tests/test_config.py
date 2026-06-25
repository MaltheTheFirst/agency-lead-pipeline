import pytest
from pydantic import ValidationError

from agency_lead_pipeline.config import Settings, load_settings
from agency_lead_pipeline.cli import _settings


def test_default_site_page_limit_and_cli_precedence(tmp_path):
    assert Settings().max_pages_per_website == 5
    assert Settings().europe_only is False
    assert Settings().allow_personal_emails is False
    assert Settings().archive_directory.name == "archive"
    config = tmp_path / "config.yaml"
    config.write_text(
        "concurrency: 1\ntimeout_seconds: 30\nallow_personal_emails: true\n",
        encoding="utf-8",
    )
    settings = load_settings(config, concurrency=3)
    assert settings.concurrency == 3
    assert settings.timeout_seconds == 30
    assert settings.allow_personal_emails is True


def test_cli_settings_automatically_load_local_config(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "europe_only: true\nconcurrency: 1\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    settings = _settings(None, concurrency=3)
    assert settings.europe_only is True
    assert settings.concurrency == 3


def test_unknown_config_keys_are_rejected(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("europe_onyl: true\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_settings(config)
