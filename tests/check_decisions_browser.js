// n85: /check's evidence report carries the decisions taken on the page. The guided demo at 375 and 1280 px: the report
// downloaded before any decision, after Accept, after changing to Reject, back on the step, and after a new run; every
// request the browser makes is recorded, and what the page keeps in storage. Then the four example buttons: how many
// lines each description takes at 375 px, at 1280 px and at the narrowest width where the four sit in one row.
const { chromium } = require("playwright");
const fs = require("fs");
(async () => {
  const [base, exe] = process.argv.slice(2);
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  for (const w of [375, 1280]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 800 }, reducedMotion: "reduce", acceptDownloads: true });
    const requests = [];
    ctx.on("request", (r) => requests.push({ method: r.method(), url: r.url(), body: r.postData() || "" }));
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(w + ": " + e.message));
    page.on("console", (m) => { if (m.type() === "error") out.errors.push(w + ": " + m.text()); });
    // waitForFunction evaluates a string in newer Playwright, which the page's CSP refuses: poll instead
    const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
    const save = async () => {
      const [d] = await Promise.all([page.waitForEvent("download"), page.click('#check-evidence a.check-dl[download$="_evidence_report.md"]')]);
      return { name: d.suggestedFilename(), text: fs.readFileSync(await d.path(), "utf8") };
    };
    const r = { downloads: {} };
    await page.goto(base + "/check?example=sample&guide=1");
    await until(() => !!document.documentElement.dataset.checkMs && document.getElementById("check-guide").dataset.step === "1");
    r.requestsAtDone = requests.length;
    r.downloads.none = await save();
    for (let i = 0; i < 2; i++) await page.click("#check-guide-next");
    r.step = await page.textContent("#check-guide-h");
    r.before = Date.now();
    await page.click("#check-guide-text >> text=Accept");
    await until(() => document.documentElement.dataset.decided === "done");   // n150: the engine has the decision
    r.saidAccepted = await page.textContent(".check-guide-said");
    r.downloads.accepted = await save();
    await page.click("#check-guide-text >> text=Reject");
    await until(() => document.documentElement.dataset.decided === "done");
    r.saidRejected = await page.textContent(".check-guide-said");
    r.downloads.rejected = await save();
    r.after = Date.now();
    await page.click("#check-guide-back"); await page.click("#check-guide-next");
    r.saidAfterBack = await page.textContent(".check-guide-said");
    r.downloads.again = await save();
    r.layout = await page.evaluate(() => {
      const box = (s) => { const x = document.querySelector(s).getBoundingClientRect(); return { left: Math.round(x.left), right: Math.round(x.right) }; };
      return { scrollWidth: document.documentElement.scrollWidth, said: box(".check-guide-said"),
               buttons: [...document.querySelectorAll("#check-guide-text button, #check-evidence a")].map((a) => { const x = a.getBoundingClientRect(); return [Math.round(x.left), Math.round(x.right)]; }) };
    });
    r.storage = await page.evaluate(() => ({ local: JSON.stringify(Object.assign({}, localStorage)), session: JSON.stringify(Object.assign({}, sessionStorage)), cookie: document.cookie }));
    r.requestsAfter = requests.slice(r.requestsAtDone);
    if (w === 1280) {                                  // a new run starts without the decisions of the last one
      await page.click("#check-crm");
      await until(() => document.documentElement.dataset.check === "done" && document.getElementById("check-status").textContent.includes("Salesforce + ERP"));
      await page.click("#check-sample");
      await until(() => document.documentElement.dataset.check === "done" && document.getElementById("check-status").textContent.includes("A total that doubles"));
      r.downloads.newRun = await save();
    }
    r.requestBodies = requests.filter((q) => q.body).map((q) => q.url);
    out["guide@" + w] = r;
    await ctx.close();
  }
  // the four example buttons: lines per description, from its height and its line height
  const lines = async (w) => {
    const page = await b.newPage({ viewport: { width: w, height: 800 } });
    await page.goto(base + "/check");
    const r = await page.$$eval(".check-examples .check-ex", (bs) => bs.map((bt) => {
      const s = bt.querySelector("span"), cs = getComputedStyle(s), lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
      return { id: bt.id, title: bt.querySelector("strong").textContent, text: s.textContent, lines: Math.round(s.getBoundingClientRect().height / lh), top: Math.round(bt.getBoundingClientRect().top) };
    }));
    await page.close();
    return { width: w, inRow: new Set(r.map((x) => x.top)).size === 1, buttons: r };
  };
  let lo = 376, hi = 1280;                            // the narrowest width where the four share a row
  if (!(await lines(hi)).inRow) throw new Error("not in one row at 1280");
  while (lo < hi) { const mid = Math.floor((lo + hi) / 2); if ((await lines(mid)).inRow) hi = mid; else lo = mid + 1; }
  out.examples = [await lines(375), await lines(hi), await lines(hi - 1), await lines(1280)];
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
