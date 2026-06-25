from __future__ import annotations

import asyncio
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag
from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright

from .config import Settings
from .dedupe import mark_discovery_duplicates
from .geography import is_european_location
from .http_utils import normalize_url, registrable_domain
from .models import AgencyRecord, Status
from .storage import read_archived_domains, read_records, write_records_atomic


LISTING_SELECTORS = ("[data-clutch-pid]", ".provider-list-item", ".provider-row", ".directory-listing", ".profile-card")
LISTING_SELECTOR = ", ".join(LISTING_SELECTORS)
CHALLENGE_MARKERS = ("__cf_chl_", "challenge-platform", "enable javascript and cookies to continue")


class DirectoryAccessError(RuntimeError):
    """Raised when a directory serves an access challenge instead of listings."""


async def load_directory_html(page, url: str, timeout_seconds: float) -> str:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
    try:
        await page.wait_for_selector(LISTING_SELECTOR, timeout=timeout_seconds * 1000)
    except PlaywrightTimeoutError as exc:
        html = await page.content()
        challenged = any(marker in html.lower() for marker in CHALLENGE_MARKERS)
        if challenged:
            raise DirectoryAccessError(
                f"Directory access challenge detected at {url}. Retry with headless: false "
                "and complete any interactive browser check; the pipeline does not bypass "
                "access controls."
            ) from exc
        raise DirectoryAccessError(f"No directory listings appeared at {url}") from exc
    return await page.content()


def directory_page_url(initial_url: str, page_index: int) -> str:
    """Build a numbered fallback page URL while preserving other filters."""
    parts = urlsplit(initial_url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key.lower() != "page"]
    query.append(("page", str(page_index)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def parse_clutch_html(html: str, source_url: str, start_order: int = 0) -> tuple[list[AgencyRecord], str]:
    soup = BeautifulSoup(html, "html.parser")
    listings: list[Tag] = []
    for selector in LISTING_SELECTORS:
        listings = list(soup.select(selector))
        if listings:
            break
    records: list[AgencyRecord] = []
    for order, listing in enumerate(listings, start=start_order):
        name_node = listing.select_one("h2, h3, .company_info a, .provider__title, [class*='company-name']")
        agency = name_node.get_text(" ", strip=True) if name_node else ""
        location_node = listing.select_one(".locality, .location, [class*='location'], [class*='country']")
        country = location_node.get_text(" ", strip=True) if location_node else ""
        profile = ""
        website = ""
        for anchor in listing.select("a[href], a[data-link]"):
            raw = str(anchor.get("data-link") or anchor.get("href") or "").strip()
            absolute = urljoin(source_url, raw)
            host = (urlsplit(absolute).hostname or "").lower()
            if "/profile/" in absolute or (host.endswith("clutch.co") and "profile" in absolute):
                profile = profile or absolute
            if raw.startswith("http") and not host.endswith("clutch.co"):
                website = website or absolute
            elif any(token in raw.lower() for token in ("redirect", "visit-website", "data-link")):
                website = website or absolute
        if agency or website or profile:
            records.append(AgencyRecord(
                agency=agency, website=website, country=country, source_url=source_url,
                clutch_profile=profile, status=Status.NEW, source_order=order,
            ))
    next_node = soup.select_one('a[rel="next"], a[aria-label*="Next" i], .pagination a.next')
    next_url = urljoin(source_url, str(next_node.get("href"))) if next_node and next_node.get("href") else ""
    return records, next_url


async def resolve_outbound(url: str, client: httpx.AsyncClient) -> str:
    if not url:
        return ""
    try:
        response = await client.get(url)
        return normalize_url(str(response.url))
    except httpx.HTTPError:
        return normalize_url(url) if not (urlsplit(url).hostname or "").endswith("clutch.co") else ""


async def discover_agencies(urls: list[str], settings: Settings, output_path) -> list[AgencyRecord]:
    archived_domains = read_archived_domains(settings.archive_directory)
    records = read_records(output_path)
    records = [record for record in records if record.domain not in archived_domains]
    if settings.europe_only:
        records = [record for record in records if is_european_location(record.country)]
    for index, record in enumerate(records):
        record.source_order = index
    domains_present_before_run = {record.domain for record in records if record.domain}
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(settings.timeout_seconds)
    new_records_count = 0
    async with async_playwright() as playwright, httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        browser = await playwright.chromium.launch(headless=settings.headless)
        page = await browser.new_page(user_agent=settings.user_agent)
        try:
            for initial_url in urls:
                current = normalize_url(initial_url)
                page_count = 0
                seen_page_signatures: set[tuple[tuple[str, str, str], ...]] = set()
                while current and page_count < settings.max_directory_pages and new_records_count < settings.max_agencies:
                    html = await load_directory_html(page, current, settings.timeout_seconds)
                    found, next_url = parse_clutch_html(html, current, len(records))
                    signature = tuple((record.agency, record.clutch_profile, record.website) for record in found)
                    if not signature or signature in seen_page_signatures:
                        break
                    seen_page_signatures.add(signature)
                    if settings.europe_only:
                        found = [record for record in found if is_european_location(record.country)]
                    for record in found[: settings.max_agencies - new_records_count]:
                        record.website = await resolve_outbound(record.website, client)
                        record.domain = registrable_domain(record.website)
                        if record.domain and record.domain in archived_domains:
                            continue
                        if record.domain and record.domain in domains_present_before_run:
                            continue
                        record.source_order = len(records)
                        records.append(record)
                        new_records_count += 1
                    mark_discovery_duplicates(records)
                    write_records_atomic(output_path, records)
                    page_count += 1
                    current = next_url or (
                        # Clutch's visible directory numbering is one-based:
                        # the unnumbered URL is page 1, so the first fallback is page=2.
                        directory_page_url(initial_url, page_count + 1)
                        if page_count < settings.max_directory_pages else ""
                    )
                    if current and settings.delay_seconds:
                        await asyncio.sleep(settings.delay_seconds)
        finally:
            await browser.close()
    return records
