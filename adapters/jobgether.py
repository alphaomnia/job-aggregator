"""Jobgether — no public API. We hit their search URL and parse the result page.

This adapter is the most fragile of the set because it depends on Jobgether's
markup. If they redesign and this stops working, the orchestrator will log
'returned 0 postings' and you can update the selectors below.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from core.models import JobPosting
from .base import BaseAdapter


class JobgetherAdapter(BaseAdapter):
    name = "jobgether"

    BASE = "https://jobgether.com"

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        queries = self.search_terms[:6] or ["Product"]
        for q in queries:
            url = f"{self.BASE}/search-jobs?q={quote_plus(q)}"
            resp = self._get(url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # Strategy 1: look for JSON-LD JobPosting entries
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    payload = json.loads(script.string or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                # Pages may have an array or a single object
                items = payload if isinstance(payload, list) else [payload]
                for entry in items:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("@type") != "JobPosting":
                        continue
                    job_url = entry.get("url") or ""
                    if not job_url or job_url in seen:
                        continue
                    seen.add(job_url)

                    hiring_org = entry.get("hiringOrganization") or {}
                    company = hiring_org.get("name", "") if isinstance(hiring_org, dict) else ""

                    location = ""
                    jl = entry.get("jobLocation")
                    if isinstance(jl, list) and jl:
                        addr = jl[0].get("address", {})
                        if isinstance(addr, dict):
                            location = addr.get("addressCountry", "") or addr.get("addressLocality", "")
                    elif isinstance(jl, dict):
                        addr = jl.get("address", {})
                        if isinstance(addr, dict):
                            location = addr.get("addressCountry", "") or addr.get("addressLocality", "")

                    desc = re.sub(r"<[^>]+>", " ", entry.get("description", "") or "")[:500].strip()
                    remote_type = ""
                    if entry.get("jobLocationType") == "TELECOMMUTE":
                        remote_type = "remote"

                    results.append(JobPosting(
                        title=entry.get("title", "").strip(),
                        company=company.strip(),
                        url=job_url,
                        source=self.name,
                        location=location.strip() or "—",
                        remote_type=remote_type,
                        description=desc,
                        posted_date=entry.get("datePosted"),
                    ))
        return results
