// n190: the redesigned home page in Chromium at 375, 768 and 1440 px (light), and 375 and 1440 px (dark): no horizontal
// page scroll, the hero's two CTAs, four intent tiles, the map drawn, visible keyboard focus on a tile and the CTAs, the
// text contrast of the tiles and chips (WCAG AA), prefers-reduced-motion respected; axe-core (WCAG 2.1 A and AA) when it
// is installed. Then each intent tile's address on /check: the run finishes and lands on its part of the result.
// Usage: node tests/n190_browser.js <base url> [screenshot dir]. Prints one JSON object.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
let axeSrc = null;
try { axeSrc = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8"); } catch (e) { axeSrc = null; }

(async () => {
  const [base, shots] = process.argv.slice(2);
  const b = await chromium.launch();
  const out = { errors: [], home: {}, intents: {}, axe: axeSrc ? {} : null };
  const views = [["light", 375], ["light", 768], ["light", 1440], ["dark", 375], ["dark", 1440]];
  for (const [scheme, w] of views) {
    const ctx = await b.newContext({ viewport: { width: w, height: 900 }, colorScheme: scheme, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(`${scheme}-${w}: ${e.message}`));
    await page.goto(base + "/");
    await page.waitForFunction(() => document.querySelector("#map-home svg"), null, { timeout: 30000 }).catch(() => {});
    const r = await page.evaluate(() => {
      const rgb = (s) => (s.match(/[\d.]+/g) || []).slice(0, 4).map(Number);
      const lum = ([r, g, bb]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(bb); };
      const ratio = (a, c) => { const [x, y] = [lum(a), lum(c)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
      const bgOf = (e) => { for (let n = e; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c.length === 3 || (c.length === 4 && c[3] > 0)) return c.slice(0, 3); } return [255, 255, 255]; };
      const contrast = (sel) => [...document.querySelectorAll(sel)].filter((x) => x.offsetParent).map((x) => Math.round(ratio(rgb(getComputedStyle(x).color), bgOf(x)) * 100) / 100);
      const ctas = [...document.querySelectorAll(".hero-ctas a")].map((a) => ({ href: a.getAttribute("href"), text: a.textContent.trim() }));
      const tiles = [...document.querySelectorAll(".intent-tile")].map((a) => ({ href: a.getAttribute("href"), title: a.querySelector("strong").textContent }));
      const nav = [...document.querySelectorAll("#site-nav a")].map((a) => a.textContent.trim());
      const h1 = document.querySelector("h1").getBoundingClientRect();
      return { ctas, tiles, nav, h1: document.querySelector("h1").textContent, h1Top: Math.round(h1.top),
               ctaTop: Math.round(document.querySelector(".hero-ctas").getBoundingClientRect().top),
               overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
               map: !!document.querySelector("#map-home svg"), chips: document.querySelectorAll(".out-grid [data-claim]").length,
               contrast: { tiles: contrast(".intent-tile strong, .intent-tile span, .intent-tile em"), chips: contrast(".chip"),
                           ba: contrast(".ba-points li, .ba-issue summary") },
               tileTransition: getComputedStyle(document.querySelector(".intent-tile")).transitionDuration };
    });
    r.focus = {};
    for (const sel of ['.intent-tile[data-intent="issues"]', '.hero-ctas a[data-cta="demo"]', ".nav-cta"]) {
      if (w < 900 && sel === ".nav-cta") continue;             // the nav is behind the menu button on narrow screens
      await page.focus(sel); await page.keyboard.press("Shift+Tab"); await page.keyboard.press("Tab");
      r.focus[sel] = await page.evaluate((s) => { const e = document.querySelector(s), c = getComputedStyle(e);
        return { active: document.activeElement === e, outline: c.outlineStyle !== "none" && parseFloat(c.outlineWidth) >= 2 }; }, sel);
    }
    if (axeSrc) {
      await page.addScriptTag({ content: axeSrc });
      out.axe[`${scheme}-${w}`] = await page.evaluate(async () => {
        const res = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
        return res.violations.map((v) => ({ id: v.id, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) }));
      });
    }
    if (shots) { fs.mkdirSync(shots, { recursive: true }); await page.screenshot({ path: path.join(shots, `home-${scheme}-${w}.png`), fullPage: true }); }
    out.home[`${scheme}-${w}`] = r;
    await ctx.close();
  }
  for (const intent of ["issues", "map", "model", "agent"]) {
    const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: "reduce" });
    const page = await ctx.newPage();
    page.on("pageerror", (e) => out.errors.push(`${intent}: ${e.message}`));
    await page.goto(base + "/check?example=sample&intent=" + intent);
    try {
      await page.waitForFunction(() => document.documentElement.dataset.check === "done", null, { timeout: 120000 });
      await page.waitForFunction((i) => document.documentElement.dataset.intent === i, intent, { timeout: 10000 });
    } catch (e) { out.intents[intent] = { error: String(e) }; await ctx.close(); continue; }
    await page.waitForTimeout(300);
    out.intents[intent] = await page.evaluate(() => {
      const seen = (id) => { const e = document.getElementById(id); if (!e || e.hidden) return false; const r = e.getBoundingClientRect();
        return r.height > 0 && r.bottom > 0 && r.top < innerHeight; };
      return { intent: document.documentElement.dataset.intent, allOpen: document.getElementById("check-all").open,
               findings: document.querySelectorAll("#check-findings li").length,
               map: seen("check-map"), modelOpen: document.getElementById("check-build-model").getAttribute("aria-expanded") === "true",
               modelShown: !document.getElementById("check-model").hidden, evidence: seen("check-tile-ontology"),
               ontologyTile: !!document.getElementById("check-tile-ontology") };
    });
    if (shots) await page.screenshot({ path: path.join(shots, `check-intent-${intent}.png`) });
    await ctx.close();
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
