// AP2b: the founder's live test of /app (25 November 2026) replayed in Chromium on invented names (tests/ap2b_support.py):
// the one greeting, the schema list of a build target with Krusgraph's own output, a typed name that is in another
// workspace (with the chip to go there), and the check whose tiles, sentence and map count the same tables.
//
// Usage: node ap2b_app_browser.js <origin> <width> <height> <scheme> <screenshot folder or "">
// Prints JSON {errors, greetings, header, schemaChips, ownLine, match, goChip, kpis, mapSummary, firstLine, closing,
// overflow, chipMin}.
const { chromium } = require('playwright');
const path = require('path');
const [origin, width, height, scheme, shots] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: Number(width), height: Number(height) }, colorScheme: scheme });
  const page = await context.newPage();
  const out = { errors: [] };
  page.on('pageerror', (e) => out.errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
  const shot = async (name) => { if (shots) await page.screenshot({ path: path.join(shots, `ap2b-${name}-${width}-${scheme}.png`), fullPage: true }); };
  const hop1 = await context.request.get(origin + '/app', { maxRedirects: 0 });
  const hop2 = await context.request.get(origin + hop1.headers()['location'], { maxRedirects: 0 });
  const entra = new URL(hop2.headers()['location']);
  await page.goto(origin + '/app/callback?code=browser&state=' + encodeURIComponent(entra.searchParams.get('state')));
  await page.locator('.app-chip', { hasText: 'build_ws' }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(200);
  out.greetings = (await page.locator('#app-log').innerText()).split('Hi!').length - 1;
  out.header = await page.locator('.app-title p').innerText();
  await shot('1-greeting');
  // demo first (its one source and schema are picked for you), then the build target
  await page.locator('.app-chip', { hasText: /^demo/ }).first().click();
  await page.locator('.app-line', { hasText: 'demo_lh' }).waitFor({ timeout: 15000 });
  await page.locator('.app-chip', { hasText: 'Change' }).click();
  await page.locator('#app-log > li:last-child .app-bub', { hasText: 'Which workspace' }).waitFor({ timeout: 15000 });
  await page.locator('.app-chip', { hasText: 'build_ws' }).click();
  await page.locator('.app-chip', { hasText: 'build_lh' }).first().waitFor({ timeout: 15000 });
  await page.locator('.app-chip', { hasText: 'build_lh' }).first().click();
  await page.locator('.app-chip', { hasText: 'written by Krusgraph' }).waitFor({ timeout: 15000 });
  await page.waitForTimeout(200);
  out.schemaChips = await page.locator('#app-input .app-chips .app-chip').evaluateAll((ns) => ns.map((n) => n.innerText.replace(/\s+/g, ' ').trim() + (n.classList.contains('suggested') ? ' [suggested]' : '')));
  out.ownLine = await page.locator('#app-log > li:last-child .app-bub p.muted').innerText();
  await shot('2-schemas');
  await page.locator('.app-type input').fill('Shop');
  await page.locator('.app-type input').press('Enter');
  await page.locator('.app-chip', { hasText: 'Go to demo' }).waitFor({ timeout: 15000 });
  out.match = await page.locator('#app-log > li:last-child .app-bub').innerText();
  out.goChip = await page.locator('.app-chip', { hasText: 'Go to demo' }).innerText();
  await shot('3-elsewhere');
  await page.locator('.app-chip', { hasText: 'Go to demo' }).click();
  await page.locator('.check-kpis').waitFor({ timeout: 30000 });
  await page.locator('.app-msg.builder').waitFor({ timeout: 5000 });
  await page.waitForTimeout(400);
  out.kpis = await page.locator('.check-kpis li').allInnerTexts();
  out.mapSummary = await page.locator('.app-msg.thinker details summary').first().innerText();
  out.firstLine = await page.locator('.app-msg.thinker').last().locator('ul:not(.check-kpis) li').first().innerText();
  out.closing = await page.locator('.app-msg.builder').last().innerText();
  out.overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  out.chipMin = await page.locator('.app-chip').evaluateAll((ns) => Math.min(...ns.map((n) => n.getBoundingClientRect().height)));
  await shot('4-check');
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
