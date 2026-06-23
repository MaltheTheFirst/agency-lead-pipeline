from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import re

import tldextract


TRACKING_KEYS = {"gclid", "fbclid", "msclkid", "ref", "source"}
TRACKING_PREFIXES = ("utm_",)
_extract = tldextract.TLDExtract(suffix_list_urls=())


def normalize_url(url: str, base: str | None = None) -> str:
    url = (url or "").strip()
    if base:
        url = urljoin(base, url)
    if not url:
        return ""
    if re.match(r"^(mailto|tel|javascript|data):", url, re.I):
        return ""
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return ""
    host = parts.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        parsed_port = parts.port
    except ValueError:
        return ""
    port = f":{parsed_port}" if parsed_port and not (
        parts.scheme.lower() == "http" and parsed_port == 80
        or parts.scheme.lower() == "https" and parsed_port == 443
    ) else ""
    query = urlencode([
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_KEYS and not k.lower().startswith(TRACKING_PREFIXES)
    ])
    path = parts.path.rstrip("/") or ""
    return urlunsplit((parts.scheme.lower(), host + port, path, query, ""))


def registrable_domain(url_or_host: str) -> str:
    value = normalize_url(url_or_host)
    host = urlsplit(value).hostname if value else url_or_host.split(":")[0].strip().lower()
    if host and host.startswith("www."):
        host = host[4:]
    result = _extract(host or "")
    return result.top_domain_under_public_suffix or ""


def is_same_domain(url: str, root_url: str) -> bool:
    left, right = registrable_domain(url), registrable_domain(root_url)
    return bool(left and right and left == right)
