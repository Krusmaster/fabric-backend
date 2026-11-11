// n198: the Data product page in Chromium (tests/test_n198_browser.py). Opens each rendered state of tests/fixtures/n198/
// (written by workload/Workload/app/items/ModelItem/dataProductPage.test.ts from DataProductView.tsx) at 375 and 1280 px,
// light and dark, and reports: horizontal scroll and elements wider than the page; each item's state in words (not only a
// colour or a mark) and its contrast; button heights; the keyboard order (every enabled button and field reached by Tab,
// each with a visible focus outline, nothing disabled reached).
// Usage: node tests/n198_browser.js <fixtures dir> [screenshots dir]. Prints one JSON object.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

(async () => {
  const [dir, shots] = process.argv.slice(2);
  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".html")).sort();
  const b = await chromium.launch();
  const out = { errors: [], runs: [] };
  for (const f of files) {
    for (const width of [375, 1280]) {
      for (const scheme of ["light", "dark"]) {
        const ctx = await b.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
        const page = await ctx.newPage();
        page.on("pageerror", (e) => out.errors.push(`${f}: ${e.message}`));
        await page.goto("file://" + path.resolve(dir, f));
        const r = await page.evaluate(() => {
          const W = window.innerWidth;
          const lum = (c) => {
            const m = c.match(/rgba?\(([^)]+)\)/);
            if (!m) return null;
            const [r, g, b, a] = m[1].split(",").map((x) => parseFloat(x));
            if (a === 0) return null;
            const l = [r, g, b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); });
            return 0.2126 * l[0] + 0.7152 * l[1] + 0.0722 * l[2];
          };
          const bgOf = (el) => {
            for (let e = el; e; e = e.parentElement) {
              const L = lum(getComputedStyle(e).backgroundColor);
              if (L !== null) return L;
            }
            return lum(getComputedStyle(document.documentElement).backgroundColor) ?? (matchMedia("(prefers-color-scheme: dark)").matches ? 0 : 1);
          };
          const ratio = (el) => {
            const a = lum(getComputedStyle(el).color), c = bgOf(el);
            return (Math.max(a, c) + 0.05) / (Math.min(a, c) + 0.05);
          };
          const wide = [...document.querySelectorAll("body *")].filter((e) => {
            const rc = e.getBoundingClientRect();
            const sr = e.closest(".kg-dp-sr") || e.tagName === "STYLE" || e.tagName === "DATALIST" || e.tagName === "OPTION";
            return !sr && rc.width > 0 && (rc.right > W + 1 || rc.left < -1);
          }).map((e) => `${e.tagName}.${e.className}`);
          const states = [...document.querySelectorAll("li[data-state]")].map((li) => {
            const s = li.querySelector(".kg-dp-state");
            const mark = s.querySelector(".kg-dp-mark");
            return { state: li.dataset.state, words: s.textContent.replace(mark ? mark.textContent : "", "").trim(), contrast: ratio(s),
              markHidden: mark ? mark.getAttribute("aria-hidden") === "true" : true };
          });
          const texts = [...document.querySelectorAll(".kg-dp p, .kg-dp-why, .kg-dp-name, .kg-dp button, .kg-dp label, .kg-dp h2, .kg-dp h3")]
            .filter((e) => e.getBoundingClientRect().width > 0).map((e) => ratio(e));
          const buttons = [...document.querySelectorAll(".kg-dp button")].map((x) => x.getBoundingClientRect().height);
          const focusable = [...document.querySelectorAll("button:not([disabled]), input:not([disabled])")].length;
          const disabledDelete = [...document.querySelectorAll("button.kg-dp-danger")].filter((x) => /^Delete \d+ item/.test(x.textContent)).map((x) => x.disabled);
          return { scroll: document.documentElement.scrollWidth - W, wide, states, minText: Math.min(...texts), minButton: Math.min(...buttons, 99),
            focusable, disabledDelete };
        });
        const order = [];
        let visible = true;
        let reachedDisabled = false;
        for (let i = 0; i < 200; i++) {
          await page.keyboard.press("Tab");
          const a = await page.evaluate(() => {
            const e = document.activeElement;
            if (!e || e === document.body) return null;
            const cs = getComputedStyle(e);
            return { tag: e.tagName, text: (e.textContent || e.id || "").trim().slice(0, 60), disabled: !!e.disabled,
              outline: cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2 };
          });
          if (!a) break;
          if (order.length && order[0].tag === a.tag && order[0].text === a.text && order.length >= r.focusable) break;
          order.push(a);
          visible = visible && a.outline;
          reachedDisabled = reachedDisabled || a.disabled;
        }
        if (shots) {
          fs.mkdirSync(shots, { recursive: true });
          await page.screenshot({ path: path.join(shots, `${f.replace(".html", "")}-${width}-${scheme}.png`), fullPage: true });
        }
        out.runs.push({ file: f, width, scheme, ...r, tabbed: order.length, focusVisible: visible, reachedDisabled,
          order: order.map((o) => o.text) });
        await ctx.close();
      }
    }
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
