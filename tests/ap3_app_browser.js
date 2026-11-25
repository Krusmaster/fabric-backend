// AP3: the caretaker at /app in Chromium (tests/test_ap3_care_browser.py runs the hosted app on localhost with the
// synthetic SAP demo, an in-memory Fabric that already holds a data product a Krusgraph Model built, and the doubles of
// tests/ap3_support.py). Signed in the way AP1's test does it, then: the "Since last time" report, Re-check the links,
// Run the pipeline once (its preview, the confirm dialog, Yes) and Update the build in place (AP2's dry run).
//
// Usage: node ap3_app_browser.js <origin> <width> <height> <scheme> <screenshot prefix or "">
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

  const hop1 = await context.request.get(origin + '/app', { maxRedirects: 0 });
  const hop2 = await context.request.get(origin + hop1.headers()['location'], { maxRedirects: 0 });
  const entra = new URL(hop2.headers()['location']);
  await page.goto(origin + '/app/callback?code=browser&state=' + encodeURIComponent(entra.searchParams.get('state')));
  try {
    await page.locator('.care-card').first().waitFor({ timeout: 60000 });
    await chip('Start something new').waitFor({ timeout: 60000 });
    await page.waitForTimeout(300);
    out.greeting = await page.locator('.app-msg.onto').first().innerText();
    out.report = await page.locator('.care-card').first().innerText();
    out.sections = await page.locator('.care-card .care-sec').evaluateAll((ns) => ns.map((n) => n.querySelector('.care-sec-h').innerText.replace(/\s+/g, ' ')));
    out.sources = await page.locator('.care-card .care-src').evaluateAll((ns) => ns.map((n) => n.innerText));
    out.buttons = await page.locator('#app-input .app-chip').evaluateAll((ns) => ns.map((n) => n.querySelector('span') ? n.querySelector('span').innerText : n.innerText));
    out.chipMin = await page.locator('.app-chip').evaluateAll((ns) => Math.min(...ns.filter((n) => n.offsetParent).map((n) => n.getBoundingClientRect().height)));
    await overflow('report');
    await snap('1-report');

    await chip('Re-check the links').click();
    await page.locator('.app-msg.verify').first().waitFor({ timeout: 60000 });
    out.recheck = await page.locator('.app-msg.verify').last().innerText();
    await chip('Run the pipeline once').waitFor({ timeout: 15000 });
    await overflow('recheck');
    await snap('2-recheck');

    await chip('Run the pipeline once').click();
    await chip('Run the pipeline once…').waitFor({ timeout: 30000 });
    out.preview = await page.locator('.app-msg.builder').last().innerText();
    await chip('Run the pipeline once…').click();
    await page.locator('dialog.app-dialog[open]').waitFor({ timeout: 5000 });
    out.dialog = await page.locator('dialog.app-dialog').innerText();
    out.dialogFocus = await page.evaluate(() => document.activeElement && document.activeElement.id);
    out.dialogModal = await page.evaluate(() => document.querySelector('dialog.app-dialog').matches(':modal'));
    await snap('3-confirm', false);
    await page.locator('dialog.app-dialog .app-chip', { hasText: 'Yes, run the pipeline once' }).click();
    await page.locator('.app-status', { hasText: 'queued in Fabric' }).waitFor({ timeout: 30000 });
    out.ran = await page.locator('.app-msg.builder').last().innerText();
    await chip('Update the build in place').waitFor({ timeout: 15000 });
    await overflow('ran');
    await snap('4-ran');

    await chip('Update the build in place').click();
    await page.locator('.app-target').first().waitFor({ timeout: 60000 });
    await page.waitForTimeout(300);
    const dry = page.locator('.app-msg.builder').last();
    out.target = await page.locator('.app-target').last().innerText();
    out.items = await dry.locator('.app-item').evaluateAll((ns) => ns.map((n) => n.querySelector('.app-item-h').innerText.replace(/\s+/g, ' ')));
    out.createButton = await chip('Create these').innerText();
    await overflow('update dry run');
    out.live = await page.locator('#app-log').getAttribute('aria-live');
    out.html = await page.content();
    await snap('5-update-dry-run');
  } catch (e) { await fail(e); }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
