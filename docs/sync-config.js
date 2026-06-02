// Cross-device sync configuration for the dashboard.
//
// Disabled by default — the board works per-device (localStorage) until you
// fill this in. To turn on sync across your phone / tablet / laptop:
//   1. Deploy the sync worker (see /sync/README.md). You get a worker URL,
//      pick a random `space` id, and set a `token` (the worker's secret).
//   2. Replace the line below with your values, e.g.:
//
//        window.SYNC_CONFIG = {
//          endpoint: "https://job-sync.<you>.workers.dev",
//          space: "a7f3c9e1-2b4d-4f88-9c10-…",   // any unguessable string
//          token: "<the SYNC_TOKEN you set on the worker>"
//        };
//
// Then every device loading this dashboard syncs automatically — no per-device
// setup. The `|| window.SYNC_CONFIG` keeps any value injected earlier (used by
// the local test harness) intact.
window.SYNC_CONFIG = window.SYNC_CONFIG || null;
