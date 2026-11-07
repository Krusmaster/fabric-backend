// /check in a browser on the six n150 datasets (tests/fixtures/check_cases): the files are given to the page's own file
// input, as a visitor would, and everything is read from the page and from the files it saves. Arguments: the site, the
// fixtures folder, a folder for the saved files, and the Chromium path (optional). Prints one JSON line.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
(async () => {
  const [base, cases, saveTo, exe] = process.argv.slice(2);
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  let saved = 0;
  async function withPage(name, fn) {
    const ctx = await b.newContext({ reducedMotion: "reduce", acceptDownloads: true, viewport: { width: 1280, height: 900 } });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(name + ": " + e.message));
    const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
    const o = (out[name] = {});
    try {
      await page.goto(base + "/check");
      const dir = path.join(cases, name.split("@")[0]);
      await page.setInputFiles("#check-files", fs.readdirSync(dir).sort().map((f) => path.join(dir, f)));
      await until(() => document.documentElement.dataset.check === "done" && !!document.documentElement.dataset.checkMs);
      const save = async (sel) => {                     // a file the page saves, kept on disk for the test to read
        const [dl] = await Promise.all([page.waitForEvent("download"), page.click(sel)]);
        const to = path.join(saveTo, (++saved) + "_" + dl.suggestedFilename());
        await dl.saveAs(to);
        return to;
      };
      const report = () => save('#check-evidence a.check-dl[download$="_evidence_report.md"]');
      const model = async () => {                       // the Power BI panel, opened (or redrawn) and its zip saved
        await page.click("#check-build-model");
        await until(() => { const m = document.getElementById("check-model"); return !m.hidden && !!m.querySelector('a[download$="_model.zip"]'); });
        return { text: await page.textContent("#check-model"), zip: await save('#check-model a[download$="_model.zip"]') };
      };
      await fn({ page, until, o, save, report, model });
    } catch (e) {
      o.error = String(e && e.stack || e);
    }
    await ctx.close();
  }
  await withPage("04_duplicate_parent", async ({ o, model }) => { o.model = await model(); });
  await withPage("05_sap_mandt", async ({ page, o, model }) => { o.model = await model(); o.findings = await page.textContent("#check-findings"); });
  await b.close();
  console.log(JSON.stringify(out));
})();
