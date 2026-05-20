"""Core utilities for the job aggregator."""
from .models import JobPosting
from .store import JobStore
from .matcher import score_job, filter_fresh
from .digest import render_digest, send_email

__all__ = ["JobPosting", "JobStore", "score_job", "filter_fresh", "render_digest", "send_email"]
