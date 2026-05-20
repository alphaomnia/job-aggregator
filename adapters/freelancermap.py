"""freelancermap — has RSS feeds for keyword searches.
Sample feed URL: https://www.freelancermap.com/projects.rss?query=product
"""
from __future__ import annotations

from urllib.parse import quote_plus

import feedparser
from dateutil import parser as date_parser

from core.models import JobPosting
from .base import BaseAdapter


class FreelancermapAdapter(BaseAdapter):
    name = "freelancermap"

    BASE = "https://www.freelancermap.com/projects.rss"

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        # freelancermap is contract-focused, so the role keywords matter here.
        queries = self.search_terms[:6] or ["Product Manager", "Head of Product"]
        for q in queries:
            url = f"{self.BASE}?query={quote_plus(q)}"
            resp = self._get(url)
            if not resp:
                continue
            parsed = feedparser.parse(resp.content)
            for entry in parsed.entries:
                link = entry.get("link", "")
                if not link or link in seen:
                    continue
                seen.add(link)

                posted = None
                if entry.get("published"):
                    try:
                        posted = date_parser.parse(entry["published"]).isoformat()
                    except (ValueError, TypeError):
                        pass

                # freelancermap titles often include location/contract type
                title = entry.get("title", "").strip()
                summary = (entry.get("summary", "") or "")[:500]

                # Try to detect "remote" or country in the summary
                lc_summary = summary.lower()
                remote_type = "remote" if "remote" in lc_summary or "homeoffice" in lc_summary else "hybrid"

                results.append(JobPosting(
                    title=title,
                    company="(freelance contract)",
                    url=link,
                    source=self.name,
                    location="EU / Remote",
                    remote_type=remote_type,
                    description=summary,
                    posted_date=posted,
                    tags=["contract", "freelance"],
                ))
        return results
