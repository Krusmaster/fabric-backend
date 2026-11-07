// /check in a browser: a CSV with a marker no request may carry, the shop example, 375 px, keyboard, reduced motion.
const { chromium } = require("playwright");
(async () => {
  const [base, exe] = process.argv.slice(2);
  const b = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { requests: [], leaks: [], foreign: [], errors: [] };
  const MARK = "zq_marker_7781";
  const ctx = await b.newContext({ reducedMotion: "reduce" });
  ctx.on("request", (r) => {                                      // page and worker requests alike
    const body = r.postData() || "";
    out.requests.push(r.method() + " " + r.url());
    if (r.url().includes(MARK) || body.includes(MARK)) out.leaks.push(r.url());
    if (!r.url().startsWith(base)) out.foreign.push(r.url());
  });
  const page = await ctx.newPage();
  // waitForFunction evaluates a string in newer Playwright, which the page's CSP (no 'unsafe-eval') refuses: poll instead
  const until = async (fn) => { for (let i = 0; i < 1200; i++) { if (await page.evaluate(fn)) return; await page.waitForTimeout(100); } throw new Error("timeout"); };
  page.on("pageerror", (e) => out.errors.push(e.message));
  await page.goto(base + "/check");
  await page.setInputFiles("#check-files", [
    { name: "customers.csv", mimeType: "text/csv", buffer: Buffer.from(`customer_id,name\n1,${MARK}\n2,b\n`) },
    { name: "orders.csv", mimeType: "text/csv", buffer: Buffer.from("order_id,customer_id,amount\n1,1,10\n2,9,20\n") }]);
  await until(() => document.documentElement.dataset.check === "done");
  out.files_text = await page.textContent("#check-run");
  out.files_coverage = await page.textContent("#check-coverage");
  // the page itself cannot send anything: a fetch with the marker is refused by its CSP
  out.page_fetch = await page.evaluate(async (m) => { try { await fetch("/x?" + m, { method: "POST", body: m }); return "sent"; } catch (e) { return "blocked"; } }, MARK);
  out.after_requests = out.requests.length;
  // keyboard: Tab to the shop button and press Enter
  await page.goto(base + "/check");
  for (let i = 0; i < 40; i++) { await page.keyboard.press("Tab"); if (await page.evaluate(() => document.activeElement.id) === "check-sample") break; }
  out.focused = await page.evaluate(() => document.activeElement.id);
  await page.keyboard.press("Enter");
  await until(() => !!document.documentElement.dataset.checkMs);
  out.sample_text = await page.textContent("#check-run");
  // n79: the evidence report beside the build buttons, saved from a Blob like the contract
  out.evidence = await page.evaluate(() => { const a = document.querySelector("#check-evidence a"); return a ? { text: a.textContent, download: a.getAttribute("download"), hidden: document.getElementById("check-evidence").hidden } : null; });
  // n80: the RDF/XML for Ontology Playground, the second download there; its first bytes read from the Blob it saves
  out.rdfxml = await page.evaluate(async () => {
    const a = document.querySelectorAll("#check-evidence a")[1];
    if (!a) return null;
    let head = null;
    const orig = URL.createObjectURL;
    URL.createObjectURL = (b) => { head = b; return orig.call(URL, b); };
    a.addEventListener("click", (e) => e.preventDefault(), { once: true });
    a.click();
    URL.createObjectURL = orig;
    return { text: a.textContent, download: a.getAttribute("download"), head: head ? (await head.text()).slice(0, 60) : null };
  });
  out.steps = await page.$$eval("#check-steps strong", (n) => n.map((x) => x.textContent));
  // n73: the finding first. At 1280 x 720 the state line, the most important finding and the folded list stand right
  // under the status line and before the map, on the screen without scrolling; the engine's steps are a closed
  // <details> under the map, opened with Enter on its summary
  out.folded = await page.evaluate(() => {
    const y = (id) => document.getElementById(id).getBoundingClientRect().top + scrollY, all = document.getElementById("check-all");
    return { open: all.open, summary: document.getElementById("check-all-sum").textContent, line: document.querySelector("#check-verdict .check-state").textContent,
             order: y("check-status") < y("check-verdict") && y("check-verdict") < y("check-all") && y("check-all") < y("check-map") && y("check-map") < y("check-engine"),
             findingsInside: all.contains(document.getElementById("check-findings")) };
  });
  out.first_screen = await page.evaluate(() => {
    const r = (id) => document.getElementById(id).getBoundingClientRect(), v = r("check-verdict"), t = document.querySelector("#check-verdict .check-top").getBoundingClientRect();
    return { width: innerWidth, height: innerHeight, verdictTop: Math.round(v.top), verdictBottom: Math.round(v.bottom), topFindingBottom: Math.round(t.bottom),
             mostImportant: document.querySelector("#check-verdict .check-top").textContent, mapTop: Math.round(r("check-map").top) };
  });
  // n75: the coverage line under the state, on the first screen with the finding, and a `checked` line per card
  out.coverage = await page.evaluate(() => ({ line: document.getElementById("check-coverage").textContent,
    onFirstScreen: document.getElementById("check-coverage").getBoundingClientRect().bottom <= innerHeight,
    cards: document.querySelectorAll("#check-all .check-finding").length,
    checked: [...document.querySelectorAll("#check-all .check-finding .check-checked")].map((p) => p.textContent) }));
  out.engine = await page.evaluate(() => { const d = document.getElementById("check-engine"); return { open: d.open, summary: d.querySelector("summary").textContent, steps: d.querySelectorAll("#check-steps li").length, stepsInside: d.contains(document.getElementById("check-steps")) }; });
  await page.focus("#check-engine summary"); await page.keyboard.press("Enter");
  out.engine.opened = await page.evaluate(() => document.getElementById("check-engine").open);
  await page.focus("#check-engine summary"); await page.keyboard.press("Enter");
  await page.click("#check-verdict [data-finding]");
  out.top_marks = await page.evaluate(() => ({ lit: document.querySelectorAll("#check-map .m-hl").length, pressed: document.querySelector("#check-verdict [data-finding]").getAttribute("aria-pressed") }));
  await page.click("#check-all-sum");
  await page.click('#check-findings [data-finding]:has-text("audit_log")');   // the keyless table, whatever its place among the findings (n71)
  out.finding_marks = await page.evaluate(() => [...document.querySelectorAll("#check-map .m-hl")].map((g) => g.textContent));
  // n53: Ask Onto — the questions the result chose, each answered on the page, by keyboard, without a request
  const before = out.requests.length;
  out.ask_questions = await page.$$eval("#check-ask-list button", (n) => n.map((x) => x.textContent));
  out.ask = {};
  // n63: domain_draft's domains on the map (a tint and a label per table, interfaces thicker) and the list under it
  out.domains = await page.evaluate(() => ({ tinted: document.querySelectorAll("#check-map .m-dom").length,
    tags: [...document.querySelectorAll("#check-map .m-dom-tag")].map((t) => t.textContent), ifaces: document.querySelectorAll("#check-map .m-iface").length,
    list: document.getElementById("check-domains").hidden ? null : document.getElementById("check-domains").textContent }));
  out.domain_fill = {};
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    out.domain_fill[scheme] = await page.evaluate(() => [...new Set([...document.querySelectorAll("#check-map .m-dom rect")].map((r) => getComputedStyle(r).fill))]);
  }
  await page.emulateMedia({ colorScheme: "light" });
  for (const id of ["total", "first", "key", "product", "own"]) {
    await page.focus(`[data-ask="${id}"]`);
    await page.keyboard.press("Enter");
    out.ask[id] = { text: await page.textContent("#check-ask-answer"), expanded: await page.getAttribute(`[data-ask="${id}"]`, "aria-expanded"),
                    lit: await page.evaluate(() => document.querySelectorAll("#check-map .m-hl").length) };
  }
  await page.focus('[data-ask="product"]'); await page.keyboard.press("Enter");
  out.ask.product.html_links = await page.$$eval("#check-ask-answer a", (n) => n.map((a) => [a.textContent, a.getAttribute("href"), a.getAttribute("download")]));
  out.ask.product.dl = await page.$$eval("#check-ask-answer a.check-dl", (n) => n.map((a) => [a.children.length, a.nextElementSibling ? a.nextElementSibling.textContent : null,
    [...document.querySelectorAll("#check-ask-answer .check-dl-status")].map((p) => p.textContent)]));
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#check-ask-answer a[download]")]);
  out.contract = { name: dl.suggestedFilename(), text: require("fs").readFileSync(await dl.path(), "utf8") };
  await page.click('[data-ask="powerbi"]');
  await until(() => !document.getElementById("check-model").hidden && document.getElementById("check-model").textContent.length > 0);
  out.ask_powerbi_focus = await page.evaluate(() => document.activeElement.id);
  // n73: one order through the example: the finding, Onto's answer, the Power BI preview and the contract name the same row
  out.same_order = { finding: await page.textContent('#check-findings li.sev-warning'), preview: await page.textContent("#check-model .check-doubled"),
                     labels: await page.$$eval("#check-model a[download], #check-ask-answer a[download]", (n) => n.map((a) => a.textContent)) };
  // n95: every download on the page: the button's own text, the description under it, and the status lines
  out.dl_items = await page.evaluate(() => [...document.querySelectorAll("a.check-dl")].map((a) => ({ text: a.textContent, children: a.children.length,
    // n86b: the ontology's item has the question mark between the button and its description
    desc: (() => { const d = a.closest(".check-dl-item") && a.closest(".check-dl-item").querySelector(":scope > .check-dl-desc"); return d ? d.textContent : null; })(),
    tip: !!(a.nextElementSibling && a.nextElementSibling.classList.contains("kg-tip")),       // the ontology's "?" sits beside its button
    status: [...(a.closest("#check-evidence, #check-model, #check-app, #check-ask-answer") || document).querySelectorAll(".check-dl-status")].map((p) => p.textContent) })));
  out.ask_requests = out.requests.slice(before).filter((u) => !u.includes("/check/event"));
  await page.evaluate(() => window.Mascots.setEnabled(false));
  out.ask_plain = await page.evaluate(() => ({ figure: getComputedStyle(document.querySelector(".check-ask-figure")).display,
    list: getComputedStyle(document.getElementById("check-ask-list")).display, n: document.querySelectorAll("#check-ask-list button").length }));
  for (const w of [375, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    out["ask_overflow_" + w] = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  }
  await page.evaluate(() => window.Mascots.setEnabled(true));
  await page.setViewportSize({ width: 1280, height: 720 });
  // reduced motion: no step is added while the run is still going (the result is hidden); they all come with it.
  // A MutationObserver runs after the task that added the steps, so it sees whether the result was shown with them.
  await page.evaluate(() => {
    window.__stepsBeforeResult = 0;
    new MutationObserver((ms) => { if (document.getElementById("check-result").hidden) window.__stepsBeforeResult += ms.reduce((n, m) => n + m.addedNodes.length, 0); })
      .observe(document.getElementById("check-steps"), { childList: true });
  });
  await page.click("#check-sap");
  await until(() => document.documentElement.dataset.check === "done" && !!document.documentElement.dataset.checkMs && document.body.textContent.includes("SAP pack"));
  out.steps_while_running = await page.evaluate(() => window.__stepsBeforeResult);
  out.sap_text = await page.textContent("#check-run");
  await page.click("#check-crm");
  await until(() => document.documentElement.dataset.check === "done" && !!document.documentElement.dataset.checkMs);
  await page.waitForTimeout(300);
  out.crm_suggested_edges = await page.evaluate(() => document.querySelectorAll("#check-map .m-sug").length);
  // n68: the domains under the map are buttons: Enter on one keeps its tables and interfaces in colour and dims the rest
  // (no transition under reduced motion), a second choice adds to it, the chosen domain names Onto's data-product
  // question and its contract, "Show all" clears it; nothing in the list reads "null" (the el() bug of n63)
  const domState = () => page.evaluate(() => ({
    list: document.getElementById("check-domains").textContent, pressed: [...document.querySelectorAll(".check-dom")].map((b) => b.getAttribute("aria-pressed")),
    focus: !!document.querySelector("#check-map svg.m-focus"), on: document.querySelectorAll("#check-map .m-node.m-on").length, onEdges: document.querySelectorAll("#check-map .m-edge-g.m-on").length,
    opacities: [...new Set([...document.querySelectorAll("#check-map .m-node rect")].map((r) => getComputedStyle(r).opacity))].sort(),
    transition: getComputedStyle(document.querySelector("#check-map .m-node rect")).transitionDuration,
    question: (document.querySelector("[data-ask=product]") || {}).textContent }));
  out.crm_domains = { before: await domState() };
  await page.focus(".check-dom >> nth=1"); await page.keyboard.press("Enter");
  out.crm_domains.one = await domState();
  await page.click("[data-ask=product]");
  out.crm_domains.one_links = await page.$$eval("#check-ask-answer a[download]", (n) => n.map((a) => a.getAttribute("download")));
  await page.click(".check-dom >> nth=0");
  out.crm_domains.two = await domState();
  await page.click("#check-dom-all");
  out.crm_domains.all = await domState();
  // n55: the guided demo: /check?example=sample&guide=1 runs the example with no click, and Onto leads four steps,
  // by keyboard, each marking the map; with the mascots off the same steps are text; it fits 375 px
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(base + "/check?example=sample&guide=1");
  await until(() => !!document.documentElement.dataset.checkMs && !document.getElementById("check-guide").hidden && document.getElementById("check-guide").dataset.step === "1");
  const guideNow = () => page.evaluate(() => ({ step: document.getElementById("check-guide").dataset.step, title: document.getElementById("check-guide-h").textContent,
    text: document.getElementById("check-guide-text").textContent, lit: document.querySelectorAll("#check-map .m-hl").length }));
  out.guide = [await guideNow()];
  for (let i = 0; i < 3; i++) { await page.focus("#check-guide-next"); await page.keyboard.press("Enter"); out.guide.push(await guideNow()); }
  out.guide_next_disabled = await page.evaluate(() => document.getElementById("check-guide-next").disabled);
  out.guide_overflow_375 = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  await page.focus("#check-guide-back"); await page.keyboard.press("Enter");
  await page.click("#check-guide-text >> text=Accept");
  await until(() => document.documentElement.dataset.decided === "done");   // n150: said once the engine has the decision
  out.guide_decided = await page.textContent(".check-guide-said");
  await page.evaluate(() => window.Mascots.setEnabled(false));
  out.guide_plain = await page.evaluate(() => ({ figure: getComputedStyle(document.querySelector(".check-guide-figure")).display, text: document.getElementById("check-guide-text").textContent.length }));
  await page.evaluate(() => window.Mascots.setEnabled(true));
  await page.setViewportSize({ width: 1280, height: 720 });
  // n55: each industry example on /use-cases opens /check with its own example running
  out.industries = {};
  for (const k of ["sample", "sap", "crm"]) {
    await page.goto(base + "/use-cases");
    await page.click(`[data-try="${k}"]`);
    await until(() => !!document.documentElement.dataset.checkMs);
    out.industries[k] = { url: page.url().replace(base, ""), status: await page.textContent("#check-status"), guide: await page.evaluate(() => document.getElementById("check-guide").hidden) };
  }
  // n78: the fourth example, Subscription billing (Younium + Salesforce), at 375 and 1280 px: four buttons without
  // sideways scrolling, each inside the viewport, and the run done with the pack's relationships
  out.billing = {};
  for (const w of [375, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto(base + "/check");
    out.billing[w] = await page.evaluate(() => {
      const bs = [...document.querySelectorAll(".check-examples .check-ex")];
      return { ids: bs.map((b) => b.id), overflow: document.documentElement.scrollWidth > innerWidth, label: (document.getElementById("check-billing") || {}).textContent,
               inside: bs.every((b) => { const r = b.getBoundingClientRect(); return r.width > 0 && r.left >= 0 && r.right <= innerWidth; }) };
    });
    await page.click("#check-billing");
    await until(() => document.documentElement.dataset.check === "done" && !!document.documentElement.dataset.checkMs);
    out.billing[w].status = await page.textContent("#check-status");
    out.billing[w].text = await page.textContent("#check-run");
    out.billing[w].ms = Number(await page.evaluate(() => document.documentElement.dataset.checkMs));
    out.billing[w].overflowAfter = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  // plain /check starts nothing by itself
  await page.goto(base + "/check");
  await page.waitForTimeout(500);
  out.plain_idle = await page.evaluate(() => ({ check: document.documentElement.dataset.check || null, guide: document.getElementById("check-guide").hidden }));
  // WCAG AA: the example buttons' text against their soft backgrounds, light and dark
  out.contrast = [];
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    out.contrast.push(...await page.evaluate(() => {
      const rgb = (c) => c.match(/[\d.]+/g).slice(0, 3).map(Number);
      const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
      const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
      const out = [];
      for (const b of document.querySelectorAll(".check-ex")) {      // the examples and, n49, the two build buttons (no tag)
        const bg = rgb(getComputedStyle(b).backgroundColor);
        for (const t of b.querySelectorAll("strong, span")) out.push(ratio(rgb(getComputedStyle(t).color), bg));
        const em = b.querySelector("em");
        if (em) out.push(ratio(rgb(getComputedStyle(em).color), rgb(getComputedStyle(em).backgroundColor)));
      }
      return out.map((x) => Math.round(x * 100) / 100);
    }));
  }
  for (const w of [375, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    out["overflow_" + w] = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  }
  console.log(JSON.stringify(out));
  await b.close();
})();
