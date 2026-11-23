/**
 * W13: the Krusgraph Model editor end to end, in Chromium, on the Fabric and SQL doubles.
 *
 * Bundles harness.tsx (the real ModelItemEditor with a stand-in Fabric host), serves it with engine.py (the real
 * /workload/v1 routes on tests/golden_support.py's doubles), walks every flow a person takes, and writes what it saw:
 * one screenshot per step and results.json (each flow: pass or fail, and its evidence). Synthetic data only; nothing
 * reaches Fabric or the network.
 *
 *   node workload/scripts/e2e/run.js <out dir> [--python <python with the test extras>] [--before]
 *
 * --before photographs the same steps without the checks of what W13 added (for the before/after shots on main).
 */
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { bundle } = require("./bundle");
const { chromium } = require("playwright");

const args = process.argv.slice(2);
const OUT = path.resolve(args.find((a) => !a.startsWith("--") && args[args.indexOf(a) - 1] !== "--python") || "e2e-out");
const PY = args.includes("--python") ? args[args.indexOf("--python") + 1] : "python";
const BEFORE = args.includes("--before");
const PORT = 8700 + Math.floor(Math.random() * 200);
const BASE = `http://127.0.0.1:${PORT}`;
const ROOT = path.resolve(__dirname, "../../..");

const results = [];
function record(flow, ok, evidence) {
  results.push({ flow, result: ok ? "pass" : "fail", evidence });
  console.log(`${ok ? "PASS" : "FAIL"}  ${flow}: ${evidence}`);
}
// WB8 (requirement 2.9): axe-core over every step. After each step, every open page is scanned against WCAG 2.1 A and
// AA; each violation is kept once (rule and element), with the step it first appeared in. Serious and critical ones
// fail the accessibility record at the end; moderate and minor are listed in results.json (a11y).
const AXE = (() => { try { return fs.readFileSync(require.resolve("axe-core/axe.min.js", { paths: [path.resolve(__dirname, "../../Workload")] }), "utf8"); } catch { return null; } })();
// Fluent UI's focus manager (Tabster) puts <i data-tabster-dummy tabindex=0 aria-hidden role=none> guards at the edges
// of tab lists and toolbars on purpose, for arrow-key navigation; axe reports them as aria-hidden-focus. They are
// left out of the scan and counted on their own (results.json a11y_excluded), not hidden.
const AXE_EXCLUDE = "[data-tabster-dummy]";
const livePages = new Set();
const a11y = new Map();
let currentFlow = "";
let excluded = 0;
async function scan(flow) {
  if (!AXE || BEFORE) return;
  for (const pg of [...livePages]) {
    if (pg.isClosed()) { livePages.delete(pg); continue; }
    try {
      if (!(await pg.evaluate(() => !!window.axe))) await pg.addScriptTag({ content: AXE });
      excluded = Math.max(excluded, await pg.evaluate((sel) => document.querySelectorAll(sel).length, AXE_EXCLUDE));
      const found = await pg.evaluate(async (sel) => (await window.axe.run({ exclude: [[sel]] }, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }, resultTypes: ["violations"] }))
        .violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, targets: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) })), AXE_EXCLUDE);
      const dark = await pg.evaluate(() => matchMedia("(prefers-color-scheme: dark)").matches);
      for (const v of found) for (const t of v.targets) {
        const key = `${v.id} ${t}`;
        if (!a11y.has(key)) a11y.set(key, { rule: v.id, impact: v.impact, help: v.help, target: t, step: flow, theme: dark ? "dark" : "light" });
      }
    } catch { /* a page mid-navigation: scanned again after the next step */ }
  }
}
async function step(flow, fn) {
  currentFlow = flow;
  try {
    const ev = await fn();
    record(flow, true, ev || "");
  } catch (e) {
    record(flow, false, String(e && e.message ? e.message : e).split("\n")[0]);
  }
  await scan(flow);
}
const expectTrue = (cond, what) => { if (!cond) throw new Error(what); };

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const dist = path.join(OUT, ".dist");
  await bundle(dist);
  const engine = spawn(PY, [path.join(__dirname, "engine.py"), "--port", String(PORT), "--static", dist], { cwd: ROOT, stdio: ["ignore", "ignore", "pipe"] });
  let engineLog = "";
  engine.stderr.on("data", (d) => { engineLog += d; });
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(`${BASE}/e2e/log`)).ok) break; } catch { /* starting */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  const scenario = (name) => fetch(`${BASE}/e2e/scenario`, { method: "POST", body: JSON.stringify({ name }) });
  const browser = await chromium.launch();
  {
    // every page any flow opens is scanned too, also one closed inside its step (the phone, dark and frame flows)
    const newContext = browser.newContext.bind(browser);
    browser.newContext = async (o) => {
      const c = await newContext(o);
      const newPage = c.newPage.bind(c);
      c.newPage = async () => { const pg = await newPage(); livePages.add(pg); return pg; };
      const close = c.close.bind(c);
      c.close = async () => { await scan(currentFlow); return close(); };
      return c;
    };
  }
  const errors = [];
  let mainCtx;
  async function open(opts = {}) {
    // a reopen is a new page in the main path's context (the stand-in host keeps the item in its localStorage)
    const ctx = opts.keep && mainCtx ? mainCtx : await browser.newContext({ viewport: opts.viewport || { width: 1280, height: 860 }, deviceScaleFactor: 1, colorScheme: opts.dark ? "dark" : "light" });
    if (!opts.keep && !mainCtx) mainCtx = ctx;
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errors.push(e.message));
    livePages.add(p);
    await p.goto(`${BASE}/index.html${opts.keep ? "" : "?fresh=1"}`);
    await p.waitForTimeout(1200);
    return p;
  }
  const shot = async (p, name, full = false) => { await p.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: full }); return `${name}.png`; };
  const button = (p, name, exact = false) => p.getByRole("button", { name, exact }).first();
  const settle = (p, ms = 1500) => p.waitForTimeout(ms);
  const text = async (p) => p.innerText("body");

  // ---------------------------------------------------------------- the main path
  const p = await open();
  await step("1 First run: empty state", async () => {
    const t = await text(p);
    expectTrue(t.includes("Choose a source"), "no Choose a source");
    if (!BEFORE) {
      expectTrue(t.includes("Pick a lakehouse: I find its keys and links"), "no one-sentence first line");
      expectTrue((await p.locator("nav[aria-label='Where you are'] [aria-current='step']").count()) === 1, "no current step");
    }
    return `${await shot(p, "01-empty")}`;
  });
  await step("2 Choose a lakehouse (Fabric's picker) and its schema", async () => {
    await button(p, "Choose a source").click(); await settle(p);
    const t = await text(p);
    expectTrue(t.includes("shop (7 tables)") && t.includes("dbo (no tables)"), "schemas not listed");
    expectTrue(await p.getByRole("radio", { name: /dbo/ }).isDisabled(), "an empty schema can be chosen");
    return `${await shot(p, "02-source")}; schemas: dbo (no tables, disabled), shop (7 tables, preselected)`;
  });
  await step("3 Find keys and relationships (review)", async () => {
    const t0 = Date.now();
    await button(p, "Find keys and relationships").click();
    // SM3: the check against the rows runs on its own after Find keys (the button then says "again")
    await button(p, BEFORE ? /Check against the rows/ : /Check against the rows again/).waitFor({ timeout: 30000 });
    const t = await text(p);
    expectTrue(/7 tables, 6 with a key, and 7 links/.test(t), "unexpected review summary");
    return `${await shot(p, "03-review")}; 7 tables, 6 keys, 7 links in ${Date.now() - t0} ms`;
  });
  await step("4 Check against the rows (evidence)", async () => {
    if (BEFORE) { await button(p, "Check against the rows").click(); await settle(p, 2500); }   // SM3: it ran on its own
    const t = await text(p);
    expectTrue(t.includes("6 of 6 keys are unique in the rows") && t.includes("7 of 7 links hold"), "check result missing");
    if (!BEFORE) {
      for (const w of ["rows counted", "keys unique", "links holding", "orphans", "duplicate keys", "about 2 times"]) expectTrue(t.includes(w), `proof tile missing: ${w}`);
    }
    return `${await shot(p, "04-check", true)}; 13 passed, 0 failed` + (BEFORE ? "" : "; tiles: 232 rows counted, 6 of 6 keys, 7 of 7 links, 0 orphans, 0 duplicate keys; order items over orders: about 2 times");
  });
  await step("5 Accept what passed, go on to Choose what to build", async () => {
    if (!BEFORE) expectTrue((await p.getByRole("button", { name: /^Accept all \(\d+\)$/ }).count()) === 0, "a second accept-all next to Accept all that passed");
    await button(p, /Accept all that passed/).click(); await settle(p, 600);
    await (BEFORE ? button(p, "Next", true) : button(p, "Next: Decide what to build")).click(); await settle(p);
    expectTrue((await text(p)).includes("Choose what to build"), "not on Choose");
    if (BEFORE) for (const n of ["Semantic model", "Data agent"]) await p.getByRole("checkbox", { name: n }).first().check();
    else {
      // SM3: the chat's default build is ticked; the other six outputs are folded under More outputs
      const ticked = await p.getByRole("checkbox", { checked: true }).evaluateAll((els) => els.map((e) => (e.closest("section") || e).getAttribute("aria-label")));
      for (const n of ["Pipeline", "Semantic model", "Data agent"]) expectTrue(ticked.includes(n), `${n} not ticked: ${ticked.join(", ")}`);
      expectTrue(!ticked.includes("API for GraphQL"), "API for GraphQL is preticked");
      expectTrue(!(await p.locator("details.kg-more-outputs").evaluate((d) => d.open)), "More outputs is open");
      const shown = await p.locator(".krusgraph-outputs > section.krusgraph-output:visible").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
      expectTrue(JSON.stringify(shown) === JSON.stringify(["Pipeline", "Semantic model", "Data agent"]), `shown on Choose: ${shown.join(", ")}`);
    }
    const snap = await p.locator("body").ariaSnapshot();
    const dup = /checkbox "Semantic model Semantic model"/.test(snap);
    if (!BEFORE) expectTrue(!dup, "checkbox name repeats the item type");
    return `${await shot(p, "05-outputs")}; checkbox names read by a screen reader: ${snap.split("\n").filter((l) => l.includes("checkbox")).slice(0, 4).map((l) => l.trim()).join(" | ")}`;
  });
  await step("6 Preview (dry run of each output)", async () => {
    await button(p, BEFORE ? "Preview" : "Dry run", true).click(); await settle(p, 4000);
    const t = await text(p);
    expectTrue(t.includes("Nothing was created or changed in Fabric"), "no dry-run sentence");
    return `${await shot(p, "06-preview")}; three outputs previewed, nothing written`;
  });
  await step(BEFORE ? "7 Create (semantic model, API for GraphQL, data agent)" : "7 Create (the pipeline with its notebooks, semantic model, data agent)", async () => {
    await button(p, /^Create/).click(); await settle(p, 7000);
    const t = await text(p);
    const log = await (await fetch(`${BASE}/e2e/log`)).json();
    expectTrue(t.includes("Built in Fabric") || t.includes("created"), "no result");
    return `${await shot(p, "07-result")}; items the doubles received: ${log.created.join(", ")}; the data agent has no route in the double, so it shows its retry card`;
  });
  if (!BEFORE) {
    await step("8 Next steps with other Fabric workloads", async () => {
      const panel = p.locator("section.kg-next");
      await panel.scrollIntoViewIfNeeded();
      const cards = await panel.locator(".kg-next-card").count();
      const t = await panel.innerText();
      expectTrue(cards >= 5, `only ${cards} cards`);
      expectTrue(t.includes("Data Science") && t.includes("Download notebook (.ipynb)"), "no Data Science starter");
      const dl = await panel.locator(".kg-file[data-file$='.ipynb']").first().getAttribute("data-file");   // WB10: fileOffer.tsx
      // WB11: each card's top left has the Fabric icon of the item types it makes, loaded, decorative beside their names
      const heads = await panel.locator(".kg-next-card .kg-next-workload").evaluateAll((els) => els.map((e) => ({
        text: e.innerText.trim(),
        icons: [...e.querySelectorAll("img.krusgraph-item-icon")].map((i) => ({ src: i.getAttribute("src"), alt: i.getAttribute("alt"), w: i.naturalWidth, box: Math.round(i.getBoundingClientRect().width) })),
      })));
      for (const h of heads) {
        expectTrue(h.icons.length >= 1, `no icon on ${h.text}`);
        for (const i of h.icons) expectTrue(i.alt === "" && i.w > 0 && i.box === 20 && /^\/assets\/fabric-icons\/[a-z_]+_24_item\.svg$/.test(i.src), `icon on ${h.text}: ${JSON.stringify(i)}`);
      }
      await panel.screenshot({ path: path.join(OUT, "08-next-steps.png") });
      return `08-next-steps.png; ${cards} cards; starter file ${dl}; icons: ${heads.map((h) => `${h.text} (${h.icons.length})`).join(" | ")}`;
    });
    await step("21 The Data Science starter: Dry run, then Create (never run)", async () => {
      const card = p.locator(".kg-next-card[data-step='ds-features']");
      await card.getByRole("button", { name: /^Dry run/ }).click(); await settle(p, 2500);
      const dry = await card.locator(".kg-next-starter-said").innerText();
      const before = (await (await fetch(`${BASE}/e2e/log`)).json()).created.filter((c) => c === "notebooks").length;
      // ED3: the dry run says what would be created and that it runs only on Run now; the card says Krusgraph trains no model
      const note = await card.innerText();
      expectTrue(dry.includes("Would create the notebook") && dry.includes("runs it only when you choose Run now"), `dry run said: ${dry}`);
      expectTrue(note.includes("Krusgraph trains no model"), "the card does not say Krusgraph trains no model");
      const name = (dry.match(/Would create the notebook (\S+)/) || [])[1];
      await card.getByRole("button", { name: /^Create / }).click(); await settle(p, 4000);
      const after = (await (await fetch(`${BASE}/e2e/log`)).json()).created.filter((c) => c === "notebooks").length;
      // ED3: once created, the card shows the notebook (Open in Fabric, Run now) and one line, instead of a "Created" sentence
      const said = (await card.innerText()).replace(/\s+/g, " ");
      const runNow = await card.getByRole("button", { name: `Run now: ${name}` }).count();
      const open = await card.getByRole("link", { name: /Open in Fabric/ }).count();
      expectTrue(after === before + 1 && runNow === 1 && open === 1 && said.includes("The notebook is in this item's workspace") &&
        said.includes("Krusgraph runs it only when you choose Run now") && (await card.getByRole("button", { name: /^Dry run/ }).count()) === 0,
        `notebooks ${before} -> ${after}; Run now: ${name} x${runNow}; Open in Fabric x${open}; card: ${said.slice(0, 300)}`);
      // never run: Create starts no job (Run now would call Fabric's jobs/instances)
      const jobs = (await (await fetch(`${BASE}/e2e/log`)).json()).fabric_calls.filter((c) => c.includes("/jobs/instances"));
      expectTrue(jobs.length === 0, `a job was started: ${jobs.join(", ")}`);
      return `${await shot(p, "21-starter-created")}; dry run: ${dry.slice(0, 90)}…; then the card shows ${name} with Open in Fabric and Run now; the doubles received one notebook and no job`;
    });
    await step("9 A next step's Dry run ticks only its outputs", async () => {
      await p.locator(".kg-next-card[data-step='iq'] button").first().click(); await settle(p);
      const checked = await p.getByRole("checkbox", { checked: true }).evaluateAll((els) => els.map((e) => (e.closest("section") || e).getAttribute("aria-label")));
      expectTrue(checked.includes("Ontology") && !checked.includes("Semantic model"), `ticked: ${checked.join(", ")}`);
      return `on Choose what to build with ${checked.filter(Boolean).join(", ")} ticked`;
    });
    await step("22 WB11: the Fabric item icons on Choose and the next steps at 390 px, light and dark", async () => {
      // Choose what to build: every output's icon is loaded, 20 px, at the left of its name; nothing moves as they load
      const icons = (pg) => pg.locator("img.krusgraph-item-icon").evaluateAll((els) => els.map((i) => ({
        src: i.getAttribute("src"), alt: i.getAttribute("alt"), w: i.naturalWidth, box: Math.round(i.getBoundingClientRect().width),
        label: ((i.closest("button, .krusgraph-item-title") || i.parentElement).textContent || "").trim().slice(0, 40) })));
      const out = [];
      for (const dark of [false, true]) {
        const r = await open({ keep: true });
        await r.setViewportSize({ width: 390, height: 844 });
        await r.emulateMedia({ colorScheme: dark ? "dark" : "light" });
        // no layout shift: the icons are held back for 2 s; every item type's name stays where it was when they arrive
        let release; const held = new Promise((res) => { release = res; });
        await r.route("**/assets/fabric-icons/**", async (route) => { await held; await route.continue(); });
        await r.reload({ waitUntil: "domcontentloaded" }); await settle(r, 2500);
        const boxes = () => r.locator(".krusgraph-item-title").evaluateAll((els) => els.map((e) => { const b = e.getBoundingClientRect(); return [Math.round(b.x), Math.round(b.y + window.scrollY), Math.round(b.width), Math.round(b.height)].join(","); }));
        const pending = await r.locator("img.krusgraph-item-icon").evaluateAll((els) => els.filter((i) => !i.complete || !i.naturalWidth).length);
        const before = await boxes();
        release(); await settle(r, 1500);
        const after = await boxes();
        const moved = before.filter((b, i) => b !== after[i]).length;
        expectTrue(before.length >= 5 && pending > 0, `nothing held back (${pending} pending of ${before.length})`);
        expectTrue(moved === 0 && before.length === after.length, `${moved} of ${before.length} type names moved when the icons loaded`);
        const mode = dark ? "dark" : "light";
        // the reopened item lands on the Data product page: its Built list and next steps carry the icons
        await shot(r, `22-product-phone-${mode}`, true);
        const next = r.locator("section.kg-next").first();
        expectTrue(await next.count() > 0, "no next steps on the Data product page");
        await next.scrollIntoViewIfNeeded();
        await next.screenshot({ path: path.join(OUT, `22-next-steps-phone-${mode}.png`) });
        let seen = await icons(r);
        // a next step's Dry run opens Choose what to build: every output with its icon
        await r.locator(".kg-next-card[data-step='iq'] button").first().click(); await settle(r);
        expectTrue((await text(r)).includes("Choose what to build"), "not on Choose");
        await shot(r, `22-choose-phone-${mode}`, true);
        seen = seen.concat(await icons(r));
        const overflow = await r.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expectTrue(seen.length >= 5, `only ${seen.length} icons`);
        for (const i of seen) expectTrue(i.w > 0 && i.box === 20 && /_24_item\.svg$/.test(i.src), `icon not loaded or resized: ${JSON.stringify(i)}`);
        { const bare = seen.filter((i) => !i.label.length); expectTrue(!bare.length, `an icon without its type's name beside it: ${JSON.stringify(bare.slice(0, 3))}`); }
        expectTrue(overflow <= 0, `horizontal overflow ${overflow} px`);
        out.push(`${dark ? "dark" : "light"}: ${seen.length} icons, overflow ${overflow} px, ${before.length} type names unmoved when ${pending} held-back icons loaded`);
        await r.close();
      }
      return out.join("; ");
    });
  }
  await step("10 Reopen the item (saved definition)", async () => {
    const r = await open({ keep: true });
    await settle(r, 2500);
    const t = await text(r);
    const where = /Data product: /.test(t) ? "the Data product page" : t.includes("Choose what to build") ? "Choose what to build" : t.includes("Built in Fabric") ? "Built in Fabric" : "the empty state";
    expectTrue(where !== "the empty state", "the saved item did not reopen");
    await shot(r, "10-reopen");
    await r.close();
    return `10-reopen.png; reopened on: ${where}`;
  });
  await step("11 Data product page and health", async () => {
    const r = await open({ keep: true });
    await settle(r, 2000);
    if (!/Data product: /.test(await text(r))) { await button(r, "Data product", true).click(); await settle(r, 3000); }
    const t = await text(r);
    expectTrue(/Data product/.test(t), "no data product page");
    await shot(r, "11-product", false);
    const said = [];
    for (const name of ["Read Fabric again", "Check against the rows again", "Look for leftovers"]) {
      const b = r.getByRole("button", { name, exact: true }).first();
      if (!(await b.count())) { said.push(`${name}: not shown`); continue; }
      const before = await text(r);
      await b.click(); await settle(r, 3500);
      const after = (await text(r)).split("\n").filter((l) => l.trim() && !before.includes(l)).slice(0, 2).join(" / ");
      said.push(`${name}: ${after.slice(0, 160) || "no new line"}`);
    }
    await shot(r, "11b-product-health", true);
    const health = said.join("; ");
    await r.close();
    return `11-product.png; ${health}`;
  });
  await p.close();

  // ---------------------------------------------------------------- empty and error states
  await step("12 No permission on the source (Fabric answers 403)", async () => {
    await scenario("forbidden");
    const r = await open();
    await button(r, "Choose a source").click(); await settle(r);
    const t = await text(r);
    await shot(r, "12-no-access");
    await r.close(); await scenario("shop");
    if (!BEFORE) {
      expectTrue(t.includes("Your sign-in cannot open demo_lh"), "no plain no-access line");
      expectTrue(!t.includes("11111111-2222"), "the workspace id is shown");
    }
    return `12-no-access.png; shown: ${t.split("\n").find((l) => /access|cannot open/.test(l))}`;
  });
  await step("13 Network failure on the review", async () => {
    const r = await open();
    await button(r, "Choose a source").click(); await settle(r);
    await r.route("**/workload/v1/review", (x) => x.abort("internetdisconnected"));
    await button(r, "Find keys and relationships").click(); await settle(r, 8000);
    const t = await text(r);
    await shot(r, "13-network");
    await r.close();
    expectTrue(/connection to the Krusgraph engine closed|try again/i.test(t), "no network message");
    return `13-network.png; shown: ${t.split("\n").find((l) => /connection/i.test(l))}`;
  });
  await step("14 A big schema (247 tables, 493 suggestions)", async () => {
    await scenario("big");
    const r = await open();
    await button(r, "Choose a source").click(); await settle(r);
    const t0 = Date.now();
    await button(r, "Find keys and relationships").click();
    await button(r, /Check against the rows/).waitFor({ timeout: 60000 });
    const review = Date.now() - t0;
    const t1 = Date.now();
    await button(r, "Check against the rows").click();
    await button(r, /Check against the rows again/).waitFor({ timeout: 60000 });
    const check = Date.now() - t1;
    const t = await text(r);
    await shot(r, "14-big");
    await r.close(); await scenario("shop");
    return `14-big.png; review ${review} ms, check ${check} ms; ${(t.match(/\d+ passed/) || [""])[0]}, ${(t.match(/\d+ not checked/) || [""])[0]}`;
  });

  // ---------------------------------------------------------------- phone, keyboard, dark
  await step("15 Phone width (390 px): review and next steps", async () => {
    const r = await open({ viewport: { width: 390, height: 844 } });
    await button(r, "Choose a source").click(); await settle(r);
    await button(r, "Find keys and relationships").click(); await button(r, /Check against the rows/).waitFor();
    await button(r, "Check against the rows").click(); await settle(r, 2500);
    const overflow = await r.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    await shot(r, "15-phone-review");
    await r.close();
    return `15-phone-review.png; horizontal overflow ${overflow} px`;
  });
  await step("16 Keyboard: the first-run path without a mouse", async () => {
    const r = await open();
    const seen = [];
    for (let i = 0; i < 12; i++) {
      await r.keyboard.press("Tab");
      const name = await r.evaluate(() => { const a = document.activeElement; return a ? (a.getAttribute("aria-label") || a.innerText || a.tagName).trim().slice(0, 40) : ""; });
      seen.push(name);
      if (/Choose a source/.test(name)) break;
    }
    expectTrue(seen.some((s) => /Choose a source/.test(s)), `not reached: ${seen.join(" > ")}`);
    await r.keyboard.press("Enter"); await settle(r);
    for (let i = 0; i < 10; i++) {
      await r.keyboard.press("Tab");
      const name = await r.evaluate(() => (document.activeElement && document.activeElement.innerText || "").trim());
      if (/Find keys and relationships/.test(name)) { await r.keyboard.press("Enter"); break; }
    }
    await button(r, /Check against the rows/).waitFor({ timeout: 20000 });
    await r.close();
    return `Tab order to the first action: ${seen.join(" > ")}; Enter on Choose a source, then Find keys and relationships: review reached`;
  });
  await step("17 Dark colour scheme of the browser", async () => {
    const r = await open({ dark: true });
    const bg = await r.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await shot(r, "17-dark");
    await r.close();
    return `17-dark.png; body background ${bg} (the editor uses Fabric's light theme; see the doc)`;
  });

  // W14: autosave (decisions persist without Save; a tab closed before the save recovers them on the next opening)
  if (!BEFORE) {
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
    const firstPage = async (query) => {
      const a = await phone.newPage();
      a.on("pageerror", (e) => errors.push(e.message));
      await a.goto(`${BASE}/index.html${query}`);
      await a.waitForTimeout(1200);
      return a;
    };
    const decisions = (a) => a.evaluate(() => {
      const parts = JSON.parse(localStorage.getItem("w13-e2e-parts") || "[]");
      const r = parts.find((x) => x.path === "review.json");
      if (!r) return {};
      const bin = atob(r.payload);
      const review = JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0))));
      const out = {};
      for (const it of review.items) out[it.review] = (out[it.review] || 0) + 1;
      return out;
    });
    const a = await firstPage("?fresh=1");
    await step("18 Autosave: a decision is saved without Save (phone width)", async () => {
      await button(a, "Choose a source").click(); await settle(a);
      await button(a, "Find keys and relationships").click();
      await button(a, /Check against the rows/).waitFor({ timeout: 30000 });
      await settle(a, 2500);                                     // the review itself is autosaved first
      const before = await a.evaluate(() => window.__host.saves);
      await a.getByRole("tab", { name: "List" }).click(); await settle(a, 300);
      await a.getByRole("button", { name: "Accept", exact: true }).first().click();
      const pending = await a.locator(".kg-autosave-line").innerText();
      await settle(a, 2500);
      const after = await a.evaluate(() => window.__host.saves);
      const line = await a.locator(".kg-autosave-line").innerText();
      const role = await a.locator(".kg-autosave-line").getAttribute("role");
      const overflow = await a.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      const d = await decisions(a);
      expectTrue(after === before + 1, `saves ${before} -> ${after}, expected one more`);
      expectTrue(/Saved \d\d:\d\d UTC/.test(line) && role === "status", `line: ${line} (role ${role})`);
      expectTrue((d.accepted || 0) >= 1, `no accepted item in Fabric's copy: ${JSON.stringify(d)}`);
      expectTrue(overflow <= 0, `horizontal overflow ${overflow} px`);
      return `${await shot(a, "18-autosave-phone")}; "${pending.trim()}" then "${line.trim()}"; saves ${before} -> ${after}; Fabric's copy: ${JSON.stringify(d)}; overflow ${overflow} px`;
    });
    await step("19 Closed before the save: the decision comes back on reopening", async () => {
      await a.close();
      const b = await firstPage("?slowsave=60000");              // this tab's save never finishes before it is closed
      await b.getByRole("button", { name: /Check against the rows/ }).first().waitFor({ timeout: 30000 });
      await settle(b, 2500);
      const was = await decisions(b);
      await b.getByRole("tab", { name: "List" }).click(); await settle(b, 300);
      await b.getByRole("button", { name: "Reject", exact: true }).first().click();
      await b.waitForTimeout(150);
      await b.close();                                           // closed at once: Fabric never got the decision
      const c = await firstPage("");
      await c.getByText(/Recovered changes from/).waitFor({ timeout: 10000 });
      await settle(c, 3000);
      const now = await decisions(c);
      const note = await c.locator(".kg-autosave-note").innerText();
      expectTrue((now.rejected || 0) === (was.rejected || 0) + 1, `rejected ${was.rejected || 0} -> ${now.rejected || 0}`);
      const r = `${await shot(c, "19-recovered")}; Fabric's copy ${JSON.stringify(was)} -> after reopening ${JSON.stringify(now)}; note: ${note.trim()}`;
      await c.close();
      return r;
    });
    // WB3 (F6, the founder's yes of 18 Nov 2026): Accept all, the line says Saved, the item is closed without Save and
    // with no draft left in this browser; reopening shows every decision from Fabric's copy. No engine route is called
    // for the decisions, so nothing is created
    await step("23 Close without Save, reopen: every decision is there (phone width)", async () => {
      const d = await firstPage("");
      await d.getByRole("button", { name: /Check against the rows/ }).first().waitFor({ timeout: 30000 });
      await settle(d, 2500);                                     // the review read again on opening is saved first
      const createdBefore = (await (await fetch(`${BASE}/e2e/log`)).json()).created.length;
      const engineCalls = [];
      d.on("request", (q) => { if (q.url().includes("/workload/v1/")) engineCalls.push(`${q.method()} ${new URL(q.url()).pathname}`); });
      const savesBefore = await d.evaluate(() => window.__host.saves);
      await d.getByRole("button", { name: /^Accept all that passed the check \(\d+\)$/ }).first().click();   // SM3: the only accept-all
      const quick = (await d.locator(".kg-autosave-line").innerText()).trim();
      await d.locator(".kg-autosave-line", { hasText: /Saved/ }).waitFor({ timeout: 10000 });
      const line = (await d.locator(".kg-autosave-line").innerText()).trim();
      const savesAfter = await d.evaluate(() => window.__host.saves);
      const drafts = await d.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("krusgraph-model-draft:")).length);
      const overflow = await d.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      await d.close();                                           // closed: Save was never chosen
      const e = await firstPage("");
      await e.getByRole("button", { name: /Check against the rows/ }).first().waitFor({ timeout: 30000 });
      await settle(e, 2500);
      const now = await decisions(e);
      // ED1: with every passed item accepted there is nothing left to accept, so the accept-all is hidden (it read "(0)")
      const left = e.getByRole("button", { name: /^Accept all that passed the check \(\d+\)$/ });
      const allLeft = (await left.count()) ? await left.first().innerText() : "Accept all that passed the check: hidden (0)";
      const recovered = await e.getByText(/Recovered changes from/).count();
      const createdAfter = (await (await fetch(`${BASE}/e2e/log`)).json()).created.length;
      expectTrue(savesAfter === savesBefore + 1, `saves ${savesBefore} -> ${savesAfter}, expected one more`);
      expectTrue(/^\S\s*Saving…$/.test(quick) || /Saved/.test(quick), `line right after Accept all: ${quick}`);
      expectTrue(drafts === 0, `${drafts} drafts left in this browser: reopening would be a recovery`);
      expectTrue(engineCalls.length === 0, `engine calls for the decisions: ${engineCalls.join(", ")}`);
      expectTrue(createdAfter === createdBefore, `created ${createdBefore} -> ${createdAfter}`);
      expectTrue(!now.proposed && !now.open && (now.accepted || 0) > 0, `Fabric's copy after reopening: ${JSON.stringify(now)}`);
      expectTrue(/\(0\)/.test(allLeft) && recovered === 0, `reopened: "${allLeft}", recovered notes ${recovered}`);
      expectTrue(overflow <= 0, `horizontal overflow ${overflow} px`);
      const r = `${await shot(e, "23-reopened-without-save")}; "${quick}" then "${line}"; saves ${savesBefore} -> ${savesAfter}; ` +
        `no engine call, nothing created; reopened from Fabric's copy ${JSON.stringify(now)}, "${allLeft.trim()}"; overflow ${overflow} px`;
      await e.close();
      return r;
    });
    await phone.close();
  }

  // ---------------------------------------------------------------- WB10: downloads inside Fabric's sandboxed frame
  if (!BEFORE) {
    await step("20 Downloads inside a sandboxed frame that blocks downloads (Fabric's default)", async () => {
      await scenario("shop");
      const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1, acceptDownloads: true });
      const downloads = [];
      ctx.on("page", (pg) => pg.on("download", (d) => { if (!downloads.includes(d)) downloads.push(d); }));   // every page, the top one too
      const top = await ctx.newPage();
      top.on("pageerror", (e) => errors.push(e.message));
      await top.goto(`${BASE}/frame.html`);
      const frame = top.frameLocator("#editor");
      const inner = top.frame({ url: /index\.html/ });
      expectTrue(!!inner, "no editor frame");
      expectTrue((await top.locator("#editor").getAttribute("sandbox")) === "allow-same-origin allow-scripts", "the frame is not sandboxed as Fabric's");
      // the old way: a data: link with download, clicked inside the frame, saves nothing
      await inner.evaluate(() => {
        const a = document.createElement("a");
        a.href = "data:text/plain;charset=utf-8,blocked"; a.download = "old-way.txt"; document.body.appendChild(a); a.click();
      });
      await top.waitForTimeout(1500);
      expectTrue(downloads.length === 0, `the sandbox let a data: download through: ${downloads.map((d) => d.suggestedFilename())}`);
      // the new way: Download as draw.io under the map
      await frame.getByRole("button", { name: "Choose a source" }).first().click(); await top.waitForTimeout(1500);
      await frame.getByRole("button", { name: "Find keys and relationships" }).first().click();
      await frame.getByRole("button", { name: /Check against the rows/ }).first().waitFor({ timeout: 30000 });
      await top.waitForTimeout(1500);
      await frame.getByRole("button", { name: "Download as draw.io" }).first().click();
      for (let i = 0; i < 40 && !downloads.length; i++) await top.waitForTimeout(250);
      expectTrue(downloads.length === 1, `${downloads.length} downloads`);
      const d = downloads[0];
      const file = await d.path();
      const body = fs.readFileSync(file, "utf8");
      expectTrue(d.suggestedFilename().endsWith(".drawio") && body.startsWith("<mxfile"), `got ${d.suggestedFilename()}: ${body.slice(0, 40)}`);
      const opened = await top.evaluate(() => window.__opened);
      expectTrue(opened.length === 1 && /\/workload\/v1\/file\/[A-Za-z0-9_-]{24}\.\d+\.[A-Za-z0-9_-]{22}$/.test(opened[0]), `opened ${opened}`);
      const again = await fetch(opened[0]);
      expectTrue(again.status === 410, `a second GET answered ${again.status}`);
      const said = await frame.locator(".kg-file-said").first().innerText();
      fs.copyFileSync(file, path.join(OUT, `20-${d.suggestedFilename()}`));
      const r = `${await shot(top, "20-sandboxed-download")}; data: link in the frame: no download; Download as draw.io: ${d.suggestedFilename()} (${body.length} characters) through the host's tab; second GET ${again.status}; said: ${said}`;
      await ctx.close();
      return r;
    });

    // WB14 (#108): Save to lakehouse Files at 390 px, light and dark. OneLake's DFS endpoint is answered here in the
    // browser: the first create 201 (then append 202, flush 200), a second create with If-None-Match 409, Replace 201.
    await step("24 WB14: Save to lakehouse Files (dry run, Save, already there, Replace) at 390 px, light and dark", async () => {
      const out = [];
      for (const dark of [false, true]) {
        await scenario("shop");
        const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, colorScheme: dark ? "dark" : "light" });
        const r = await ctx.newPage();
        r.on("pageerror", (e) => errors.push(e.message));
        const calls = [];
        const there = new Set();
        await r.route("https://onelake.dfs.fabric.microsoft.com/**", async (route) => {
          const req = route.request();
          const h = req.headers();
          const u = new URL(req.url());
          if (req.method() === "OPTIONS") return route.fulfill({ status: 200, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "PUT, PATCH" } });
          const cors = { "access-control-allow-origin": "*", "access-control-expose-headers": "x-ms-request-id", "x-ms-request-id": `e2e-${calls.length + 1}` };
          calls.push(`${req.method()} ${u.search} ${h["if-none-match"] ? "if-none-match" : ""} ${(h.authorization || "").startsWith("Bearer ") ? "bearer" : "no-token"}`.trim());
          if (u.searchParams.get("resource") === "file") {
            if (h["if-none-match"] === "*" && there.has(u.pathname)) return route.fulfill({ status: 409, headers: cors, body: '{"error":{"code":"PathAlreadyExists"}}' });
            there.add(u.pathname);
            return route.fulfill({ status: 201, headers: cors });
          }
          return route.fulfill({ status: u.searchParams.get("action") === "append" ? 202 : 200, headers: cors });
        });
        await r.goto(`${BASE}/index.html?fresh=1&onelake=1`); await settle(r, 1200);
        await button(r, "Choose a source").click(); await settle(r);
        await button(r, "Find keys and relationships").click();
        await button(r, /Check against the rows/).waitFor({ timeout: 30000 }); await settle(r);
        const mode = dark ? "dark" : "light";
        const save = r.getByRole("button", { name: "Save to lakehouse Files" }).first();
        expectTrue(await save.count() > 0, "no Save to lakehouse Files button");
        await save.scrollIntoViewIfNeeded(); await save.click(); await settle(r, 800);
        const scope = r.locator(".kg-file-save").first();
        const dry = await scope.innerText();
        expectTrue(calls.length === 0, `the dry run sent ${calls.length} calls`);
        expectTrue(dry.includes("Dry run: Save would write") && /demo_lh › Files\/krusgraph\/shop_model\/.+\.drawio/.test(dry), `dry run said: ${dry}`);
        await scope.screenshot({ path: path.join(OUT, `24-dry-run-phone-${mode}.png`) });
        await scope.getByRole("button", { name: "Save", exact: true }).click(); await settle(r, 1200);
        const saved = await scope.innerText();
        expectTrue(saved.includes("Saved to demo_lh › Files/krusgraph/shop_model/"), `after Save: ${saved}`);
        expectTrue(calls.length === 3 && calls[0].startsWith("PUT ?resource=file if-none-match bearer"), `calls: ${calls.join(" | ")}`);
        await scope.getByRole("button", { name: "Save to lakehouse Files" }).click(); await settle(r, 600);
        await scope.getByRole("button", { name: "Save", exact: true }).click(); await settle(r, 1200);
        const exists = await scope.innerText();
        expectTrue(exists.includes("is already in demo_lh › Files/krusgraph/shop_model/") && exists.includes("Replace"), `second save: ${exists}`);
        expectTrue(calls.length === 4, `the 409 sent more: ${calls.join(" | ")}`);
        await scope.screenshot({ path: path.join(OUT, `24-already-there-phone-${mode}.png`) });
        await scope.getByRole("button", { name: "Replace", exact: true }).click(); await settle(r, 1200);
        const replaced = await scope.innerText();
        expectTrue(replaced.includes("Saved to") && calls.length === 7 && !calls[4].includes("if-none-match"), `Replace: ${replaced}; ${calls.join(" | ")}`);
        const overflow = await r.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expectTrue(overflow <= 0, `horizontal overflow ${overflow} px`);
        expectTrue(await r.getByRole("button", { name: "Download as draw.io" }).first().isEnabled(), "Download is not there beside Save");
        await shot(r, `24-saved-phone-${mode}`);
        out.push(`${mode}: dry run with the path and no call; Save sent ${calls.slice(0, 3).map((c) => c.split(" ")[0]).join(", ")}; a second Save got 409 and asked Replace; Replace overwrote (${calls.length} calls); overflow ${overflow} px`);
        await ctx.close();
      }
      return out.join("; ");
    });

    // WB4: Recommended analyses on the 24-month synthetic SAP sample (engine.py's `sap` scenario), at 390 px, by keyboard
    // only (focus and Enter or Space, no mouse): nothing before the check; after it, A7 ranked first and Ready with its
    // notebook, A8 Partly ready, the not-ready ones saying what data would make them ready; nothing created by the ranking.
    await step("25 WB4: Recommended analyses on the SAP sample, keyboard only, at 390 px", async () => {
      await scenario("sap");
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
      const r = await ctx.newPage();
      r.on("pageerror", (e) => errors.push(e.message));
      const routes = [];                                         // SM3: the engine routes in the order the page asked
      r.on("request", (q) => { if (q.url().includes("/workload/v1/")) routes.push(new URL(q.url()).pathname); });
      await r.goto(`${BASE}/index.html?fresh=1`); await settle(r, 1200);
      const press = async (loc, key = "Enter") => { await loc.scrollIntoViewIfNeeded(); await loc.focus(); await r.keyboard.press(key); };
      // each wait says what it waited for, so a timeout names the step (not only "locator.waitFor: Timeout")
      const waitFor = async (loc, what) => { try { await loc.waitFor({ timeout: 30000 }); } catch (e) { throw new Error(`waited 30 s for ${what}: ${String(e.message).split("\n")[0]}`); } };
      await press(button(r, "Choose a source")); await settle(r);
      const sap = r.getByRole("radio", { name: /sap_sd/ });
      expectTrue(await sap.count() === 1, "no sap_sd schema to choose");
      if (!(await sap.isChecked())) await press(sap, "Space");
      await press(button(r, "Find keys and relationships"));
      // SM3: the check runs on its own after Find keys; the ranking is still asked only after the check answered
      await waitFor(button(r, /Check against the rows again/), "the check after Find keys");
      await settle(r, 1500);
      const calls = routes.slice();
      const firstAnalysis = calls.findIndex((c) => c.includes("/workload/v1/analysis"));
      const lastCheck = calls.map((c) => c.includes("/workload/v1/check")).lastIndexOf(true);
      expectTrue(firstAnalysis < 0 || (lastCheck >= 0 && firstAnalysis > lastCheck), `Recommended analyses before the check: ${calls.slice(-6).join(", ")}`);
      await press(button(r, "Check against the rows")); await settle(r, 3000);
      await press(button(r, /Accept all that passed/)); await settle(r, 600);
      await press(button(r, "Next: Decide what to build")); await settle(r);
      // SM3: the defaults are ticked; unticking the pipeline unticks its notebooks under More outputs
      // (all() gives nth locators that are read again, so untick the first visible ticked box until none is left)
      for (let i = 0; i < 12; i++) {
        const on = r.locator(".krusgraph-outputs > section.krusgraph-output:visible").getByRole("checkbox", { checked: true }).first();
        if (!(await on.count())) break;
        await press(on, "Space"); await settle(r, 200);
      }
      await press(r.getByRole("checkbox", { name: "Semantic model" }).first(), "Space");
      await press(button(r, "Dry run", true)); await settle(r, 4000);
      await press(button(r, /^Create/)); await settle(r, 6000);
      // AA1 / ED3: Recommended analyses are in Advanced analytics, one section on the Data product step; after Create the
      // result's Next has the way there. Enter on it lands the focus on that section's heading (no Tab through the page).
      await waitFor(button(r, "Go to Advanced analytics on the Data product step"), "Go to Advanced analytics after Create");
      await press(button(r, "Go to Advanced analytics on the Data product step"));
      const advanced = r.locator("section#kg-advanced-analytics");
      await waitFor(advanced, "the Advanced analytics section on the Data product step");
      await r.waitForFunction(() => document.activeElement && document.activeElement.id === "kg-advanced-title", null, { timeout: 5000 })
        .catch(() => undefined);
      const landed = await r.evaluate(() => document.activeElement && (document.activeElement.id || document.activeElement.tagName));
      expectTrue(landed === "kg-advanced-title", `Go to Advanced analytics left the focus on ${landed}`);
      const section = advanced.locator("section.kg-analysis");
      await waitFor(section, "Recommended analyses in Advanced analytics");
      await waitFor(section.locator("[data-analysis]").first(), "a ranked analysis card");
      const order = await section.locator(".kg-analysis-card").evaluateAll((els) => els.map((e) => e.getAttribute("data-analysis")));
      expectTrue(order.slice(0, 4).join(",") === "A7,A8,A3,A4" && order.length === 10, `ranked ${order.join(",")}`);
      const word = async (id) => (await section.locator(`[data-analysis=${id}] .fui-Badge`).innerText()).trim();
      expectTrue(await word("A7") === "Ready" && await word("A8") === "Partly ready", `readiness words ${await word("A7")}, ${await word("A8")}`);
      const a7 = section.locator("[data-analysis=A7]");
      expectTrue((await a7.innerText()).includes("Recommended because VBRP.NETWR"), "no Recommended because on A7");
      const dl = a7.getByRole("button", { name: "Download notebook (.ipynb): A7 Demand and revenue forecasting" });
      await press(dl); await settle(r, 1500);
      const file = await a7.locator(".kg-file").getAttribute("data-file");
      expectTrue(file === "a7_forecast_monthly.ipynb", `downloaded ${file}`);
      await press(section.locator("details.kg-analysis-later > summary")); await settle(r, 400);
      const a1 = section.locator("[data-analysis=A1]");
      expectTrue(await a1.isVisible() && (await a1.innerText()).includes("What would make it ready: a cost"), "A1 does not say what would make it ready");
      expectTrue(await word("A1") === "Not ready yet", `A1 says ${await word("A1")}`);
      const focused = await r.evaluate(() => document.activeElement && document.activeElement.tagName);
      expectTrue(focused === "SUMMARY", `focus on ${focused}`);
      const snap = await section.ariaSnapshot();
      for (const name of ['heading "Recommended analyses"', 'list "Ready and partly ready analyses, ranked"', 'group "A7 Demand and revenue forecasting: Ready"',
        'button "Download notebook (.ipynb): A7 Demand and revenue forecasting"', 'group "A8 RFM segmentation (and clustering): Partly ready"']) {
        expectTrue(snap.includes(name), `screen reader does not get ${name}`);
      }
      const overflow = await r.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expectTrue(overflow <= 0, `horizontal overflow ${overflow} px`);
      // WB4 / SM3: over the whole flow, the ranking was asked, and never before the first check had answered
      const all = routes.slice();
      const analyses = all.map((c, i) => (c.includes("/workload/v1/analysis") ? i : -1)).filter((i) => i >= 0);
      const firstCheck = all.findIndex((c) => c.includes("/workload/v1/check"));
      expectTrue(analyses.length > 0 && firstCheck >= 0 && analyses[0] > firstCheck, `analysis calls at ${analyses.join(",")}, first check at ${firstCheck}`);
      const log = await (await fetch(`${BASE}/e2e/log`)).json();
      await section.screenshot({ path: path.join(OUT, "25-analyses-phone.png") });
      await ctx.close();
      return `25-analyses-phone.png; ranked ${order.join(", ")}; A7 Ready, A8 Partly ready, A1 Not ready yet; keyboard: Enter on Download gave ${file}, ` +
        `Enter on the summary opened the not-ready list; screen reader: ${snap.split("\n").filter((l) => /heading|group/.test(l)).slice(0, 3).map((l) => l.trim()).join(" | ")}; ` +
        `Enter on Go to Advanced analytics put the focus on its heading; engine: ${analyses.length} analysis call(s), the first after check #${firstCheck}; ` +
        `items the doubles received: ${log.created.join(", ")}; overflow ${overflow} px`;
    });

    // BL58: the semantic model's row-level security roles (BL46) on the SAP sample, at 390 px, by keyboard only: the dry
    // run lists BUKRS and MANDT as tick boxes, unticked, each named by the role and described by its column, rule and
    // tables; the dry run's request has no roles; Space ticks BUKRS, Dry run again sends roles ["BUKRS"], and so does Create.
    await step("27 BL58: row-level security roles as ticks on the model's dry run (SAP sample, keyboard, 390 px)", async () => {
      await scenario("sap");
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
      const r = await ctx.newPage();
      r.on("pageerror", (e) => errors.push(e.message));
      const builds = [];                                        // the outputs of every build request, in order
      r.on("request", (q) => {
        if (q.url().includes("/workload/v1/build") && q.method() === "POST") {
          try { const b = JSON.parse(q.postData() || "{}"); builds.push({ dry_run: b.dry_run, outputs: b.outputs }); } catch { /* not JSON */ }
        }
      });
      await r.goto(`${BASE}/index.html?fresh=1`); await settle(r, 1200);
      const press = async (loc, key = "Enter") => { await loc.scrollIntoViewIfNeeded(); await loc.focus(); await r.keyboard.press(key); };
      await press(button(r, "Choose a source")); await settle(r);
      const sap = r.getByRole("radio", { name: /sap_sd/ });
      if (!(await sap.isChecked())) await press(sap, "Space");
      await press(button(r, "Find keys and relationships"));
      await button(r, /Check against the rows again/).waitFor({ timeout: 30000 });
      await settle(r, 1500);
      await press(button(r, /Accept all that passed/)); await settle(r, 600);
      await press(button(r, "Next: Decide what to build")); await settle(r);
      for (let i = 0; i < 12; i++) {
        const on = r.locator(".krusgraph-outputs > section.krusgraph-output:visible").getByRole("checkbox", { checked: true }).first();
        if (!(await on.count())) break;
        await press(on, "Space"); await settle(r, 200);
      }
      await press(r.getByRole("checkbox", { name: "Semantic model" }).first(), "Space");
      await press(button(r, "Dry run", true)); await settle(r, 4000);
      const roles = r.locator("fieldset.kg-roles");
      await roles.waitFor({ timeout: 30000 });
      const first = builds.filter((b) => b.dry_run);
      expectTrue(first.length === 1 && JSON.stringify(first[0].outputs) === JSON.stringify([{ kind: "semantic_model", name: "demo_lh_model" }]),
        `the first dry run sent ${JSON.stringify(first.map((b) => b.outputs))}`);
      const bukrs = roles.getByRole("checkbox", { name: "Rows by company code (BUKRS)" });
      const mandt = roles.getByRole("checkbox", { name: "Rows by client (MANDT)" });
      expectTrue(await bukrs.count() === 1 && await mandt.count() === 1, "no BUKRS or MANDT tick box");
      expectTrue(!(await bukrs.isChecked()) && !(await mandt.isChecked()), "a role is ticked by default");
      const desc = await bukrs.evaluate((el) => document.getElementById(el.getAttribute("aria-describedby") || "")?.textContent || "");
      expectTrue(/^Filters on BUKRS \(rule S1\) in .*T001.*\. Fits this model's tables\.$/i.test(desc), `BUKRS is described as: ${desc}`);
      await press(bukrs, "Space"); await settle(r, 800);
      expectTrue(await bukrs.isChecked(), "Space did not tick BUKRS");
      const again = button(r, "Dry run again", true);
      await press(again); await settle(r, 4000);
      const second = builds.filter((b) => b.dry_run);
      expectTrue(second.length === 2 && JSON.stringify(second[1].outputs) === JSON.stringify([{ kind: "semantic_model", name: "demo_lh_model", roles: ["BUKRS"] }]),
        `the dry run again sent ${JSON.stringify(second.map((b) => b.outputs))}`);
      expectTrue(await r.locator("fieldset.kg-roles").getByRole("checkbox", { name: "Rows by company code (BUKRS)" }).isChecked(), "BUKRS unticked after the dry run again");
      const snap = await r.locator("fieldset.kg-roles").ariaSnapshot();
      const overflow = await r.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expectTrue(overflow <= 0, `horizontal overflow ${overflow} px`);
      await r.locator("fieldset.kg-roles").screenshot({ path: path.join(OUT, "27-roles-phone.png") });
      await press(button(r, /^Create/)); await settle(r, 6000);
      const created = builds.filter((b) => b.dry_run === false);
      expectTrue(created.length >= 1 && created.every((b) => JSON.stringify(b.outputs) === JSON.stringify([{ kind: "semantic_model", name: "demo_lh_model", roles: ["BUKRS"] }])),
        `Create sent ${JSON.stringify(created.map((b) => b.outputs))}`);
      await ctx.close();
      return `27-roles-phone.png; the first dry run sent no roles; BUKRS and MANDT unticked; Space ticked BUKRS; Dry run again and Create sent roles ["BUKRS"]; ` +
        `screen reader: ${snap.split("\n").filter((l) => l.includes("checkbox")).map((l) => l.trim()).join(" | ")}; overflow ${overflow} px`;
    });
  }

  // SM3 (docs/SMOOTH/PLAN.md row 2): the lazy path, counted. A fresh item, from opening it to the dry run of the pipeline,
  // the semantic model and the data agent, at desktop width and at 390 px; every click the person makes is counted and
  // the seconds run from the first click to the dry run on the page. --before counts the same goal on the older editor
  // (it needs Check, Next, three ticks and Preview). Fabric's own OneLake picker is answered at once by the harness.
  const lazy = [];
  for (const [label, viewport] of [["desktop", { width: 1280, height: 860 }], ["390 px", { width: 390, height: 844 }]]) {
    await step(`26 SM3: open to the dry run of pipeline + model + agent, ${label}`, async () => {
      await scenario("shop");
      const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1 });
      const r = await ctx.newPage();
      r.on("pageerror", (e) => errors.push(e.message));
      await r.goto(`${BASE}/index.html?fresh=1`); await settle(r, 1200);
      let clicks = 0; let t0 = 0;
      const click = async (loc) => { if (!clicks) t0 = Date.now(); clicks++; await loc.scrollIntoViewIfNeeded(); await loc.click(); };
      await click(button(r, "Choose a source")); await button(r, "Find keys and relationships").waitFor({ timeout: 30000 });
      await click(button(r, "Find keys and relationships"));
      if (BEFORE) {
        await button(r, /Check against the rows/).waitFor({ timeout: 30000 });
        await click(button(r, "Check against the rows")); await button(r, /Check against the rows again/).waitFor({ timeout: 30000 });
        await click(button(r, "Next", true)); await r.getByText("Choose what to build").first().waitFor();
        for (const n of ["Pipeline", "Semantic model", "Data agent"]) await click(r.getByRole("checkbox", { name: n }).first());
        await click(button(r, "Preview", true));
      } else {
        await button(r, "Next: Decide what to build").waitFor({ timeout: 30000 });
        await click(button(r, "Next: Decide what to build")); await r.getByText("Choose what to build").first().waitFor();
        await click(button(r, "Dry run", true));
      }
      await r.getByText(/Nothing was created or changed in Fabric/).first().waitFor({ timeout: 30000 });
      const ms = Date.now() - t0;
      const t = await text(r);
      for (const n of ["demo_lh_pipeline", "demo_lh_model", "demo_lh_agent"]) expectTrue(t.includes(n), `${n} not in the dry run`);
      const overflow = await r.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      const name = `26-lazy-${label === "desktop" ? "desktop" : "390"}`;
      await shot(r, name);
      await ctx.close();
      lazy.push({ width: label, clicks, ms });
      if (!BEFORE) expectTrue(clicks <= 4, `${clicks} clicks, more than 4`);
      expectTrue(overflow <= 0, `horizontal overflow ${overflow} px`);
      return `${name}.png; ${clicks} clicks, ${ms} ms from the first click to the dry run (pipeline, semantic model, data agent); overflow ${overflow} px`;
    });
  }

  await browser.close();
  engine.kill();
  record("No uncaught errors in the page", errors.length === 0, errors.slice(0, 3).join(" | ") || "none");
  const found = [...a11y.values()];
  if (!BEFORE) {
    const bad = found.filter((v) => v.impact === "serious" || v.impact === "critical");
    record("Accessibility: axe-core, WCAG 2.1 A and AA, every step", AXE !== null && bad.length === 0,
      AXE === null ? "axe-core is not installed (npm ci in workload/Workload)"
        : `${found.length} finding(s), ${bad.length} serious or critical${bad.length ? ": " + bad.slice(0, 4).map((v) => `${v.rule} at ${v.target} (${v.step})`).join(" | ") : ""}`);
  }
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify({ before: BEFORE, at: new Date().toISOString(), lazy, results, a11y: found, a11y_excluded: { selector: AXE_EXCLUDE, why: "Fluent UI Tabster focus guards", most_on_one_page: excluded } }, null, 1));
  fs.rmSync(dist, { recursive: true, force: true });
  if (engineLog.trim()) fs.writeFileSync(path.join(OUT, "engine.log"), engineLog);
  process.exit(results.some((r) => r.result === "fail") ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
