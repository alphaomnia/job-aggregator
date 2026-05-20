"""Base class for all source adapters.

To add a new portal:
  1. Create adapters/yourportal.py
  2. Subclass BaseAdapter
  3. Implement fetch() returning a list of JobPosting
  4. Register the class in adapters/__init__.py
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import requests

from core.models import JobPosting


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class BaseAdapter(ABC):
    """Abstract base. Subclasses set `name` and implement `fetch`."""

    name: str = ""
    timeout: int = 20

    def __init__(self, search_terms: list[str] | None = None):
        # Search terms come from config.yaml (roles.strong + roles.good).
        # Adapters that support keyword search use these; others ignore them.
        self.search_terms = search_terms or []
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    @abstractmethod
    def fetch(self) -> list[JobPosting]:
        """Return current job postings from this source. Must not raise -- log and return []."""
        ...

    def _get(self, url: str, **kwargs: Any) -> requests.Response | None:
        try:
            r = self.session.get(url, timeout=self.timeout, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            print(f"[{self.name}] GET {url} failed: {e}")
            return None

    def _safe_fetch(self) -> list[JobPosting]:
        """Wrap fetch() so a broken adapter never crashes the whole run."""
        try:
            jobs = self.fetch() or []
            print(f"[{self.name}] returned {len(jobs)} postings")
            return jobs
        except Exception as e:  # noqa: BLE001
            print(f"[{self.name}] crashed: {type(e).__name__}: {e}")
            return []
