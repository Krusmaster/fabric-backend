// n170: "Try in Claude" on the home page and /start. Usage: node try_claude_browser.js <base> [chromium] [shotdir]
// For each page: clicks the button with the clipboard allowed, and reports the tab it opened, what the clipboard holds and
// what the note under the button says; the Claude Desktop link's address; and whether the button is visible.
// claude.ai is never contacted: the new tab's request is answered here with an empty page.
const { chromium } = require('playwright');
(async () => {
  const [base, exe, shots] = process.argv.slice(2);
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = {};
  for (const path of ['/', '/start#step-3']) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: shots ? 2 : 1 });
    await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
    await ctx.route('https://claude.ai/**', r => r.fulfill({ status: 200, contentType: 'text/html', body: '<p>claude</p>' }));
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + path, { waitUntil: 'load' });
    const a = page.locator('[data-try-claude]').first();
    const info = {
      visible: await a.isVisible(), href: await a.getAttribute('href'), target: await a.getAttribute('target'),
      question: await a.getAttribute('data-question'),
      desktop: await page.locator('[data-desktop-link]').first().getAttribute('href'),
      // n206: the home page's note is one line with no link; /start's links to step 3
      connect: await page.evaluate(() => { const l = document.querySelector('.try-claude-note a'); return l ? l.getAttribute('href') : null; }),
      noteBefore: await page.locator('.try-claude-note').first().innerText(),
    };
    if (shots) await page.locator('.try-claude').first().screenshot({ path: `${shots}/try${path === '/' ? '_home' : '_start'}.png` });
    const [popup] = await Promise.all([ctx.waitForEvent('page', { timeout: 5000 }), a.click()]);
    await page.waitForTimeout(300);
    info.opened = popup.url();
    info.clipboard = await page.evaluate(() => navigator.clipboard.readText());
    info.noteAfter = await page.locator('.try-claude-note').first().innerText();
    info.errors = errors;
    out[path] = info;
    await ctx.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
