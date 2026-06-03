"""Per-sender parsers for job-alert emails.

The Gmail adapter (gmail_alerts.py) reads alert emails and hands each one to the
parser whose `from_domains` match the sender. To add a new source later
(Indeed, Wellfound, …): subclass EmailAlertParser, implement `parse`, and append
an instance to PARSERS at the bottom. Nothing else changes.
"""
from __future__ import annotations

import re
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Optional

from bs4 import BeautifulSoup

from core.models import JobPosting


# --- shared helpers ----------------------------------------------------------

def clean_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, TypeError):
        return payload.decode("utf-8", errors="replace")


def extract_html(msg: Message) -> str:
    """Best HTML body from an email; falls back to wrapping the plain-text part."""
    html_parts: list[str] = []
    text_parts: list[str] = []
    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.is_multipart():
            continue
        disp = str(part.get("Content-Disposition", ""))
        if disp.lower().startswith("attachment"):
            continue
        ctype = part.get_content_type()
        if ctype == "text/html":
            html_parts.append(_decode_part(part))
        elif ctype == "text/plain":
            text_parts.append(_decode_part(part))
    if html_parts:
        return "\n".join(html_parts)
    return "\n".join(text_parts)


def parse_email_date(msg: Message) -> Optional[str]:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        return None


# Lines in a job card that are chrome, not company/location.
_NOISE_RE = re.compile(
    r"^(view job|see job|view all jobs|apply|easy apply|actively recruiting|"
    r"be an early applicant|promoted|new|saved|\d+\s*(applicants?|connections?)|"
    r"\d+\s*(minutes?|hours?|days?|weeks?|months?)\s*ago)$",
    re.I,
)
# A location-ish line: has a comma, or a work-mode marker in parentheses.
_LOCATION_RE = re.compile(r",|\((remote|hybrid|on-?site)\)", re.I)


def _remote_type(location: str) -> str:
    low = location.lower()
    if "remote" in low:
        return "remote"
    if "hybrid" in low:
        return "hybrid"
    if "on-site" in low or "on site" in low or "onsite" in low:
        return "on-site"
    return ""


# --- parser interface --------------------------------------------------------

class EmailAlertParser:
    """Override in a subclass per email source."""
    source: str = ""
    from_domains: list[str] = []   # IMAP FROM filters, e.g. ["linkedin.com"]
    # An IMAP TEXT query that finds this source's emails even when they've been
    # auto-forwarded (so the From header is your address, not the original
    # sender). Should be a distinctive string from the body.
    text_query: str = ""

    def parse(self, html: str, subject: str = "", posted_date: Optional[str] = None) -> list[JobPosting]:
        raise NotImplementedError


# --- LinkedIn ----------------------------------------------------------------

class LinkedInParser(EmailAlertParser):
    source = "linkedin"
    from_domains = ["linkedin.com"]
    text_query = "linkedin.com/jobs/view"
    _JOB_RE = re.compile(r"/jobs/view/(\d+)")

    def parse(self, html: str, subject: str = "", posted_date: Optional[str] = None) -> list[JobPosting]:
        soup = BeautifulSoup(html or "", "html.parser")
        found: dict[str, JobPosting] = {}
        for a in soup.find_all("a", href=True):
            m = self._JOB_RE.search(a["href"])
            if not m:
                continue
            job_id = m.group(1)
            title = clean_text(a.get_text())
            # Skip the logo / "view job" anchors that point at the same job but
            # carry no real title.
            if len(title) < 3 or _NOISE_RE.match(title):
                continue
            if job_id in found:
                continue
            company, location = self._fields(a, title)
            found[job_id] = JobPosting(
                title=title,
                company=company,
                url=f"https://www.linkedin.com/jobs/view/{job_id}/",
                source=self.source,
                location=location,
                remote_type=_remote_type(location),
                posted_date=posted_date,
                tags=["email-alert", "linkedin"],
            )
        return list(found.values())

    def _fields(self, anchor, title: str) -> tuple[str, str]:
        """Pull company + location from the job card around the title anchor."""
        container = anchor
        for _ in range(4):
            if container.parent is None:
                break
            container = container.parent
            if getattr(container, "name", None) == "td":
                break
        lines: list[str] = []
        seen: set[str] = set()
        for s in container.stripped_strings:
            t = clean_text(s)
            if not t or t == title or _NOISE_RE.match(t) or t in seen:
                continue
            seen.add(t)
            lines.append(t)
        location = next((x for x in lines if _LOCATION_RE.search(x)), "")
        company = next((x for x in lines if x != location), "")
        return company, location


# Register parsers here. Order doesn't matter; each is matched by from_domains.
PARSERS: list[EmailAlertParser] = [
    LinkedInParser(),
    # Add later, e.g.:
    # IndeedParser(), WellfoundParser(),
]
