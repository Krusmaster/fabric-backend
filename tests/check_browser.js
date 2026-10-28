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
  // waitForFunction evaluates a string in newer Playwright, which the page's CSP (no 'unsafe-eval') refuses: poll instead
  const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
  page.on("pageerror", (e) => out.errors.push(e.message));
  await page.goto(base + "/check");
  await page.setInputFiles("#check-files", [
    { name: "customers.csv", mimeType: "text/csv", buffer: Buffer.from(`customer_id,name\n1,${MARK}\n2,b\n`) },
    { name: "orders.csv", mimeType: "text/csv", buffer: Buffer.from("order_id,customer_id,amount\n1,1,10\n2,9,20\n") }]);
  await until(() => document.documentElement.dataset.check === "done");
  out.files_text = await page.textContent("#check-result");
  // the page itself cannot send anything: a fetch with the marker is refused by its CSP
  out.page_fetch = await page.evaluate(async (m) => { try { await fetch("/x?" + m, { method: "POST", body: m }); return "sent"; } catch (e) { return "blocked"; } }, MARK);
  out.after_requests = out.requests.length;
  // keyboard: Tab to the shop button and press Enter
  await page.goto(base + "/check");
  for (let i = 0; i < 40; i++) { await page.keyboard.press("Tab"); if (await page.evaluate(() => document.activeElement.id) === "check-sample") break; }
  out.focused = await page.evaluate(() => document.activeElement.id);
  await page.keyboard.press("Enter");
  await until(() => !!document.documentElement.dataset.checkMs);
  out.sample_text = await page.textContent("#check-result");
  out.steps = await page.$$eval("#check-steps strong", (n) => n.map((x) => x.textContent));
  // reduced motion: the steps column stays empty while the engine runs, then fills at once
  out.steps_while_running = 0;
  await page.click("#check-sap");
  while (await page.evaluate(() => document.documentElement.dataset.check) === "running") {
    out.steps_while_running = Math.max(out.steps_while_running, await page.evaluate(() => document.getElementById("check-run").hidden ? 0 : document.querySelectorAll("#check-steps li").length));
    await page.waitForTimeout(20);
  }
  out.sap_text = await page.textContent("#check-result");
  await page.click("#check-crm");
  await until(() => document.documentElement.dataset.check === "done" && !!document.documentElement.dataset.checkMs);
  await page.waitForTimeout(300);
  out.crm_suggested_edges = await page.evaluate(() => document.querySelectorAll("#check-map .m-sug").length);
  // WCAG AA: the example buttons' text against their soft backgrounds, light and dark
  out.contrast = [];
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    out.contrast.push(...await page.evaluate(() => {
      const rgb = (c) => c.match(/[\d.]+/g).slice(0, 3).map(Number);
      const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
      const out = [];
      for (const b of document.querySelectorAll(".check-ex")) {
        const bg = rgb(getComputedStyle(b).backgroundColor);
        for (const t of b.querySelectorAll("strong, span")) out.push(ratio(rgb(getComputedStyle(t).color), bg));
        const em = b.querySelector("em");
        out.push(ratio(rgb(getComputedStyle(em).color), rgb(getComputedStyle(em).backgroundColor)));
      }
      return out.map((x) => Math.round(x * 100) / 100);
    }));
  }
  for (const w of [375, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    out["overflow_" + w] = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  }
  console.log(JSON.stringify(out));
  await b.close();
})();
