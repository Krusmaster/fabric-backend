// n225: the Model editor's own pages on a phone (tests/test_n225_phone.py). Opens each page of tests/fixtures/n225/
// (written by workload/Workload/app/items/ModelItem/phonePages.test.tsx with Fluent's styles and ModelItem.scss) at 375,
// 412 and 1280 px and reports: horizontal scroll and elements wider than the page; visible text smaller than 14 px (not
// SVG, not hidden); tap targets (buttons, links, fields, checkboxes with their label, summaries) under 44 px tall.
// Usage: node tests/n225_browser.js <fixtures dir> [screenshots dir]. Prints one JSON object.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

(async () => {
  const [dir, shots] = process.argv.slice(2);
  const files = fs.readdirSync(dir).filter((f) => f.endsWith(".html")).sort();
  const b = await chromium.launch();
  const out = { errors: [], runs: [] };
  for (const f of files) {
    for (const width of [375, 412, 1280]) {
      const ctx = await b.newContext({ viewport: { width, height: 900 } });
      const page = await ctx.newPage();
      page.on("pageerror", (e) => out.errors.push(`${f}: ${e.message}`));
      await page.goto("file://" + path.resolve(dir, f));
      const r = await page.evaluate(() => {
        const W = document.documentElement.clientWidth;
        const shown = (el) => {
          const cs = getComputedStyle(el);
          const box = el.getBoundingClientRect();
          return cs.visibility !== "hidden" && cs.display !== "none" && box.width > 1 && box.height > 1 && !el.closest("[hidden],details:not([open])>*:not(summary)");
        };
        const wide = [];
        for (const el of document.body.querySelectorAll("*")) {
          if (el.closest("svg") || !shown(el)) continue;
          const box = el.getBoundingClientRect();
          if (box.right > W + 1 && !el.closest(".krusgraph-map,.krusgraph-flow,pre")) wide.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 40)} ${Math.round(box.right)}`);
        }
        const small = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          const el = n.parentElement;
          if (!el || !n.textContent.trim() || el.closest("svg,style,script,.kg-dp-sr,[aria-hidden=true]") || !shown(el)) continue;
          const px = parseFloat(getComputedStyle(el).fontSize);
          if (px < 14) small.push(`${px}px "${n.textContent.trim().slice(0, 40)}"`);
        }
        const targets = [];
        const sel = "button,a[href],input:not([type=hidden]),select,textarea,summary,[role=button],[role=tab],[role=checkbox]";
        for (const el of document.body.querySelectorAll(sel)) {
          if (el.closest("svg")) continue;
          const holder = el.closest("label,.fui-Checkbox,.fui-Radio,.fui-Switch") || el;
          if (!shown(holder)) continue;
          const h = Math.max(el.getBoundingClientRect().height, holder.getBoundingClientRect().height);
          targets.push({ what: `${el.tagName.toLowerCase()} "${(holder.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 40)}"`, h: Math.round(h) });
        }
        return { scroll: document.documentElement.scrollWidth - W, wide: wide.slice(0, 20), small: [...new Set(small)].slice(0, 30), targets };
      });
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        await page.screenshot({ path: path.join(shots, `${f.replace(".html", "")}-${width}.png`), fullPage: true });
      }
      out.runs.push({ file: f, width, ...r });
      await ctx.close();
    }
  }
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
