"""Remotive — official public JSON API. Most reliable source.
Docs: https://remotive.com/api-documentation
"""
from __future__ import annotations

from html import unescape
import re

from core.models import JobPosting
from .base import BaseAdapter


class RemotiveAdapter(BaseAdapter):
    name = "remotive"

    API = "https://remotive.com/api/remote-jobs"

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []

        # Remotive supports a `search` param. Run one query per role keyword,
        # dedupe by URL.
        seen: set[str] = set()
        queries = self.search_terms or [""]
        # Cap to avoid hammering the API
        for q in queries[:8]:
            params = {"search": q, "limit": 50} if q else {"limit": 50}
            resp = self._get(self.API, params=params)
            if not resp:
                continue
            data = resp.json()
            for item in data.get("jobs", []):
                url = item.get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)

                desc_html = item.get("description") or ""
                description = _strip_html(desc_html)[:500]

                results.append(JobPosting(
                    title=item.get("title", "").strip(),
                    company=item.get("company_name", "").strip(),
                    url=url,
                    source=self.name,
                    location=item.get("candidate_required_location", "").strip() or "Remote",
                    remote_type="remote",
                    description=description,
                    posted_date=item.get("publication_date"),
                    salary=item.get("salary", "").strip(),
                    tags=item.get("tags") or [],
                ))
        return results


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return unescape(_TAG_RE.sub(" ", s)).replace("\xa0", " ").strip()
