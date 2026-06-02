# Cross-device sync

Keeps your dashboard status (interested / applied / dismissed — and therefore
the dismiss-learning) in sync across phone, tablet and laptop. It's a tiny
Cloudflare Worker backed by Workers KV; the dashboard reads/writes one small
JSON document per "space" and merges per-role by newest change (last-write-wins).

Everything is **off until you configure it** — the board falls back to
per-device localStorage, exactly as before.

## Why a Worker

A static GitHub Pages site has no backend, so cross-device state needs a shared
store. A Worker keeps the secret server-side (nothing sensitive in the page),
costs nothing on the free tier, and requires **zero per-device setup** — once
deployed and configured, every device just works.

## One-time setup (~5 minutes)

You need a free Cloudflare account and `npx` (bundled with Node).

```bash
cd sync

# 1. Authenticate
npx wrangler login

# 2. Create the KV namespace, then paste the printed id into wrangler.toml
npx wrangler kv namespace create STATE

# 3. Set a shared secret (any long random string). Clients send it as a token.
npx wrangler secret put SYNC_TOKEN

# 4. Deploy. Note the printed https://job-sync.<you>.workers.dev URL.
npx wrangler deploy
```

## Turn it on in the dashboard

Edit `docs/sync-config.js` and set your values:

```js
window.SYNC_CONFIG = {
  endpoint: "https://job-sync.<you>.workers.dev",
  space: "pick-any-long-random-string",   // your private namespace
  token: "<the SYNC_TOKEN you set above>"
};
```

Commit it. On the next Pages deploy, all devices sync automatically.

> The `token` lives in the page, so treat the URL as private (don't share it).
> It only guards this one namespace of dismiss/interested/applied flags. If you
> want stricter access, restrict the Worker by `Origin` or rotate `SYNC_TOKEN`.

## Try it without deploying

The driver runs the exact GET/PUT/merge contract against a local mock and proves
two "devices" converge:

```bash
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
node ../.claude/skills/run-job-aggregator/driver.mjs sync
```

## Contract

```
GET  /?space=<id>                         -> { states: { [jobId]: {status, ts} }, updated }
PUT  /?space=<id>   body { states: {...} } -> merges (newest ts per role wins), returns merged doc
Authorization: Bearer <SYNC_TOKEN>         (required when the secret is set)
```
