// n229: the build card after a Create and at a gated dry run, in a real browser under a fake host.
// Usage: node n229_cards_browser.js <card.html> <cases.json>
//   cases.json: {created: {result, args}, gated: {result, args}, verify: CallToolResult}
// The host runs tools/call for verify_build (answering `verify`) and records ui/message texts.
// Prints JSON {errors, created: {...}, gated: {...}}.
const { chromium } = require('playwright');
const fs = require('fs');
const [cardPath, casesPath] = process.argv.slice(2);
const card = fs.readFileSync(cardPath, 'utf8'), cases = JSON.parse(fs.readFileSync(casesPath, 'utf8'));

async function open(browser, which, errors) {
  const page = await browser.newPage({ viewport: { width: 720, height: 900 } });
  page.on('pageerror', e => errors.push(which + ': ' + e.message));
  const calls = [], said = [];
  await page.exposeFunction('kgCall', c => { calls.push(c); });
  await page.exposeFunction('kgSaid', t => { said.push(t); });
  await page.setContent('<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:680px;height:6000px"></iframe></body>');
  await page.evaluate(([card, c, verify, tool]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data;
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: { serverTools: {}, openLinks: {} }, hostContext: { toolInfo: { tool: { name: tool } } } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: c.args } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: c.result }, '*');
      } else if (m.method === 'tools/call') {
        window.kgCall({ name: m.params.name, arguments: m.params.arguments || {} });
        if (m.params.name === 'verify_build') reply(verify);
        else f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, error: { code: -32000, message: 'not in this test' } }, '*');
      } else if (m.method === 'ui/message') {
        const c0 = m.params.content; window.kgSaid(Array.isArray(c0) ? c0[0].text : c0.text); reply({});
      } else if (m.method === 'ui/open-link') reply({});
    });
    f.srcdoc = card;
  }, [card, cases[which], cases.verify, cases[which].tool]);
  await page.waitForTimeout(1000);
  return { page, fr: page.frameLocator('#f'), calls, said };
}

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const out = { errors };

  // 1. after a Create that succeeded
  let { page, fr, calls, said } = await open(browser, 'created', errors);
  const rows = fr.locator('#next .act');
  const created = { verdict: await fr.locator('#verdict').innerText(), buttons: [], reasons: [], done: [] };
  for (let i = 0; i < await rows.count(); i++) {
    created.buttons.push((await rows.nth(i).locator('button').first().innerText()).trim());
    const why = rows.nth(i).locator('.act-reason');
    created.reasons.push(await why.count() ? (await why.first().innerText()).trim() : '');
  }
  created.groups = await fr.locator('#next .act-who').allInnerTexts();
  created.done = await fr.locator('#next .act-done').allInnerTexts();
  created.nextHeading = await fr.locator('#next .nx-h').count();
  created.primary = await fr.locator('#next button.act-create').count();
  // Verify what was built: the host runs the read-only tool and the rows are drawn
  const verifyRow = fr.locator('#next .act', { has: fr.locator('button', { hasText: 'Verify what was built' }) }).first();
  await verifyRow.locator('button').first().click();
  await verifyRow.locator('.ck-table').first().waitFor({ timeout: 5000 });
  created.verifyCalls = calls.slice();
  created.pills = await verifyRow.locator('.ck-sum .pill').allInnerTexts();
  created.label = await verifyRow.locator('.ck-label').first().innerText();
  created.rowStates = await verifyRow.locator('.ck-table tbody tr td:nth-child(2)').allInnerTexts();
  created.rowWhat = await verifyRow.locator('.ck-table tbody tr td:nth-child(1)').allInnerTexts();
  const sqlButtons = verifyRow.locator('.ck-table button');
  created.sqlButtons = await sqlButtons.allInnerTexts();
  created.sqlHiddenFirst = await verifyRow.locator('.ck-table pre').first().isHidden();
  await sqlButtons.first().click();
  created.sqlShown = await verifyRow.locator('.ck-table pre').first().innerText();
  // a step that is a sentence for the chat: nothing runs from the card
  const before = calls.length;
  const refreshRow = fr.locator('#next .act', { has: fr.locator('button', { hasText: 'Refresh the model once' }) }).first();
  await refreshRow.locator('button').first().click();
  await page.waitForTimeout(300);
  created.said = said.slice();
  created.callsAfterSay = calls.length - before;
  created.sayNote = (await refreshRow.locator('.out').innerText()).slice(0, 40);
  created.overflow = await fr.locator('html').evaluate(e => e.scrollWidth > e.clientWidth);
  out.created = created;
  await page.close();

  // 2. a gated dry run
  ({ page, fr, calls, said } = await open(browser, 'gated', errors));
  const g = { verdict: await fr.locator('#verdict').innerText(), buttons: await fr.locator('#next .act > button').allInnerTexts() };
  g.note = await fr.locator('#next .act-note').first().innerText();
  g.primary = await fr.locator('#next button.act-create').count();
  const anyway = fr.locator('#next .act > button').nth(1);             // by place: its words change once it is armed
  g.anywayClass = await anyway.getAttribute('class');
  await anyway.click();                                              // the first click only asks
  g.armed = await anyway.innerText();
  g.callsAfterFirstClick = calls.length;
  await fr.locator('#next button', { hasText: 'Build the silver step first' }).first().click();
  await page.waitForTimeout(300);
  g.said = said.slice();
  g.calls = calls.slice();
  out.gated = g;
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
