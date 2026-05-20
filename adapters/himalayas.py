"""Himalayas — remote jobs aggregator with a sitemap-style index we can poll.
We use their /jobs page filtered by category, since they don't offer a stable public API.
This adapter uses the JSON-LD that pages render in their HTML.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from core.models import JobPosting
from .base import BaseAdapter


class HimalayasAdapter(BaseAdapter):
    name = "himalayas"

    # Filter pages by category/seniority that match product leadership
    LISTING_URLS = [
        "https://himalayas.app/jobs/categories/management",
        "https://himalayas.app/jobs/categories/product",
    ]

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        for url in self.LISTING_URLS:
            resp = self._get(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")

            # Himalayas embeds a JSON-LD ItemList of jobs on listing pages
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    payload = json.loads(script.string or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                items = payload.get("itemListElement") or []
                for entry in items:
                    job_data = entry.get("item") if isinstance(entry, dict) else None
                    if not isinstance(job_data, dict):
                        continue
                    job_url = job_data.get("url", "")
                    if not job_url or job_url in seen:
                        continue
                    seen.add(job_url)

                    hiring_org = job_data.get("hiringOrganization") or {}
                    location = ""
                    job_location = job_data.get("jobLocation")
                    if isinstance(job_location, list) and job_location:
                        addr = job_location[0].get("address", {})
                        location = addr.get("addressCountry", "") if isinstance(addr, dict) else ""

                    description = re.sub(r"<[^>]+>", " ", job_data.get("description", "") or "")[:500]

                    results.append(JobPosting(
                        title=job_data.get("title", "").strip(),
                        company=hiring_org.get("name", "").strip() if isinstance(hiring_org, dict) else "",
                        url=job_url,
                        source=self.name,
                        location=location or "Remote",
                        remote_type="remote",
                        description=description.strip(),
                        posted_date=job_data.get("datePosted"),
                    ))
        return results
