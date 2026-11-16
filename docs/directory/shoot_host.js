// D2: one chat card framed the way a chat host shows an MCP App, written as a PNG cropped to the app response.
// Usage: node shoot_host.js <card.html> <input.json> <result.json> <out.png> <width> <tool name>
// The host page answers ui/initialize (light theme), sends the tool's input and result, grows the frame to the height the
// card reports (ui/notifications/size-changed) or measures, and answers no tools/call: the image shows the first answer.
// The card keeps the specification's restrictive default CSP, inherited by the srcdoc frame, and sandbox="allow-scripts".
const fs = require("fs");
const { chromium } = require("playwright");

const [cardPath, inputPath, resultPath, out, widthArg, tool] = process.argv.slice(2);
const card = fs.readFileSync(cardPath, "utf8");
const input = fs.readFileSync(inputPath, "utf8");
const result = fs.readFileSync(resultPath, "utf8");
const width = Number(widthArg);
const CSP = "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; " +
            "img-src 'self' data:; media-src 'self' data:; connect-src 'none'";
const column = width >= 1000 ? 760 : width - 24;

const host = `<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}">
<style>
  html, body { margin: 0; background: #faf9f5; font: 14px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif; color: #3d3929; }
  .turn { width: ${column}px; margin: 0 auto; padding: 16px 0; }
  .tool { display: flex; gap: 8px; align-items: center; margin: 0 0 8px; color: #6b6656; font-size: 13px; }
  .tool b { font-weight: 600; color: #3d3929; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #c96442; }
  .app { border: 1px solid #e8e4d8; border-radius: 12px; overflow: hidden; background: #fff; }
  iframe { display: block; width: 100%; height: 400px; border: 0; }
</style></head><body>
<div class="turn" id="turn"><div class="tool"><span class="dot"></span><span>Krusgraph · <b>${tool}</b></span></div>
<div class="app"><iframe id="view" sandbox="allow-scripts" title="Krusgraph card"></iframe></div></div>
<script>
const view = document.getElementById("view");
const INPUT = ${input};
const RESULT = ${result};
window.reported = 0;
function post(m) { view.contentWindow.postMessage(m, "*"); }
window.addEventListener("message", (e) => {
  if (e.source !== view.contentWindow) return;
  const m = e.data || {};
  if (m.method === "ui/initialize") post({ jsonrpc: "2.0", id: m.id, result: { protocolVersion: "2026-01-26",
      hostCapabilities: {}, hostInfo: { name: "screenshot-host", version: "0" },
      hostContext: { theme: "light", displayMode: "inline", toolInfo: { tool: { name: ${JSON.stringify(tool)} } } } } });
  else if (m.method === "ui/notifications/initialized") {
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: INPUT } });
    post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: RESULT });
  } else if (m.method === "ui/notifications/size-changed" && m.params && m.params.height) {
    window.reported = Math.ceil(m.params.height); view.style.height = window.reported + "px";
  } else if (m.id !== undefined && m.method) post({ jsonrpc: "2.0", id: m.id, result: {} });
});
view.srcdoc = ${JSON.stringify(card).replace(/<\//g, "<\\/")};
</script></body></html>`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.setContent(host);
  await page.waitForTimeout(1500);                                   // the card renders from the result
  const frame = page.frames().find((f) => f !== page.mainFrame());
  const measured = await frame.evaluate(() => Math.ceil(document.documentElement.scrollHeight));
  const reported = await page.evaluate(() => window.reported);
  const h = Math.max(reported, measured);
  await page.evaluate((h) => { document.getElementById("view").style.height = h + "px"; }, h);
  await page.setViewportSize({ width, height: Math.max(900, h + 120) });
  await page.waitForTimeout(400);
  const box = await page.locator("#turn").boundingBox();
  await page.screenshot({ path: out, clip: { x: 0, y: box.y, width, height: Math.ceil(box.height) } });
  const text = await frame.evaluate(() => document.body.innerText.slice(0, 160).replace(/\s+/g, " "));
  console.log(JSON.stringify({ out, height: Math.ceil(box.height), reported, measured, errors, text }));
  await browser.close();
  if (errors.length) process.exit(2);
})().catch((e) => { console.error(e); process.exit(1); });
