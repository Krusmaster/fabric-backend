// n188: /check's four "Go further" tiles in Chromium: a 2 x 2 grid at 1280 px and stacked at 375 px, light and dark;
// each tile's download still saves its file; the text contrast of every tile (WCAG AA) and a visible keyboard focus.
// Usage: node tests/n188_browser.js <base url>. Prints one JSON object.
const { chromium } = require("playwright");
(async () => {
  const [base] = process.argv.slice(2);
  const b = await chromium.launch();
  const out = { errors: [], runs: {} };
  for (const scheme of ["light", "dark"]) for (const w of [1280, 375]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, reducedMotion: "reduce", acceptDownloads: true });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(e.message));
    const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
    await page.goto(base + "/check?example=sample");
    await until(() => document.documentElement.dataset.check === "done" && !document.getElementById("check-evidence").hidden);
    const run = await page.evaluate(() => {
      const ids = ["check-build-model", "check-build-app", "check-tile-ontology", "check-tile-evidence"];
      const rgb = (s) => (s.match(/[\d.]+/g) || []).slice(0, 4).map(Number);
      const lum = ([r, g, bb]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bb); };
      const ratio = (a, c) => { const [x, y] = [lum(a), lum(c)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
      const bgOf = (e) => { for (let n = e; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c.length === 3 || (c.length === 4 && c[3] > 0)) return c.slice(0, 3); } return [255, 255, 255]; };
      const tiles = ids.map((id) => {
        const t = document.getElementById(id), r = t.getBoundingClientRect(), bg = rgb(getComputedStyle(t).backgroundColor).slice(0, 3);
        const texts = [...t.querySelectorAll("strong, span, p")].filter((x) => x.offsetParent && x.textContent.trim() && !x.closest(".kg-tip-body"))
          .map((x) => ({ text: x.textContent.trim().slice(0, 40), ratio: Math.round(ratio(rgb(getComputedStyle(x).color), bgOf(x)) * 100) / 100 }));
        return { id, cls: t.className, title: (t.querySelector("strong") || {}).textContent, left: Math.round(r.left), top: Math.round(r.top),
                 width: Math.round(r.width), bg, texts, link: (t.querySelector("a.check-dl") || {}).textContent || null,
                 tip: !!t.querySelector(".kg-tip-q") };
      });
      const grid = document.querySelector(".check-build-choices"), st = document.querySelector("#check-evidence > .check-dl-status");
      return { tiles, columns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
               status: st ? st.textContent : null, statusBelow: st ? st.getBoundingClientRect().top >= Math.max(...tiles.map((t) => t.top)) : false,
               pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth };
    });
    // keyboard focus on each tile's download: an outline is drawn
    run.focus = {};
    for (const sel of ['#check-tile-ontology a.check-dl', '#check-tile-evidence a.check-dl', '#check-build-model']) {
      await page.focus(sel); await page.keyboard.press("Shift+Tab"); await page.keyboard.press("Tab");
      run.focus[sel] = await page.evaluate((s) => { const e = document.querySelector(s), c = getComputedStyle(e);
        return { active: document.activeElement === e, outline: c.outlineStyle !== "none" && parseFloat(c.outlineWidth) >= 2 }; }, sel);
    }
    // each tile's download saves its file
    run.downloads = {};
    for (const sel of ['#check-tile-ontology a.check-dl', '#check-tile-evidence a.check-dl']) {
      const [d] = await Promise.all([page.waitForEvent("download"), page.click(sel)]);
      const text = require("fs").readFileSync(await d.path(), "utf8");
      run.downloads[sel] = { name: d.suggestedFilename(), head: text.slice(0, 40), bytes: text.length };
    }
    out.runs[scheme + "-" + w] = run;
    await ctx.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
