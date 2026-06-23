from agency_lead_pipeline.config import Settings, load_settings


def test_default_site_page_limit_and_cli_precedence(tmp_path):
    assert Settings().max_pages_per_website == 5
    config = tmp_path / "config.yaml"
    config.write_text("concurrency: 1\ntimeout_seconds: 30\n", encoding="utf-8")
    settings = load_settings(config, concurrency=3)
    assert settings.concurrency == 3
    assert settings.timeout_seconds == 30

