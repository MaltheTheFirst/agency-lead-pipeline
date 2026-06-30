from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, Tag

from .config import Settings
from .dedupe import mark_discovery_duplicates
from .geography import is_european_location
from .http_utils import normalize_url, registrable_domain
from .logging_utils import console
from .models import AgencyRecord, Status
from .storage import read_archived_domains, read_records, write_records_atomic


IGNORED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
}

COUNTRY_NAMES = {
    "Argentina", "Armenia", "Australia", "Austria", "Bangladesh", "Belgium",
    "Brazil", "Bulgaria", "Canada", "Chile", "Colombia", "Croatia",
    "Czech Republic", "Czechia", "Denmark", "Egypt", "Estonia", "Finland",
    "France", "Georgia", "Germany", "Greece", "Hungary", "India", "Indonesia",
    "Ireland", "Israel", "Italy", "Kenya", "Latvia", "Lithuania", "Mexico",
    "Moldova", "Netherlands", "Nigeria", "Norway", "Pakistan", "Philippines",
    "Poland", "Portugal", "Romania", "Serbia", "Singapore", "Slovakia",
    "Slovenia", "South Africa", "Spain", "Sri Lanka", "Sweden", "Switzerland",
    "Turkey", "Turkiye", "UAE", "Ukraine", "United Arab Emirates",
    "United Kingdom", "United States", "USA", "Vietnam",
}


def _known_country_from_text(text: str) -> str:
    for country in sorted(COUNTRY_NAMES, key=len, reverse=True):
        if re.search(rf"(?<![A-Za-z]){re.escape(country)}(?![A-Za-z])", text, re.IGNORECASE):
            return country
    return ""


def _location_from_context(anchor: Tag) -> str:
    for parent in anchor.parents:
        if not isinstance(parent, Tag):
            continue
        for node in parent.select('[class*="location" i], [class*="country" i], [class*="address" i], [id*="location" i], [id*="country" i], [id*="address" i]'):
            text = node.get_text(" ", strip=True)
            country = _known_country_from_text(text)
            if country:
                return text if "," in text and len(text) <= 120 else country
        text = parent.get_text(" ", strip=True)
        if len(text) > 2500:
            break
        country = _known_country_from_text(text)
        if country:
            return country
    return ""


def _log_line(path, message: str) -> None:
    if not path:
        return
    from datetime import datetime

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")


def parse_external_website_links(html: str, source_url: str, start_order: int = 0) -> list[AgencyRecord]:
    source_domain = registrable_domain(source_url)
    soup = BeautifulSoup(html, "html.parser")
    records: list[AgencyRecord] = []
    seen_domains: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = normalize_url(str(anchor.get("href", "")), source_url)
        domain = registrable_domain(href)
        if not domain or domain == source_domain or domain in IGNORED_DOMAINS or domain in seen_domains:
            continue
        host = (urlsplit(href).hostname or "").lower()
        if host.startswith(("www.google.", "maps.google.")):
            continue
        agency = anchor.get_text(" ", strip=True) or domain
        seen_domains.add(domain)
        records.append(
            AgencyRecord(
                agency=agency,
                website=href,
                domain=domain,
                country=_location_from_context(anchor),
                source_url=source_url,
                status=Status.NEW,
                source_order=start_order + len(records),
            )
        )
    return records


def generic_next_page_url(html: str, source_url: str, page_index: int) -> str:
    soup = BeautifulSoup(html, "html.parser")
    next_node = soup.select_one(
        'a[rel="next"], a[aria-label*="Next" i], a.next, .pagination a[rel="next"], .pagination a[aria-label*="Next" i]'
    )
    if next_node and next_node.get("href"):
        return normalize_url(str(next_node.get("href")), source_url)

    parts = urlsplit(source_url)
    query_items = parse_qsl(parts.query)
    current_page = next(
        (
            int(value)
            for key, value in query_items
            if key.lower() == "page" and value.isdigit()
        ),
        None,
    )
    next_page = (current_page + 1) if current_page is not None else page_index
    query = [(key, value) for key, value in query_items if key.lower() != "page"]
    query.append(("page", str(next_page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


async def discover_generic_websites(
    urls: list[str],
    settings: Settings,
    output_path,
    max_sites: int | None = None,
    max_pages: int | None = None,
) -> list[AgencyRecord]:
    archived_domains = read_archived_domains(settings.archive_directory)
    records = [record for record in read_records(output_path) if record.domain not in archived_domains]
    domains_present = {record.domain for record in records if record.domain}
    accepted = 0
    limit = max_sites or settings.max_agencies
    page_limit = max_pages or settings.max_directory_pages
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(settings.timeout_seconds)
    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        for url in urls:
            if accepted >= limit:
                break
            current = normalize_url(url)
            page_count = 0
            seen_urls: set[str] = set()
            while current and current not in seen_urls and page_count < page_limit and accepted < limit:
                seen_urls.add(current)
                page_count += 1
                _log_line(settings.log_file, f"DISCOVER_PAGE start page={page_count} url={current}")
                try:
                    response = await client.get(current)
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    console.print(
                        f"[yellow]Skipping {current}: HTTP {exc.response.status_code} from directory page.[/yellow]"
                    )
                    _log_line(settings.log_file, f"DISCOVER_PAGE skip status={exc.response.status_code} url={current}")
                    break
                except httpx.HTTPError as exc:
                    console.print(f"[yellow]Skipping {current}: {exc!r}[/yellow]")
                    _log_line(settings.log_file, f"DISCOVER_PAGE skip error={exc!r} url={current}")
                    break
                found = parse_external_website_links(response.text, str(response.url), len(records))
                accepted_before = accepted
                for record in found:
                    if accepted >= limit:
                        break
                    if settings.europe_only and not is_european_location(record.country):
                        continue
                    if not record.domain or record.domain in archived_domains or record.domain in domains_present:
                        continue
                    record.source_order = len(records)
                    records.append(record)
                    domains_present.add(record.domain)
                    accepted += 1
                mark_discovery_duplicates(records)
                write_records_atomic(output_path, records)
                next_url = generic_next_page_url(response.text, str(response.url), page_count + 1)
                _log_line(
                    settings.log_file,
                    f"DISCOVER_PAGE done found={len(found)} accepted={accepted - accepted_before} total={len(records)} next={next_url or '-'} url={current}",
                )
                current = next_url if next_url and next_url not in seen_urls else ""
                if current and settings.delay_seconds:
                    await asyncio.sleep(settings.delay_seconds)
    return records
