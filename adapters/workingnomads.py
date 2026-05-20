"""Working Nomads — they publish a JSON endpoint of all current jobs."""
from __future__ import annotations

from core.models import JobPosting
from .base import BaseAdapter


class WorkingNomadsAdapter(BaseAdapter):
    name = "workingnomads"

    API = "https://www.workingnomads.com/api/exposed_jobs/"

    def fetch(self) -> list[JobPosting]:
        resp = self._get(self.API)
        if not resp:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []

        results: list[JobPosting] = []
        for item in data:
            url = item.get("url", "")
            if not url:
                continue
            tags_raw = item.get("tags", "") or ""
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if isinstance(tags_raw, str) else (tags_raw or [])

            results.append(JobPosting(
                title=item.get("title", "").strip(),
                company=item.get("company_name", "").strip(),
                url=url,
                source=self.name,
                location=item.get("location", "").strip() or "Remote",
                remote_type="remote",
                description=(item.get("description", "") or "")[:500],
                posted_date=item.get("pub_date"),
                tags=tags,
            ))
        return results
