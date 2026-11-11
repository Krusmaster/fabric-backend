// n172 (addition 9): the build buttons end to end on the Plan card, under a fake host that runs tools/call (as Claude
// does with hostCapabilities.serverTools) and answers with results the MCP SDK produced for the same calls.
// Founder, 8 November 2026: the dry run was drawn on the card but no Create appeared under it.
// Usage: node mcp_apps_n172_create_browser.js <card.html> <plan.json> <answers.json> <steps.json>
//   plan.json: the plan_backend CallToolResult (as the SDK returned it), with __args
//   answers.json: {"<tool>:dry" | "<tool>:create": CallToolResult}
//   steps.json: [{build: "<label prefix>", within?: "<label prefix of the build whose created card holds it>"}]
// Prints JSON {errors, calls: [{name, arguments}], steps: [{build, dryShown, createVisible, created}]}.
const { chromium } = require('playwright');
const fs = require('fs');
const [cardPath, planPath, answersPath, stepsPath] = process.argv.slice(2);
const card = fs.readFileSync(cardPath, 'utf8'), plan = JSON.parse(fs.readFileSync(planPath, 'utf8'));
const answers = JSON.parse(fs.readFileSync(answersPath, 'utf8')), steps = JSON.parse(fs.readFileSync(stepsPath, 'utf8'));
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 720, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.exposeFunction('kgRecord', (c) => { calls.push(c); });
  const calls = [];
  await page.setContent('<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:680px;height:6000px"></iframe></body>');
  await page.evaluate(([card, plan, answers]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data;
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: { serverTools: {}, openLinks: {} }, hostContext: { toolInfo: { tool: { name: 'plan_backend' } } } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: plan.__args || {} } }, '*');
        const r = Object.assign({}, plan); delete r.__args;
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: r }, '*');
      } else if (m.method === 'tools/call') {
        const a = m.params.arguments || {};
        window.kgRecord({ name: m.params.name, arguments: a });
        const r = answers[m.params.name + ':' + (a.dry_run === false ? 'create' : 'dry')];
        if (r) reply(r); else f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, error: { code: -32000, message: 'no answer in the test for ' + m.params.name } }, '*');
      } else if (m.method === 'ui/open-link') reply({});
    });
    f.srcdoc = card;
  }, [card, plan, answers]);
  await page.waitForTimeout(1200);
  const fr = page.frameLocator('#f');
  const out = [];
  for (const s of steps) {
    const scope = s.within ? fr.locator('.act', { has: fr.locator('button.act-b', { hasText: s.within }) }).first() : fr.locator('#next');
    const row = scope.locator('.act', { has: fr.locator('button.act-b', { hasText: s.build }) }).last();
    await row.locator('button.act-b', { hasText: s.build }).first().click();
    const res = { build: s.build, dryShown: false, createVisible: false, created: false };
    try { await row.locator('.out .res-box').first().waitFor({ timeout: 5000 }); res.dryShown = true; } catch (e) { /* reported */ }
    const create = row.locator('button.act-create').first();
    try { await create.waitFor({ state: 'visible', timeout: 5000 }); res.createVisible = true; } catch (e) { res.note = await row.innerText(); }
    if (res.createVisible) {
      await create.click();                                                 // n218: the first click only asks
      res.armed = await create.innerText();
      res.callsBeforeConfirm = calls.length;
      await create.click();
      try { await row.locator('.act .out').filter({ hasText: /Created|Fabric answered|Open in Fabric/ }).first().waitFor({ timeout: 5000 }); res.created = true; } catch (e) { res.note = await row.innerText(); }
    }
    out.push(res);
  }
  await browser.close();
  process.stdout.write(JSON.stringify({ errors, calls, steps: out }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
