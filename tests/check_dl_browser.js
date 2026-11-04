// n95: /check's downloads under the page's own policy (the local server sends it), at 375 and 1280 px, light and dark:
// no text outside its button's edge, and none of the page outside the viewport. With SHOTS=<dir> it saves screenshots.
const { chromium } = require("playwright");
const path = require("path");
(async () => {
  const [base, exe] = process.argv.slice(2);
  const SHOTS = process.env.SHOTS;
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [], runs: {} };
  for (const scheme of ["light", "dark"]) for (const w of [375, 1280]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(e.message));
    const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
    await page.goto(base + "/check?example=sample");
    await until(() => document.documentElement.dataset.check === "done");
    const measure = () => page.evaluate(() => [...document.querySelectorAll("a.check-dl")].filter((a) => a.offsetParent).map((a) => {
      const box = a.getBoundingClientRect(), r = document.createRange(); r.selectNodeContents(a);
      const outside = [...r.getClientRects()].some((t) => t.left < box.left - 0.5 || t.right > box.right + 0.5 || t.top < box.top - 0.5 || t.bottom > box.bottom + 0.5);
      return { text: a.textContent, outside, overflow: a.scrollWidth > a.clientWidth + 1, offPage: box.right > document.documentElement.clientWidth + 0.5 || box.left < -0.5 };
    }));
    const shot = async (name, sel) => { if (SHOTS) { const el = await page.$(sel); if (el) { await el.scrollIntoViewIfNeeded(); await el.screenshot({ path: path.join(SHOTS, `${name}-${w}-${scheme}.png`) }); } } };
    const items = [];
    await page.evaluate(() => document.getElementById("check-evidence").scrollIntoView());
    items.push(...await measure()); await shot("evidence", "#check-evidence");
    await page.click('[data-ask="product"]');
    await until(() => !!document.querySelector("#check-ask-answer a.check-dl"));
    items.push(...await measure()); await shot("contract", "#check-ask-answer");
    await page.click("#check-build-model");
    await until(() => !!document.querySelector("#check-model a.check-dl"));
    items.push(...await measure()); await shot("model", "#check-model .ctas");
    await page.click("#check-build-app");
    await until(() => !!document.querySelector("#check-app a.check-dl"));
    items.push(...await measure()); await shot("app", "#check-app .ctas");
    const seen = new Map(); items.forEach((i) => seen.set(i.text, Object.assign(seen.get(i.text) || {}, i, { outside: (seen.get(i.text) || {}).outside || i.outside })));
    items.splice(0, items.length, ...seen.values());
    const pageOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    out.runs[scheme + "-" + w] = { items, pageOverflow };
    await ctx.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
