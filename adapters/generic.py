"""Generic adapter - reads user-defined sources from sources.yaml.

Lets you add new RSS feeds, JSON-LD pages, or JSON endpoints by editing
one YAML file rather than writing Python. See sources.yaml at the repo root
for the schema.

Supported source types:
  - rss:      RSS or Atom feed URL
  - jsonld:   HTML page(s) embedding <script type="application/ld+json"> JobPosting data
  - json_api: Direct JSON endpoint returning an array of jobs (with field mapping)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import feedparser
import yaml
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from core.models import JobPosting
from .base import BaseAdapter


SOURCES_FILE = Path(__file__).resolve().parent.parent / "sources.yaml"


class GenericAdapter(BaseAdapter):
    """Reads sources.yaml and dispatches each entry to the right handler.

    Each entry's `name` field becomes the `source` of any JobPosting it
    produces, so the dashboard source filter can distinguish them.
    """
    name = "generic"

    def fetch(self) -> list[JobPosting]:
        if not SOURCES_FILE.exists():
            print(f"[{self.name}] sources.yaml not found at {SOURCES_FILE}. Skipping.")
            return []

        try:
            with SOURCES_FILE.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            print(f"[{self.name}] sources.yaml parse error: {e}")
            return []

        sources = config.get("sources") or []
        if not sources:
            print(f"[{self.name}] sources.yaml has no entries.")
            return []

        all_results: list[JobPosting] = []

        for src in sources:
            if not isinstance(src, dict):
                continue
            source_name = (src.get("name") or "user_source").strip()
            source_type = (src.get("type") or "").lower()

            try:
                if source_type == "rss":
                    results = self._fetch_rss(src, source_name)
                elif source_type == "jsonld":
                    results = self._fetch_jsonld(src, source_name)
                elif source_type == "json_api":
                    results = self._fetch_json_api(src, source_name)
                else:
                    print(f"[{self.name}/{source_name}] unknown type '{source_type}'")
                    continue
                print(f"[{self.name}/{source_name}] returned {len(results)} postings")
                all_results.extend(results)
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}/{source_name}] crashed: {type(e).__name__}: {e}")

        return all_results

    # ---------- RSS ----------

    def _fetch_rss(self, src: dict, source_name: str) -> list[JobPosting]:
        url = src.get("url")
        if not url:
            return []

        resp = self._get(url)
        if not resp:
            return []

        default_location = src.get("default_location", "") or ""
        default_remote = src.get("default_remote", "") or ""

        results: list[JobPosting] = []
        seen: set[str] = set()
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

            title = (entry.get("title", "") or "").strip()
            summary_raw = (entry.get("summary", "") or "").strip()
            clean_summary = re.sub(r"<[^>]+>", " ", summary_raw)[:500].strip()

            # Best-effort company extraction from common title patterns
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

            remote_type = default_remote
            if not remote_type:
                lc = (title + " " + clean_summary).lower()
                if "remote" in lc:
                    remote_type = "remote"
                elif "hybrid" in lc:
                    remote_type = "hybrid"

            results.append(JobPosting(
                title=title,
                company=company or "—",
                url=link,
                source=source_name,
                location=default_location or "—",
                remote_type=remote_type,
                description=clean_summary,
                posted_date=posted,
            ))

        return results

    # ---------- JSON-LD pages ----------

    def _fetch_jsonld(self, src: dict, source_name: str) -> list[JobPosting]:
        urls = src.get("urls") or ([src["url"]] if src.get("url") else [])
        if not urls:
            return []

        default_location = src.get("default_location", "") or ""

        results: list[JobPosting] = []
        seen: set[str] = set()

        for url in urls:
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
                    if entry.get("@type") == "JobPosting":
                        self._absorb_jsonld(entry, seen, results, source_name, default_location)
                    elif "@graph" in entry:
                        for g in entry["@graph"]:
                            if isinstance(g, dict) and g.get("@type") == "JobPosting":
                                self._absorb_jsonld(g, seen, results, source_name, default_location)
                    elif entry.get("@type") == "ItemList":
                        for itm in entry.get("itemListElement", []) or []:
                            job = itm.get("item") if isinstance(itm, dict) and isinstance(itm.get("item"), dict) else itm
                            if isinstance(job, dict) and job.get("@type") == "JobPosting":
                                self._absorb_jsonld(job, seen, results, source_name, default_location)
        return results

    def _absorb_jsonld(self, entry: dict, seen: set, results: list,
                       source_name: str, default_location: str) -> None:
        url = entry.get("url") or ""
        if not url or url in seen:
            return
        seen.add(url)

        hiring_org = entry.get("hiringOrganization") or {}
        company = hiring_org.get("name", "") if isinstance(hiring_org, dict) else ""

        location = default_location
        jl = entry.get("jobLocation")
        if isinstance(jl, dict):
            addr = jl.get("address", {})
            if isinstance(addr, dict):
                location = addr.get("addressLocality", "") or addr.get("addressCountry", "") or location
        elif isinstance(jl, list) and jl:
            first = jl[0]
            if isinstance(first, dict):
                addr = first.get("address", {})
                if isinstance(addr, dict):
                    location = addr.get("addressLocality", "") or addr.get("addressCountry", "") or location

        remote_type = "remote" if entry.get("jobLocationType") == "TELECOMMUTE" else ""
        desc = re.sub(r"<[^>]+>", " ", entry.get("description", "") or "")[:500].strip()

        results.append(JobPosting(
            title=(entry.get("title", "") or "").strip(),
            company=company.strip() or "—",
            url=url,
            source=source_name,
            location=location.strip() or "—",
            remote_type=remote_type,
            description=desc,
            posted_date=entry.get("datePosted"),
        ))

    # ---------- JSON API ----------

    def _fetch_json_api(self, src: dict, source_name: str) -> list[JobPosting]:
        url = src.get("url")
        if not url:
            return []

        resp = self._get(url)
        if not resp:
            return []

        try:
            data = resp.json()
        except ValueError:
            print(f"[generic/{source_name}] response was not valid JSON")
            return []

        # Find the array of jobs - could be at root or under a common key
        jobs_array: list | None = None
        if isinstance(data, list):
            jobs_array = data
        elif isinstance(data, dict):
            for key in ("jobs", "data", "results", "items", "postings", "openings"):
                if isinstance(data.get(key), list):
                    jobs_array = data[key]
                    break

        if jobs_array is None:
            print(f"[generic/{source_name}] couldn't find jobs array in JSON")
            return []

        fields = src.get("fields") or {}
        default_location = src.get("default_location", "") or ""
        default_remote = src.get("default_remote", "") or ""

        results: list[JobPosting] = []
        seen: set[str] = set()
        for item in jobs_array:
            if not isinstance(item, dict):
                continue

            job_url = _get_nested(item, fields.get("url", "url"))
            if not job_url or job_url in seen:
                continue
            seen.add(job_url)

            title = _get_nested(item, fields.get("title", "title")) or ""
            company = _get_nested(item, fields.get("company", "company")) or ""
            location = _get_nested(item, fields.get("location", "location")) or default_location
            description = _get_nested(item, fields.get("description", "description")) or ""
            posted = _get_nested(item, fields.get("posted_date", "posted_date"))

            results.append(JobPosting(
                title=str(title).strip(),
                company=str(company).strip() or "—",
                url=str(job_url),
                source=source_name,
                location=str(location).strip() or "—",
                remote_type=default_remote,
                description=re.sub(r"<[^>]+>", " ", str(description))[:500].strip(),
                posted_date=str(posted) if posted else None,
            ))

        return results


def _get_nested(obj: dict, path: str) -> Any:
    """Walk a dotted path through nested dicts. e.g. 'employer.name'."""
    if not path:
        return None
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur
