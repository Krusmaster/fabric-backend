// n189: builds the generated App package with Vite against the fake connector and checks it in Chromium: screenshots
// at 1280 x 720 and 375 x 812 (light and dark), axe-core (WCAG 2.1 A and AA), overflow, keyboard, network, and what the
// filters, the sort, the search and the pager pass to the queries. Prints one JSON line.
//   node shoot.mjs <project root> <screenshot dir> [chromium executable]
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { copyFileSync, mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { extname, join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const [root, shots, executable] = process.argv.slice(2).map((a, i) => (i < 2 ? resolve(a) : a));
mkdirSync(shots, { recursive: true });

// the harness goes into the project (beside the fake-data.json the test wrote there), so it resolves react from it
mkdirSync(join(root, 'kg-render'), { recursive: true });
for (const f of ['main.tsx', 'fake-connectors.js']) copyFileSync(join(here, f), join(root, 'kg-render', f));
const { build } = await import('vite');
writeFileSync(join(root, 'index.html'), '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Rayfin App check</title></head><body style="margin:0"><div id="root"></div><script type="module" src="/kg-render/main.tsx"></script></body></html>');
await build({
  root, logLevel: 'error', configFile: false, publicDir: false,
  resolve: {
    alias: [
      { find: /^.*\/lib\/app-connectors(\.ts)?$/, replacement: join(root, 'kg-render', 'fake-connectors.js') },
      { find: '@app', replacement: join(root, 'src') },
    ],
  },
  esbuild: { jsx: 'automatic' },
  build: { outDir: join(root, 'dist'), emptyOutDir: true, target: 'es2022', minify: false },
});

const dist = join(root, 'dist');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const server = createServer((req, res) => {
  const p = join(dist, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  const file = existsSync(p) && !p.endsWith('/') ? p : join(dist, 'index.html');
  res.writeHead(200, { 'content-type': types[extname(file)] ?? 'application/octet-stream' });
  res.end(readFileSync(file));
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const base = `http://127.0.0.1:${server.address().port}`;

const { chromium } = require('playwright');
const browser = await chromium.launch(executable ? { executablePath: executable } : {});
const axe = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const out = { shots: [], axe: {}, overflow: {}, errors: [], external: [], mutations: [], checks: {} };

async function open(viewport, theme) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => out.errors.push(String(e)));
  page.on('console', (m) => m.type() === 'error' && out.errors.push(m.text()));
  page.on('request', (r) => !r.url().startsWith(base) && !r.url().startsWith('data:') && out.external.push(r.url()));
  await page.goto(`${base}/?theme=${theme}`);
  await page.waitForSelector('.kg-app');
  await settle(page);
  return { ctx, page };
}

async function settle(page) {
  await page.waitForFunction(() => !document.querySelector('.kg-loading'));
  await page.waitForTimeout(150);
}

async function check(page, name) {
  await page.addScriptTag({ content: axe });
  const r = await page.evaluate(async () => {
    const res = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } });
    return res.violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(' ') + ' ' + (n.failureSummary || '').slice(0, 200)) }));
  });
  out.axe[name] = r;
  out.overflow[name] = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
}

async function shoot(page, name) {
  const path = join(shots, `${name}.png`);
  await page.screenshot({ path, fullPage: true });
  out.shots.push(path);
}

const queries = (page) => page.evaluate(() => window.__kgQueries.splice(0));
const sizes = { desktop: { width: 1280, height: 720 }, phone: { width: 375, height: 812 } };
const tabs = async (page) => page.$$eval('.kg-nav button', (b) => b.map((x) => x.textContent.trim()));

for (const [size, viewport] of Object.entries(sizes)) {
  for (const theme of ['light', 'dark']) {
    const { ctx, page } = await open(viewport, theme);
    out.checks.tabs = await tabs(page);
    out.checks.title = await page.textContent('.kg-header h1');
    out.checks.refreshed = await page.textContent('.kg-header .kg-meta');
    out.checks.accent = await page.$eval('.kg-app', (e) => e.getAttribute('data-accent'));
    out.checks.cards = await page.$$eval('.kg-kpi', (c) => c.map((x) => ({ label: x.querySelector('.kg-kpi-label').textContent, value: x.querySelector('.kg-kpi-value').textContent, unit: x.querySelector('.kg-kpi-unit').textContent })));
    out.checks.charts = await page.$$eval('.kg-chart', (c) => c.map((x) => ({ title: x.querySelector('figcaption').textContent, kind: x.querySelector('.kg-line') ? 'line' : x.querySelector('.kg-bars') ? 'bar' : x.querySelector('table.kg-table') ? 'table' : 'empty' })));
    out.checks.filters = await page.$$eval('.kg-filters .kg-field > span', (c) => c.map((x) => x.textContent));
    await check(page, `overview-${size}-${theme}`);
    await shoot(page, `overview-${size}-${theme}`);
    if (out.checks.tabs.length > 1) {
      await page.click('.kg-nav button >> nth=1');
      await settle(page);
      await check(page, `list-${size}-${theme}`);
      await shoot(page, `list-${size}-${theme}`);
    }
    out.mutations.push(...(await page.evaluate(() => window.__kgMutations || [])));
    await ctx.close();
  }
}

// What the controls pass to the queries (desktop, light)
{
  const { ctx, page } = await open(sizes.desktop, 'light');
  const before = await queries(page);
  out.checks.before = before;
  const multi = await page.$('.kg-multi');
  if (multi) {
    await page.click('.kg-multi >> nth=0 >> summary');
    await page.click('.kg-multi >> nth=0 >> input[type=checkbox] >> nth=0');
    await settle(page);
    out.checks.after_values = await queries(page);
    out.checks.cards_after = await page.$$eval('.kg-kpi .kg-kpi-value', (c) => c.map((x) => x.textContent));
    await page.click('text=Clear filters');
    await settle(page);
    await queries(page);
  }
  const date = await page.$('.kg-dates input[type=date]');
  if (date) {
    await page.fill('.kg-dates input[type=date] >> nth=0', '2026-10-01');
    await settle(page);
    out.checks.after_dates = await queries(page);
  }
  // keyboard: the skip link first, then the page tabs; Enter opens a page
  await page.goto(`${base}/?theme=light`);
  await settle(page);
  await page.keyboard.press('Tab');
  out.checks.first_tab = await page.evaluate(() => document.activeElement?.textContent?.trim());
  const tabCount = (await tabs(page)).length;
  if (tabCount > 1) {
    await page.focus('.kg-nav button >> nth=1');
    await page.keyboard.press('Enter');
    await settle(page);
    out.checks.after_enter = await page.$eval('.kg-nav button[aria-current=page]', (b) => b.textContent.trim());
    await queries(page);
    // the list page: sort, search, next page
    const sortable = await page.$('.kg-sort >> nth=1');
    if (sortable) {
      await sortable.click();
      await settle(page);
      out.checks.after_sort = await queries(page);
      out.checks.aria_sort = await page.$$eval('th[aria-sort]', (t) => t.map((x) => x.getAttribute('aria-sort')));
    }
    const search = await page.$('input[type=search]');
    if (search) {
      await search.fill('a');
      await page.keyboard.press('Enter');
      await settle(page);
      out.checks.after_search = await queries(page);
    }
    out.checks.next_enabled = await page.$eval('.kg-pager button >> nth=1', (b) => !b.disabled);
  }
  out.mutations.push(...(await page.evaluate(() => window.__kgMutations || [])));
  await ctx.close();
}

await browser.close();
server.close();
console.log(JSON.stringify(out));
