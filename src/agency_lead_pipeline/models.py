from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


CSV_COLUMNS = [
    "Agency", "Website", "Domain", "Country", "Email", "Email_Source_Page",
    "Source_URL", "Clutch_Profile", "Status", "Notes",
]


class Status(StrEnum):
    NEW = "New"
    EMAIL_FOUND = "Email_Found"
    NO_EMAIL = "No_Email"
    WEBSITE_UNREACHABLE = "Website_Unreachable"
    TIMEOUT = "Timeout"
    DUPLICATE = "Duplicate"
    SKIPPED = "Skipped"


FINALIZED_STATUSES = {
    Status.EMAIL_FOUND, Status.NO_EMAIL, Status.WEBSITE_UNREACHABLE,
    Status.TIMEOUT, Status.SKIPPED,
}


class AgencyRecord(BaseModel):
    agency: str = ""
    website: str = ""
    domain: str = ""
    country: str = ""
    email: str = ""
    email_source_page: str = ""
    source_url: str = ""
    clutch_profile: str = ""
    status: Status = Status.NEW
    notes: str = ""
    source_order: int = Field(default=0, exclude=True)

    def to_csv_row(self) -> dict[str, str]:
        return dict(zip(CSV_COLUMNS, [
            self.agency, self.website, self.domain, self.country, self.email,
            self.email_source_page, self.source_url, self.clutch_profile,
            self.status.value, self.notes,
        ]))

    @classmethod
    def from_csv_row(cls, row: dict[str, str], source_order: int = 0) -> "AgencyRecord":
        return cls(
            agency=row.get("Agency", "").strip(), website=row.get("Website", "").strip(),
            domain=row.get("Domain", "").strip(), country=row.get("Country", "").strip(),
            email=row.get("Email", "").strip(),
            email_source_page=row.get("Email_Source_Page", "").strip(),
            source_url=row.get("Source_URL", "").strip(),
            clutch_profile=row.get("Clutch_Profile", "").strip(),
            status=Status(row.get("Status", Status.NEW.value)), notes=row.get("Notes", "").strip(),
            source_order=source_order,
        )


class EmailCandidate(BaseModel):
    email: str
    source_page: str
    method: str
    valid: bool = True
    score: int = 0


class ExtractionResult(BaseModel):
    """Internal result retaining every candidate while CSV exports only the best."""

    record: AgencyRecord
    candidates: list[EmailCandidate] = Field(default_factory=list)
