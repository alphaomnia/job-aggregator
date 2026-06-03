#!/usr/bin/env node
// Driver for the job-aggregator dashboard (docs/index.html).
//
// The dashboard is a static, no-backend web app: index.html fetches jobs.json
// and renders a filterable list. Status (interested/applied/dismissed) lives in
// localStorage, and the board "learns" from dismissals client-side. This driver
// serves docs/ over http, drives it with Playwright (headless Chromium), takes
// screenshots, and exercises the dismiss -> learn-and-hide flow as a smoke test.
//
// Usage:
//   node driver.mjs shot  [out.png]   # screenshot the dashboard as loaded
//   node driver.mjs learn [out.png]   # dismiss a role, prove similar ones hide
//   node driver.mjs                   # both (default)
//
// Env it relies on (the SKILL.md exports these):
//   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers   # pre-installed browser build
//   (playwright is resolved from the global npm root)

import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const gRoot = execSync('npm root -g').toString().trim();
const { chromium } = require(path.join(gRoot, 'playwright'));

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const UNIT = path.resolve(__dirname, '../../..');          // repo root
const DOCS = path.join(UNIT, 'docs');
const OUTDIR = path.join(__dirname, 'screenshots');

const MIME = {
  '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript',
  '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.ico': 'image/x-icon', '.webmanifest': 'application/manifest+json',
};

// Same exclusions the dashboard uses, so we pick a token that will actually be
// learned (generic seniority/structure words are never learned).
const STOP = new Set('the a an and or of for to in at on by with as is are be we our your you new remote hybrid onsite full part time fulltime parttime contract contractor freelance freelancer fractional interim permanent temporary job jobs role roles position positions opening openings hiring team teams'.split(/\s+/));
const GENERIC = new Set('product manager managers management senior junior mid lead leader leadership director directors head vp president chief officer principal staff executive specialist coordinator associate analyst owner'.split(/\s+/));
const tok = (t) => (t || '').toLowerCase().split(/[^a-z0-9+#]+/).filter(w => w.length >= 3 && !STOP.has(w) && !GENERIC.has(w));

function serveDocs() {
  const server = http.createServer(async (req, res) => {
    let p = decodeURIComponent(req.url.split('?')[0]);
    if (p === '/') p = '/index.html';
    try {
      const buf = await readFile(path.join(DOCS, p));
      res.writeHead(200, { 'Content-Type': MIME[path.extname(p)] || 'application/octet-stream' });
      res.end(buf);
    } catch {
      res.writeHead(404); res.end('not found');
    }
  });
  return new Promise((resolve) => server.listen(0, () => resolve(server)));
}

async function main() {
  const cmd = process.argv[2] || 'all';
  const outArg = process.argv[3];
  await import('node:fs').then(m => m.promises.mkdir(OUTDIR, { recursive: true }));

  if (cmd === 'sync') { await runSync(); return; }

  const server = await serveDocs();
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });
  let failed = false;
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.job', { timeout: 15000 });
    const total = await page.locator('.job').count();
    console.log(`Dashboard loaded: ${total} roles rendered.`);
    console.log('Stats:', (await page.locator('#stats').innerText()).trim());

    if (cmd === 'shot' || cmd === 'all') {
      const out = path.resolve(cmd === 'shot' && outArg ? outArg : path.join(OUTDIR, 'dashboard.png'));
      await page.screenshot({ path: out, fullPage: false });
      console.log('Screenshot:', out);
    }

    if (cmd === 'learn' || cmd === 'all') {
      // Pick a non-generic title keyword shared by >=2 roles, dismiss ONE role
      // that has it, and prove the others get hidden by the learning logic.
      const titles = await page.$$eval('.job', els => els.map(e => ({
        id: e.getAttribute('data-id'),
        title: e.querySelector('h2 a')?.textContent || '',
      })));
      const freq = {};
      for (const { title } of titles) for (const w of new Set(tok(title))) freq[w] = (freq[w] || 0) + 1;
      const shared = Object.entries(freq).filter(([, c]) => c >= 2).sort((a, b) => b[1] - a[1])[0];
      if (!shared) { console.log('No shared learnable keyword in current data; skipping learn flow.'); }
      else {
        const [kw, count] = shared;
        const target = titles.find(t => new Set(tok(t.title)).has(kw));
        console.log(`Keyword "${kw}" appears in ${count} roles. Dismissing one: "${target.title}".`);
        const beforeShown = await page.locator('.job').count();
        await page.click(`.job[data-id="${target.id}"] .action-btn.dismissed`);
        await page.waitForTimeout(300);
        const afterShown = await page.locator('.job').count();
        const barHidden = await page.locator('#learnBar').getAttribute('hidden');
        const stats = (await page.locator('#stats').innerText()).trim();
        console.log(`Visible roles: ${beforeShown} -> ${afterShown}`);
        console.log('Learn bar:', barHidden === null ? 'VISIBLE' : 'hidden');
        console.log('Stats now:', stats);
        const out = path.resolve(cmd === 'learn' && outArg ? outArg : path.join(OUTDIR, 'after-dismiss.png'));
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: out, fullPage: false });
        console.log('Screenshot:', out);
        if (!(afterShown < beforeShown && barHidden === null && /hidden by learning/.test(stats))) {
          console.error('SMOKE FAIL: dismissing a role did not hide similar roles.');
          failed = true;
        } else {
          console.log('SMOKE OK: learning hid similar roles after one dismissal.');
        }
      }
    }
  } catch (e) {
    console.error('DRIVER ERROR:', e.message);
    failed = true;
  } finally {
    await browser.close();
    server.close();
  }
  process.exit(failed ? 1 : 0);
}

// --- Cross-device sync smoke test -------------------------------------------
// Stands up a local mock of the Worker contract (sync/worker.js) and drives two
// independent browser contexts (= two devices) to prove a status change on one
// propagates to the other through the endpoint.

async function waitFor(fn, timeout = 6000, every = 100) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await fn()) return true;
    await new Promise(r => setTimeout(r, every));
  }
  throw new Error('waitFor timed out');
}

function startMock() {
  const store = new Map(); // space -> { states, updated }
  const merge = (a = {}, b = {}) => {
    const o = { ...a };
    for (const [id, r] of Object.entries(b)) {
      if (!o[id] || (r.ts || 0) > (o[id].ts || 0)) o[id] = { status: r.status || '', ts: r.ts || 0 };
    }
    return o;
  };
  const CORS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,PUT,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
  };
  const send = (res, code, body) => { res.writeHead(code, { ...CORS, 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
  const server = http.createServer((req, res) => {
    if (req.method === 'OPTIONS') { res.writeHead(204, CORS); return res.end(); }
    const space = new URL(req.url, 'http://x').searchParams.get('space');
    if (!space) return send(res, 400, { error: 'missing space' });
    const key = `space:${space}`;
    if (req.method === 'GET') return send(res, 200, store.get(key) || { states: {}, updated: 0 });
    let raw = '';
    req.on('data', c => (raw += c));
    req.on('end', () => {
      let body; try { body = JSON.parse(raw); } catch { return send(res, 400, { error: 'bad body' }); }
      const cur = store.get(key) || { states: {} };
      const doc = { states: merge(cur.states, body.states || {}), updated: Date.now() };
      store.set(key, doc);
      send(res, 200, doc);
    });
  });
  return new Promise(resolve => server.listen(0, () => resolve({
    server, port: server.address().port,
    get: (space) => store.get(`space:${space}`),
  })));
}

async function runSync() {
  const docsServer = await serveDocs();
  const base = `http://127.0.0.1:${docsServer.address().port}/`;
  const mock = await startMock();
  const SPACE = 'driver-test';
  const cfg = { endpoint: `http://127.0.0.1:${mock.port}`, space: SPACE, token: 'testtoken' };
  const inject = `window.SYNC_CONFIG = ${JSON.stringify(cfg)};`;
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] });
  let failed = false;
  try {
    const lsStatus = (id) => { try { return JSON.parse(localStorage.getItem('roles_user_states_v1') || '{}')[id]; } catch { return undefined; } };

    // Device A
    const ctxA = await browser.newContext({ viewport: { width: 1280, height: 1200 } });
    await ctxA.addInitScript(inject);
    const A = await ctxA.newPage();
    await A.goto(base, { waitUntil: 'domcontentloaded' });
    await A.waitForSelector('.job');
    const targetId = await A.$eval('.job', e => e.getAttribute('data-id'));
    const targetTitle = await A.$eval('.job h2 a', e => e.textContent);
    await A.click(`.job[data-id="${targetId}"] .action-btn.dismissed`);
    await waitFor(() => { const d = mock.get(SPACE); return !!(d && d.states[targetId] && d.states[targetId].status === 'dismissed'); });
    console.log(`A dismissed "${targetTitle}" -> pushed to endpoint. ✓`);

    // Device B (separate context = separate localStorage = another device)
    const ctxB = await browser.newContext({ viewport: { width: 1280, height: 1200 } });
    await ctxB.addInitScript(inject);
    const B = await ctxB.newPage();
    await B.goto(base, { waitUntil: 'domcontentloaded' });
    await B.waitForSelector('.job');
    await waitFor(async () => (await B.evaluate(lsStatus, targetId)) === 'dismissed');
    console.log('B pulled A\'s dismissal on load. ✓');
    await B.evaluate(() => window.scrollTo(0, 0));
    await B.screenshot({ path: path.join(OUTDIR, 'sync-device-b.png') });

    // Reverse direction: B marks another role interested, A picks it up on refresh.
    const targetId2 = await B.$$eval('.job', els => (els.find(e => !e.classList.contains('suppressed')) || els[0]).getAttribute('data-id'));
    await B.click(`.job[data-id="${targetId2}"] .action-btn.interested`);
    await waitFor(() => { const d = mock.get(SPACE); return !!(d && d.states[targetId2] && d.states[targetId2].status === 'interested'); });
    await A.reload({ waitUntil: 'domcontentloaded' });
    await A.waitForSelector('.job');
    await waitFor(async () => (await A.evaluate(lsStatus, targetId2)) === 'interested');
    console.log('A pulled B\'s "interested" after refresh. ✓');
    console.log('SMOKE OK: two devices converged through the sync endpoint.');
  } catch (e) {
    console.error('SYNC SMOKE FAIL:', e.message);
    failed = true;
  } finally {
    await browser.close();
    docsServer.close();
    mock.server.close();
  }
  process.exit(failed ? 1 : 0);
}

main();
