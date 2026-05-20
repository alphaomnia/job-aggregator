"""The Org - org chart platform that also runs a Jobs platform.
Their listing pages embed JSON-LD JobPosting for SEO.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from core.models import JobPosting
from .base import BaseAdapter


class TheOrgAdapter(BaseAdapter):
    name = "theorg"

    LISTING_URLS = [
        "https://theorg.com/jobs/product-management",
        "https://theorg.com/jobs/executive",
        "https://theorg.com/jobs?role=product",
    ]

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        for url in self.LISTING_URLS:
            resp = self._get(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")

            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    payload = json.loads(script.string or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue
                items = payload if isinstance(payload, list) else [payload]
                for entry in items:
                    if not isinstance(entry, dict):
                        continue
                    # Sometimes wrapped in @graph
                    if "@graph" in entry:
                        for g in entry["@graph"]:
                            if isinstance(g, dict) and g.get("@type") == "JobPosting":
                                self._absorb(g, seen, results)
                    elif entry.get("@type") == "JobPosting":
                        self._absorb(entry, seen, results)

        return results

    def _absorb(self, entry: dict, seen: set, results: list) -> None:
        url = entry.get("url") or ""
        if not url or url in seen:
            return
        seen.add(url)
        hiring_org = entry.get("hiringOrganization") or {}
        company = hiring_org.get("name", "") if isinstance(hiring_org, dict) else ""

        location = ""
        jl = entry.get("jobLocation")
        if isinstance(jl, dict):
            addr = jl.get("address", {})
            if isinstance(addr, dict):
                location = addr.get("addressLocality", "") or addr.get("addressCountry", "")
        elif isinstance(jl, list) and jl:
            addr = jl[0].get("address", {})
            if isinstance(addr, dict):
                location = addr.get("addressLocality", "") or addr.get("addressCountry", "")

        remote_type = "remote" if entry.get("jobLocationType") == "TELECOMMUTE" else ""
        desc = re.sub(r"<[^>]+>", " ", entry.get("description", "") or "")[:500].strip()

        results.append(JobPosting(
            title=entry.get("title", "").strip(),
            company=company.strip(),
            url=url,
            source=self.name,
            location=location.strip() or "—",
            remote_type=remote_type,
            description=desc,
            posted_date=entry.get("datePosted"),
        ))
