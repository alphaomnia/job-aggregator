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

main();
