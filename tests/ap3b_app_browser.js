// AP3b: the caretaker's report at /app in Chromium with a long "What was built, read back" (tests/test_ap3b_browser.py
// serves the app with AP3's doubles; the pipeline part is slow the first time, so it is "Not read in time").
// Checked: the busy line names the parts still being read and ticks the ones done; no section overlaps the next and no
// section's text runs out of its box, on screen and in print media; Read again reads the product again.
//
// Usage: node ap3b_app_browser.js <origin> <width> <height> <scheme> <screenshot prefix or ""> <pdf path or "">
// The PDF is the page printed on US Letter, landscape, as the founder's browser printed it (the overlap of the live run
// was Chromium's print fragmentation of the report's nested grid: a section that crossed a page was given less height
// than its text, and the next section was drawn over it).
const { chromium } = require('playwright');
const [origin, width, height, scheme, shot, pdf] = process.argv.slice(2);

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: Number(width), height: Number(height) }, colorScheme: scheme });
  const page = await context.newPage();
  const out = { errors: [], overflow: [], overlaps: [] };
  page.on('pageerror', (e) => out.errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') out.errors.push(m.text()); });
  const snap = async (name, full = true) => { if (shot) await page.screenshot({ path: shot + '-' + name + '.png', fullPage: full }); };
  const chip = (text) => page.locator('#app-input .app-chip', { hasText: text }).first();
  // every section of every report: its box and the boxes of its contents; a section must end before the next begins,
  // and nothing inside it may reach past its bottom or its right edge
  const layout = async (where) => {
    const got = await page.evaluate(() => {
      const bad = [];
      document.querySelectorAll('.care-card').forEach((card, ci) => {
        const secs = [...card.querySelectorAll(':scope > .care-sec')];
        secs.forEach((s, i) => {
          const r = s.getBoundingClientRect();
          const next = secs[i + 1] && secs[i + 1].getBoundingClientRect();
          if (next && r.bottom > next.top + 0.5) bad.push(`card ${ci} section ${i} ends at ${r.bottom}, the next starts at ${next.top}`);
          if (s.scrollHeight > s.clientHeight + 1) bad.push(`card ${ci} section ${i} text is taller than its box`);
          if (s.scrollWidth > s.clientWidth + 1) bad.push(`card ${ci} section ${i} text is wider than its box`);
          s.querySelectorAll('li, p, a, h4, button').forEach((n) => {
            const b = n.getBoundingClientRect();
            if (b.bottom > r.bottom + 0.5 || b.right > r.right + 0.5) bad.push(`card ${ci} section ${i}: ${n.tagName} runs out of it`);
          });
        });
        const c = card.getBoundingClientRect();
        const last = secs.length && secs[secs.length - 1].getBoundingClientRect();
        if (last && last.bottom > c.bottom + 0.5) bad.push(`card ${ci}: its last section runs out of the card`);
      });
      return { bad, sections: document.querySelectorAll('.care-sec').length };
    });
    out.overlaps.push([where, got.bad]);
    out.overflow.push([where, await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)]);
    return got;
  };

  const hop1 = await context.request.get(origin + '/app', { maxRedirects: 0 });
  const hop2 = await context.request.get(origin + hop1.headers()['location'], { maxRedirects: 0 });
  const entra = new URL(hop2.headers()['location']);
  await page.goto(origin + '/app/callback?code=browser&state=' + encodeURIComponent(entra.searchParams.get('state')));
  try {
    await page.locator('.care-parts li.done').first().waitFor({ timeout: 60000 });
    out.busy = await page.locator('.care-reading .app-busy').first().innerText();
    out.ticks = await page.locator('.care-parts li').evaluateAll((ns) => ns.map((n) => n.innerText.replace(/\s+/g, ' ')));
    await snap('0-reading', false);
    await page.locator('.care-card').first().waitFor({ timeout: 60000 });
    await chip('Start something new').waitFor({ timeout: 60000 });
    await page.waitForTimeout(300);
    out.late = await page.locator('.care-sec.s-unknown').first().innerText();
    out.verify = await page.locator('.care-sec', { hasText: 'What was built, read back' }).first().innerText();
    out.first = (await layout('report')).sections;
    await snap('1-report');
    await page.emulateMedia({ media: 'print' });
    await layout('report, print');
    out.printDisplay = await page.evaluate(() => ['.app-bub', '.care-card', '.care-sec'].map((s) => getComputedStyle(document.querySelector(s)).display));
    if (pdf) await page.pdf({ path: pdf, format: 'Letter', landscape: true, printBackground: true, displayHeaderFooter: true });
    await page.emulateMedia({ media: 'screen' });

    await page.locator('.care-sec .care-again').first().click();
    await page.locator('.care-reading').first().waitFor({ timeout: 10000 });
    await page.locator('.care-card').first().waitFor({ timeout: 60000 });
    await chip('Start something new').waitFor({ timeout: 60000 });
    await page.waitForTimeout(300);
    out.again = await page.locator('.care-card').first().innerText();
    out.lateAfter = await page.locator('.care-sec.s-unknown').count();
    await layout('read again');
    await snap('2-read-again');
    out.buttons = await page.locator('#app-input .app-chip').evaluateAll((ns) => ns.map((n) => n.querySelector('span') ? n.querySelector('span').innerText : n.innerText));
  } catch (e) {
    throw new Error(e.message + ' errors ' + JSON.stringify(out.errors) + ' text ' + (await page.locator('body').innerText()).slice(-2500));
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
