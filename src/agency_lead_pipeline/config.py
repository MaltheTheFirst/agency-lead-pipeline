from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class Settings(BaseModel):
    clutch_urls: list[str] = Field(default_factory=list)
    delay_seconds: float = Field(default=1.5, ge=0)
    max_directory_pages: int = Field(default=10, ge=1)
    max_agencies: int = Field(default=500, ge=1)
    max_pages_per_website: int = Field(default=5, ge=1)
    timeout_seconds: float = Field(default=20, gt=0)
    concurrency: int = Field(default=2, ge=1, le=10)
    europe_only: bool = False
    user_agent: str = "agency-lead-pipeline/0.1 (+https://github.com/)"
    raw_output: Path = Path("data/raw_agencies.csv")
    leads_output: Path = Path("data/leads.csv")
    headless: bool = True


def load_settings(path: Path | None = None, **overrides: Any) -> Settings:
    data: dict[str, Any] = {}
    if path:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("Configuration root must be a mapping")
        data.update(loaded)
    data.update({key: value for key, value in overrides.items() if value is not None})
    return Settings.model_validate(data)
