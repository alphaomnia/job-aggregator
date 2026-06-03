// Cross-device sync configuration for the dashboard.
//
// Live: synced across devices through the Cloudflare Worker in /sync.
// The `window.SYNC_CONFIG ||` prefix lets the local test harness inject its own
// endpoint without being overridden.
//
// Note: the token is served to the browser (unavoidable on a static site). It
// only guards this one namespace of status flags — keep the dashboard URL
// private. To rotate it: `npx wrangler secret put SYNC_TOKEN` then update here.
window.SYNC_CONFIG = window.SYNC_CONFIG || {
  endpoint: "https://job-sync.jobagg.workers.dev",
  space: "6994e08d-f532-41a1-98f8-143f7af7cc4a",
  token: "kwV8iWMJC9URwKeiH5DK2nk80B_ws07WLfTk4yNUdoU"
};
