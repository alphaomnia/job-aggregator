"""Talent.com Czech Republic - aggregator with strong CZ coverage.

Talent.com is a meta-aggregator pulling from many ATSes and job boards.
We query their Czech subdomain filtered to Czech Republic locations.

Note: Talent.com sets noindex on search pages. Use sparingly and only for
personal job-search aggregation, not for redistribution.
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from core.models import JobPosting
from .base import BaseAdapter


class TalentCzAdapter(BaseAdapter):
    name = "talent_cz"

    BASE = "https://cz.talent.com"

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        # Use top search terms; CZ-focused so we narrow location to Czech Republic.
        queries = self.search_terms[:5] or ["Product Manager"]

        for i, q in enumerate(queries):
            # Be polite - small delay between queries
            if i > 0:
                time.sleep(1.0)

            url = f"{self.BASE}/en/jobs?k={quote_plus(q)}&l=Czech+Republic"
            resp = self._get(url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # Strategy 1: JSON-LD JobPosting entries (most reliable, Google requires
            # these for jobs to surface in their Job Search results).
            jsonld_count = 0
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    payload = json.loads(script.string or "{}")
                except (json.JSONDecodeError, TypeError):
                    continue

                # Talent.com may use a few different JSON-LD shapes
                items = payload if isinstance(payload, list) else [payload]
                for entry in items:
                    if not isinstance(entry, dict):
                        continue

                    # Direct JobPosting
                    if entry.get("@type") == "JobPosting":
                        if self._absorb_jsonld(entry, seen, results):
                            jsonld_count += 1

                    # ItemList wrapper
                    elif entry.get("@type") == "ItemList":
                        for itm in entry.get("itemListElement", []) or []:
                            if not isinstance(itm, dict):
                                continue
                            job = itm.get("item") if isinstance(itm.get("item"), dict) else itm
                            if isinstance(job, dict) and job.get("@type") == "JobPosting":
                                if self._absorb_jsonld(job, seen, results):
                                    jsonld_count += 1

                    # @graph wrapper
                    elif "@graph" in entry:
                        for g in entry["@graph"]:
                            if isinstance(g, dict) and g.get("@type") == "JobPosting":
                                if self._absorb_jsonld(g, seen, results):
                                    jsonld_count += 1

            # Strategy 2: HTML card parsing if JSON-LD yielded nothing for this query.
            # Talent's result cards have <h2> with an <a> linking to /en/view?id=...
            if jsonld_count == 0:
                for h2 in soup.find_all("h2"):
                    a = h2.find("a") or h2.find_parent("a")
                    if not a:
                        continue
                    href = a.get("href", "")
                    if not href or "view?id=" not in href:
                        continue
                    if not href.startswith("http"):
                        href = self.BASE + href
                    if href in seen:
                        continue
                    seen.add(href)

                    title = h2.get_text(strip=True)
                    company = ""
                    location = ""

                    # Walk the parent to find a "Company•Location" line
                    parent = h2.find_parent("div") or h2.parent
                    if parent:
                        for line in parent.stripped_strings:
                            if "•" in line:
                                parts = line.split("•", 1)
                                company = parts[0].strip()
                                location = parts[1].strip() if len(parts) > 1 else ""
                                break

                    remote_type = "remote" if "remote" in title.lower() else ""

                    results.append(JobPosting(
                        title=title,
                        company=company or "(via Talent.com)",
                        url=href,
                        source=self.name,
                        location=location or "Czech Republic",
                        remote_type=remote_type,
                        description="",
                        posted_date=None,
                    ))

        return results

    def _absorb_jsonld(self, entry: dict, seen: set, results: list) -> bool:
        """Add one JobPosting from a JSON-LD entry. Returns True if added."""
        url = entry.get("url") or ""
        if not url or url in seen:
            return False
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
            first = jl[0]
            if isinstance(first, dict):
                addr = first.get("address", {})
                if isinstance(addr, dict):
                    location = addr.get("addressLocality", "") or addr.get("addressCountry", "")

        remote_type = "remote" if entry.get("jobLocationType") == "TELECOMMUTE" else ""
        desc = re.sub(r"<[^>]+>", " ", entry.get("description", "") or "")[:500].strip()

        results.append(JobPosting(
            title=(entry.get("title", "") or "").strip(),
            company=company.strip(),
            url=url,
            source=self.name,
            location=location.strip() or "Czech Republic",
            remote_type=remote_type,
            description=desc,
            posted_date=entry.get("datePosted"),
        ))
        return True
