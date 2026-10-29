// /check, n49: Onto hops while the engine loads and is gone with the result; under the result, the Power BI model and
// the app previews with their downloads made in the browser (no request carries them); 375 and 1280 px, keyboard,
// reduced motion, light and dark. n51: the choices in the map column from 1024 px and after the map at 375 px; a click
// scrolls to the preview's heading; the total that doubles beside the right one on the home page's own rows.
const { chromium } = require("playwright");
(async () => {
  const [base, exe] = process.argv.slice(2);
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { requests: [], errors: [] };
  for (const motion of ["no-preference", "reduce"]) {
    const ctx = await b.newContext({ reducedMotion: motion, acceptDownloads: true, viewport: { width: 375, height: 800 } });
    ctx.on("request", (r) => out.requests.push(r.method() + " " + r.url()));
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(e.message));
    const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
    await page.goto(base + "/check");
    const o = (out[motion] = {});
    o.loading_at_start = await page.evaluate(() => !document.getElementById("check-loading").hidden && document.getElementById("check-loading-text").textContent);
    o.hop_animation = await page.evaluate(() => getComputedStyle(document.querySelector(".check-hop")).animationName);
    o.mascot_drawn = await page.evaluate(() => !!document.querySelector("#check-loading svg.mascot"));
    await page.click("#check-crm");
    await until(() => !!document.documentElement.dataset.checkMs);
    o.loading_after_result = await page.evaluate(() => !document.getElementById("check-loading").hidden);
    o.build_shown = await page.evaluate(() => !document.getElementById("check-build-head").hidden && document.getElementById("check-build").hidden);
    const where = () => page.evaluate(() => {
      const r = (id) => document.getElementById(id).getBoundingClientRect();
      const head = r("check-build-head"), map = r("check-map-summary"), steps = r("check-steps");
      const order = ["check-steps", "check-map", "check-build-model", "check-build-app", "check-model"].map((id) => document.getElementById(id));
      return { in_map_col: !!document.getElementById("check-build-head").closest(".check-map-col"),
               right_of_steps: head.left >= steps.right, below_map: head.top >= map.bottom, beside_steps: head.top < steps.bottom,
               dom_order: order.every((n, i) => !i || order[i - 1].compareDocumentPosition(n) & Node.DOCUMENT_POSITION_FOLLOWING) };
    });
    o.at_375 = await where();
    await page.setViewportSize({ width: 1280, height: 900 });
    o.at_1280 = await where();
    await page.setViewportSize({ width: 375, height: 800 });
    const before = out.requests.length;
    // keyboard: focus the model button and press Enter
    await page.focus("#check-build-model");
    await page.keyboard.press("Enter");
    await until(() => !document.getElementById("check-model").hidden);
    o.model_text = await page.textContent("#check-model");
    o.focus = await page.evaluate(() => document.activeElement.id);
    await page.waitForTimeout(1200);                                   // the smooth scroll lands
    o.heading_top = await page.evaluate(() => Math.round(document.getElementById("check-model-h").getBoundingClientRect().top));
    o.next_links = await page.$$eval("#check-build-next a", (a) => a.map((x) => x.textContent + " " + x.getAttribute("href")));
    const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#check-model a[download]")]);
    o.download_name = dl.suggestedFilename();
    const fs = require("fs"), p = await dl.path();
    o.download_head = fs.readFileSync(p).subarray(0, 2).toString();          // "PK": a zip
    o.download_size = fs.statSync(p).size;
    await page.click("#check-build-app");
    await until(() => !document.getElementById("check-app").hidden);
    o.app_text = await page.textContent("#check-app");
    o.app_rows = await page.$$eval("#check-app tbody tr", (r) => r.length);
    o.requests_while_building = out.requests.slice(before);
    for (const w of [375, 1280]) {
      await page.setViewportSize({ width: w, height: 900 });
      o["overflow_" + w] = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
    }
    o.contrast = [];
    for (const scheme of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme: scheme });
      o.contrast.push(...await page.evaluate(() => {
        const rgb = (c) => c.match(/[\d.]+/g).slice(0, 3).map(Number);
        const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
        const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
        const bg = (n) => { while (n) { const c = getComputedStyle(n).backgroundColor; if (!/rgba\(.*, 0\)|transparent/.test(c)) return rgb(c); n = n.parentElement; } return [255, 255, 255]; };
        return [...document.querySelectorAll("#check-model .check-kpis li span, #check-app .check-kpis li span, #check-app td, .check-bar-l, #check-loading-text")]
          .map((t) => Math.round(ratio(rgb(getComputedStyle(t).color), bg(t)) * 100) / 100);
      }));
    }
    if (motion === "reduce") {
      // the shop example: no header amount, so no comparison; then the home page's two tables as files
      await page.click("#check-sample");
      await until(() => document.documentElement.dataset.check === "done" && !document.getElementById("check-build-head").hidden);
      await page.click("#check-build-model");
      await until(() => !document.getElementById("check-model").hidden);
      o.shop_doubled = await page.evaluate(() => !!document.querySelector("#check-model .check-doubled"));
      await page.setInputFiles("#check-files", [
        { name: "orders.csv", mimeType: "text/csv", buffer: Buffer.from(process.env.CHECK_ORDERS) },
        { name: "order_lines.csv", mimeType: "text/csv", buffer: Buffer.from(process.env.CHECK_LINES) }]);
      await until(() => document.documentElement.dataset.check === "done" && !document.getElementById("check-build-head").hidden);
      await page.click("#check-build-model");
      await until(() => !document.getElementById("check-model").hidden);
      o.files_doubled = await page.$$eval("#check-model .check-doubled li", (l) => l.map((x) => x.textContent));
    }
    await ctx.close();
  }
  console.log(JSON.stringify(out));
  await b.close();
})();
