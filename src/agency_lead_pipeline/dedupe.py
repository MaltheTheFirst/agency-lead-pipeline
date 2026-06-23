from __future__ import annotations

from .http_utils import normalize_url, registrable_domain
from .models import AgencyRecord, Status


def _canonical_key(record: AgencyRecord) -> tuple[int, int, int]:
    valid_website = bool(normalize_url(record.website) and registrable_domain(record.website))
    richness = sum(bool(value.strip()) for value in (record.agency, record.country))
    return (int(valid_website), richness, -record.source_order)


def mark_discovery_duplicates(records: list[AgencyRecord]) -> list[AgencyRecord]:
    groups: dict[str, list[AgencyRecord]] = {}
    for record in records:
        key = record.domain or registrable_domain(record.website)
        if not key:
            continue
        record.domain = key
        groups.setdefault(key, []).append(record)
    for group in groups.values():
        canonical = max(group, key=_canonical_key)
        for record in group:
            if record is not canonical:
                record.status = Status.DUPLICATE
                record.notes = "Duplicate registrable domain"
            elif record.status == Status.DUPLICATE:
                record.status, record.notes = Status.NEW, ""
    return records


def dedupe_records(records: list[AgencyRecord]) -> list[AgencyRecord]:
    chosen: dict[str, AgencyRecord] = {}
    unkeyed: list[AgencyRecord] = []
    for record in records:
        key = record.domain or registrable_domain(record.website)
        if not key:
            unkeyed.append(record)
            continue
        record.domain = key
        current = chosen.get(key)
        if current is None or _canonical_key(record) > _canonical_key(current):
            chosen[key] = record
    return sorted([*chosen.values(), *unkeyed], key=lambda item: item.source_order)

