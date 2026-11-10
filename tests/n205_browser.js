// n205: /trust in Chromium at 375 and 1280 px, light and dark: the page renders with its headings and tables, no
// horizontal page scroll (a wide table scrolls inside its own box), and the footer links to it.
// Usage: node tests/n205_browser.js <base url>. Prints one JSON object.
const { chromium } = require("playwright");
(async () => {
  const [base] = process.argv.slice(2);
  const b = await chromium.launch();
  const out = { errors: [], runs: {} };
  for (const scheme of ["light", "dark"]) for (const w of [1280, 375]) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(e.message));
    const resp = await page.goto(base + "/trust");
    out.runs[`${scheme}-${w}`] = await page.evaluate((status) => {
      const main = document.querySelector("main");
      const h1 = main.querySelector("h1");
      const r = main.querySelector("article").getBoundingClientRect();
      return { status, h1: h1 ? h1.textContent.trim() : null,
               h2: [...main.querySelectorAll("h2")].map((h) => h.textContent.trim()),
               tables: main.querySelectorAll("table").length,
               articleWidth: Math.round(r.width), articleLeft: Math.round(r.left),
               pageOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
               footerLink: !!document.querySelector('footer a[href="/trust"]'),
               bodyBg: getComputedStyle(document.body).backgroundColor };
    }, resp.status());
    await ctx.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
