// n158 (review of 8 November 2026): /check in Chromium. M3: the Power BI and app panels of the shop example carry no
// literal "null"; L10: a finding that says "Accept" has a button for it; L12: the file chooser does not offer .txt.
const { chromium } = require("playwright");
(async () => {
  const [base, exe] = process.argv.slice(2);
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  const ctx = await b.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => out.errors.push(e.message));
  const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
  await page.goto(base + "/check?example=sample");
  await until(() => document.documentElement.dataset.check === "done" && !document.getElementById("check-build-head").hidden);
  await page.click("#check-build-model");
  await until(() => !document.getElementById("check-model").hidden);
  out.model_text = await page.textContent("#check-model");
  await page.click("#check-build-app");
  await until(() => !document.getElementById("check-app").hidden);
  out.app_text = await page.textContent("#check-app");
  out.accept = await page.getAttribute("#check-files", "accept");
  // a keyless CSV: every finding whose next step says Accept must have the button for it
  await page.setInputFiles("#check-files", [{ name: "events.csv", mimeType: "text/csv", buffer: Buffer.from(process.env.CHECK_KEYLESS) }]);
  await until(() => document.documentElement.dataset.check === "done");
  out.keyless = await page.evaluate(() => [...document.querySelectorAll("#check-findings > li, #check-suggestions > li")].map((li) => ({
    text: li.textContent, buttons: li.querySelectorAll("button[data-decide]").length })));
  await ctx.close();
  console.log(JSON.stringify(out));
  await b.close();
})();
