// n177: the pages and fixes of round n177 in Chromium. Usage:
//   node tests/n177_browser.js site <base url>          the film in full screen on a phone, the product offering diagram
//                                                        on / and /choose, /start's "Use it in Fabric", the docs'
//                                                        screenshots, the /check map
//   node tests/n177_browser.js card <card.html> <data.json>   the dbt_schema card under a fake host
// Prints one JSON object. No request leaves the base URL (checked).
const { chromium, devices } = require('playwright');
const fs = require('fs');

async function site(base) {
  const browser = await chromium.launch();
  const out = { errors: [], external: [] };
  const watch = (page, tag) => {
    page.on('pageerror', (e) => out.errors.push(`${tag}: ${e.message}`));
    page.on('request', (r) => { if (!r.url().startsWith(base) && !r.url().startsWith('data:')) out.external.push(r.url()); });
  };

  // 1. the film in full screen on a phone: letterboxed (contain), the 4:5 file upright, the 16:9 file turned
  {
    const ctx = await browser.newContext({ ...devices['Pixel 7'] });
    const page = await ctx.newPage(); watch(page, 'film');
    await page.goto(base + '/docs', { waitUntil: 'networkidle' });   // n190: the film is on /docs, not the home page
    await page.evaluate(() => {                        // a real tap starts full screen: the browser asks for a user gesture
      const b = document.createElement('button'); b.id = 'fs'; b.textContent = 'fs';
      b.style.cssText = 'position:fixed;top:0;left:0;z-index:99999';
      b.onclick = () => document.querySelector('#film video').requestFullscreen();
      document.body.appendChild(b);
    });
    const v = '#film video';
    out.filmBefore = await page.evaluate((s) => { const e = document.querySelector(s); return { fit: getComputedStyle(e).objectFit }; }, v);
    await page.click('#fs');
    await page.waitForFunction(() => document.fullscreenElement !== null, null, { timeout: 5000 });
    await page.waitForTimeout(300);
    const read = () => page.evaluate((s) => {
      const e = document.querySelector(s), r = e.getBoundingClientRect(), cs = getComputedStyle(e);
      return { full: document.fullscreenElement === e, fit: cs.objectFit, w: Math.round(r.width), h: Math.round(r.height),
               vw: innerWidth, vh: innerHeight, src: e.getAttribute('src') || '' };
    }, v);
    out.filmPortrait = await read();
    // turned to landscape (a full-screen window cannot be resized, so the device metrics are emulated over CDP)
    const cdp = await ctx.newCDPSession(page);
    const turn = (w, h, type, angle) => cdp.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 2.625, mobile: true,
                                                                                         screenOrientation: { type, angle } });
    await turn(915, 412, 'landscapePrimary', 90);
    await page.waitForTimeout(400);
    out.filmLandscape = await read();
    await turn(412, 915, 'portraitPrimary', 0);                          // and back
    await page.waitForTimeout(400);
    out.filmBack = await read();
    await page.evaluate(() => document.exitFullscreen());
    await ctx.close();
  }

  // 2. the diagram, on /choose and on the home page, at 1280 and 375, light and dark
  for (const [path, w] of [['/choose', 1280], ['/choose', 375], ['/', 1280], ['/', 375]]) {
    for (const scheme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width: w, height: 900 }, colorScheme: scheme }); watch(page, `${path}@${w}`);
      await page.goto(base + path, { waitUntil: 'networkidle' });
      const d = await page.evaluate(() => {
        const box = document.getElementById('offering'), ways = [...box.querySelectorAll('.off-way-a')];
        const rects = ways.map((a) => a.getBoundingClientRect());
        const eng = box.querySelector('.off-engine-box').getBoundingClientRect(), built = box.querySelector('.off-built').getBoundingClientRect();
        const ins = box.querySelector('.off-ways').getBoundingClientRect(), src = box.querySelector('.off-src').getBoundingClientRect();
        const det = box.querySelector('details.off-words');
        const mid = (r) => (r.top + r.bottom) / 2;
        return {
          ways: ways.map((a) => ({ href: a.getAttribute('href'), name: a.querySelector('.off-way-n').textContent, data: a.querySelector('.off-way-data').textContent })),
          words: [...box.querySelectorAll('.off-words-l li')].map((li) => ({ text: li.textContent, href: li.querySelector('a').getAttribute('href') })),
          built: [...box.querySelectorAll('.off-built li')].map((li) => li.textContent),
          // n183: ways in -> tables -> engine -> built
          stacked: ins.bottom <= src.top + 1 && src.bottom <= eng.top + 1 && eng.bottom <= built.top + 1,
          flow: ins.bottom <= Math.min(src.top, eng.top, built.top) + 1 && src.right <= eng.left + 1 && eng.right <= built.left + 1
                && Math.abs(mid(src) - mid(eng)) < eng.height && Math.abs(mid(built) - mid(eng)) < built.height,
          rects: [ins, src, eng, built].map((r) => [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]),
          details: det && { open: det.open, summary: det.querySelector('summary').textContent.trim(), items: det.querySelectorAll('.off-words-l li').length },
          pics: [...box.querySelectorAll('.off-pic-svg')].map((s) => ({ role: s.getAttribute('role'), label: s.getAttribute('aria-label'), w: Math.round(s.getBoundingClientRect().width) })),
          overflow: document.documentElement.scrollWidth - innerWidth,
          bg: getComputedStyle(document.body).backgroundColor, ink: getComputedStyle(box.querySelector('.off-engine-n')).color,
          img: box.querySelectorAll('img').length,
        };
      });
      // keyboard: Tab reaches each way, with a visible focus ring
      const focus = [];
      await page.focus('#offering');
      await page.evaluate(() => document.querySelector('#offering .off-way-a').focus());
      for (let i = 0; i < 4; i++) {
        focus.push(await page.evaluate(() => {
          const a = document.activeElement, cs = getComputedStyle(a);
          return { href: a.getAttribute('href'), ring: cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) >= 2 };
        }));
        await page.keyboard.press('Tab');
      }
      d.focus = focus;
      out[`${path}@${w}@${scheme}`] = d;
      if (scheme === 'light' && process.env.SHOTS) await (await page.$('#offering')).screenshot({ path: `${process.env.SHOTS}/offering-${path === '/' ? 'home' : 'choose'}@${w}.png` });
      await page.close();
    }
  }

  // every link the diagram has answers 200
  {
    const page = await browser.newPage(); watch(page, 'links');
    await page.goto(base + '/choose', { waitUntil: 'networkidle' });
    out.linkStatus = await page.evaluate(async () => {
      const hrefs = [...new Set([...document.querySelectorAll('#offering a, .decide a, .choose-table a')].map((a) => a.getAttribute('href')))];
      const r = {};
      for (const h of hrefs) r[h] = (await fetch(h)).status;
      return r;
    });
    out.choose = await page.evaluate(() => ({
      decide: [...document.querySelectorAll('.choose-decide .decide li')].map((li) => li.textContent.replace(/\s+/g, ' ').trim()),
      heads: [...document.querySelectorAll('.choose-table thead th')].map((t) => t.textContent.trim()),
      rows: [...document.querySelectorAll('.choose-table tbody th')].map((t) => t.textContent.trim()),
      noAi: document.querySelector('.no-ai').textContent,
    }));
    await page.close();
  }

  // 3. /start: "Use it in Fabric" next to Claude and the other agents; the docs' screenshots load
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } }); watch(page, 'start');
    await page.goto(base + '/start', { waitUntil: 'networkidle' });
    out.start = await page.evaluate(() => ({
      paths: [...document.querySelectorAll('.start-paths .path-card h2')].map((h) => h.textContent),
      fabricHref: document.querySelector('.path-fabric').getAttribute('href'),
      short: !!document.querySelector('#which .decide'),
    }));
    await page.goto(base + '/docs/krusgraph-for-fabric/what-the-krusgraph-model-item-does', { waitUntil: 'networkidle' });
    out.shots = await page.evaluate(async () => {
      const imgs = [...document.querySelectorAll('figure.shot img')];
      await Promise.all(imgs.map((i) => i.decode().catch(() => null)));
      return imgs.map((i) => ({ src: new URL(i.src).pathname, w: i.naturalWidth, alt: i.alt, cap: i.closest('figure').querySelector('figcaption').textContent }));
    });
    await page.close();
  }

  // 4. /check: linked tables sit close; the interface line says so; the dashed "?" says what it is on hover
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } }); watch(page, 'check');
    await page.goto(base + '/check?example=sample', { waitUntil: 'networkidle' });
    await page.waitForSelector('#check-map svg .m-sug', { timeout: 120000 });
    await page.waitForTimeout(800);
    out.map = await page.evaluate(() => {
      const at = {};
      document.querySelectorAll('#check-map svg [data-table]').forEach((g) => {
        const m = /translate\(([-\d.]+) ([-\d.]+)\)/.exec(g.getAttribute('transform')); at[g.getAttribute('data-table')] = [+m[1], +m[2]];
      });
      const d = (a, b) => Math.hypot(at[a][0] - at[b][0], at[a][1] - at[b][1]);
      const names = Object.keys(at), all = [];
      for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) all.push(d(names[i], names[j]));
      all.sort((x, y) => x - y);
      const sug = document.querySelector('#check-map .m-sug'), hit = sug.querySelector('.m-hit');
      const r = hit.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
      const under = document.elementFromPoint(x, y);
      return { orderItemsProducts: d('order_items', 'products'), median: all[Math.floor(all.length / 2)],
               labels: [...document.querySelectorAll('#check-map .m-iface .m-rule')].map((t) => t.textContent),
               title: (sug.querySelector('title') || {}).textContent || '', hitUnder: !!(under && under.closest('.m-sug')),
               hitEvents: getComputedStyle(hit).pointerEvents };
    });
    await page.close();
  }
  await browser.close();
  return out;
}

async function card(file, dataFile) {
  const html = fs.readFileSync(file, 'utf8'), data = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 760, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setContent('<iframe id="f" sandbox="allow-scripts" style="width:720px;height:1800px"></iframe>');
  await page.evaluate(([html, data]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', (e) => {
      const m = e.data, reply = (r) => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: {}, hostContext: { toolInfo: { tool: { name: 'dbt_schema' } } } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: data.args } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: data.result }, '*');
      }
    });
    f.srcdoc = html;
  }, [html, data]);
  const fr = page.frameLocator('#f');
  await fr.locator('.kgf').waitFor({ timeout: 10000 });
  const before = await fr.locator('main').evaluate((m) => ({
    title: document.getElementById('title').textContent, verdict: document.getElementById('verdict').textContent,
    cols: [...m.querySelectorAll('.kgf-col')].map((c) => ({ h: c.querySelector('.kgf-h').textContent, boxes: c.querySelectorAll('.kgf-box').length })),
    open: m.querySelectorAll('.kgf-code:not([hidden])').length,
  }));
  await fr.locator('button.kgf-box', { hasText: 'stg_shop__orders' }).click();
  await fr.locator('button.kgf-box', { hasText: 'customers' }).first().press('Enter');
  const after = await fr.locator('main').evaluate((m) => ({
    open: [...m.querySelectorAll('.kgf-code:not([hidden])')].map((p) => p.textContent),
    expanded: [...m.querySelectorAll('button.kgf-box[aria-expanded=true]')].map((b) => b.querySelector('.kgf-n').textContent),
  }));
  await browser.close();
  return { errors, before, after };
}

(async () => {
  const [mode, a, b] = process.argv.slice(2);
  const out = mode === 'card' ? await card(a, b) : await site(a);
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
