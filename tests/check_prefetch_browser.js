// n49: the start page fetches /check's engine ahead only on a pointer or focus on a link to /check, or after a still
// while on a fast connection; then /check is answered by the browser's cache (the server counts the requests: the
// Python side reads its access log).
const { chromium } = require("playwright");
(async () => {
  const [base, exe] = process.argv.slice(2);
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  const engine = (u) => /\/static\/pyodide\/|\/check\/engine\.zip/.test(u);
  // 1. a page left alone for 3 s fetches nothing ahead; left still longer on a fast connection, it does
  {
    const ctx = await b.newContext();
    const page = await ctx.newPage();
    const seen = [];
    ctx.on("request", (r) => { if (engine(r.url())) seen.push(r.url()); });
    page.on("pageerror", (e) => out.errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error") out.errors.push(m.text()); });
    await page.goto(base + "/");
    await page.waitForTimeout(3000);
    out.before_still = seen.length;
    out.connection = await page.evaluate(() => navigator.connection ? { type: navigator.connection.effectiveType, save: navigator.connection.saveData } : null);
    await page.waitForTimeout(6000);
    out.after_still = seen.length;
    await ctx.close();
  }
  // 2. a pointer on a link to /check fetches it ahead, low priority; then /check runs from the cache
  const ctx = await b.newContext();
  const page = await ctx.newPage();
  const seen = [], done = new Set();
  ctx.on("request", (r) => { if (engine(r.url())) seen.push(r.url()); });
  ctx.on("requestfinished", (r) => { if (engine(r.url())) done.add(r.url()); });
  page.on("pageerror", (e) => out.errors.push(e.message));
  await page.goto(base + "/");
  await page.waitForTimeout(500);
  out.before_hover = seen.length;
  await page.hover('a[href="/check"]');
  for (let i = 0; i < 300 && done.size < 7; i++) await page.waitForTimeout(100);
  out.prefetched = [...done].map((u) => u.replace(base, "")).sort();
  console.error("PREFETCHED");
  await page.waitForTimeout(500);
  await page.goto(base + "/check");
  await page.click("#check-sample");
  for (let i = 0; i < 1200; i++) { if (await page.evaluate(() => !!document.documentElement.dataset.checkMs)) break; await page.waitForTimeout(100); }
  out.check_done = await page.evaluate(() => !!document.documentElement.dataset.checkMs);
  out.check_requests = seen.length - out.prefetched.length;
  console.log(JSON.stringify(out));
  await b.close();
})();
