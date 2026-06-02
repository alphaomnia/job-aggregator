"""Persistent storage in a JSON file, with deduplication and merge logic."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .models import JobPosting


class JobStore:
    """Read/write JobPostings to a JSON file.

    Source of truth is docs/jobs.json (committed to the repo, also served by GitHub Pages).
    """

    def __init__(self, path: Path):
        self.path = path
        self._jobs: dict[str, JobPosting] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._jobs = {}
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            jobs_data = raw.get("jobs", []) if isinstance(raw, dict) else raw
            self._jobs = {}
            for item in jobs_data:
                job = JobPosting.from_dict(item)
                self._jobs[job.id] = job
        except (json.JSONDecodeError, OSError) as e:
            print(f"[store] Could not read {self.path}: {e}. Starting fresh.")
            self._jobs = {}

    def all(self) -> list[JobPosting]:
        return list(self._jobs.values())

    def get(self, job_id: str) -> JobPosting | None:
        return self._jobs.get(job_id)

    def merge(self, incoming: Iterable[JobPosting]) -> list[JobPosting]:
        """Add new postings. Return list of jobs that are genuinely new this run."""
        new_jobs: list[JobPosting] = []
        for job in incoming:
            if job.id in self._jobs:
                # Preserve first_seen and user-set status from the existing record
                existing = self._jobs[job.id]
                job.first_seen = existing.first_seen
                job.status = existing.status if existing.status != "new" else job.status
                self._jobs[job.id] = job
            else:
                self._jobs[job.id] = job
                new_jobs.append(job)
        return new_jobs

    def prune(self, max_age_days: int = 60) -> int:
        """Drop postings whose first_seen is older than max_age_days. Returns count removed."""
        cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).date().isoformat()
        before = len(self._jobs)
        self._jobs = {
            jid: job for jid, job in self._jobs.items()
            if job.first_seen >= cutoff or job.status in ("interested", "applied")
        }
        return before - len(self._jobs)

    def save(self, meta: dict | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "count": len(self._jobs),
            "jobs": sorted(
                (j.to_dict() for j in self._jobs.values()),
                key=lambda j: (j.get("first_seen", ""), j.get("score", 0)),
                reverse=True,
            ),
        }
        if meta:
            # e.g. per-adapter health so the dashboard can flag dead sources.
            payload.update(meta)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
