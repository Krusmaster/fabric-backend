// n169: the build card in Chromium under a fake host. Usage: node mcp_apps_build_browser.js <card.html> <data.json> <tools|msg>
// data.json: {args, plan, dry, created}. The host answers tools/call with `dry` for a dry run and `created` otherwise.
// Prints JSON {log, text, errors, reportButtons}: every message the card sent, the card's text, page errors.
const { chromium } = require('playwright');
const fs = require('fs');
const [card, data] = [fs.readFileSync(process.argv[2], 'utf8'), JSON.parse(fs.readFileSync(process.argv[3], 'utf8'))];
const caps = process.argv[4] === 'tools' ? { serverTools: {}, openLinks: {} } : {};
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const log = [], errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.exposeFunction('logMsg', m => log.push(m));
  await page.setContent('<iframe id="f" sandbox="allow-scripts" style="width:700px;height:1600px"></iframe>');
  await page.evaluate(([card, data, caps]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data; window.logMsg(m);
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: caps, hostContext: { toolInfo: { tool: { name: 'plan_backend' } } } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: data.args } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { content: [{ type: 'text', text: JSON.stringify(data.plan) }] } }, '*');
      } else if (m.method === 'tools/call') {
        const r = m.params.arguments.dry_run === false ? data.created : data.dry;
        setTimeout(() => reply({ content: [{ type: 'text', text: JSON.stringify(r) }], structuredContent: r }), 30);
      } else if (m.method === 'ui/message' || m.method === 'ui/open-link') reply({});
    });
    f.srcdoc = card;
  }, [card, data, caps]);
  const fr = page.frameLocator('#f');
  await fr.locator('button', { hasText: 'Build a semantic model' }).click({ timeout: 10000 });
  await page.waitForTimeout(300);
  let reportButtons = 0;
  if (caps.serverTools) {
    await fr.locator('button.act-create').click({ timeout: 10000 });
    await page.waitForTimeout(300);
    await fr.locator('button', { hasText: 'Open in Fabric' }).click({ timeout: 10000 });
    await page.waitForTimeout(200);
    reportButtons = await fr.locator('button', { hasText: 'Create a report on it' }).count();
  }
  const text = await fr.locator('main').innerText();
  await browser.close();
  process.stdout.write(JSON.stringify({ log: log.filter(m => m.method !== 'ui/notifications/size-changed'), text, errors, reportButtons }));
})().catch(e => { process.stderr.write(String(e)); process.exit(1); });
