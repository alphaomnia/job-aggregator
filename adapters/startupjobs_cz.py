"""StartupJobs.cz — Czech startup job board. Critical source for Prague-based roles.

Their listing pages include JSON-LD job postings. We filter to product-related
categories via URL query params.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from core.models import JobPosting
from .base import BaseAdapter


class StartupJobsCzAdapter(BaseAdapter):
    name = "startupjobs_cz"

    LISTING_URLS = [
        # Product category, English UI
        "https://www.startupjobs.cz/en/search?profession=product-manager",
        "https://www.startupjobs.cz/en/search?profession=product",
        "https://www.startupjobs.cz/en/search?q=Head%20of%20Product",
        "https://www.startupjobs.cz/en/search?q=Director%20of%20Product",
    ]

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        for url in self.LISTING_URLS:
            resp = self._get(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")

            # Try JSON-LD first
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
                        continue
                    job_url = entry.get("url") or ""
                    if not job_url or job_url in seen:
                        continue
                    seen.add(job_url)

                    hiring_org = entry.get("hiringOrganization") or {}
                    company = hiring_org.get("name", "") if isinstance(hiring_org, dict) else ""

                    location = "Czech Republic"
                    jl = entry.get("jobLocation")
                    if isinstance(jl, dict):
                        addr = jl.get("address", {})
                        if isinstance(addr, dict):
                            location = addr.get("addressLocality", "") or addr.get("addressCountry", "") or location
                    elif isinstance(jl, list) and jl:
                        addr = jl[0].get("address", {})
                        if isinstance(addr, dict):
                            location = addr.get("addressLocality", "") or addr.get("addressCountry", "") or location

                    remote_type = "remote" if entry.get("jobLocationType") == "TELECOMMUTE" else "on-site"
                    desc = re.sub(r"<[^>]+>", " ", entry.get("description", "") or "")[:500].strip()

                    results.append(JobPosting(
                        title=entry.get("title", "").strip(),
                        company=company.strip(),
                        url=job_url,
                        source=self.name,
                        location=location.strip(),
                        remote_type=remote_type,
                        description=desc,
                        posted_date=entry.get("datePosted"),
                    ))

        return results
