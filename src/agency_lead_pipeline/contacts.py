from __future__ import annotations

import asyncio
import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Browser, TimeoutError as PlaywrightTimeoutError

from .config import Settings
from .email_utils import best_candidate, candidates_from_text
from .http_utils import is_same_domain, normalize_url, registrable_domain
from .models import AgencyRecord, EmailCandidate, ExtractionResult, Status


COMMON_PATHS = ("/contact", "/contact-us", "/about", "/about-us", "/impressum", "/legal", "/privacy", "/privacy-policy", "/team")
CONTACT_TERMS = ("contact", "about", "impressum", "legal", "privacy", "team")


def parse_contact_html(
    html: str,
    page_url: str,
    agency_domain: str,
    allow_personal_emails: bool = False,
) -> tuple[list[EmailCandidate], list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[EmailCandidate] = []
    for anchor in soup.select('a[href^="mailto:"]'):
        value = anchor.get("href", "").split(":", 1)[-1].split("?", 1)[0]
        candidates.extend(candidates_from_text(
            value, page_url, "mailto", agency_domain, allow_personal_emails
        ))
    candidates.extend(candidates_from_text(
        soup.get_text(" ", strip=True), page_url, "visible_text", agency_domain,
        allow_personal_emails,
    ))
    for node in soup.select('script[type="application/ld+json"]'):
        candidates.extend(candidates_from_text(
            node.get_text(" "), page_url, "json_ld", agency_domain,
            allow_personal_emails,
        ))
    links: list[str] = []
    for anchor in soup.select("a[href]"):
        href = normalize_url(str(anchor.get("href", "")), page_url)
        label = (anchor.get_text(" ", strip=True) + " " + str(anchor.get("href", ""))).lower()
        if href and any(term in label for term in CONTACT_TERMS) and is_same_domain(href, page_url):
            links.append(href)
    return candidates, list(dict.fromkeys(links))


async def _browser_html(browser: Browser, url: str, root: str, settings: Settings) -> str:
    page = await browser.new_page(user_agent=settings.user_agent)
    try:
        async def restrict_navigation(route):
            request = route.request
            if request.resource_type == "document" and not is_same_domain(request.url, root):
                await route.abort()
            else:
                await route.continue_()
        await page.route("**/*", restrict_navigation)
        await page.goto(url, wait_until="domcontentloaded", timeout=settings.timeout_seconds * 1000)
        return await page.content()
    finally:
        await page.close()


async def extract_record(record: AgencyRecord, client: httpx.AsyncClient, browser: Browser, settings: Settings) -> ExtractionResult:
    root = normalize_url(record.website)
    if not root:
        return ExtractionResult(record=record.model_copy(update={"status": Status.SKIPPED, "notes": "Missing or invalid website"}))
    domain = registrable_domain(root)
    queue = [root, *[normalize_url(path, root) for path in COMMON_PATHS]]
    visited: set[str] = set()
    all_candidates: list[EmailCandidate] = []
    saw_response = False
    timeout_count = unreachable_count = 0

    while queue and len(visited) < settings.max_pages_per_website:
        url = queue.pop(0)
        if not url or url in visited or not is_same_domain(url, root):
            continue
        visited.add(url)
        html = ""
        try:
            response = await client.get(url, follow_redirects=False)
            redirects = 0
            while response.is_redirect and redirects < 5:
                target = normalize_url(response.headers.get("location", ""), str(response.url))
                if not target or not is_same_domain(target, root):
                    raise httpx.HTTPError("Off-domain redirect refused")
                response = await client.get(target, follow_redirects=False)
                redirects += 1
            response.raise_for_status()
            html, saw_response = response.text, True
        except httpx.TimeoutException:
            timeout_count += 1
        except httpx.HTTPError:
            unreachable_count += 1
        if not html or ("@" not in html and "contact" not in html.lower()):
            try:
                rendered = await _browser_html(browser, url, root, settings)
                if rendered:
                    html, saw_response = rendered, True
            except PlaywrightTimeoutError:
                timeout_count += 1
            except Exception:
                unreachable_count += 1
        if html:
            found, links = parse_contact_html(
                html, url, domain, settings.allow_personal_emails
            )
            all_candidates.extend(found)
            queue.extend(link for link in links if link not in visited)
        if settings.delay_seconds:
            await asyncio.sleep(settings.delay_seconds)

    unique = {candidate.email: candidate for candidate in sorted(all_candidates, key=lambda item: item.score)}
    best = best_candidate(list(unique.values()))
    if best:
        return ExtractionResult(
            record=record.model_copy(update={
                "website": root, "domain": domain, "email": best.email,
                "email_source_page": best.source_page, "status": Status.EMAIL_FOUND,
                "notes": f"Found {len(unique)} valid email candidate(s)",
            }),
            candidates=list(unique.values()),
        )
    if saw_response:
        status, note = Status.NO_EMAIL, f"No valid email found across {len(visited)} page(s)"
    elif timeout_count and not unreachable_count:
        status, note = Status.TIMEOUT, "All website requests timed out"
    else:
        status, note = Status.WEBSITE_UNREACHABLE, "Website could not be reached"
    return ExtractionResult(
        record=record.model_copy(update={"website": root, "domain": domain, "status": status, "notes": note}),
        candidates=list(unique.values()),
    )
