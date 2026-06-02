"""Main orchestrator. Run daily via GitHub Actions.

Pipeline:
  1. Load config.yaml
  2. Load existing jobs from docs/jobs.json
  3. For each enabled adapter, fetch fresh postings
  4. Merge into store (dedup, preserve user-set status)
  5. Score every job, prune very old, save back to docs/jobs.json
  6. Regenerate docs/index.html
  7. Send digest email of newly-arrived high-score jobs
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

from adapters import ADAPTERS
from core import JobStore, render_digest, score_job, send_email
from core.matcher import filter_fresh

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "docs" / "jobs.json"
DASHBOARD_TEMPLATE = ROOT / "docs" / "_template.html"
DASHBOARD_OUTPUT = ROOT / "docs" / "index.html"


def main() -> int:
    print("=" * 60)
    print("Job aggregator run")
    print("=" * 60)

    # 1. Load config (+ optional feedback.yaml for server-side suppression)
    config_path = ROOT / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    feedback_path = ROOT / "feedback.yaml"
    if feedback_path.exists():
        with feedback_path.open("r", encoding="utf-8") as f:
            config["feedback"] = yaml.safe_load(f) or {}

    enabled = config.get("adapters", [])
    print(f"Enabled adapters: {enabled}")

    # Search terms passed to adapters that support keyword search.
    search_terms = (config.get("roles", {}).get("strong", [])
                    + config.get("roles", {}).get("good", []))

    # 2. Load existing store
    store = JobStore(DATA_PATH)
    print(f"Loaded {len(store.all())} existing jobs from {DATA_PATH}")

    # 3. Run all adapters concurrently (they're network-bound and never raise).
    known = [(name, ADAPTERS[name]) for name in enabled if name in ADAPTERS]
    for name in enabled:
        if name not in ADAPTERS:
            print(f"[main] Unknown adapter '{name}' — skipping")

    def run_adapter(item: tuple[str, type]) -> tuple[str, list]:
        name, cls = item
        return name, cls(search_terms=search_terms)._safe_fetch()

    incoming = []
    sources_used: list[str] = []
    per_source: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=max(1, len(known))) as pool:
        for name, jobs in pool.map(run_adapter, known):
            per_source[name] = len(jobs)
            if jobs:
                incoming.extend(jobs)
                sources_used.append(name)

    # Surface silent failures: an enabled source that returned nothing.
    dead = [n for n, c in per_source.items() if c == 0]
    if dead:
        print(f"[main] WARNING: enabled sources returned 0 postings: {', '.join(dead)}")

    print(f"Fetched {len(incoming)} total raw postings")

    # 4. Merge - this returns only the jobs that were not in the store before
    new_jobs = store.merge(incoming)
    print(f"{len(new_jobs)} are genuinely new since last run")

    # 5. Score everything (new and existing) and filter fresh window
    for job in store.all():
        job.score = score_job(job, config)

    # Drop very stale postings (>60 days unless interested/applied)
    pruned = store.prune(max_age_days=60)
    if pruned:
        print(f"Pruned {pruned} stale postings")

    store.save(meta={"sources": {
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "counts": per_source,
    }})
    print(f"Saved {len(store.all())} jobs to {DATA_PATH}")

    # 6. Regenerate dashboard
    if DASHBOARD_TEMPLATE.exists():
        DASHBOARD_OUTPUT.write_text(
            DASHBOARD_TEMPLATE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        print(f"Dashboard regenerated: {DASHBOARD_OUTPUT}")
    else:
        print(f"[warn] Template missing: {DASHBOARD_TEMPLATE}")

    # 7. Email digest - only new jobs above threshold, ranked
    threshold = config.get("digest_score_threshold", 15)
    max_jobs = config.get("digest_max_jobs", 20)
    # Jobs were already scored above (step 5); reuse job.score, don't re-score.
    new_above_threshold = sorted(
        [j for j in new_jobs if j.score >= threshold],
        key=lambda j: j.score,
        reverse=True,
    )[:max_jobs]

    # Restrict to fresh postings
    new_above_threshold = filter_fresh(new_above_threshold, config)

    # Where's the dashboard hosted? Configured via env so we can change it
    # without touching code. GitHub Actions sets DASHBOARD_URL from the
    # repository's Pages URL.
    dashboard_url = os.environ.get("DASHBOARD_URL", "https://example.github.io/job-aggregator/")

    subject, html = render_digest(
        new_jobs=new_above_threshold,
        total_count=len(store.all()),
        dashboard_url=dashboard_url,
        sources=sources_used,
    )
    send_email(subject, html)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
