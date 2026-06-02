# Project briefing — job-aggregator

A personal, automated job-search tool for Reuven (product leadership roles, Czech Republic / EU / remote). This file is loaded by Claude Code as project context on every session. Keep it short, accurate, and useful.

## What it does

Every morning a GitHub Action runs `main.py`, which fetches postings from a list of enabled adapters, deduplicates them against `docs/jobs.json`, scores each against `config.yaml`, regenerates the dashboard HTML, commits the changes back to the repo, and emails Reuven a digest of new high-score matches via Resend.

The dashboard at https://alphaomnia.github.io/job-aggregator/ is a static HTML page that reads `docs/jobs.json` and renders an editorial-style filterable list. Status (interested/applied/dismissed) is stored in browser localStorage. No backend — everything runs on the GitHub free tier.

## Architecture

```
job-aggregator/
├── .github/workflows/daily.yml       # 2x daily cron + workflow_dispatch
├── adapters/                          # One file per source. All subclass BaseAdapter.
│   ├── base.py                        # Shared interface, _safe_fetch wrapper
│   ├── __init__.py                    # Registry: ADAPTERS dict maps name → class
│   ├── remotive.py                    # WORKING — official JSON API
│   ├── weworkremotely.py              # WORKING — RSS feeds
│   ├── workingnomads.py               # WORKING — JSON endpoint
│   ├── generic.py                     # WORKING — reads sources.yaml
│   ├── himalayas.py                   # BROKEN — 403 Cloudflare
│   ├── jobgether.py                   # BROKEN — 403 Cloudflare
│   ├── startupjobs_cz.py              # BROKEN — now React SPA
│   ├── welcometothejungle.py          # BROKEN — React SPA
│   ├── dynamitejobs.py                # BROKEN — 0 postings
│   ├── theorg.py                      # BROKEN — URLs changed, React SPA
│   ├── eustartups.py                  # BROKEN — RSS endpoint 404
│   ├── freelancermap.py               # BROKEN — RSS endpoint moved
│   └── talent_cz.py                   # BROKEN — React SPA
├── core/
│   ├── models.py                      # JobPosting dataclass (id, score, status, etc.)
│   ├── store.py                       # JSON load/save + dedup + prune
│   ├── matcher.py                     # score_job() and filter_fresh()
│   └── digest.py                      # Resend email rendering & sending
├── docs/                              # Published by GitHub Pages
│   ├── _template.html                 # Dashboard source. main.py copies to index.html each run.
│   ├── index.html                     # Regenerated daily.
│   ├── jobs.json                      # Source of truth, committed to repo.
│   ├── manifest.json                  # PWA manifest
│   ├── icon-{16,32,180,192,512}.png   # Favicon + Apple touch + PWA icons
│   ├── apple-touch-icon.png
│   ├── favicon.ico
│   └── logo.svg                       # Vector source for the three-circle logo
├── config.yaml                        # Role keywords, locations, work modes, enabled adapters
├── sources.yaml                       # User-defined sources read by generic adapter (RSS/JSONLD/JSON API)
├── main.py                            # Orchestrator
└── requirements.txt
```

## Currently enabled adapters (in `config.yaml`)

Only the four working sources are enabled. Broken adapters remain as code references but are not in `config.yaml`'s `adapters:` list. Don't re-enable them without verifying they work first.

```yaml
adapters:
  - remotive
  - weworkremotely
  - workingnomads
  - generic
```

## Conventions and patterns

- **Adapters never raise.** They wrap fetch logic so errors log but don't kill the run. See `BaseAdapter._safe_fetch`. New adapters should follow this pattern.
- **JobPosting IDs are content hashes** based on URL (falling back to title+company). See `models.py`. This makes dedup work across runs and sources.
- **The store preserves user state.** When a job already exists, the store merges incoming data but preserves `first_seen` and any user-set `status` other than "new".
- **Scoring lives in `matcher.py`.** Strong-role keywords get +30 in title / +15 in description; good-role keywords get +12 / +5; avoid-keywords get -40. Czech Republic locations get +20; EU/remote gets +8. Fresh postings (<2 days) get +8. See `config.yaml` for the keyword lists.
- **The digest threshold is in `config.yaml`** (`digest_score_threshold`). Tune up if too noisy, down if too few matches.
- **Don't add new dependencies** without a strong reason. Current deps: requests, beautifulsoup4, lxml, feedparser, PyYAML, jinja2, python-dateutil. Anything new must work on the GitHub Actions Python 3.11 runner.

## How to add a new source

Three options, in increasing order of effort:

1. **RSS / JSON-LD / JSON API site:** add an entry to `sources.yaml`. The `generic` adapter handles it. No code. See the inline docs in that file.
2. **Site needing custom parsing:** create `adapters/yourname.py` subclassing `BaseAdapter`, implement `fetch() -> list[JobPosting]`, register in `adapters/__init__.py` and `config.yaml`.
3. **Site behind authentication / Cloudflare / React SPA:** don't scrape. Use the planned `gmail_alerts` adapter (see below) and set up email alerts on the site instead.

## Open work

### Next: `gmail_alerts` adapter
The single highest-leverage thing left to build. Many of the most valuable sources (LinkedIn, Indeed, Wellfound, DailyRemote, StartupJobs.com, Welcome to the Jungle) cannot be scraped directly — they're either behind aggressive bot detection, are React SPAs, or prohibit automation in their ToS. But all of them offer **email alerts** from saved searches, which we can ingest legally and reliably.

The adapter should:
- Authenticate to a dedicated Gmail inbox via IMAP + App Password (simpler than OAuth, sufficient for a personal tool)
- Credentials stored in GitHub Secrets: `GMAIL_USER`, `GMAIL_APP_PASSWORD`
- Pull unread emails from known job-alert senders (linkedin.com, indeed.com, wellfound.com, dailyremote.com, startupjobs.com, etc.)
- Parse each email's HTML to extract job links + titles + companies + locations
- Per-sender parsing functions (each platform formats their alerts differently)
- Tag each `JobPosting` with `source` based on sender domain (e.g., "linkedin", "indeed")
- Mark processed emails as read OR use a "processed" Gmail label so we don't re-ingest
- Be robust to formatting changes — log and skip emails it can't parse, don't crash

### Smaller TODOs
- Maybe later: a `feedback.yaml` file for the user to manually mark "good" companies to boost scoring, or "bad" companies to suppress.
- Possibly: an "interested" CSV export so applied/interested jobs can be tracked in an external tracker.

## Important non-obvious facts

- **Workflow runs twice daily** (06:00 + 14:00 UTC) as resilience against GitHub Actions cron unreliability. Both runs are dedup-aware so this just creates two chances per day rather than duplicate emails.
- **The action commits back to the repo** with the github-actions[bot] identity. The `permissions: contents: write` setting must remain in the workflow file, and Settings → Actions → General → Workflow permissions must stay on "Read and write" or commits will fail.
- **`docs/index.html` is regenerated from `docs/_template.html`** on every run by `main.py`. Edits to `index.html` directly will be overwritten — always edit the template.
- **The dashboard uses Google Fonts** (Fraunces, Inter, JetBrains Mono). They're loaded via CDN — first paint is slightly slow, especially on mobile. Acceptable trade-off for the editorial aesthetic.
- **Resend free tier without verified domain** can only send to the email address that owns the Resend account. The `EMAIL_FROM` is `onboarding@resend.dev`, which is Resend's sandbox sender.
