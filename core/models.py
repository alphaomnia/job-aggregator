"""Shared data models for job postings."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class JobPosting:
    """A single job posting from any source.

    The `id` is a stable hash that we use for deduplication across runs and sources.
    """
    title: str
    company: str
    url: str
    source: str
    location: str = ""
    remote_type: str = ""  # "remote" | "hybrid" | "on-site" | ""
    description: str = ""
    posted_date: Optional[str] = None  # ISO 8601 date string
    salary: str = ""
    tags: list[str] = field(default_factory=list)

    # Computed at ingestion
    id: str = ""
    first_seen: str = ""  # ISO date when we first saw this posting
    score: int = 0
    status: str = "new"  # new | seen | interested | applied | dismissed

    def compute_id(self) -> str:
        """Stable hash based on URL primarily, falling back to (title, company)."""
        if self.url:
            key = self.url.lower().split("?")[0].rstrip("/")
        else:
            key = f"{self.title.lower().strip()}|{self.company.lower().strip()}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def __post_init__(self) -> None:
        if not self.id:
            self.id = self.compute_id()
        if not self.first_seen:
            self.first_seen = datetime.utcnow().date().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "JobPosting":
        # Filter unknown keys so old data with extra fields doesn't break us
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})
