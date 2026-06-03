"""Ingest job-alert emails from a dedicated mailbox via IMAP.

This is the legal/reliable way to pull from sources that can't be scraped
(LinkedIn, Indeed, Wellfound, …): you subscribe to *their* email job alerts and
this adapter reads the resulting emails. It never logs into those sites, stores
their credentials, or scrapes them — only the alert emails you opted into.

Works with any IMAP provider (Gmail, iCloud, Fastmail, …). It finds alert emails
both by sender and by a body signature, so emails you auto-forward from another
inbox (which may rewrite the From header) are still picked up. Adding a new
source is done in email_parsers.py (PARSERS); this file is generic.

Env (set whichever matches your provider; GMAIL_* kept for convenience):
  IMAP_USER / GMAIL_USER             the mailbox address
  IMAP_PASSWORD / GMAIL_APP_PASSWORD an app-specific password (2FA required)
  IMAP_HOST                          default imap.gmail.com (iCloud: imap.mail.me.com)
  IMAP_PORT                          default 993
  GMAIL_MARK_SEEN                    "0" to leave messages unread (default: mark read)
"""
from __future__ import annotations

import email
import imaplib
import os
from datetime import datetime, timedelta

from core.models import JobPosting
from .base import BaseAdapter
from .email_parsers import PARSERS, extract_html, parse_email_date

LOOKBACK_DAYS = 30
MAX_MESSAGES = 100  # safety cap across all senders


class GmailAlertsAdapter(BaseAdapter):
    name = "gmail_alerts"

    def fetch(self) -> list[JobPosting]:
        user = os.environ.get("IMAP_USER") or os.environ.get("GMAIL_USER")
        password = os.environ.get("IMAP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD")
        if not (user and password):
            print(f"[{self.name}] IMAP_USER/IMAP_PASSWORD (or GMAIL_*) not set. Skipping.")
            return []

        # `or` (not a default arg) so an empty env var — which GitHub Actions
        # sets for an undefined `vars.IMAP_HOST` — still falls back correctly.
        host = os.environ.get("IMAP_HOST") or "imap.gmail.com"
        port = int(os.environ.get("IMAP_PORT") or "993")
        mark_seen = os.environ.get("GMAIL_MARK_SEEN", "1") != "0"
        since = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")

        try:
            imap = imaplib.IMAP4_SSL(host, port)
            imap.login(user, password)
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] IMAP login to {host} failed: {type(e).__name__}: {e}")
            return []

        results: list[JobPosting] = []
        try:
            imap.select("INBOX")
            # Count-only diagnostics (no subjects/senders — Actions logs are public).
            try:
                typ, data = imap.uid("SEARCH", "UNSEEN")
                unseen_total = len(data[0].split()) if (typ == "OK" and data and data[0]) else 0
            except Exception:  # noqa: BLE001
                unseen_total = -1
            uids = self._candidate_uids(imap, since)
            print(f"[{self.name}] inbox unread: {unseen_total}; matched alert filters: {len(uids)}")
            for uid in uids[:MAX_MESSAGES]:
                msg = self._fetch_message(imap, uid)
                if msg is None:
                    continue
                html = extract_html(msg)
                subject = msg.get("Subject", "")
                posted = parse_email_date(msg)
                matched = False
                # Run every parser; in practice each email matches exactly one
                # (they key off distinctive job-link patterns). This is what
                # makes forwarded emails work regardless of the From header.
                for parser in PARSERS:
                    try:
                        jobs = parser.parse(html, subject, posted)
                    except Exception as e:  # noqa: BLE001 -- one bad email must not stop the rest
                        print(f"[{self.name}] {parser.source} parse error (uid {uid!r}): {e}")
                        continue
                    if jobs:
                        results.extend(jobs)
                        matched = True
                if matched and mark_seen:
                    try:
                        imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")
                    except Exception:  # noqa: BLE001
                        pass
            print(f"[{self.name}] extracted {len(results)} postings from alert emails")
        finally:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
        return results

    def _candidate_uids(self, imap: imaplib.IMAP4_SSL, since: str) -> list[bytes]:
        """Unread emails matching any parser, by sender OR by body signature."""
        queries: list[list[str]] = []
        for parser in PARSERS:
            for domain in parser.from_domains:
                queries.append(["UNSEEN", "SINCE", since, "FROM", domain])
            if parser.text_query:
                queries.append(["UNSEEN", "SINCE", since, "TEXT", parser.text_query])
        seen: set[bytes] = set()
        ordered: list[bytes] = []
        for q in queries:
            try:
                typ, data = imap.uid("SEARCH", *q)
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] search failed for {q}: {e}")
                continue
            if typ == "OK" and data and data[0]:
                for uid in data[0].split():
                    if uid not in seen:
                        seen.add(uid)
                        ordered.append(uid)
        return ordered

    def _fetch_message(self, imap: imaplib.IMAP4_SSL, uid: bytes):
        try:
            typ, data = imap.uid("FETCH", uid, "(RFC822)")
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] fetch failed (uid {uid!r}): {e}")
            return None
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            return None
        return email.message_from_bytes(data[0][1])

