"""Ingest job-alert emails from a dedicated Gmail inbox via IMAP.

This is the legal/reliable way to pull from sources that can't be scraped
(LinkedIn, Indeed, Wellfound, …): you subscribe to *their* email job alerts and
this adapter reads the resulting emails. It never logs into those sites, stores
their credentials, or scrapes them — only the alert emails you opted into.

Flow: connect IMAP -> for each registered parser, find UNSEEN messages from that
sender -> parse out JobPostings -> mark the message read so it isn't re-ingested.
Adding a new source is done in email_parsers.py (PARSERS); this file is generic.

Env:
  GMAIL_USER           the dedicated inbox address (e.g. you.jobalerts@gmail.com)
  GMAIL_APP_PASSWORD   a Google App Password (requires 2FA on that account)
  GMAIL_MARK_SEEN      optional; "0" to leave messages unread (default: mark read)
"""
from __future__ import annotations

import email
import imaplib
import os
from datetime import datetime, timedelta

from core.models import JobPosting
from .base import BaseAdapter
from .email_parsers import PARSERS, extract_html, parse_email_date

IMAP_HOST = "imap.gmail.com"
LOOKBACK_DAYS = 14
MAX_MESSAGES_PER_SENDER = 50  # safety cap


class GmailAlertsAdapter(BaseAdapter):
    name = "gmail_alerts"

    def fetch(self) -> list[JobPosting]:
        user = os.environ.get("GMAIL_USER")
        password = os.environ.get("GMAIL_APP_PASSWORD")
        if not (user and password):
            print(f"[{self.name}] GMAIL_USER/GMAIL_APP_PASSWORD not set. Skipping.")
            return []

        mark_seen = os.environ.get("GMAIL_MARK_SEEN", "1") != "0"
        since = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")

        try:
            imap = imaplib.IMAP4_SSL(IMAP_HOST)
            imap.login(user, password)
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] IMAP login failed: {type(e).__name__}: {e}")
            return []

        results: list[JobPosting] = []
        try:
            imap.select("INBOX")
            for parser in PARSERS:
                uids = self._search(imap, parser.from_domains, since)
                if uids:
                    print(f"[{self.name}] {parser.source}: {len(uids)} unread alert email(s)")
                for uid in uids[:MAX_MESSAGES_PER_SENDER]:
                    msg = self._fetch_message(imap, uid)
                    if msg is None:
                        continue
                    try:
                        jobs = parser.parse(
                            extract_html(msg),
                            msg.get("Subject", ""),
                            parse_email_date(msg),
                        )
                    except Exception as e:  # noqa: BLE001 -- one bad email must not stop the rest
                        print(f"[{self.name}] {parser.source} parse error (uid {uid!r}): {e}")
                        continue
                    results.extend(jobs)
                    if mark_seen:
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

    def _search(self, imap: imaplib.IMAP4_SSL, domains: list[str], since: str) -> list[bytes]:
        uids: list[bytes] = []
        for domain in domains:
            try:
                typ, data = imap.uid("SEARCH", "UNSEEN", "FROM", domain, "SINCE", since)
            except Exception as e:  # noqa: BLE001
                print(f"[{self.name}] search failed for {domain}: {e}")
                continue
            if typ == "OK" and data and data[0]:
                uids.extend(data[0].split())
        return uids

    def _fetch_message(self, imap: imaplib.IMAP4_SSL, uid: bytes):
        try:
            typ, data = imap.uid("FETCH", uid, "(RFC822)")
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] fetch failed (uid {uid!r}): {e}")
            return None
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            return None
        return email.message_from_bytes(data[0][1])
