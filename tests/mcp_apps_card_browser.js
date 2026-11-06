// Round n119: the validate_plan card in Chromium, with this script acting as the MCP Apps host.
// The host page sets the specification's restrictive default CSP (2026-01-26, "Restrictive Default"), which a srcdoc
// iframe inherits, and frames the card with sandbox="allow-scripts". The host answers ui/initialize, sends
// ui/notifications/tool-input and ui/notifications/tool-result, clicks every button and answers each tools/call.
// Usage: node mcp_apps_card_browser.js <card.html> <input.json> <result.json>   → prints one JSON report.
const fs = require("fs");
const { chromium } = require("playwright");

const [card, input, result] = process.argv.slice(2).map((p) => fs.readFileSync(p, "utf8"));
const CSP = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data:; media-src 'self' data:; connect-src 'none'";

const host = `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}"></head><body>
<iframe id="view" sandbox="allow-scripts" style="width:480px;height:600px;border:0"></iframe>
<script>
window.log = []; window.violations = [];
document.addEventListener("securitypolicyviolation", (e) => window.violations.push(e.violatedDirective + " " + e.blockedURI));
const view = document.getElementById("view");
const INPUT = ${input};
const RESULT = ${result};
function post(m) { view.contentWindow.postMessage(m, "*"); }
window.addEventListener("message", (e) => {
  if (e.source !== view.contentWindow) return;
  const m = e.data; window.log.push(m);
  if (m.method === "ui/initialize") post({ jsonrpc: "2.0", id: m.id, result: { protocolVersion: "2026-01-26",
      hostCapabilities: { serverTools: {} }, hostInfo: { name: "test-host", version: "0" }, hostContext: { theme: "light" } } });
  if (m.method === "ui/notifications/initialized") {
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: INPUT } });
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: RESULT });
  }
  if (m.method === "tools/call") post({ jsonrpc: "2.0", id: m.id, result: { content: [{ type: "text", text: "answer of " + m.params.name }] } });
});
view.srcdoc = ${JSON.stringify(card).replace(/<\//g, "<\\/")};
</script></body></html>`;

(async () => {
  const browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {});
  const page = await browser.newPage();
  const requests = [], errors = [];
  page.on("request", (r) => { if (!r.url().startsWith("data:") && r.url() !== "about:blank" && r.url() !== "about:srcdoc") requests.push(r.url()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.setContent(host);
  const frame = page.frameLocator("#view");
  await frame.locator("#counts").waitFor({ state: "visible", timeout: 10000 });
  const buttons = frame.locator("button");
  const n = await buttons.count();
  for (let i = 0; i < n; i++) {
    await buttons.nth(i).click();
    await frame.locator("pre").nth(i).filter({ hasText: "answer of " }).waitFor({ timeout: 5000 });
  }
  const text = await frame.locator("body").innerText();
  const log = await page.evaluate(() => window.log);
  const violations = await page.evaluate(() => window.violations);
  console.log(JSON.stringify({ text, buttons: n, log, requests, errors, violations }));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
