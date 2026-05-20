"""EU Startups Jobs - WordPress-based job board covering European startup roles.
WordPress sites typically expose a /feed/ RSS endpoint per category.
"""
from __future__ import annotations

import feedparser
from dateutil import parser as date_parser

from core.models import JobPosting
from .base import BaseAdapter


class EuStartupsAdapter(BaseAdapter):
    name = "eustartups"

    FEEDS = [
        "https://www.eu-startups.com/jobs/feed/",
        # Category feeds as backup. WP usually serves these even if the main feed paginates.
        "https://www.eu-startups.com/category/eu-startups-jobs-portal/feed/",
    ]

    def fetch(self) -> list[JobPosting]:
        results: list[JobPosting] = []
        seen: set[str] = set()

        for feed_url in self.FEEDS:
            resp = self._get(feed_url)
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

                title = entry.get("title", "").strip()
                summary = (entry.get("summary", "") or "").strip()
                # EU Startups summaries are usually short; strip HTML tags
                import re as _re
                clean_summary = _re.sub(r"<[^>]+>", " ", summary)[:500].strip()

                # Title often follows the pattern "Company is hiring a Role"
                # or "Role at Company". Try to split company/title heuristically.
                company = ""
                if " at " in title:
                    parts = title.rsplit(" at ", 1)
                    if len(parts) == 2:
                        title, company = parts[0].strip(), parts[1].strip()
                elif " is hiring " in title.lower():
                    parts = title.split(" is hiring ", 1)
                    if len(parts) == 2:
                        company = parts[0].strip()
                        title = parts[1].strip()

                # Detect remote/hybrid signals in title or summary
                lc = (title + " " + clean_summary).lower()
                remote_type = ""
                if "remote" in lc:
                    remote_type = "remote"
                elif "hybrid" in lc:
                    remote_type = "hybrid"

                results.append(JobPosting(
                    title=title,
                    company=company or "—",
                    url=link,
                    source=self.name,
                    location="Europe",
                    remote_type=remote_type,
                    description=clean_summary,
                    posted_date=posted,
                ))
        return results
