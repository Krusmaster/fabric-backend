// Round n124: the review_plan card in Chromium, with this script acting as the MCP Apps host (as mcp_apps_card_browser.js
// does for n119's card). The host page sets the specification's restrictive default CSP, which a srcdoc iframe inherits,
// and frames the card with sandbox="allow-scripts". It answers ui/initialize, sends ui/notifications/tool-input and
// ui/notifications/tool-result, reads the diagram, clicks the first decision button and answers that tools/call with
// <reply.json> (a review_plan answer), then reports.
// Usage: node mcp_apps_review_browser.js <card.html> <input.json> <result.json> <reply.json> <width> <light|dark> [<shot.png>]
const fs = require("fs");
const { chromium } = require("playwright");

const [cardP, inputP, resultP, replyP, widthS, scheme, shot] = process.argv.slice(2);
const [card, input, result, reply] = [cardP, inputP, resultP, replyP].map((p) => fs.readFileSync(p, "utf8"));
const width = Number(widthS);
const CSP = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data:; media-src 'self' data:; connect-src 'none'";

const host = `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}">
<style>html,body{margin:0}</style></head><body>
<iframe id="view" sandbox="allow-scripts" style="width:${width}px;height:1600px;border:0;display:block"></iframe>
<script>
window.log = []; window.violations = [];
document.addEventListener("securitypolicyviolation", (e) => window.violations.push(e.violatedDirective + " " + e.blockedURI));
const view = document.getElementById("view");
const INPUT = ${input};
const RESULT = ${result};
const REPLY = ${reply};
function post(m) { view.contentWindow.postMessage(m, "*"); }
window.addEventListener("message", (e) => {
  if (e.source !== view.contentWindow) return;
  const m = e.data; window.log.push(m);
  if (m.method === "ui/initialize") post({ jsonrpc: "2.0", id: m.id, result: { protocolVersion: "2026-01-26",
      hostCapabilities: { serverTools: {} }, hostInfo: { name: "test-host", version: "0" }, hostContext: { theme: "${scheme}" } } });
  if (m.method === "ui/notifications/initialized") {
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: INPUT } });
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: RESULT });
  }
  if (m.method === "tools/call") post({ jsonrpc: "2.0", id: m.id, result: REPLY });
});
view.srcdoc = ${JSON.stringify(card).replace(/<\//g, "<\\/")};
</script></body></html>`;

(async () => {
  const browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {});
  const page = await browser.newPage({ viewport: { width, height: 1600 }, colorScheme: scheme, deviceScaleFactor: shot ? 2 : 1 });
  const requests = [], errors = [];
  page.on("request", (r) => { if (!r.url().startsWith("data:") && r.url() !== "about:blank" && r.url() !== "about:srcdoc") requests.push(r.url()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.setContent(host);
  const frame = page.frameLocator("#view");
  await frame.locator("#diagram svg").waitFor({ state: "visible", timeout: 10000 });
  const f = page.frames().find((x) => x !== page.mainFrame());
  const diagram = await f.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
    const svg = document.querySelector("#diagram svg");
    const tables = [...svg.querySelectorAll("g.table")].map((g) => ({
      name: g.getAttribute("data-table"), finding: g.classList.contains("finding"),
      text: [...g.querySelectorAll("text")].map((t) => t.textContent),
      keys: [...g.querySelectorAll("text.tag.key")].map((t) => t.previousSibling.textContent), box: box(g.querySelector("rect")) }));
    const rels = [...svg.querySelectorAll("g.rel")].map((g) => ({ id: g.getAttribute("data-id"), rule: g.getAttribute("data-rule"),
      finding: g.classList.contains("finding") }));
    const labels = [...svg.querySelectorAll("g.label")].map((g) => ({ for: g.getAttribute("data-for"),
      text: [...g.querySelectorAll("text")].map((t) => t.textContent), box: box(g.querySelector("rect")) }));
    const over = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
    const overlaps = labels.filter((l) => tables.some((t) => over(l.box, t.box))).length +
                     labels.filter((l, i) => labels.some((m, j) => j < i && over(l.box, m.box))).length;
    return { tables, rels, labels, overlaps, svgWidth: svg.getBoundingClientRect().width,
             docWidth: document.documentElement.scrollWidth, viewWidth: document.documentElement.clientWidth,
             colors: { body: getComputedStyle(document.body).backgroundColor, ink: getComputedStyle(document.body).color } };
  });
  const buttons = await frame.locator("button[data-item]").evaluateAll((bs) => bs.map((b) => b.getAttribute("data-item")));
  const before = await frame.locator("body").innerText();
  if (shot) await page.screenshot({ path: shot, fullPage: true });
  let after = null;
  if (buttons.length) {
    await frame.locator("button[data-item]").first().click();
    await frame.locator("#call").filter({ hasText: "review_plan answered" }).waitFor({ timeout: 5000 });
    after = { text: await frame.locator("body").innerText(),
              buttons: await frame.locator("button[data-item]").evaluateAll((bs) => bs.map((b) => b.getAttribute("data-item"))) };
  }
  const log = await page.evaluate(() => window.log);
  const violations = await page.evaluate(() => window.violations);
  console.log(JSON.stringify({ text: before, diagram, buttons, after, log, requests, errors, violations }));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
