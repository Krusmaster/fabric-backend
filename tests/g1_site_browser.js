// G1: the site's legal and accessibility checks in a real browser, on every public page at 375 and 1280 px, light and
// dark. Run by tests/test_g1_legal_site.py. Prints one JSON line: {problems: [...], pages: n}.
//  - nothing is requested from another host, and nothing is stored (no cookie, no localStorage or sessionStorage key)
//    before the visitor does anything;
//  - every image has alt text (alt="" for decorative ones), every button, link and form field has a name;
//  - text contrast meets WCAG AA (4.5:1, 3:1 for large text) against the nearest solid background;
//  - the footer's cookie panel opens from the keyboard, shows a focus outline, and lists what is stored.
// An equivalent of axe-core's checks for these rules, with no new dependency (axe-core itself ran in the audit).
const { chromium } = require('playwright');
const base = process.argv[2];
const pages = JSON.parse(process.argv[3]);
const executablePath = process.argv[4];

function inPage() {
  const problems = [];
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[hidden],[aria-hidden=true]'); };
  const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  function background(el) {
    for (let n = el; n; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null;          // a gradient or image: not judged here
      if (parseFloat(s.opacity) < 1) return null;
      const c = parse(s.backgroundColor);
      if (c && c.a >= 0.99) return c;
      if (c && c.a > 0) return null;                                                // a translucent layer: not judged here
    }
    return parse(getComputedStyle(document.body).backgroundColor);
  }
  // contrast: elements with their own text
  for (const el of document.querySelectorAll('body *')) {
    if (!vis(el) || ['SCRIPT', 'STYLE', 'svg', 'SVG', 'OPTION'].includes(el.tagName) || el.closest('svg,video,.kgc-launch,[disabled]')) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const s = getComputedStyle(el); const fg = parse(s.color); const bg = background(el);
    if (!fg || !bg || fg.a < 1) continue;
    const size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight, 10) >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    const r = ratio(fg, bg);
    if (r < need) problems.push({ rule: 'contrast', el: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''), text: el.textContent.trim().slice(0, 40), ratio: +r.toFixed(2), need });
  }
  // images
  for (const img of document.querySelectorAll('img')) if (!img.hasAttribute('alt')) problems.push({ rule: 'alt', el: img.src });
  // names
  const nameOf = el => {
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const by = el.getAttribute('aria-labelledby'); if (by) return by.split(' ').map(i => (document.getElementById(i) || {}).textContent || '').join(' ');
    if (el.labels && el.labels.length) return [...el.labels].map(l => l.textContent).join(' ');
    if (el.title) return el.title;
    return (el.textContent || '') + [...el.querySelectorAll('img[alt]')].map(i => i.alt).join(' ');
  };
  for (const el of document.querySelectorAll('a[href],button,input:not([type=hidden]),textarea,select,summary')) {
    if (el.closest('[hidden]')) continue;
    if (!nameOf(el).trim()) problems.push({ rule: 'name', el: el.outerHTML.slice(0, 80) });
  }
  return problems;
}

(async () => {
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const problems = [];
  for (const path of pages) {
    for (const width of [375, 1280]) {
      for (const scheme of ['light', 'dark']) {
        const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
        const page = await ctx.newPage();
        const where = `${path} @${width} ${scheme}`;
        page.on('request', r => { const u = new URL(r.url()); if (u.protocol.startsWith('http') && !['127.0.0.1', 'localhost'].includes(u.hostname)) problems.push({ rule: 'third-party', where, url: r.url() }); });
        await page.goto(base + path, { waitUntil: 'networkidle' });
        const stored = await page.evaluate(() => ({ local: Object.keys(localStorage), session: Object.keys(sessionStorage) }));
        const cookies = await ctx.cookies();
        if (stored.local.length || stored.session.length || cookies.length) problems.push({ rule: 'stored-before-consent', where, stored, cookies: cookies.map(c => c.name) });
        for (const p of await page.evaluate(inPage)) problems.push({ ...p, where });
        if (width === 1280 && scheme === 'light') {
          // the cookie panel from the keyboard: focus its summary, Enter opens it, the outline shows, the list is there
          const r = await page.evaluate(() => { const s = document.querySelector('.cookie-panel > summary'); if (!s) return null; s.focus(); return document.activeElement === s; });
          if (!r) { problems.push({ rule: 'cookie-panel-missing', where }); }
          else {
            await page.keyboard.press('Enter');
            const st = await page.evaluate(() => { const s = document.querySelector('.cookie-panel > summary'); const d = s.parentElement;
              return { open: d.open, outline: getComputedStyle(s).outlineStyle, rows: d.querySelectorAll('.storage-list li').length, policy: !!d.querySelector('a[href="/cookies"]') }; });
            if (!st.open || st.outline === 'none' || st.rows < 3 || !st.policy) problems.push({ rule: 'cookie-panel', where, st });
          }
        }
        await ctx.close();
      }
    }
  }
  await browser.close();
  console.log(JSON.stringify({ problems, pages: pages.length }));
})().catch(e => { console.error(e); process.exit(1); });
