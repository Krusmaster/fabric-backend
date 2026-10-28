// /check in a browser: a CSV with a marker no request may carry, the shop example, 375 px, keyboard, reduced motion.
const { chromium } = require("playwright");
(async () => {
  const [base, exe] = process.argv.slice(2);
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { requests: [], leaks: [], foreign: [], errors: [] };
  const MARK = "zq_marker_7781";
  const ctx = await b.newContext({ reducedMotion: "reduce" });
  ctx.on("request", (r) => {                                      // page and worker requests alike
    const body = r.postData() || "";
    out.requests.push(r.method() + " " + r.url());
    if (r.url().includes(MARK) || body.includes(MARK)) out.leaks.push(r.url());
    if (!r.url().startsWith(base)) out.foreign.push(r.url());
  });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => out.errors.push(e.message));
  await page.goto(base + "/check");
  await page.setInputFiles("#check-files", [
    { name: "customers.csv", mimeType: "text/csv", buffer: Buffer.from(`customer_id,name\n1,${MARK}\n2,b\n`) },
    { name: "orders.csv", mimeType: "text/csv", buffer: Buffer.from("order_id,customer_id,amount\n1,1,10\n2,9,20\n") }]);
  await page.waitForFunction(() => document.documentElement.dataset.check === "done", null, { timeout: 120000 });
  out.files_text = await page.textContent("#check-result");
  // the page itself cannot send anything: a fetch with the marker is refused by its CSP
  out.page_fetch = await page.evaluate(async (m) => { try { await fetch("/x?" + m, { method: "POST", body: m }); return "sent"; } catch (e) { return "blocked"; } }, MARK);
  out.after_requests = out.requests.length;
  // keyboard: Tab to the shop button and press Enter
  await page.goto(base + "/check");
  for (let i = 0; i < 40; i++) { await page.keyboard.press("Tab"); if (await page.evaluate(() => document.activeElement.id) === "check-sample") break; }
  out.focused = await page.evaluate(() => document.activeElement.id);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.documentElement.dataset.checkMs, null, { timeout: 120000 });
  out.sample_text = await page.textContent("#check-result");
  for (const w of [375, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    out["overflow_" + w] = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  }
  console.log(JSON.stringify(out));
  await b.close();
})();
