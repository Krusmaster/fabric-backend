// n197: a reload in the middle of a Create step resumes the same operation (Chromium). The page (served by
// tests/test_n197_resume_browser.py next to the engine's routes) starts one step with Prefer: respond-async, keeps the
// operation id where the editor keeps it (the item's saved state; here localStorage), and is reloaded while the step
// still runs. After the reload it reads the item's operations and the same operation to its end, sending nothing again.
// Usage: node tests/n197_resume_browser.js <base url>. Prints one JSON object.
const { chromium } = require("playwright");
(async () => {
  const [base] = process.argv.slice(2);
  const b = await chromium.launch();
  const out = { errors: [] };
  const page = await (await b.newContext()).newPage();
  page.on("pageerror", (e) => out.errors.push(e.message));
  const until = async (fn, n = 600) => { for (let i = 0; i < n; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
  await page.goto(base + "/page");
  await until(() => !!document.body.dataset.op);
  out.before = await page.evaluate(() => ({ op: document.body.dataset.op, state: document.body.dataset.state }));
  await page.reload();                                           // mid-step: the engine still works on it
  await until(() => document.body.dataset.state === "done" || document.body.dataset.state === "lost", 900);
  out.after = await page.evaluate(() => ({ op: document.body.dataset.op, state: document.body.dataset.state, resumed: document.body.dataset.resumed,
    listed: document.body.dataset.listed, created: document.body.dataset.created, seen: JSON.parse(document.body.dataset.seen || "[]"),
    longest: Number(document.body.dataset.longest || 0) }));
  await b.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
