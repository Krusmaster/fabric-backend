// Round n136: the mascots on an MCP Apps card (validate_plan's or review_plan's) in Chromium, with this script as the
// host, framed the way mcp_apps_card_browser.js frames it (the specification's restrictive default CSP, sandbox
// allow-scripts). It sends the call's arguments and result, then reads each figure (shown, pose, glad, sentence), the
// card's text with the mascots on and off (the card's own switch), and the layout (sideways scroll, colours).
// Usage: node mcp_apps_mascots_browser.js <card.html> <input.json> <result.json> <width> <light|dark> [<shot.png>]
const fs = require("fs");
const { chromium } = require("playwright");

const [cardP, inputP, resultP, widthS, scheme, shot] = process.argv.slice(2);
const [card, input, result] = [cardP, inputP, resultP].map((p) => fs.readFileSync(p, "utf8"));
const width = Number(widthS);
const CSP = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data:; media-src 'self' data:; connect-src 'none'";

const host = `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}">
<style>html,body{margin:0}</style></head><body>
<iframe id="view" sandbox="allow-scripts" style="width:${width}px;height:1400px;border:0;display:block"></iframe>
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
      hostCapabilities: { serverTools: {} }, hostInfo: { name: "test-host", version: "0" }, hostContext: { theme: "${scheme}" } } });
  if (m.method === "ui/notifications/initialized") {
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: INPUT } });
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: RESULT });
  }
});
view.srcdoc = ${JSON.stringify(card).replace(/<\//g, "<\\/")};
</script></body></html>`;

(async () => {
  const browser = await chromium.launch(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {});
  const page = await browser.newPage({ viewport: { width, height: 1400 }, colorScheme: scheme, deviceScaleFactor: shot ? 2 : 1 });
  const requests = [], errors = [];
  page.on("request", (r) => { if (!r.url().startsWith("data:") && r.url() !== "about:blank" && r.url() !== "about:srcdoc") requests.push(r.url()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.setContent(host);
  const frame = page.frameLocator("#view");
  await frame.locator("#verdict").filter({ hasNotText: "Waiting for" }).waitFor({ timeout: 10000 });
  const f = page.frames().find((x) => x !== page.mainFrame());
  const read = () => f.evaluate(() => {
    const box = document.getElementById("kg-mascots");
    const shown = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
    const figures = [...box.querySelectorAll("[data-mascot]")].map((li) => ({
      kind: li.getAttribute("data-mascot"), shown: shown(li), pose: li.querySelector("svg").getAttribute("data-pose"),
      glad: li.classList.contains("glad"), who: li.querySelector(".kg-who").textContent,
      text: li.querySelector(".kg-line").textContent,
      confetti: getComputedStyle(li.querySelector(".m-confetti")).opacity, heart: getComputedStyle(li.querySelector(".m-heart")).opacity,
      bubble: getComputedStyle(li.querySelector(".kg-bub")).backgroundColor, ink: getComputedStyle(li.querySelector(".kg-line")).color,
      figWidth: li.querySelector(".kg-fig").getBoundingClientRect().width,
      fill: li.querySelector(".m-body path").getAttribute("fill"),          // n164: which colour the figure wears
      right: li.getBoundingClientRect().right }));
    const t = document.getElementById("kg-toggle");
    return { figures, boxShown: shown(box), toggle: { shown: shown(t), text: t.textContent, pressed: t.getAttribute("aria-pressed") },
             text: document.body.innerText, docWidth: document.documentElement.scrollWidth,
             viewWidth: document.documentElement.clientWidth,
             colors: { body: getComputedStyle(document.body).backgroundColor, ink: getComputedStyle(document.body).color } };
  });
  const on = await read();
  if (shot) await page.screenshot({ path: shot, fullPage: true });
  await frame.locator("#kg-toggle").click();
  const off = await read();
  await frame.locator("#kg-toggle").click();
  const again = await read();
  const log = await page.evaluate(() => window.log);
  const violations = await page.evaluate(() => window.violations);
  console.log(JSON.stringify({ on, off, again, log, requests, errors, violations }));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
