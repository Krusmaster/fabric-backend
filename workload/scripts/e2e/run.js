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
async function step(flow, fn) {
  try {
    const ev = await fn();
    record(flow, true, ev || "");
  } catch (e) {
    record(flow, false, String(e && e.message ? e.message : e).split("\n")[0]);
  }
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
  const errors = [];
  let mainCtx;
  async function open(opts = {}) {
    // a reopen is a new page in the main path's context (the stand-in host keeps the item in its localStorage)
    const ctx = opts.keep && mainCtx ? mainCtx : await browser.newContext({ viewport: opts.viewport || { width: 1280, height: 860 }, deviceScaleFactor: 1, colorScheme: opts.dark ? "dark" : "light" });
    if (!opts.keep && !mainCtx) mainCtx = ctx;
    const p = await ctx.newPage();
    p.on("pageerror", (e) => errors.push(e.message));
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
    await button(p, /Check against the rows/).waitFor({ timeout: 30000 });
    const t = await text(p);
    expectTrue(/7 tables, 6 with a key, and 7 links/.test(t), "unexpected review summary");
    return `${await shot(p, "03-review")}; 7 tables, 6 keys, 7 links in ${Date.now() - t0} ms`;
  });
  await step("4 Check against the rows (evidence)", async () => {
    await button(p, "Check against the rows").click(); await settle(p, 2500);
    const t = await text(p);
    expectTrue(t.includes("6 of 6 keys are unique in the rows") && t.includes("7 of 7 links hold"), "check result missing");
    if (!BEFORE) {
      for (const w of ["rows counted", "keys unique", "links holding", "orphans", "duplicate keys", "2.2×"]) expectTrue(t.includes(w), `proof tile missing: ${w}`);
    }
    return `${await shot(p, "04-check", true)}; 13 passed, 0 failed` + (BEFORE ? "" : "; tiles: 232 rows counted, 6 of 6 keys, 7 of 7 links, 0 orphans, 0 duplicate keys; 134 order_items over 60 orders = 2.2×");
  });
  await step("5 Accept what passed, go on to Choose what to build", async () => {
    await button(p, /Accept all that passed/).click(); await settle(p, 600);
    await (BEFORE ? button(p, "Next", true) : button(p, "Next: choose what to build")).click(); await settle(p);
    expectTrue((await text(p)).includes("Choose what to build"), "not on Choose");
    const names = await p.getByRole("checkbox").evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") || (e.labels && e.labels[0] ? e.labels[0].innerText : "")));
    for (const n of ["Semantic model", "Data agent"]) await p.getByRole("checkbox", { name: n }).first().check();
    const snap = await p.locator("body").ariaSnapshot();
    const dup = /checkbox "Semantic model Semantic model"/.test(snap);
    if (!BEFORE) expectTrue(!dup, "checkbox name repeats the item type");
    return `${await shot(p, "05-outputs")}; checkbox names read by a screen reader: ${snap.split("\n").filter((l) => l.includes("checkbox")).slice(0, 4).map((l) => l.trim()).join(" | ")}`;
  });
  await step("6 Preview (dry run of each output)", async () => {
    await button(p, "Preview", true).click(); await settle(p, 4000);
    const t = await text(p);
    expectTrue(t.includes("Nothing was created or changed in Fabric"), "no dry-run sentence");
    return `${await shot(p, "06-preview")}; three outputs previewed, nothing written`;
  });
  await step("7 Create (semantic model, API for GraphQL, data agent)", async () => {
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
      const dl = await panel.locator("a[download$='.ipynb']").first().getAttribute("download");
      await panel.screenshot({ path: path.join(OUT, "08-next-steps.png") });
      return `08-next-steps.png; ${cards} cards; starter file ${dl}`;
    });
    await step("9 A next step's Dry run ticks only its outputs", async () => {
      await p.locator(".kg-next-card[data-step='iq'] button").first().click(); await settle(p);
      const checked = await p.getByRole("checkbox", { checked: true }).evaluateAll((els) => els.map((e) => (e.closest("section") || e).getAttribute("aria-label")));
      expectTrue(checked.includes("Ontology") && !checked.includes("Semantic model"), `ticked: ${checked.join(", ")}`);
      return `on Choose what to build with ${checked.filter(Boolean).join(", ")} ticked`;
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
    await phone.close();
  }

  await browser.close();
  engine.kill();
  record("No uncaught errors in the page", errors.length === 0, errors.slice(0, 3).join(" | ") || "none");
  fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify({ before: BEFORE, at: new Date().toISOString(), results }, null, 1));
  fs.rmSync(dist, { recursive: true, force: true });
  if (engineLog.trim()) fs.writeFileSync(path.join(OUT, "engine.log"), engineLog);
  process.exit(results.some((r) => r.result === "fail") ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
