// AP2: the whole guided path at /app in Chromium (tests/test_ap2_browser.py runs the hosted app on localhost with the
// synthetic SAP demo and an in-memory Fabric behind the doubles of tests/ap2_support.py). Signed in the way AP1's test
// does it (tests/ap1_app_browser.js), then: the workspace, Next: Check, Next: Decide, Accept with quarantine on the one
// open decision, Next: Dry run, Change where to build -> the build workspace -> its lakehouse, Show definition, Create
// ... -> the confirm dialog, Yes -> each item created with its link, and verify_build's card.
//
// Usage: node ap2_app_browser.js <origin> <width> <height> <scheme> <screenshot prefix or "">
// Prints JSON with what the page showed at each step.
const { chromium } = require('playwright');
const [origin, width, height, scheme, shot] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: Number(width), height: Number(height) }, colorScheme: scheme });
  const page = await context.newPage();
  const out = { errors: [], overflow: [] };
  page.on('pageerror', (e) => out.errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
  const fail = async (e) => { throw new Error(e.message + ' errors ' + JSON.stringify(out.errors) + ' text ' + (await page.locator('body').innerText()).slice(-2500)); };
  const overflow = async (where) => out.overflow.push([where, await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)]);
  const snap = async (name, full = true) => { if (shot) await page.screenshot({ path: shot + '-' + name + '.png', fullPage: full }); };
  const chip = (text) => page.locator('#app-input .app-chip', { hasText: text }).first();
  const named = (name) => page.locator('#app-input .app-chip').filter({ has: page.locator('span', { hasText: new RegExp('^' + name + '$') }) }).first();

  const hop1 = await context.request.get(origin + '/app', { maxRedirects: 0 });
  const hop2 = await context.request.get(origin + hop1.headers()['location'], { maxRedirects: 0 });
  const entra = new URL(hop2.headers()['location']);
  await page.goto(origin + '/app/callback?code=browser&state=' + encodeURIComponent(entra.searchParams.get('state')));
  try {
    await named('demo').waitFor({ timeout: 15000 });
    await named('demo').click();
    await chip('Next: Check').waitFor({ timeout: 15000 });
    await chip('Next: Check').click();
    await chip('Next: Decide').waitFor({ timeout: 30000 });
    out.focusAfterCheck = await page.evaluate(() => (document.activeElement && document.activeElement.textContent) || '');
    await chip('Next: Decide').click();
    await page.locator('.app-dec').first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(300);
    out.decision = await page.locator('.app-dec').first().innerText();
    out.focusOnOption = await page.evaluate(() => (document.activeElement && document.activeElement.closest('.app-dec-opts')) ? document.activeElement.textContent : '');
    await overflow('decide');
    await snap('1-decide');
    await page.locator('.app-dec-opts .app-chip', { hasText: 'Accept with quarantine' }).last().click();
    await page.locator('.app-badge.mine').first().waitFor({ timeout: 30000 });
    out.decided = await page.locator('.app-badge.mine').last().innerText();
    await chip('Next: Dry run').click();
    await page.locator('.app-target').first().waitFor({ timeout: 30000 });
    out.firstTarget = await page.locator('.app-target').last().innerText();
    await chip('Change where to build').click();
    await named('build').waitFor({ timeout: 15000 });
    await named('build').click();
    await named('build_lh').waitFor({ timeout: 15000 });
    await named('build_lh').click();
    await page.waitForFunction(() => document.querySelectorAll('.app-target').length >= 2, null, { timeout: 30000 });
    await page.waitForTimeout(300);
    out.target = await page.locator('.app-target').last().innerText();
    const dry = page.locator('.app-msg.builder').last();
    out.items = await dry.locator('.app-item').evaluateAll((ns) => ns.map((n) => n.querySelector('.app-item-h').innerText.replace(/\s+/g, ' ')));
    out.decidedInDry = await dry.locator('.app-decided').innerText();
    await dry.locator('details summary', { hasText: 'Show definition' }).nth(3).click();
    out.definition = (await dry.locator('.app-def').nth(3).innerText()).slice(0, 200);
    await overflow('dry run');
    await snap('2-dry-run');
    await chip('Create these').click();
    await page.locator('dialog.app-dialog[open]').waitFor({ timeout: 5000 });
    out.dialog = await page.locator('dialog.app-dialog').innerText();
    out.dialogFocus = await page.evaluate(() => document.activeElement && document.activeElement.id);
    out.dialogModal = await page.evaluate(() => document.querySelector('dialog.app-dialog').matches(':modal'));
    await snap('3-confirm', false);
    await page.locator('dialog.app-dialog .app-chip', { hasText: 'Yes, create them' }).click();
    await page.locator('.app-msg.verify').waitFor({ timeout: 90000 });
    await page.waitForTimeout(300);
    out.created = await page.locator('.app-msg.builder').nth(-2).locator('.app-item').evaluateAll((ns) => ns.map((n) => n.querySelector('.app-item-h').innerText.replace(/\s+/g, ' ')));
    out.links = await page.locator('.app-item a').evaluateAll((ns) => ns.map((a) => a.getAttribute('href')));
    out.verify = await page.locator('.app-msg.verify').innerText();
    await overflow('verify');
    out.chipMin = await page.locator('.app-chip').evaluateAll((ns) => Math.min(...ns.filter((n) => n.offsetParent).map((n) => n.getBoundingClientRect().height)));
    out.live = await page.locator('#app-log').getAttribute('aria-live');
    out.html = await page.content();
    await snap('4-created-and-verified');
  } catch (e) { await fail(e); }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
