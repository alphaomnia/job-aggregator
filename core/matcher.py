"""Score job postings against user config so we can rank them in the digest."""
from __future__ import annotations

import re
from datetime import datetime
from functools import lru_cache
from typing import Any

from dateutil import parser as date_parser

from .models import JobPosting


def _haystack(job: JobPosting) -> str:
    return " ".join([
        job.title, job.company, job.description, job.location,
        " ".join(job.tags),
    ]).lower()


@lru_cache(maxsize=2048)
def _needle_pattern(needle: str) -> re.Pattern:
    # Whole-word(ish) match so "lead" no longer matches "leadership" and "CPO"
    # doesn't match inside another token. Multi-word needles match literally.
    return re.compile(r"(?<!\w)" + re.escape(needle.lower()) + r"(?!\w)")


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(_needle_pattern(n).search(text) for n in needles)


def score_job(job: JobPosting, config: dict[str, Any]) -> int:
    """Score a job posting 0-100ish based on config preferences.

    Higher = better match. Negative penalties for explicit avoid signals.
    """
    score = 0
    text = _haystack(job)

    # Role match - the biggest signal
    roles = config.get("roles", {})
    if _contains_any(job.title.lower(), roles.get("strong", [])):
        score += 30
    elif _contains_any(text, roles.get("strong", [])):
        score += 15
    if _contains_any(job.title.lower(), roles.get("good", [])):
        score += 12
    elif _contains_any(text, roles.get("good", [])):
        score += 5

    # Negative signals - effectively excludes
    if _contains_any(job.title.lower(), roles.get("avoid", [])):
        score -= 40

    # Location
    locations = config.get("locations", {})
    if _contains_any(text, locations.get("priority", [])):
        score += 20
    elif _contains_any(text, locations.get("acceptable", [])):
        score += 8

    # Remote / hybrid / on-site
    work_modes = config.get("work_modes", {})
    preferred = work_modes.get("prefer", [])
    if job.remote_type and job.remote_type.lower() in [p.lower() for p in preferred]:
        score += 10
    elif "remote" in text and "remote" in preferred:
        score += 5

    # Freshness - decay older postings
    if job.posted_date:
        try:
            posted = date_parser.parse(job.posted_date)
            if posted.tzinfo:
                posted = posted.replace(tzinfo=None)
            age_days = (datetime.utcnow() - posted).days
            if age_days <= 2:
                score += 8
            elif age_days <= 7:
                score += 4
            elif age_days > 30:
                score -= 5
        except (ValueError, TypeError):
            pass

    # Contract / fractional bonus if you're open to it
    contract_types = [c.lower() for c in config.get("contract_types", [])]
    contract_signals = ["fractional", "interim", "contract", "freelance", "part-time", "part time"]
    if any(sig in text for sig in contract_signals) and any(sig in contract_types for sig in contract_signals):
        score += 6

    # Learned suppression (feedback loop). feedback.yaml lets us teach the
    # server-side scorer to push down roles like the ones being dismissed, so
    # the email digest and every device benefit -- not just one browser's
    # localStorage. Empty by default, so this is a no-op until populated.
    feedback = config.get("feedback") or {}
    title = job.title.lower()
    for kw in feedback.get("suppress_title_keywords", []):
        if _needle_pattern(str(kw)).search(title):
            score -= int(feedback.get("title_keyword_penalty", 12))
    for company in feedback.get("suppress_companies", []):
        if str(company).lower().strip() and str(company).lower().strip() in job.company.lower():
            score -= int(feedback.get("company_penalty", 25))

    return score


def filter_fresh(jobs: list[JobPosting], config: dict[str, Any]) -> list[JobPosting]:
    """Drop jobs older than config.max_age_days based on posted_date OR first_seen."""
    max_age = config.get("max_age_days", 14)
    cutoff_date = datetime.utcnow().date()
    fresh: list[JobPosting] = []
    for job in jobs:
        anchor = job.posted_date or job.first_seen
        if not anchor:
            fresh.append(job)
            continue
        try:
            d = date_parser.parse(anchor).date()
            if (cutoff_date - d).days <= max_age:
                fresh.append(job)
        except (ValueError, TypeError):
            fresh.append(job)
    return fresh
