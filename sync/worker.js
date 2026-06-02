// Cloudflare Worker: cross-device state sync for the job-aggregator dashboard.
//
// Stores one small JSON document per `space` in Workers KV and merges updates
// per-role by newest timestamp (last-write-wins). The dashboard calls:
//   GET  /?space=<id>            -> { states: {jobId:{status,ts}}, updated }
//   PUT  /?space=<id>  {states}  -> merges, stores, returns the merged doc
//
// Bindings required (see sync/README.md):
//   - KV namespace bound as STATE
//   - Secret SYNC_TOKEN (optional but recommended): clients must send
//     Authorization: Bearer <SYNC_TOKEN>
//
// Deploy: `cd sync && npx wrangler deploy` (after wrangler.toml is set up).

function cors(extra = {}) {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,PUT,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Max-Age': '86400',
    ...extra,
  };
}
function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: cors({ 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }),
  });
}

// Per-role last-write-wins.
function mergeStates(a = {}, b = {}) {
  const out = { ...a };
  for (const [id, r] of Object.entries(b)) {
    if (!out[id] || (r.ts || 0) > (out[id].ts || 0)) out[id] = { status: r.status || '', ts: r.ts || 0 };
  }
  return out;
}

export default {
  async fetch(request, env) {
    if (request.method === 'OPTIONS') return new Response(null, { headers: cors() });

    const url = new URL(request.url);
    const space = url.searchParams.get('space');
    if (!space) return json({ error: 'missing space' }, 400);

    if (env.SYNC_TOKEN) {
      const auth = request.headers.get('Authorization') || '';
      if (auth !== `Bearer ${env.SYNC_TOKEN}`) return json({ error: 'unauthorized' }, 401);
    }

    const key = `space:${space}`;

    if (request.method === 'GET') {
      const raw = await env.STATE.get(key);
      return json(raw ? JSON.parse(raw) : { states: {}, updated: 0 });
    }

    if (request.method === 'PUT' || request.method === 'POST') {
      const body = await request.json().catch(() => null);
      if (!body || typeof body !== 'object') return json({ error: 'bad body' }, 400);
      const cur = JSON.parse((await env.STATE.get(key)) || '{"states":{}}');
      const merged = mergeStates(cur.states || {}, body.states || {});
      const doc = { states: merged, updated: Date.now() };
      await env.STATE.put(key, JSON.stringify(doc));
      return json(doc);
    }

    return json({ error: 'method not allowed' }, 405);
  },
};
