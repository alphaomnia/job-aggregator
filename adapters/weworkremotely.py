"""We Work Remotely — public RSS feeds. We use the all-jobs feed and filter locally."""
from __future__ import annotations

import feedparser
from dateutil import parser as date_parser

from core.models import JobPosting
from .base import BaseAdapter


class WeWorkRemotelyAdapter(BaseAdapter):
    name = "weworkremotely"

    FEEDS = [
        # Categories most relevant to product leadership.
        "https://weworkremotely.com/categories/remote-product-jobs.rss",
        "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss",
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
                url = entry.get("link", "")
                if not url or url in seen:
                    continue
                seen.add(url)

                # WWR titles are formatted like "Company: Role title"
                raw_title = entry.get("title", "")
                if ":" in raw_title:
                    company, title = raw_title.split(":", 1)
                    company = company.strip()
                    title = title.strip()
                else:
                    company = ""
                    title = raw_title

                # Try to extract a posted date
                posted = None
                if entry.get("published"):
                    try:
                        posted = date_parser.parse(entry["published"]).isoformat()
                    except (ValueError, TypeError):
                        pass

                description = (entry.get("summary", "") or "")[:500]

                results.append(JobPosting(
                    title=title,
                    company=company,
                    url=url,
                    source=self.name,
                    location="Remote",
                    remote_type="remote",
                    description=description,
                    posted_date=posted,
                ))
        return results
