"""Dynamite Jobs — remote-only job board. We scrape their listing page
and extract JSON-LD JobPosting structured data.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from core.models import JobPosting
from .base import BaseAdapter


class DynamiteJobsAdapter(BaseAdapter):
    name = "dynamitejobs"

    LISTING_URL = "https://dynamitejobs.com/remote-product-jobs"
    FALLBACK_URLS = [
        "https://dynamitejobs.com/remote-management-jobs",
    ]

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        for url in [self.LISTING_URL] + self.FALLBACK_URLS:
            resp = self._get(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")

            # JSON-LD approach
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    payload = json.loads(script.string or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                items = payload if isinstance(payload, list) else [payload]
                for entry in items:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("@type") != "JobPosting":
                        # Sometimes wrapped in @graph
                        graph = entry.get("@graph") or []
                        for g in graph:
                            if isinstance(g, dict) and g.get("@type") == "JobPosting":
                                self._absorb(g, seen, results)
                        continue
                    self._absorb(entry, seen, results)

            # Fallback: scrape anchor cards if JSON-LD missing
            if not results:
                for a in soup.select("a[href*='/remote-jobs/']"):
                    job_url = a.get("href", "")
                    if not job_url.startswith("http"):
                        job_url = "https://dynamitejobs.com" + job_url
                    if job_url in seen:
                        continue
                    title = a.get_text(strip=True)
                    if not title:
                        continue
                    seen.add(job_url)
                    results.append(JobPosting(
                        title=title,
                        company="",
                        url=job_url,
                        source=self.name,
                        location="Remote",
                        remote_type="remote",
                    ))

        return results

    def _absorb(self, entry: dict, seen: set, results: list) -> None:
        url = entry.get("url") or ""
        if not url or url in seen:
            return
        seen.add(url)
        hiring_org = entry.get("hiringOrganization") or {}
        desc = re.sub(r"<[^>]+>", " ", entry.get("description", "") or "")[:500].strip()
        results.append(JobPosting(
            title=entry.get("title", "").strip(),
            company=(hiring_org.get("name", "") if isinstance(hiring_org, dict) else "").strip(),
            url=url,
            source=self.name,
            location="Remote",
            remote_type="remote",
            description=desc,
            posted_date=entry.get("datePosted"),
        ))
