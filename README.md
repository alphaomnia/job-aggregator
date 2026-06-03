# Job Aggregator

A personal job-search aggregator that runs daily on GitHub Actions, pulls roles from multiple portals, deduplicates them, scores them against your search criteria, and emails you a digest with a link to a filterable dashboard hosted on GitHub Pages.

## What it does

Every day at 06:00 UTC (07:00 Prague in winter, 08:00 in summer):

1. **Fetches** new postings from each configured adapter (Remotive, We Work Remotely, Working Nomads, Himalayas, Jobgether, freelancermap, Dynamite Jobs, StartupJobs CZ).
2. **Deduplicates** against `docs/jobs.json` using URL + (title, company) hash.
3. **Scores** each role against your `config.yaml` (role keywords, location, remote type, seniority).
4. **Writes** the merged dataset to `docs/jobs.json` and regenerates `docs/index.html` (in the runner — not committed to `main`).
5. **Persists** the dataset to the `data` branch (a single force-pushed commit) and **deploys** the dashboard to GitHub Pages via Actions.
6. **Emails** you a digest of the new high-score matches with a link to the dashboard.

## Setup (one-time, ~15 minutes)

### 1. Create the repo

```bash
gh repo create job-aggregator --private --source=. --remote=origin --push
```

### 2. Enable GitHub Pages

Settings → Pages → Source: **"GitHub Actions"** → Save.

The daily workflow builds the dashboard in the runner and deploys it straight to
Pages — nothing is committed to `main`. The store (`jobs.json`) is persisted on a
dedicated `data` branch as a single, force-pushed commit, so `main`'s history
never grows. After the first action run, your dashboard will be at
`https://<your-username>.github.io/job-aggregator/`.

> **Cutover (one time):** flip the Pages source to "GitHub Actions", then run the
> workflow once manually (Actions → "Daily Job Aggregator" → Run workflow). Pages
> keeps serving the previous version until the first Actions deploy succeeds, so
> there's no downtime.

### 3. Get a Resend API key (for the email digest)

Sign up at [resend.com](https://resend.com). Free tier covers 3,000 emails/month — overkill for daily digests. Verify a sending domain (or use their onboarding sandbox for the first few days). Copy the API key.

### 4. Add secrets to the repo

Settings → Secrets and variables → Actions → New repository secret. Add:

- `RESEND_API_KEY` — from step 3
- `EMAIL_FROM` — e.g. `jobs@yourdomain.com` (must be on a verified Resend domain)
- `EMAIL_TO` — your inbox

### 5. Edit `config.yaml`

Adjust your search terms, target locations, seniority, and remote preference. Defaults are pre-tuned for your profile (product leadership, Czech Republic priority, EU remote).

### 6. Trigger the first run manually

Actions tab → "Daily Job Aggregator" → "Run workflow". After ~2 minutes, check your inbox and your Pages URL.

## Project layout

```
job-aggregator/
├── .github/workflows/daily.yml   # The cron job
├── adapters/                     # One file per source portal
│   ├── base.py                   # Shared adapter interface
│   ├── remotive.py               # Uses official Remotive JSON API
│   ├── weworkremotely.py         # RSS feed parser
│   ├── workingnomads.py          # JSON endpoint
│   ├── himalayas.py              # JSON endpoint
│   ├── jobgether.py              # HTML scrape (most fragile)
│   ├── freelancermap.py          # RSS feed parser
│   ├── dynamitejobs.py           # HTML scrape
│   └── startupjobs_cz.py         # HTML scrape (Czech roles)
├── core/
│   ├── models.py                 # JobPosting dataclass
│   ├── store.py                  # JSON read/write + dedup
│   ├── matcher.py                # Scoring against config
│   └── digest.py                 # Email rendering & sending
├── docs/                         # Published by GitHub Pages
│   ├── index.html                # The dashboard (regenerated daily)
│   └── jobs.json                 # Source of truth (committed)
├── config.yaml                   # Your search preferences
├── main.py                       # Orchestrator
└── requirements.txt
```

## Adding a new portal

1. Create `adapters/yourportal.py` subclassing `BaseAdapter`.
2. Implement `fetch() -> list[JobPosting]`.
3. Register it in `adapters/__init__.py`.

That's it. The orchestrator picks it up automatically.

## Sources NOT covered (and why)

- **LinkedIn** — terms of service prohibit automated access; aggressive anti-scraping. Set up LinkedIn job alert emails and forward them to a dedicated Gmail address; a future adapter can ingest those.
- **Indeed / cz.indeed.com** — public API was deprecated. Same workaround: subscribe to their alert emails.
- **Toptal, Go Fractional, Fractional Jobs** — require authenticated sessions. Treat as bookmarks in the dashboard's "Manual sources" section rather than scrape targets.

## Filtering on the dashboard

The dashboard runs entirely client-side (no server). You can filter by:

- Role match score
- Source portal
- Location (country / remote / hybrid / on-site)
- Posted within last N days
- Status (new / seen / interested / applied / dismissed)

Status changes are saved to your browser's localStorage — they survive page reloads but are per-device.

## Costs

- GitHub Actions: free (well under the 2,000 minutes/month limit on a free account; this runs ~3 min/day = ~90 min/month)
- GitHub Pages: free
- Resend: free up to 3,000 emails/month
- **Total: $0/month**
