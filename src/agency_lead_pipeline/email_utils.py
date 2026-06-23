from __future__ import annotations

import html
import re

from .models import EmailCandidate


EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63})(?![\w.-])", re.I)
PREFERRED = {"hello": 100, "info": 90, "contact": 80, "sales": 70, "team": 60, "business": 50}
PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net", "test.com", "domain.com", "email.com"}
ASSET_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico")


def deobfuscate(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r"(?:\s*\[\s*at\s*\]\s*|\s*\(\s*at\s*\)\s*|\s+at\s+)", "@", text, flags=re.I)
    text = re.sub(r"(?:\s*\[\s*dot\s*\]\s*|\s*\(\s*dot\s*\)\s*|\s+dot\s+)", ".", text, flags=re.I)
    return text


def is_valid_email(email: str) -> bool:
    email = email.strip().lower().strip(".,;:()[]<>'\"")
    if not EMAIL_RE.fullmatch(email) or len(email) > 254:
        return False
    local, domain = email.rsplit("@", 1)
    if local in {"noreply", "no-reply", "do-not-reply"} or local.startswith(("noreply+", "no-reply+")):
        return False
    if domain in PLACEHOLDER_DOMAINS or any(email.endswith(suffix) for suffix in ASSET_SUFFIXES):
        return False
    return ".." not in email and not domain.startswith(".")


def score_email(email: str, agency_domain: str = "") -> int:
    local, domain = email.lower().rsplit("@", 1)
    return PREFERRED.get(local, 10) + (25 if agency_domain and domain == agency_domain else 0)


def candidates_from_text(text: str, source_page: str, method: str, agency_domain: str = "") -> list[EmailCandidate]:
    found: dict[str, EmailCandidate] = {}
    for match in EMAIL_RE.findall(deobfuscate(text)):
        email = match.lower().strip(".,;:()[]<>'\"")
        if is_valid_email(email):
            found[email] = EmailCandidate(
                email=email, source_page=source_page, method=method,
                score=score_email(email, agency_domain),
            )
    return list(found.values())


def best_candidate(candidates: list[EmailCandidate]) -> EmailCandidate | None:
    valid = [candidate for candidate in candidates if candidate.valid]
    return sorted(valid, key=lambda item: (-item.score, item.email))[0] if valid else None
