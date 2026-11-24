// AP1: the guided chat at /app in Chromium (tests/test_ap1_browser.py runs the hosted app on localhost with the
// synthetic SAP demo behind the doubles). Each run signs in the way a browser does: /app sends it to /app/login, which
// sends it to Microsoft Entra; Entra's answer is played here as its redirect back to /app/callback, so the code, state
// and flow cookie take the real path. Then the journey is walked: a workspace (tapped, or typed), Next: Check by
// keyboard, the check's counts, and the closing "coming next" bubble.
//
// Usage: node ap1_app_browser.js <origin> <width> <height> <scheme> <typed: 0|1> <screenshot path or "">
// Prints JSON {errors, bubbles, live, focusOnNext, kpis, next, overflow, chipMin, cookies, said, url}.
const { chromium } = require('playwright');
const [origin, width, height, scheme, typed, shot] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: Number(width), height: Number(height) }, colorScheme: scheme });
  const page = await context.newPage();
  const out = { errors: [] };
  page.on('pageerror', (e) => out.errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
  // The browser's way in, hop by hop in this context (its cookies are the page's): /app -> /app/login -> Entra. Entra's
  // answer is its redirect back to /app/callback with a code and the state it was sent; that address is opened in the page.
  const hop1 = await context.request.get(origin + '/app', { maxRedirects: 0 });
  out.first = [hop1.status(), hop1.headers()['location']];
  const hop2 = await context.request.get(origin + out.first[1], { maxRedirects: 0 });
  const entra = new URL(hop2.headers()['location']);
  out.entra = [hop2.status(), entra.origin, entra.searchParams.get('redirect_uri'), entra.searchParams.get('code_challenge_method')];
  await page.goto(origin + '/app/callback?code=browser&state=' + encodeURIComponent(entra.searchParams.get('state')));
  out.url = new URL(page.url()).pathname;
  try { await page.locator('.app-chip', { hasText: 'sales_archive' }).waitFor({ timeout: 15000 }); } catch (e) { throw new Error(e.message + ' at ' + page.url() + ' errors ' + JSON.stringify(out.errors) + ' text ' + (await page.locator('body').innerText()).slice(0, 1500)); }
  out.live = await page.locator('#app-log').getAttribute('aria-live');
  if (typed === '1') {
    await page.locator('.app-type input').fill('DEMO');
    await page.locator('.app-type input').press('Enter');
  } else {
    await page.locator('.app-chip', { hasText: /^demo/ }).first().focus();
    await page.keyboard.press('Enter');
  }
  await page.locator('.app-line', { hasText: 'demo_lh' }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(100);
  out.focusOnNext = await page.evaluate(() => (document.activeElement && document.activeElement.textContent) || '');
  if (!out.focusOnNext.startsWith('Next')) await page.locator('.app-chip', { hasText: 'Next: Check' }).focus();
  await page.keyboard.press('Enter');
  await page.locator('.check-kpis').waitFor({ timeout: 30000 });
  await page.locator('.app-msg.builder').waitFor({ timeout: 5000 });
  await page.waitForTimeout(400);
  out.kpis = await page.locator('.check-kpis li').allInnerTexts();
  out.next = await page.locator('.app-msg.builder').last().innerText();
  out.bubbles = await page.locator('#app-log > li').evaluateAll((ns) => ns.map((n) => n.className + ': ' + n.innerText.split('\n').slice(0, 2).join(' | ')));
  out.said = await page.locator('#app-log').innerText();
  out.overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  out.chipMin = await page.locator('.app-chip').evaluateAll((ns) => Math.min(...ns.map((n) => n.getBoundingClientRect().height)));
  out.cookies = (await context.cookies()).map((c) => ({ name: c.name, httpOnly: c.httpOnly, secure: c.secure, sameSite: c.sameSite }));
  out.html = await page.content();
  if (shot) await page.screenshot({ path: shot, fullPage: true });
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
