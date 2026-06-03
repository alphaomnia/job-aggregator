"""Tests for the email-alert parsers. Run: python tests/test_gmail_alerts.py

These exercise the fragile part (parsing alert HTML) without any network or
credentials — the IMAP plumbing in gmail_alerts.py only runs in CI with secrets.
"""
from __future__ import annotations

import email
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.email_parsers import LinkedInParser, extract_html, parse_email_date

# A representative LinkedIn job-alert body: two jobs in <td> cards, plus a logo
# anchor and a "View job" CTA pointing at the same first job (must be deduped /
# ignored, not turned into bogus postings).
LINKEDIN_HTML = """
<html><body>
  <table><tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/3812345678/?trk=eml-title">Senior Product Manager</a>
    <p>Acme Corp</p>
    <p>Prague, Czechia (Hybrid)</p>
    <p>Actively recruiting</p>
    <a href="https://www.linkedin.com/comm/jobs/view/3812345678/?trk=eml-logo"><img src="logo.png"/></a>
    <a href="https://www.linkedin.com/comm/jobs/view/3812345678/?trk=eml-cta">View job</a>
  </td></tr></table>
  <table><tr><td>
    <a href="https://www.linkedin.com/comm/jobs/view/3899999999/?trk=eml-title">Head of Product</a>
    <p>Globex GmbH</p>
    <p>Berlin, Germany (Remote)</p>
  </td></tr></table>
</body></html>
"""


def test_linkedin_extracts_unique_jobs():
    jobs = LinkedInParser().parse(LINKEDIN_HTML, "Your job alert", "2026-06-03")
    assert len(jobs) == 2, f"expected 2 unique jobs, got {len(jobs)}"


def test_linkedin_fields_and_canonical_url():
    jobs = {j.url: j for j in LinkedInParser().parse(LINKEDIN_HTML, "", "2026-06-03")}
    j1 = jobs["https://www.linkedin.com/jobs/view/3812345678/"]  # tracking stripped
    assert j1.title == "Senior Product Manager"
    assert j1.company == "Acme Corp"
    assert j1.location == "Prague, Czechia (Hybrid)"
    assert j1.remote_type == "hybrid"
    assert j1.source == "linkedin"
    assert "email-alert" in j1.tags
    j2 = jobs["https://www.linkedin.com/jobs/view/3899999999/"]
    assert j2.company == "Globex GmbH"
    assert j2.remote_type == "remote"


def test_linkedin_ignores_noise_anchors():
    # No posting should ever have the title "View job".
    titles = [j.title.lower() for j in LinkedInParser().parse(LINKEDIN_HTML)]
    assert "view job" not in titles


def test_empty_html_is_safe():
    assert LinkedInParser().parse("") == []
    assert LinkedInParser().parse(None) == []


RAW_EMAIL = (
    "From: jobalerts-noreply@linkedin.com\r\n"
    "Subject: Your job alert\r\n"
    "Date: Tue, 03 Jun 2026 06:00:00 +0000\r\n"
    "MIME-Version: 1.0\r\n"
    'Content-Type: multipart/alternative; boundary="B"\r\n'
    "\r\n"
    "--B\r\n"
    "Content-Type: text/plain; charset=UTF-8\r\n"
    "\r\n"
    "plain fallback text\r\n"
    "--B\r\n"
    "Content-Type: text/html; charset=UTF-8\r\n"
    "\r\n"
    + LINKEDIN_HTML
    + "\r\n--B--\r\n"
)


def test_extract_html_prefers_html_part():
    msg = email.message_from_string(RAW_EMAIL)
    html = extract_html(msg)
    assert "jobs/view/3812345678" in html
    assert "plain fallback" not in html


def test_parse_email_date():
    msg = email.message_from_string(RAW_EMAIL)
    assert parse_email_date(msg) == "2026-06-03"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
