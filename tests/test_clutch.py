import pytest

from agency_lead_pipeline.clutch import (
    DirectoryAccessError,
    directory_page_url,
    load_directory_html,
    parse_clutch_html,
)


def test_parse_clutch_listing_and_next_page():
    html = """
    <div class="provider-list-item">
      <h3>North Star Studio</h3>
      <span class="location">Copenhagen, Denmark</span>
      <a href="/profile/north-star">Profile</a>
      <a data-link="https://northstar.example/?utm_source=clutch">Visit website</a>
    </div>
    <a rel="next" href="?page=2">Next</a>
    """
    records, next_url = parse_clutch_html(html, "https://clutch.co/web-developers")
    assert records[0].agency == "North Star Studio"
    assert records[0].country == "Copenhagen, Denmark"
    assert records[0].clutch_profile == "https://clutch.co/profile/north-star"
    assert records[0].website.startswith("https://northstar.example")
    assert next_url == "https://clutch.co/web-developers?page=2"


def test_directory_page_fallback_preserves_filters_and_replaces_page():
    assert directory_page_url(
        "https://clutch.co/web-developers?sort_by=0&page=3", 4
    ) == "https://clutch.co/web-developers?sort_by=0&page=4"


class ChallengePage:
    async def goto(self, *args, **kwargs):
        return None

    async def wait_for_selector(self, *args, **kwargs):
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        raise PlaywrightTimeoutError("timed out")

    async def content(self):
        return "<div>Enable JavaScript and cookies to continue</div><script src='challenge-platform'></script>"


@pytest.mark.asyncio
async def test_directory_access_challenge_fails_loudly():
    with pytest.raises(DirectoryAccessError, match="access challenge"):
        await load_directory_html(ChallengePage(), "https://directory.example", 1)


class InteractiveChallengePage:
    def __init__(self):
        self.waits = 0

    async def goto(self, *args, **kwargs):
        return None

    async def wait_for_selector(self, *args, **kwargs):
        self.waits += 1
        if self.waits == 1:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError

            raise PlaywrightTimeoutError("timed out")
        return None

    async def content(self):
        if self.waits == 1:
            return "<div>Enable JavaScript and cookies to continue</div><script src='challenge-platform'></script>"
        return "<div class='provider-list-item'><h3>Cleared Agency</h3></div>"

    async def bring_to_front(self):
        return None


@pytest.mark.asyncio
async def test_interactive_challenge_waits_for_listing_after_manual_check():
    html = await load_directory_html(
        InteractiveChallengePage(),
        "https://directory.example",
        1,
        interactive_challenge=True,
        challenge_wait_seconds=1,
    )

    assert "Cleared Agency" in html
