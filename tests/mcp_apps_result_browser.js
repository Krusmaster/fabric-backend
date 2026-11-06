// Round n137: an MCP Apps card (validate_plan's or review_plan's) in Chromium, fed one CallToolResult exactly as given
// (text content with the JSON, the {"result": "<JSON text>"} wrapper, structuredContent, or something unreadable).
// Framed the way mcp_apps_card_browser.js frames it (the specification's restrictive default CSP, sandbox
// allow-scripts). After the card has rendered, it presses the first button (a next step or a decision), answers that
// tools/call with <reply.json> as given, and reports the card's DOM before and after.
// Usage: node mcp_apps_result_browser.js <card.html> <input.json> <result.json> <reply.json>
const fs = require("fs");
const { chromium } = require("playwright");

const [cardP, inputP, resultP, replyP] = process.argv.slice(2);
const [card, input, result, reply] = [cardP, inputP, resultP, replyP].map((p) => fs.readFileSync(p, "utf8"));
const CSP = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data:; media-src 'self' data:; connect-src 'none'";

const host = `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}">
<style>html,body{margin:0}</style></head><body>
<iframe id="view" sandbox="allow-scripts" style="width:520px;height:1600px;border:0;display:block"></iframe>
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
      hostCapabilities: { serverTools: {} }, hostInfo: { name: "test-host", version: "0" }, hostContext: { theme: "light" } } });
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
  const page = await browser.newPage({ viewport: { width: 520, height: 1600 }, deviceScaleFactor: 1 });
  const requests = [], errors = [];
  page.on("request", (r) => { if (!r.url().startsWith("data:") && r.url() !== "about:blank" && r.url() !== "about:srcdoc") requests.push(r.url()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.setContent(host);
  const frame = page.frameLocator("#view");
  await frame.locator("#verdict").filter({ hasNotText: "Waiting for" }).waitFor({ timeout: 10000 });
  const f = page.frames().find((x) => x !== page.mainFrame());
  const read = () => f.evaluate(() => {
    const shown = (e) => !!e && !e.closest("[hidden]") && !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
    const txt = (sel) => [...document.querySelectorAll(sel)].filter(shown).map((e) => e.textContent);
    const box = document.getElementById("kg-mascots");
    const figures = [...box.querySelectorAll("[data-mascot]")].map((li) => ({
      kind: li.getAttribute("data-mascot"), shown: shown(li), pose: li.querySelector("svg").getAttribute("data-pose"),
      glad: li.classList.contains("glad"), text: li.querySelector(".kg-line").textContent }));
    const svg = document.querySelector("#diagram svg");
    const out = {
      verdict: document.getElementById("verdict").textContent,
      attention: txt("#attention-list li"),
      attentionShown: shown(document.getElementById("attention")),
      counts: [...document.querySelectorAll("#counts > div")].filter(shown).map((d) => [d.querySelector("dt").textContent, d.querySelector("dd").textContent]),
      result: (document.getElementById("result") || {}).textContent || "",
      resultShown: shown(document.getElementById("result")),
      steps: txt("#steps .step > p"),
      buttons: [...document.querySelectorAll("main button")].filter(shown).map((b) => b.textContent),
      outputs: txt("#steps pre"),
      decisions: [...document.querySelectorAll("button[data-item]")].filter(shown).map((b) => b.getAttribute("data-item")),
      note: txt("#note"), call: txt("#call"),
      diagram: svg && shown(svg) ? {
        tables: [...svg.querySelectorAll("g.table")].map((g) => ({ name: g.getAttribute("data-table"), finding: g.classList.contains("finding"),
                                                                     text: [...g.querySelectorAll("text")].map((t) => t.textContent) })),
        rels: [...svg.querySelectorAll("g.rel")].map((g) => ({ id: g.getAttribute("data-id"), rule: g.getAttribute("data-rule") })),
        labels: [...svg.querySelectorAll("g.label")].map((g) => [...g.querySelectorAll("text")].map((t) => t.textContent).join(" ")) } : null,
      figures, mascotsShown: shown(box), text: document.body.innerText };
    return out;
  });
  const before = await read();
  let after = null;
  const first = frame.locator("#steps button, button[data-item]").first();
  if (await first.count()) {
    await first.click();
    await frame.locator("#steps pre, #call").filter({ hasNotText: "Asked the host" }).filter({ hasText: /./ }).first().waitFor({ timeout: 10000 });
    after = await read();
  }
  const log = await page.evaluate(() => window.log);
  const violations = await page.evaluate(() => window.violations);
  console.log(JSON.stringify({ before, after, calls: log.filter((m) => m.method === "tools/call"), requests, errors, violations }));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
