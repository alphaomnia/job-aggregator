---
name: run-job-aggregator
description: Build, run, and screenshot the job-aggregator — its daily Python pipeline (main.py) and its static dashboard (docs/index.html). Use when asked to run, start, launch, build, test, smoke-test, or screenshot the job aggregator or its dashboard, or to verify the dismiss/learning, freshness, or filtering behaviour of the board.
---

# Run: job-aggregator

Two surfaces share this repo root:

1. **The pipeline** — `main.py`, a daily CLI orchestrator. It runs each enabled
   adapter, dedups/scores postings into `docs/jobs.json`, regenerates
   `docs/index.html` from `docs/_template.html`, and emails a digest. Driven
   with plain `python main.py`.
2. **The dashboard** — `docs/index.html`, a static, no-backend web app that
   fetches `docs/jobs.json` and renders a filterable editorial list. Status and
   the "learn from what you dismiss" logic run client-side in localStorage.
   Driven headless with Playwright via **`.claude/skills/run-job-aggregator/driver.mjs`**.

> Paths below are relative to the repo root (the `<unit>`). The driver lives at
> `.claude/skills/run-job-aggregator/driver.mjs`.

## Prerequisites

Python 3.11 and Node are already present. Install the Python deps in a venv:

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
```

The dashboard driver uses Playwright (installed globally) plus the **pre-installed**
Chromium build at `/opt/pw-browsers` — do **not** run `playwright install`, the
download is network-blocked here (see Gotchas):

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
```

## Run the pipeline (CLI)

```bash
. .venv/bin/activate
python main.py
```

Expected here: every networked adapter logs `403`/`returned 0 postings` (the
sandbox blocks outbound scraping), then it re-scores the existing jobs, prints
`Saved N jobs to .../docs/jobs.json`, `Dashboard regenerated`, and
`[digest] Email env vars not set ... Skipping send.`, ending `Done.` (exit 0).
It never raises on adapter failure — `BaseAdapter._safe_fetch` swallows errors.

Note: this rewrites `docs/jobs.json` and `docs/index.html`. If you only meant to
test, restore them with `git checkout docs/jobs.json docs/index.html` afterward.

## Run the dashboard (agent path) — driver.mjs

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
node .claude/skills/run-job-aggregator/driver.mjs          # screenshot + learn smoke (default)
node .claude/skills/run-job-aggregator/driver.mjs shot     # just screenshot the board
node .claude/skills/run-job-aggregator/driver.mjs learn    # dismiss a role, prove similar ones hide
node .claude/skills/run-job-aggregator/driver.mjs sync     # two-device cross-device sync smoke test
```

The `sync` command stands up a local mock of the Cloudflare Worker contract
(`sync/worker.js`), drives two independent browser contexts (= two devices)
pointed at the same sync `space`, and asserts a dismissal on device A reaches
device B and an "interested" on B reaches A after refresh. Verified output:

```
A dismissed "Head of Product" -> pushed to endpoint. ✓
B pulled A's dismissal on load. ✓
A pulled B's "interested" after refresh. ✓
SMOKE OK: two devices converged through the sync endpoint.
```

The driver serves `docs/` on an ephemeral port, loads it in headless Chromium,
and writes PNGs to `.claude/skills/run-job-aggregator/screenshots/`
(`dashboard.png`, `after-dismiss.png`). The `learn` flow is also a smoke test:
it finds a non-generic title keyword shared by ≥2 roles, dismisses **one** role
that has it, and asserts the others get hidden. Verified output:

```
Dashboard loaded: 157 roles rendered.
Keyword "developer" appears in 32 roles. Dismissing one: "Senior Backend Rust Developer".
Visible roles: 157 -> 124
Learn bar: VISIBLE
Stats now: 124 shown of 157 on the board · 33 hidden by learning · updated 2 Jun, 21:52
SMOKE OK: learning hid similar roles after one dismissal.
```

Exit code is non-zero if the dismiss→hide behaviour breaks, so it doubles as a
regression check for the learning feature.

## Run the dashboard (human path)

```bash
python3 -m http.server 8765 -d docs
# then open http://127.0.0.1:8765/  (useless headless — use the driver instead)
```

## Gotchas

- **Don't `playwright install`.** The browser download is blocked
  (`Failed to download Chromium ... Download failure`). The build is already on
  disk at `/opt/pw-browsers`; just `export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`.
- **`file://` won't work** for the dashboard — `index.html` does
  `fetch('jobs.json')`, which Chromium blocks cross-origin from `file://`. You
  must serve over http (the driver does this for you).
- **Every networked adapter 403s in the sandbox** (freelancermap, dynamitejobs,
  startupjobs_cz, welcometothejungle, theorg, eustartups, talent_cz, plus the
  Cloudflare-gated ones). That's the network policy, not a code bug — the
  pipeline still completes and regenerates the dashboard from existing data.
- **`generic` adapter logs `sources.yaml not found`** and returns 0. That file
  isn't in the repo despite being referenced in `config.yaml`/`CLAUDE.md`; the
  adapter skips it cleanly.
- **The pipeline mutates committed files.** `python main.py` rewrites
  `docs/jobs.json` (re-score/re-sort) and `docs/index.html`. `git checkout` them
  if the run was just a test.
- **Learning ignores generic role words.** Dismissing "Head of Product" hides
  nothing, because `product`/`head`/`manager`/`director`/etc. are excluded from
  learned keywords by design. Use a role with a distinctive token (engineer,
  developer, marketing…) to see suppression — the driver picks one automatically.
- **No email is sent** unless `RESEND_API_KEY`/`EMAIL_FROM`/`EMAIL_TO` are set;
  it logs `Would have sent: ...` and continues.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Cannot find package 'playwright'` | The driver resolves it from `npm root -g`; ensure Node global modules are intact (`npm ls -g playwright`). |
| `browserType.launch: Executable doesn't exist` | `export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers` before running the driver. |
| Driver hangs at `waitForSelector('.job')` | `docs/jobs.json` is empty/invalid — run `python main.py` first, or `git checkout docs/jobs.json`. |
| `pip install` SSL/network errors | Deps are small and pure-Python; retry, the venv only needs requirements.txt. |
