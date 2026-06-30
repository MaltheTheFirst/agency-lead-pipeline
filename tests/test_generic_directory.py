import httpx
import pytest

from agency_lead_pipeline.config import Settings
from agency_lead_pipeline.generic_directory import (
    discover_generic_websites,
    generic_next_page_url,
    parse_external_website_links,
)


def test_parse_external_website_links_keeps_unique_non_directory_domains():
    html = """
    <a href="https://directory.test/profile/acme">Profile</a>
    <article>
      <a href="https://acme.com">Acme Studio</a>
      <span class="location">Ahmedabad, India</span>
    </article>
    <a href="https://www.linkedin.com/company/acme">LinkedIn</a>
    <a href="https://acme.com/contact">Duplicate Acme</a>
    <a href="https://northstar.com">North Star</a>
    """

    records = parse_external_website_links(html, "https://directory.test/web-agencies")

    assert [(record.agency, record.domain) for record in records] == [
        ("Acme Studio", "acme.com"),
        ("North Star", "northstar.com"),
    ]
    assert records[0].country == "Ahmedabad, India"


def test_generic_next_page_url_prefers_next_link():
    html = '<a rel="next" href="/directory/web-development?page=2">Next</a>'

    assert generic_next_page_url(html, "https://example.com/directory/web-development", 2) == (
        "https://example.com/directory/web-development?page=2"
    )


def test_generic_next_page_url_increments_existing_page_parameter():
    assert generic_next_page_url("", "https://example.com/directory/web-development?page=51", 2) == (
        "https://example.com/directory/web-development?page=52"
    )


@pytest.mark.asyncio
async def test_discover_generic_websites_skips_blocked_pages(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            if "blocked" in url:
                return httpx.Response(403, request=httpx.Request("GET", url))
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                text='<a href="https://acme.com">Acme Studio</a>',
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    output = tmp_path / "raw.csv"

    records = await discover_generic_websites(
        ["https://blocked.com", "https://directory.com"],
        Settings(delay_seconds=0),
        output,
        max_sites=10,
    )

    assert [record.domain for record in records] == ["acme.com"]


@pytest.mark.asyncio
async def test_discover_generic_websites_filters_to_europe_when_enabled(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                text="""
                <article><a href="https://acme.com">Acme</a><span class="location">Ahmedabad, India</span></article>
                <article><a href="https://northstar.com">North Star</a><span class="location">Copenhagen, Denmark</span></article>
                """,
            )

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    output = tmp_path / "raw.csv"

    records = await discover_generic_websites(
        ["https://directory.com"],
        Settings(delay_seconds=0, europe_only=True),
        output,
        max_sites=10,
    )

    assert [(record.domain, record.country) for record in records] == [
        ("northstar.com", "Copenhagen, Denmark")
    ]
