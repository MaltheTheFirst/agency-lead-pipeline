from __future__ import annotations

import asyncio
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag
from playwright.async_api import async_playwright

from .config import Settings
from .dedupe import mark_discovery_duplicates
from .http_utils import normalize_url, registrable_domain
from .models import AgencyRecord, Status
from .storage import read_records, write_records_atomic


LISTING_SELECTORS = ("[data-clutch-pid]", ".provider-list-item", ".provider-row", ".directory-listing", ".profile-card")


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
    records = read_records(output_path)
    for index, record in enumerate(records):
        record.source_order = index
    domains_present_before_run = {record.domain for record in records if record.domain}
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(settings.timeout_seconds)
    async with async_playwright() as playwright, httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        browser = await playwright.chromium.launch(headless=settings.headless)
        page = await browser.new_page(user_agent=settings.user_agent)
        try:
            for initial_url in urls:
                current = normalize_url(initial_url)
                page_count = 0
                while current and page_count < settings.max_directory_pages and len(records) < settings.max_agencies:
                    await page.goto(current, wait_until="domcontentloaded", timeout=settings.timeout_seconds * 1000)
                    found, next_url = parse_clutch_html(await page.content(), current, len(records))
                    for record in found[: settings.max_agencies - len(records)]:
                        record.website = await resolve_outbound(record.website, client)
                        record.domain = registrable_domain(record.website)
                        if record.domain and record.domain in domains_present_before_run:
                            continue
                        record.source_order = len(records)
                        records.append(record)
                    mark_discovery_duplicates(records)
                    write_records_atomic(output_path, records)
                    current, page_count = next_url, page_count + 1
                    if current and settings.delay_seconds:
                        await asyncio.sleep(settings.delay_seconds)
        finally:
            await browser.close()
    return records
