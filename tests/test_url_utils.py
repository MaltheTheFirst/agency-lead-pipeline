from agency_lead_pipeline.http_utils import is_same_domain, normalize_url, registrable_domain


def test_normalize_url_removes_www_tracking_fragment_and_slash():
    assert normalize_url("HTTPS://WWW.Example.COM/path/?utm_source=x&a=1#top") == "https://example.com/path?a=1"


def test_registrable_domain_handles_public_suffix():
    assert registrable_domain("https://www.agency.example.co.uk/contact") == "example.co.uk"


def test_same_domain_allows_subdomains_not_external():
    assert is_same_domain("https://contact.example.com", "https://example.com")
    assert not is_same_domain("https://example.net", "https://example.com")


def test_rejects_unsupported_or_malformed_urls():
    assert normalize_url("mailto:hello@example.com") == ""
    assert normalize_url("") == ""

