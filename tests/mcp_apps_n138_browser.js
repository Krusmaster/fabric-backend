// Round n138: either MCP Apps card in Chromium, with this script acting as the host (as mcp_apps_review_browser.js does).
// It reports the ER diagram's geometry in SVG coordinates (each table's box, each edge's points, each label's box), the
// card's text, and what the first button sends and shows, for a host in one of these modes:
//   tools    hostCapabilities.serverTools, answers each tools/call with <reply.json>
//   none     no serverTools in its capabilities (a host that does not proxy tool calls from the view)
//   error    serverTools, but answers tools/call with the JSON-RPC error -32601 (method not found)
//   iserror  serverTools, answers with a CallToolResult that has isError: true
//   silent   serverTools, never answers tools/call (the page clock is moved on by a minute)
//   bytool   serverTools, <reply.json> maps a tool name to its CallToolResult; every button of the card is clicked
// Usage: node mcp_apps_n138_browser.js <card.html> <input.json> <result.json> <reply.json> <width> <light|dark> <mode> [<shot.png>]
const fs = require("fs");
const { chromium } = require("playwright");

const [cardP, inputP, resultP, replyP, widthS, scheme, mode, shot] = process.argv.slice(2);
const [card, input, result, reply] = [cardP, inputP, resultP, replyP].map((p) => fs.readFileSync(p, "utf8"));
const width = Number(widthS);
const CSP = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data:; media-src 'self' data:; connect-src 'none'";
const caps = mode === "none" ? {} : { serverTools: {} };

const host = `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}">
<style>html,body{margin:0}</style></head><body>
<iframe id="view" sandbox="allow-scripts" style="width:${width}px;height:2400px;border:0;display:block"></iframe>
<script>
window.log = []; window.violations = [];
document.addEventListener("securitypolicyviolation", (e) => window.violations.push(e.violatedDirective + " " + e.blockedURI));
const view = document.getElementById("view");
const INPUT = ${input};
const RESULT = ${result};
const REPLY = ${reply};
const MODE = ${JSON.stringify(mode)};
function post(m) { view.contentWindow.postMessage(m, "*"); }
window.addEventListener("message", (e) => {
  if (e.source !== view.contentWindow) return;
  const m = e.data; window.log.push(m);
  if (m.method === "ui/initialize") post({ jsonrpc: "2.0", id: m.id, result: { protocolVersion: "2026-01-26",
      hostCapabilities: ${JSON.stringify(caps)}, hostInfo: { name: "test-host", version: "0" }, hostContext: { theme: "${scheme}" } } });
  if (m.method === "ui/notifications/initialized") {
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: INPUT } });
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: RESULT });
  }
  if (m.method === "tools/call") {
    if (MODE === "tools" || MODE === "none") post({ jsonrpc: "2.0", id: m.id, result: REPLY });
    else if (MODE === "bytool") post({ jsonrpc: "2.0", id: m.id, result: REPLY[m.params.name] });
    else if (MODE === "error") post({ jsonrpc: "2.0", id: m.id, error: { code: -32601, message: "Method not found" } });
    else if (MODE === "iserror") post({ jsonrpc: "2.0", id: m.id, result: { isError: true, content: [{ type: "text", text: "workspace not found" }] } });
  }
});
view.srcdoc = ${JSON.stringify(card).replace(/<\//g, "<\\/")};
</script></body></html>`;

(async () => {
  const browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {});
  const page = await browser.newPage({ viewport: { width, height: 2400 }, colorScheme: scheme, deviceScaleFactor: shot ? 2 : 1 });
  if (mode === "silent") await page.clock.install();
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
    const num = (e, a) => Number(e.getAttribute(a));
    const svg = document.querySelector("#diagram svg");
    let diagram = null;
    if (svg && shown(svg)) {
      const tables = [...svg.querySelectorAll("g.table")].map((g) => {
        const m = /translate\(([-\d.]+),([-\d.]+)\)/.exec(g.getAttribute("transform")), r = g.querySelector("rect");
        return { name: g.getAttribute("data-table"), box: { x: +m[1], y: +m[2], w: num(r, "width"), h: num(r, "height") } };
      });
      const edges = [...svg.querySelectorAll("g.rel")].map((g) => ({
        id: g.getAttribute("data-id"), source: g.getAttribute("data-source"), target: g.getAttribute("data-target"),
        d: g.querySelector("path.line").getAttribute("d"),
        points: g.querySelector("path.line").getAttribute("d").trim().split(/\s+/).map((c) => c.slice(1).split(",").map(Number)) }));
      const labels = [...svg.querySelectorAll("g.label")].map((g) => {
        const r = g.querySelector("rect");
        return { for: g.getAttribute("data-for"), text: [...g.querySelectorAll("text")].map((t) => t.textContent),
                 box: { x: num(r, "x"), y: num(r, "y"), w: num(r, "width"), h: num(r, "height") } };
      });
      diagram = { tables, edges, labels, width: num(svg, "width"), height: num(svg, "height"),
                  svgWidth: svg.getBoundingClientRect().width };
    }
    return {
      verdict: document.getElementById("verdict").textContent,
      result: txt("#result"), attention: txt("#attention-list li"), attentionNone: txt("#attention-none"),
      attentionShown: shown(document.getElementById("attention")),
      outputs: txt("#steps .out"), call: txt("#call"), diagram,
      results: [...document.querySelectorAll(".res-box")].filter(shown).map((o) => ({
        lines: [...o.querySelectorAll(":scope > ul.res:not(.res-q) > li")].map((li) => li.textContent),
        questions: [...o.querySelectorAll("ul.res-q > li")].map((li) => [li.firstChild.textContent, li.querySelector(".res-why").textContent]),
        details: o.querySelector("details") ? { open: o.querySelector("details").open, summary: o.querySelector("details > summary").textContent,
                                                 preShown: o.querySelector("details pre").checkVisibility(), text: o.querySelector("details pre").textContent } : null,
        visible: o.innerText })),
      docWidth: document.documentElement.scrollWidth, viewWidth: document.documentElement.clientWidth,
      background: getComputedStyle(document.body).backgroundColor, text: document.body.innerText };
  });
  const before = await read();
  if (shot) await page.screenshot({ path: shot, fullPage: true });
  let after = null;
  if (mode === "bytool") {
    const buttons = frame.locator(".step button");
    for (let i = 0; i < await buttons.count(); i++) {
      await buttons.nth(i).click();
      await frame.locator(".step .out").nth(i).locator("details").waitFor({ state: "attached", timeout: 10000 });
    }
    after = await read();
    if (shot) await page.screenshot({ path: shot.replace(/\.png$/, "-after.png"), fullPage: true });
  }
  const first = frame.locator("#steps button, button[data-item]").first();
  if (mode !== "bytool" && await first.count()) {
    await first.click();
    if (mode === "silent") await page.clock.runFor(60000);
    const done = mode === "silent" ? /No answer/ : /^(?!Asked the host)./;
    await frame.locator("#steps .out, #call").filter({ hasText: done }).first().waitFor({ timeout: 10000 });
    after = await read();
  }
  const log = await page.evaluate(() => window.log);
  const violations = await page.evaluate(() => window.violations);
  console.log(JSON.stringify({ before, after, log, requests, errors, violations }));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
