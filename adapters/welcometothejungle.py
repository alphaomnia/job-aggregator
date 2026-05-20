"""Welcome to the Jungle (formerly Otta) - their UK/EU/US tech jobs platform.
Heavy Czech Republic presence (WTTJ has a Prague office).

Strategy: WTTJ uses Next.js; we try JSON-LD first, then fall back to parsing
__NEXT_DATA__. Their full Algolia search API requires keys, so this adapter
is best-effort. If it returns 0, the orchestrator just skips it.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from core.models import JobPosting
from .base import BaseAdapter


class WelcomeToTheJungleAdapter(BaseAdapter):
    name = "welcometothejungle"

    SEARCH_URL = "https://www.welcometothejungle.com/en/jobs"

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        queries = self.search_terms[:5] or ["Head of Product"]
        for q in queries:
            url = f"{self.SEARCH_URL}?query={quote_plus(q)}&page=1"
            resp = self._get(url)
            if not resp:
                continue
            soup = BeautifulSoup(resp.text, "lxml")

            # Strategy 1: JSON-LD JobPosting entries
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
                    self._absorb(entry, seen, results)

            # Strategy 2: parse __NEXT_DATA__ for hydrated jobs
            next_data = soup.find("script", id="__NEXT_DATA__")
            if next_data and next_data.string:
                try:
                    blob = json.loads(next_data.string)
                except json.JSONDecodeError:
                    blob = None
                if blob:
                    for hit in self._walk_for_jobs(blob):
                        url = hit.get("url") or hit.get("link")
                        if not url:
                            continue
                        if not url.startswith("http"):
                            url = "https://www.welcometothejungle.com" + url
                        if url in seen:
                            continue
                        seen.add(url)
                        results.append(JobPosting(
                            title=hit.get("name", "").strip() or hit.get("title", "").strip(),
                            company=(hit.get("organization", {}) or {}).get("name", "").strip()
                                     if isinstance(hit.get("organization"), dict)
                                     else hit.get("company_name", "").strip(),
                            url=url,
                            source=self.name,
                            location=hit.get("office_main_country", "") or hit.get("location", ""),
                            remote_type=("remote" if hit.get("remote") == "fulltime"
                                          else "hybrid" if hit.get("remote") == "punctual"
                                          else ""),
                            description=re.sub(r"<[^>]+>", " ",
                                                hit.get("description", "") or "")[:500].strip(),
                            posted_date=hit.get("published_at") or hit.get("created_at"),
                        ))

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

    def _walk_for_jobs(self, obj, depth: int = 0):
        """Recursively walk __NEXT_DATA__ looking for job-like objects.
        WTTJ's payload structure changes; we identify jobs by having both a
        title/name and a slug/url-ish field.
        """
        if depth > 8:
            return
        if isinstance(obj, dict):
            looks_like_job = (
                ("name" in obj or "title" in obj)
                and ("slug" in obj or "url" in obj or "link" in obj)
                and ("organization" in obj or "company_name" in obj or "office" in obj)
            )
            if looks_like_job:
                yield obj
            for v in obj.values():
                yield from self._walk_for_jobs(v, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                yield from self._walk_for_jobs(item, depth + 1)
