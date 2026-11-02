// n80: the Connect menu in a browser, with client registration on (all four clients), at 375 and 1280 px.
// Usage: node tests/connect_browser.js <base url> [chromium path]. Prints one JSON object the Python test asserts on.
// Everything by keyboard: Tab to the hero's Connect, Enter opens it; the Tab order through the panel; Enter on
// "Other clients"; each copy button pressed with the keyboard and the clipboard read back; Escape closes.
const { chromium } = require('playwright');
const base = process.argv[2];
const exe = process.argv[3];
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  for (const width of [375, 1280]) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, permissions: ['clipboard-read', 'clipboard-write'] });
    const page = await ctx.newPage();
    page.on('pageerror', e => out.errors.push(`${width}: pageerror ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') out.errors.push(`${width}: console ${m.text()}`); });
    await page.goto(base + '/', { waitUntil: 'networkidle' });
    const r = {};
    // Tab from the top of the page until the hero's Connect has the focus
    let tabs = 0;
    for (; tabs < 40; tabs++) {
      await page.keyboard.press('Tab');
      if (await page.evaluate(() => document.activeElement === document.querySelector('.hero-ctas summary'))) break;
    }
    r.reachedByTab = tabs < 40;
    await page.keyboard.press('Enter'); await page.waitForTimeout(150);
    const panel = '.hero-ctas .connect-panel';
    r.closedView = await page.evaluate((sel) => {
      const p = document.querySelector(sel), box = p.getBoundingClientRect();
      // checkVisibility: a closed <details> hides its content with content-visibility, which a box size does not show
      const visible = (e) => e.checkVisibility({ visibilityProperty: true, contentVisibilityAuto: true }) && e.getBoundingClientRect().width > 0;
      const text = [...p.querySelectorAll('*')].filter((e) => visible(e) && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()))
        .map((e) => [...e.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('')).join(' ');
      const main = p.querySelector('.connect-main').getBoundingClientRect(), copy = p.querySelector('.connect-claude [data-copy-text]').getBoundingClientRect();
      return {
        open: p.closest('details').open, inside: box.left >= 0 && box.right <= window.innerWidth, wide: document.documentElement.scrollWidth,
        headings: [...p.querySelectorAll('.connect-item > strong')].filter(visible).map((e) => e.textContent),
        other: { present: !!p.querySelector('details.connect-other'), open: p.querySelector('details.connect-other').open },
        foot: visible(p.querySelector('.connect-foot')) ? p.querySelector('.connect-foot').textContent.trim() : null,
        footLast: p.lastElementChild.classList.contains('connect-foot'),
        printedUrl: /https?:\/\/|\/mcp/.test(text) || p.querySelectorAll('code').length > 0, text,
        mainBigger: main.height >= copy.height && main.width > copy.width,
        besideCopy: Math.abs((main.top + main.bottom) / 2 - (copy.top + copy.bottom) / 2) < 4 || copy.top >= main.bottom - 1,
      };
    }, panel);
    // the Tab order through the open panel, as labels
    const order = [];
    for (let i = 0; i < 12; i++) {
      await page.keyboard.press('Tab');
      const label = await page.evaluate((sel) => { const a = document.activeElement; return a.closest(sel) ? (a.childNodes[0] && a.childNodes[0].textContent || a.textContent).trim() : null; }, panel);
      if (label === null) break;
      order.push(label);
      if (label === 'Other clients') {
        r.otherFocusRing = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
        await page.keyboard.press('Enter'); await page.waitForTimeout(100);
        r.otherOpened = await page.evaluate((sel) => {
          const d = document.querySelector(sel + ' details.connect-other'), box = document.querySelector(sel).getBoundingClientRect();
          return { open: d.open, clients: [...d.querySelectorAll('.connect-item > strong')].map((e) => e.textContent),
                   links: [...d.querySelectorAll('a')].map((a) => a.getAttribute('href').split('?')[0]), inside: box.left >= 0 && box.right <= window.innerWidth,
                   wide: document.documentElement.scrollWidth, outerOpen: document.querySelector(sel).closest('details').open };
        }, panel);
      }
    }
    r.tabOrder = order;
    // each copy button pressed from the keyboard, and what it put on the clipboard
    r.copies = {};
    const buttons = await page.$$(panel + ' [data-copy-text]');
    for (const b of buttons) {
      const label = (await b.textContent()).trim();
      const where = await b.evaluate((e) => e.closest('.connect-item') ? e.closest('.connect-item').querySelector('strong').textContent : 'foot');
      await b.focus(); await page.keyboard.press('Enter'); await page.waitForTimeout(80);
      r.copies[where + ': ' + label] = { clip: await page.evaluate(() => navigator.clipboard.readText()), after: (await b.textContent()).trim() };
      await page.waitForTimeout(1700);                               // the label comes back ("Copied" for 1.6 s)
    }
    await page.focus('.hero-ctas summary');
    await page.keyboard.press('Escape');
    r.afterEscape = await page.evaluate(() => ({ open: document.querySelector('.hero-ctas details').open, focus: document.activeElement === document.querySelector('.hero-ctas summary') }));
    if (!r.afterEscape.open) { await page.keyboard.press('Enter'); await page.waitForTimeout(100); }
    await page.keyboard.press('Escape');
    r.afterEscape2 = await page.evaluate(() => ({ open: document.querySelector('.hero-ctas details').open, focus: document.activeElement === document.querySelector('.hero-ctas summary') }));
    out[width] = r;
    // /consent/done after a granted consent: the next step, and its copy button
    await page.goto(base + '/consent/done?admin_consent=True', { waitUntil: 'networkidle' });
    const q = await page.$('[data-copy-text]');
    await q.focus(); await page.keyboard.press('Enter'); await page.waitForTimeout(80);
    out['consent' + width] = { clip: await page.evaluate(() => navigator.clipboard.readText()), wide: await page.evaluate(() => document.documentElement.scrollWidth),
                               next: await page.evaluate(() => document.getElementById('next').textContent) };
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
