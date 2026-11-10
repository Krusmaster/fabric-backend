// /check: hand files to the engine in a Web Worker (check-worker.js) and draw what it reports, step by step: the
// left column lists each engine step as it finishes (its rules and its time), the right column builds the map from the
// same events. Files are read with the File API into memory and posted to the worker; the page itself makes no request
// with them (its CSP: connect-src 'none'). With prefers-reduced-motion the steps and the map appear at once, when done.
// n49: while the engine loads or runs, Onto hops beside the step under way (still, with reduced motion; hidden with the
// mascots switched off); under the result, a Power BI model and an app from the same input, previewed on the rows and
// downloaded as zips made in the worker and saved from a Blob: no request carries them either.
// n51: the two choices sit in the map column, under the legend, once the run is done (the empty space beside the long
// steps column); the preview they open stays full width under the result, and the click scrolls to its heading.
// n53: "Ask Onto" under the verdict: three to five questions picked from what the engine found, each answered here from
// the engine's own result (its check and rule names), never sent anywhere; the doubled total and a missing key are
// also marked on the map. No free text: a question box would have to send what is typed.
// n73: the finding first. After a run the state line, the most important finding and the folded list come right under
// the status line, before the map; the engine's steps are a <details> under the map ("How the engine got here"),
// closed on every run. One example row runs through the example: the finding, Onto's answer, the Power BI preview and
// the contract all name the header row the engine read (its key, its amount, its lines), never a number of their own.
// Every download button says "Download" and what the file is; its description stands under it and its status word from
// tool_status is said once above the list (n95).
// n85: the decisions taken on this page (the guided demo's Accept and Reject) go into the evidence report when it is
// downloaded, each with what, the decision, the browser's time and "by: not recorded". They stay in this browser:
// nothing is sent or saved, and a new run starts without them.
// n150: Accept and Skip sit under each suggestion in the plain list as well as in the guide, and a decision reaches the
// engine: an accepted relationship is a `confirmed` entry of the plan (browser_check.decide, browser_build.build), so it
// is among the evidence report's relationships and checks, counted in the rows, and in the Power BI model; a skipped
// one stays out of both. The export panel says where each decision went.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const script = document.currentScript || document.querySelector("script[data-worker]");
  const status = $("check-status"), run = $("check-run"), result = $("check-result");
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const worker = new Worker(script.dataset.worker, { type: "module" });
  const pending = new Map();
  let seq = 0, busy = false, onStep = null;
  const bootSteps = [];

  const loading = $("check-loading"), loadingText = $("check-loading-text");
  function hop(text) { loadingText.textContent = text; loading.hidden = false; }
  function landed() { loading.hidden = true; }
  const NEXT = { runtime: "Loading the engine…", engine: "The engine is ready." };

  worker.onmessage = (e) => {
    const d = e.data;
    if (d.step && !busy && NEXT[d.step.step]) hop(NEXT[d.step.step]);
    else if (d.step && busy) hop(d.step.title + "…");
    if (d.step) { if (onStep) onStep(d.step); else bootSteps.push(d.step); return; }
    const p = pending.get(d.id); if (p) { pending.delete(d.id); p(d); }
  };
  worker.onerror = () => say("The engine could not start in this browser. It needs WebAssembly and module workers (a current Chrome, Edge, Firefox or Safari).");
  // Two counts for the operator, sent as an image request that carries only the step's name (never a file, a file
  // name, a table or a column): "loaded" when the engine has started, "done" when a check has finished.
  const ping = (step) => { try { new Image().src = "/check/event?e=" + step; } catch (_) { /* counting is optional */ } };
  const call = (msg) => new Promise((resolve) => { const id = ++seq; pending.set(id, resolve); worker.postMessage({ id, ...msg }); });
  function say(text) { status.textContent = text; }
  const seconds = (ms) => (ms / 1000).toFixed(1) + " s";

  let booted = false, last = null, lastResult = null, built = null, map = null;
  const decisions = new Map();                       // n85: what -> the latest decision on this page; memory only, never sent or stored
  say("Loading the engine in this browser…");
  hop("Starting the Python runtime…");
  const boot = call({ kind: "boot" }).then((r) => {
    booted = r.ok;
    if (!busy) landed();
    if (r.ok) ping("loaded");
    if (!busy) say(r.ok ? "The engine is ready. Nothing has been read yet." : "The engine could not start: " + r.error);
    return r;
  });

  const LABELS = { sample: "the example “A total that doubles”", sap: "the example “SAP sales tables”", crm: "the example “Salesforce + ERP”", billing: "the example “Subscription billing”", columns: "the list of columns" };

  async function start(kind, files, text) {
    if (busy) return;
    busy = true;
    last = { kind, files: files || [], text: text || "" };
    lastResult = null;
    built = null;
    decisions.clear();                               // n85: a decision belongs to the run it was taken on
    resetBuild();
    hop(booted ? "Reading the input…" : "Loading the engine…");
    document.documentElement.dataset.check = "running";
    delete document.documentElement.dataset.checkMs;
    const what = LABELS[kind] || (files.length + (files.length === 1 ? " file" : " files"));
    const t0 = performance.now();
    say("Reading " + what + " in this browser…");
    const events = [];
    map = new MapView($("check-map"));
    $("check-ask").hidden = true;
    $("check-pilot").hidden = true;
    $("check-steps").replaceChildren();
    $("check-engine").open = false;                  // n73: the steps stay folded; the hop text names the step under way
    $("check-all").hidden = true;
    $("check-verdict").replaceChildren();
    result.hidden = true;
    if (!still) run.hidden = false;
    const show = (s) => { addStep(s); map.update(s); };
    // the engine's own start-up, if it was still loading when the visitor chose: shown as the first steps of this run
    const early = bootSteps.splice(0);
    onStep = (s) => { events.push(s); if (!still) show(s); };
    early.forEach((s) => onStep(s));
    try {
      if (!booted) await boot;
      const r = await call({ kind, files, text });
      onStep = null;
      if (!r.ok) { landed(); say("The engine stopped: " + r.error); return; }
      if (still) { run.hidden = false; events.forEach(show); }
      landed();
      lastResult = r.result;
      draw(r.result);
      if (guided) guide(r.result);
      $("check-build-head").hidden = !r.result.tables.length;
      evidence(r.result);
      ping("done");
      const ms = Math.round(performance.now());
      document.documentElement.dataset.checkMs = String(ms);
      say("Done: " + what + ", read in this browser in " + seconds(performance.now() - t0) + ". The result showed " + seconds(ms) + " after the page opened; nothing was uploaded.");
      run.focus({ preventScroll: true });
      // n86b: /docs/concepts/ontologies links to the downloads (#check-evidence) for the ontology's RDF/XML file
      const ev = $("check-evidence");
      if (location.hash === "#check-evidence" && !evidenceShown && !ev.hidden) { evidenceShown = true; ev.scrollIntoView({ behavior: "auto", block: "center" }); }
      else if (intent && INTENTS[intent] && !intentDone) {
        // after this run's finally (busy is still true here), so the Power BI draft can start; data-intent says it landed
        intentDone = true;
        setTimeout(() => Promise.resolve(INTENTS[intent]()).then(() => { document.documentElement.dataset.intent = intent; }), 0);
      }
      else run.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
    } finally {
      onStep = null;
      busy = false;
      document.documentElement.dataset.check = "done";
    }
  }

  async function readFiles(list) {
    const files = [];
    for (const f of list) files.push({ name: f.name, bytes: await f.arrayBuffer() });
    return files;
  }

  $("check-files").addEventListener("change", async (e) => { if (e.target.files.length) start("files", await readFiles(e.target.files)); });
  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => { guided = false; $("check-guide").hidden = true; start(b.dataset.example); }));
  let guided = false;                       // n55: set from the address at the end of this file
  // n190: the home page's intent tiles open /check?example=sample&intent=<key>; once the run is done, each lands on the
  // part of the result it names (pages.INTENTS): the findings, the map, the Power BI model, the ontology and evidence.
  let intent = null, intentDone = false;
  const INTENTS = {
    issues: () => { const all = $("check-all"); all.hidden = false; all.open = true; all.scrollIntoView({ behavior: "auto", block: "start" }); },
    map: () => { $("check-map").scrollIntoView({ behavior: "auto", block: "center" }); },
    model: () => openBuild("model"),
    agent: () => { const t = $("check-tile-ontology") || $("check-build-head"); t.scrollIntoView({ behavior: "auto", block: "center" }); },
  };
  $("check-columns-run").addEventListener("click", () => {
    const text = $("check-columns").value.trim();
    if (!text) { say("Paste a list of columns first: one table.column per line."); $("check-columns").focus(); return; }
    start("columns", [], text);
  });
  const drop = $("check-drop");
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
  drop.addEventListener("drop", async (e) => { e.preventDefault(); if (e.dataTransfer.files.length) start("files", await readFiles(e.dataTransfer.files)); });
  window.addEventListener("dragover", (e) => e.preventDefault());       // a file dropped beside the box stays on the page
  window.addEventListener("drop", (e) => e.preventDefault());

  // ------------------------------------------------------------------ n49: go further from the graph
  const panels = { model: $("check-model"), app: $("check-app") };
  const choices = { model: $("check-build-model"), app: $("check-build-app") };
  function resetBuild() {
    $("check-build-head").hidden = true; $("check-build").hidden = true; $("check-build-next").hidden = true; $("check-build-status").textContent = "";
    $("check-evidence").hidden = true; $("check-evidence").replaceChildren();
    for (const k in panels) { panels[k].hidden = true; panels[k].replaceChildren(); choices[k].setAttribute("aria-expanded", "false"); }
  }
  async function openBuild(which) {
    if (!last || busy) return;
    const other = which === "model" ? "app" : "model";
    panels[other].hidden = true; choices[other].setAttribute("aria-expanded", "false");
    choices[which].setAttribute("aria-expanded", "true");
    $("check-build").hidden = false;
    if (!built) {
      busy = true;
      $("check-build-status").textContent = "Drafting from your rows in this browser…";
      try {
        const r = await call({ kind: "build", input: last.kind, files: last.files, text: last.text, confirmed: acceptedLinks() });
        if (!r.ok) { $("check-build-status").textContent = "The engine stopped: " + r.error; return; }
        built = r.result;
        drawModel(built); drawApp(built);
      } finally { busy = false; }
    }
    $("check-build-status").textContent = which === "model" ? "The Power BI model draft is shown below." : "The app draft is shown below.";
    panels[which].hidden = false; $("check-build-next").hidden = false;
    const h = panels[which].querySelector("h3");
    h.focus({ preventScroll: true });
    panels[which].scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
  }
  choices.model.addEventListener("click", () => openBuild("model"));
  choices.app.addEventListener("click", () => openBuild("app"));

  const fmt = (v) => v == null ? "–" : typeof v === "number" ? v.toLocaleString("en-US") : String(v);
  const tag = (t) => el("span", { class: "status-tag" }, t);
  // n73: a download says what the file holds; n95: the button is short ("Download" and what the file is), the
  // description stands under it as plain text, and the status is said once above the list (statusLines)
  function dlItem(a, desc) {
    return el("div", { class: "check-dl-item" }, a, desc ? el("p", { class: "muted tiny check-dl-desc" }, desc) : null);
  }
  const statusSaid = (s, n) => /^draft/i.test(s) ? (n > 1 ? "drafts" : "a draft") + " for you to review" : s.charAt(0).toLowerCase() + s.slice(1);
  const listedJs = (xs) => xs.length < 2 ? xs.join("") : xs.slice(0, -1).join(", ") + " and " + xs[xs.length - 1];
  // files: [{ what, status }] as shown; one line when they share a status, otherwise one line per status
  function statusLines(files) {
    const by = new Map();
    files.filter((f) => f.status).forEach((f) => { if (!by.has(f.status)) by.set(f.status, []); by.get(f.status).push(f.what); });
    const line = (t) => el("p", { class: "muted tiny check-dl-status" }, t);
    if (by.size === 1) {
      const [[s, ws]] = [...by];
      return [line((ws.length > 1 ? "These files are " : "This file is ") + statusSaid(s, ws.length) + ".")];
    }
    return [...by].map(([s, ws]) => { const t = listedJs(ws); return line(t.charAt(0).toUpperCase() + t.slice(1) + (ws.length > 1 ? " are " : " is ") + statusSaid(s, ws.length) + "."); });
  }
  function download(name, b64, what, desc) {
    const a = el("a", { class: "btn primary small check-dl", href: "#", download: name }, "Download " + what);
    a.addEventListener("click", (e) => {               // the zip was made in the worker; a Blob saves it, nothing is fetched
      const bin = atob(b64), bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
      a.href = url; setTimeout(() => { URL.revokeObjectURL(url); a.href = "#"; }, 1000);
    });
    return dlItem(a, desc);
  }
  function figures(items) {
    return el("ul", { class: "check-kpis" }, ...items.map((m) => el("li", null, el("span", { class: "check-kpi-v" }, fmt(m.value)), el("span", { class: "check-kpi-l" }, m.name || m.label))));
  }
  function bars(c) {
    if (!c) return el("p", { class: "muted tiny" }, "No chart: no single-column relationship from a table with a measure to a table with a name to group by.");
    const max = Math.max(...c.bars.map((b) => Number(b.value) || 0), 1);
    const list = el("ul", { class: "check-bars", "aria-label": c.title },
      ...c.bars.map((b) => el("li", null, el("span", { class: "check-bar-l" }, b.label),
        el("span", { class: "check-bar-t" }, el("span", { class: "check-bar", style: "width:" + Math.max(2, Math.round(100 * (Number(b.value) || 0) / max)) + "%" })),
        el("span", { class: "check-bar-v mono" }, fmt(b.value)))));
    return el("figure", { class: "check-chart" }, el("figcaption", null, el("strong", null, c.title), c.more ? " (largest eight; " + c.more + " more)" : ""), list);
  }
  const noRows = () => el("p", { class: "muted" }, "A list of columns has no rows, so there is nothing to count: the download below has the model, the preview needs files with rows.");
  // n73: the total that doubles in the run's result, the same one Onto answers about: the amount finding whose sum over
  // the lines is the larger (else the first), with the example row the engine read
  const doubledFinding = (r) => { const a = (r ? r.findings : []).filter((f) => f.check === "amount_level" && f.amount); return a.find((f) => Number(f.amount.wrong) > Number(f.amount.right)) || a[0] || null; };
  const times = (n) => n === 1 ? "once" : n === 2 ? "twice" : n + " times";
  const rowsOf = (n, t) => n + " " + t + " row" + (n === 1 ? "" : "s");
  // "For example order_id 1: 1,000 on its orders row; 2 order_lines rows point at it, so the join counts it twice: 2,000."
  const exampleRow = (a) => a.example ? el("p", null, "For example ", code(a.example.key + " " + a.example.id), ": " + fmt(a.example.amount) + " on its " + a.header + " row; "
    + rowsOf(a.example.lines, a.line) + " point at it, so the join counts it " + times(a.example.lines) + ": " + fmt(a.example.repeated) + ".") : null;
  function doubledBlock(f, b) {
    const a = f.amount, inModel = !!(b && b.report.doubled && b.report.doubled.column === a.header + "." + a.column);
    return el("div", { class: "check-doubled" },
      el("p", null, el("strong", null, "The total that doubles: " + a.header + "." + a.column)),
      el("ul", { class: "check-kpis" }, el("li", { class: "bad" }, el("span", { class: "check-kpi-v" }, fmt(a.wrong)), el("span", { class: "check-kpi-l" }, "Summed over the joined lines (" + a.line + ")")),
        el("li", { class: "ok" }, el("span", { class: "check-kpi-v" }, fmt(a.right)), el("span", { class: "check-kpi-l" }, "Summed once per header (" + a.header + ")"))),
      exampleRow(a),
      el("p", { class: "muted tiny" }, "Summed over the " + a.line + " rows each " + a.header + " row counts once per line; summed on " + a.header + " it counts once. "
        + (inModel ? "The model's measure sums it the right way." : a.on_map ? "The model sums it on " + a.header + "." : "The example's two tables (" + a.header + ", " + a.line + ") sit beside the shop's and are not in this model; the rule is the same there: an amount is summed on the table it belongs to.")));
  }
  function drawModel(b) {
    const r = b.report, dbl = doubledFinding(lastResult);
    const kids = [el("h3", { id: "check-model-h", tabindex: "-1" }, "A simple report from your rows"),
      el("p", { class: "tiny" }, tag(b.status.report), " The report preview is drawn here: Krusgraph has no report tool. The model: ", tag(b.status.model), " (semantic_model_draft).")];
    if (!r.has_data) kids.push(noRows());
    else {
      kids.push(figures(r.measures));
      if (dbl) kids.push(doubledBlock(dbl, b));      // the run's own finding, so the preview and the finding show one order
      else if (r.doubled) kids.push(el("div", { class: "check-doubled" },
        el("p", null, el("strong", null, "The total that doubles: " + r.doubled.column)),
        el("ul", { class: "check-kpis" }, el("li", { class: "bad" }, el("span", { class: "check-kpi-v" }, fmt(r.doubled.wrong)), el("span", { class: "check-kpi-l" }, "Summed over the joined lines (" + r.doubled.line + ")")),
          el("li", { class: "ok" }, el("span", { class: "check-kpi-v" }, fmt(r.doubled.right)), el("span", { class: "check-kpi-l" }, "Summed once per header (" + r.doubled.header + ")"))),
        el("p", { class: "muted tiny" }, r.doubled.why + " The model's measure sums it the right way.")));
      kids.push(bars(r.chart));
    }
    const zip = Object.keys(b.downloads).find((n) => n.endsWith("_model.zip"));
    kids.push(el("h3", null, "The model as a Power BI project"),
      el("p", null, r.tables + " tables and " + modelRelationships(r) + " from the plan, as TMDL (Direct Lake) in a Power BI project (.pbip) with an empty report page. Before it shows data, the tables have to be in a Fabric lakehouse; the README in the zip says what to fill in. Opened in Power BI Desktop on 30 October 2026: the empty report page opens, and the data shows once the tables are in a Fabric lakehouse."),
      notBuilt(r), decisionsInModel(r),
      ...statusLines([{ what: "the Power BI project", status: b.status.model }]),
      el("div", { class: "ctas" }, download(zip, b.downloads[zip], "Power BI project", "The model (.pbip) with the plan's keys and relationships" + (r.has_data ? " as checked in the rows" : "") + ", and an empty report page.")),
      el("p", { class: "muted tiny" }, "Creating the model in Fabric (create_semantic_model): ", tag(b.status.create_model), "."));
    fill(panels.model, ...kids);       // review M3: notBuilt and decisionsInModel give null when there is nothing to say
  }
  // n150: the count is what the model holds; a relationship of the plan that is not in it is said with its reason
  const plural = (n, w) => n + " " + w + (n === 1 ? "" : "s");
  function modelRelationships(r) {
    const nb = r.not_built || [];
    if (!nb.length) return plural(r.relationships, "relationship");
    const dup = nb.filter((x) => x.reason === "key_not_unique").length, comb = nb.length - dup;
    return plural(r.plan_relationships, "relationship") + " (" + r.relationships + " exported"
      + (dup ? ", " + dup + " not built: the key on the one side is not unique" : "")
      + (comb ? ", " + comb + (comb === 1 ? " needs" : " need") + " a combined key column (see README)" : "") + ")";
  }
  function notBuilt(r) {
    const keys = (r.keys_not_unique || []).map((k) => el("li", null, code(k.table + "." + k.columns.join(" + ")),
      " is not exported as a key: " + plural(k.rows, "row") + ", " + k.distinct + " distinct" + (k.nulls ? ", " + k.nulls + " NULL" : "") + "."));
    const rels = (r.not_built || []).filter((x) => x.reason === "key_not_unique").map((x) => el("li", null, code(x.what),
      " is not built: the key it points at is not unique in the rows (see README)."));
    return keys.length || rels.length ? el("ul", { class: "tiny check-not-built" }, ...keys, ...rels) : null;
  }
  // n150: each decision taken on this page, beside what the model holds
  function decisionsInModel(r) {
    const ds = [...decisions.values()].filter((d) => d.confirmed);
    if (!ds.length) return null;
    const ref = (c) => c.source + "." + c.source_cols.join("+") + " → " + c.target;
    return el("ul", { class: "tiny check-model-decisions" }, ...ds.map((d) => {
      const what = ref(d.confirmed), nb = (r.not_built || []).find((x) => x.what === what);
      if (d.decision !== "accepted") return el("li", null, "Skipped on this page: ", code(what), " is not in the model.");
      if (nb) return el("li", null, "Accepted on this page: ", code(what), " is not in the model: " + nb.why + ".");
      return el("li", null, "Accepted on this page: ", code(what), (r.built || []).includes(what) ? " is in the model as a confirmed relationship." : " is not in the model.");
    }));
  }
  function drawApp(b) {
    const a = b.app;
    const kids = [el("h3", { id: "check-app-h", tabindex: "-1" }, "A small app over the same data"),
      el("p", { class: "tiny" }, tag("Draft only"), " A preview drawn here from your rows. The code: Rayfin connector ", tag(b.status.rayfin), "; app starter ", tag(b.status.app_starter), ".")];
    if (!a.has_data) kids.push(noRows());
    else {
      kids.push(figures(a.kpis));
      if (a.list) kids.push(el("div", { class: "check-table-wrap" }, el("table", { class: "check-list" },
        el("caption", null, "First rows of " + a.list.table),
        el("thead", null, el("tr", null, ...a.list.columns.map((c) => el("th", { scope: "col" }, c)))),
        el("tbody", null, ...a.list.rows.map((row) => el("tr", null, ...row.map((v) => el("td", null, fmt(v)))))))));
      kids.push(bars(a.chart));
    }
    const zip = Object.keys(b.downloads).find((n) => n.endsWith("_app.zip"));
    kids.push(el("h3", null, "The app's starter code"),
      el("p", null, "Rayfin connector entities with the plan's keys and relationships, and an app starter for Lovable: a prompt, GraphQL queries and the server function that keeps the secrets out of the browser, for an API over the same plan. The API does not exist until you create it in your own Fabric; the README in the zip says what to fill in."),
      ...statusLines([{ what: "the app starter", status: b.status.app_starter }]),
      el("div", { class: "ctas" }, download(zip, b.downloads[zip], "app starter", "For Lovable, with Rayfin connector entities from the same plan; the API itself does not exist yet.")));
    fill(panels.app, ...kids);
  }

  // ------------------------------------------------------------------ drawing (textContent only: names come from files)
  // a child that is null, undefined or false is left out (n68: a conditional child written as `cond ? node : null`),
  // and fill() does the same for a node's replaceChildren, which would otherwise write the word "null" into the page
  const kept = (k) => k != null && k !== false;
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (kept(v)) n.setAttribute(k, v);
    for (const k of kids) if (kept(k)) n.append(k);
    return n;
  }
  const fill = (node, ...kids) => node.replaceChildren(...kids.filter(kept));
  const code = (t) => el("code", null, t);
  // n86b: the question mark next to a concept (site.js); nothing when site.js has not run
  const tip = (name) => (window.KGTip && window.KGTip.els(name)) || { button: null, body: null };
  let evidenceShown = false;

  function addStep(s) {
    $("check-steps").append(el("li", { class: "check-step" + (still ? "" : " in") },
      el("span", { class: "check-step-ms mono" }, s.ms < 1000 ? s.ms + " ms" : seconds(s.ms)),
      el("strong", null, s.title), el("span", { class: "check-step-detail" }, s.detail)));
  }

  // n59: the renderer is in map.js, shared with /use-cases
  const MapView = function (box) { return new window.KrusMap.MapView(box, { still, summary: (t) => { $("check-map-summary").textContent = t; } }); };

  // n55: the map first. Under it one line with the state and the count, the most important finding, and every item
  // folded into "Show all N findings"; selecting a finding's title marks its relationship or table on the map.
  // where a finding is on the map, most precise first: its relationship, the amount's lines → header, its table
  const where = (f) => window.KrusMap.where(f);
  function mark(f, btn) {
    const shown = !!map && where(f).some((x) => map.highlight(x));
    if (!shown && map) map.highlight(null);
    document.querySelectorAll("[data-finding]").forEach((b) => b.setAttribute("aria-pressed", String(b === btn && shown)));
    if (shown) $("check-map").scrollIntoView({ behavior: still ? "auto" : "smooth", block: "center" });
    say(shown ? "Marked on the map: " + f.title + "." : f.title + ": not on the map.");
  }
  const findingButton = (f, cls) => {
    const b = el("button", { type: "button", class: cls, "data-finding": "", "aria-pressed": "false" }, f.title);
    b.addEventListener("click", () => mark(f, b));
    return b;
  };

  function draw(r) {
    result.hidden = false;
    const all = r.findings.concat(r.suggestions), n = all.length, top = all[0];
    $("check-verdict").replaceChildren(
      el("p", { class: "check-state check-" + r.verdict.headline.state }, el("strong", null, r.verdict.headline.title),
        " · " + (n ? n + (n === 1 ? " thing" : " things") + " to check" : "nothing to check")),
      top ? el("p", { class: "check-top" }, el("span", { class: "muted" }, "Most important: "), findingButton(top, "check-finding-link")) : el("p", { class: "muted" }, r.verdict.headline.text),
      // n75: how much the run counted in the rows, from the result itself (never a fixed sentence)
      r.coverage && r.coverage.text ? el("p", { class: "muted tiny check-coverage", id: "check-coverage" }, r.coverage.text) : null);
    $("check-all").hidden = !r.tables.length && !n;
    $("check-all").open = false;
    $("check-all-sum").textContent = "Show all " + n + (n === 1 ? " finding" : " findings");
    $("check-verdict-items").replaceChildren(el("li", null, r.verdict.headline.text),
      ...r.verdict.items.map((i) => el("li", null, el("strong", null, i.title), " ", i.text)));
    if (r.tables.length) $("check-map-summary").textContent = r.tables.length + " tables, " + r.relationships.length + " relationships. " + r.health;
    const list = (items) => items.map((f) => el("li", { class: "check-finding sev-" + f.severity },
      el("p", { class: "check-finding-title" }, el("strong", null, findingButton(f, "check-finding-link"))),
      el("p", { class: "tiny check-tags" }, code(f.check), ...f.rules.map((x) => code("rule " + x)), " ", f.severity),
      el("p", null, f.saw), el("p", { class: "muted" }, f.means), f.next ? el("p", null, el("strong", null, "Next: "), f.next) : null,
      f.checked ? el("p", { class: "muted tiny check-checked" }, f.checked) : null,           // n75: what the check read
      f.confirmed && f.link ? decideButtons(f, "Skip") : null,                                // n150: Accept or Skip, here too
      f.sql ? el("details", null, el("summary", null, "SQL to look for yourself"), el("pre", null, f.sql)) : null));
    $("check-findings").replaceChildren(...(r.findings.length ? list(r.findings) : [el("li", null, r.tables.length ? "Nothing the engine counts as wrong or unclear." : "Nothing could be read.")]));
    $("check-suggestions-h").hidden = !r.suggestions.length;
    $("check-suggestions").replaceChildren(...list(r.suggestions));
    $("check-tables").replaceChildren(...r.tables.map((t) => el("p", { class: "tiny" }, el("strong", null, t.name), " ",
      ...(t.key.length ? ["key ", code(t.key.join(" + ")), " (rule " + t.key_rule + ")"] : ["no key (rule K3)"]))));
    $("check-notes").replaceChildren(...((r.source && r.source.notes) || []).map((n) => el("li", null, n)));
    domainsOn(r);
    $("check-pilot").hidden = !r.findings.length;     // n58: one way from a finding to the pilot page
    ask(r);
  }

  // ------------------------------------------------------------------ n55: the guided demo
  // Onto leads four steps over the run on the page: how the tables connect, the total that doubles, a suggestion to
  // decide on (orders.ship_to_id, the old /demo story), and on to Power BI or an app. Each step marks the map; with the
  // mascots off the same steps are text. The decision stays on this page: nothing is sent or saved.
  function guide(r) {
    const box = $("check-guide"), text = $("check-guide-text"), back = $("check-guide-back"), next = $("check-guide-next");
    const amount = r.findings.find((f) => f.check === "amount_level" && f.amount);
    const sug = r.suggestions.find((f) => f.link);
    const rel = r.relationships[0];
    const steps = [{ title: "How the tables connect", at: rel ? { source: rel.source, target: rel.target, source_cols: rel.source_cols } : null, body: () => [
      el("p", null, "The engine read " + r.tables.length + " tables and found " + r.relationships.length + " relationships from the column names alone. Each line on the map is one, with the rule that found it."),
      rel ? el("p", null, "For example ", code(rel.source + "." + rel.source_cols.join(" + ")), " → ", code(rel.target), ", rule " + rel.rule + ": marked on the map.") : null,
      el("p", { class: "muted tiny" }, r.health)] }];
    if (amount) steps.push({ title: "Here the total doubles", finding: amount, body: () => {
      const a = amount.amount;
      return [el("p", null, code(a.header + "." + a.column), " is an amount on each ", code(a.header), " row. Join ", code(a.line), " to it and sum, and every line repeats it."),
        el("ul", { class: "check-kpis" },
          el("li", { class: "bad" }, el("span", { class: "check-kpi-v" }, fmt(a.wrong)), el("span", { class: "check-kpi-l" }, "Summed over the joined lines")),
          el("li", { class: "ok" }, el("span", { class: "check-kpi-v" }, fmt(a.right)), el("span", { class: "check-kpi-l" }, "Summed once per " + a.header + " row"))),
        el("p", { class: "muted tiny" }, amount.next || "")];
    } });
    if (sug) steps.push({ title: "A suggestion to decide on", at: sug.link, body: () => {
      const said = el("p", { class: "check-guide-said", role: "status" });
      const tell = (d) => { said.textContent = saidFor(d); };
      const decide = async (yes) => tell(await decideRel(sug, yes ? "accepted" : "rejected"));
      const yes = el("button", { type: "button", class: "btn secondary small" }, "Accept"), no = el("button", { type: "button", class: "btn ghost small" }, "Reject");
      yes.addEventListener("click", () => decide(true)); no.addEventListener("click", () => decide(false));
      tell(decisions.get(relWhat(sug)));             // back on this step: the latest choice is still shown
      return [el("p", null, code(sug.link.source + "." + sug.link.source_cols.join(" + ")), " names no table, so no naming rule links it. The values point at ", code(sug.link.target), ": the dashed line."),
        el("p", null, sug.saw), el("p", { class: "muted" }, sug.means || "What it means is your decision: a delivery address, or something else?"),
        el("p", { class: "ctas" }, yes, no), said];
    } });
    steps.push({ title: "On to Power BI or an app", body: () => {
      const m = el("button", { type: "button", class: "btn primary small" }, "Build a Power BI model"), a = el("button", { type: "button", class: "btn secondary small" }, "See it as an app");
      m.addEventListener("click", () => openBuild("model")); a.addEventListener("click", () => openBuild("app"));
      return [el("p", null, "From the same plan and the rows, in this browser: a simple report and the model as a Power BI project, or a small app and its starter code. In your own Fabric it is a step in Claude."),
        el("p", { class: "ctas" }, m, a)];
    } });
    let i = 0;
    function show(focus) {
      const s = steps[i];
      $("check-guide-n").textContent = "The guided demo · step " + (i + 1) + " of " + steps.length + " · synthetic data";
      $("check-guide-h").textContent = s.title;
      text.replaceChildren(...s.body().filter(Boolean));
      if (map) { if (s.finding) mark(s.finding, null); else map.highlight(s.at || null); }
      back.disabled = i === 0; next.disabled = i === steps.length - 1;
      box.dataset.step = String(i + 1);
      if (focus) $("check-guide-h").focus({ preventScroll: true });
    }
    back.onclick = () => { if (i > 0) { i--; show(true); } };
    next.onclick = () => { if (i < steps.length - 1) { i++; show(true); } };
    box.hidden = false;
    show(false);
  }

  // ------------------------------------------------------------------ n63: domains on the map
  // domain_draft's proposal from the worker's result (browser_check runs domains.draft on the same plan): with two
  // domains or more the map tints each domain's tables and labels them, and a list under the map says the same in words.
  // n68: each domain in the list is a button: chosen (one or several), its tables and interfaces keep full colour on
  // the map and the rest is dimmed; "Show all" clears the choice. The same choice names the domain Onto offers to
  // package as a data product, and the contract that answer saves.
  const domainsOf = (r) => (r.domains && r.domains.domains) || [];
  let picked = [];
  function domainsOn(r) {
    const box = $("check-domains"), ds = domainsOf(r);
    picked = [];
    if (ds.length < 2) { box.hidden = true; box.replaceChildren(); return; }
    const tint = map ? map.domains(r.domains) : {};
    const name = (slug) => (ds.find((d) => d.slug === slug) || { name: slug }).name;
    const ifs = r.domains.interfaces || [];
    const said = el("p", { class: "muted tiny check-dom-said", role: "status" });
    const buttons = ds.map((d) => {
      const b = el("button", { type: "button", class: "check-dom", "data-domain": d.slug, "aria-pressed": "false" },
        el("span", { class: "check-dom-sw m-dom-" + (tint[d.slug] != null ? tint[d.slug] : 0), "aria-hidden": "true" }),
        el("strong", null, d.name), ": " + d.tables.join(", "));
      b.addEventListener("click", () => choose(picked.includes(d.slug) ? picked.filter((x) => x !== d.slug) : picked.concat(d.slug)));
      return b;
    });
    const all = el("button", { type: "button", class: "btn ghost small", id: "check-dom-all" }, "Show all");
    all.addEventListener("click", () => choose([]));
    function choose(slugs) {
      picked = slugs;
      buttons.forEach((b) => b.setAttribute("aria-pressed", String(picked.includes(b.dataset.domain))));
      if (map) map.focus(r.domains, picked);
      const names = picked.map(name);
      said.textContent = names.length ? "On the map: " + names.join(" and ") + ", with the tables and interfaces of " + (names.length === 1 ? "that domain" : "those domains") + "; the rest is dimmed." : "";
      ask(r);
    }
    const dt = tip("data-products");
    fill(box, el("h4", null, "Proposed domains", dt.button), dt.body,
      el("p", { class: "muted tiny" }, "From the keys and relationships alone (domain_draft): a proposal to review, not a decision. Choose one or more to see them on the map. ",
        el("a", { href: "/docs/concepts/data-products" }, "Domains and data products, explained")),
      el("ul", { class: "check-dom-list" }, ...buttons.map((b) => el("li", null, b))),
      el("p", { class: "check-dom-actions" }, all), said,
      ifs.length ? el("p", { class: "tiny" }, el("strong", null, "Interfaces between them (the thicker lines): ")) : null,
      ifs.length ? el("ul", { class: "tiny check-dom-ifs" }, ...ifs.map((i) => el("li", null, code(i.source + "." + i.source_cols.join(" + ")), " → ", code(i.target),
        " (" + i.rule + "): " + name(i.consumer) + " uses the key of " + name(i.provider)))) : null,
      (r.domains.unassigned || []).length ? el("p", { class: "muted tiny" }, "Not placed: " + r.domains.unassigned.map((u) => u.table + " (" + u.reason + ")").join("; ") + ".") : null);
    box.hidden = false;
  }
  function saveText(name, text, what, desc, type) {   // written here; a Blob saves it, nothing is fetched
    const a = el("a", { class: "btn secondary small check-dl", href: "#", download: name }, "Download " + what);
    a.addEventListener("click", () => {                  // n85: a function is called at each click, so the file is as of now
      const url = URL.createObjectURL(new Blob([typeof text === "function" ? text() : text], { type: type || "application/yaml" }));
      a.href = url; setTimeout(() => { URL.revokeObjectURL(url); a.href = "#"; }, 1000);
    });
    return dlItem(a, desc);
  }

  // n85: the decisions taken on this page (`decisions`, declared at the top), latest choice per item
  function decideOn(what, decision, confirmed) {
    const d = { what, decision, confirmed: confirmed || null, at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z") };
    decisions.delete(what); decisions.set(what, d);
    return d;
  }
  // n150: one decision for a suggested relationship, wherever it was taken (the list or the guide), sent to the engine
  // in this browser: the evidence report and the model are made again with it
  const relWhat = (f) => "suggested relationship " + f.link.source + "." + f.link.source_cols.join("+") + " -> " + f.link.target;
  const acceptedLinks = () => [...decisions.values()].filter((d) => d.decision === "accepted" && d.confirmed).map((d) => d.confirmed);
  // review L11: what the engine said about the decision (decide's not_in_model), not a sentence written in advance
  const saidFor = (d) => !d ? "" : d.decision === "accepted"
    ? "Accepted on this page: the relationship is in the plan as confirmed and counted in the rows; " + (d.notInModel
      ? "it is not in the Power BI model, because the key it points at is not unique in the rows (see the model's panel)."
      : "the Power BI model takes it.") + " In Claude, the review keeps your decision and its reason. The evidence report lists it."
    : "Rejected on this page: the column stays unlinked. The evidence report lists the decision.";
  let deciding = Promise.resolve();
  function decideRel(f, decision) {
    const d = decideOn(relWhat(f), decision, f.confirmed);
    const run = last;
    document.documentElement.dataset.decided = "running";
    deciding = deciding.then(async () => {
      const r = await call({ kind: "decide", input: run.kind, files: run.files, text: run.text, accepted: acceptedLinks(),
                             rejected: [...decisions.values()].filter((x) => x.decision !== "accepted" && x.confirmed).map((x) => x.confirmed) });
      if (run !== last) return;                       // a new run started meanwhile: its own result stands
      if (r.ok && lastResult) lastResult.evidence_report = r.result.evidence_report;
      if (r.ok) d.notInModel = (r.result.not_in_model || []).includes(f.link.source + "." + f.link.source_cols.join("+") + " -> " + f.link.target);
      built = null;
      const open = Object.keys(panels).find((k) => !panels[k].hidden);
      if (open) {                                      // the preview on the screen is drawn again with the decision
        const b = await call({ kind: "build", input: run.kind, files: run.files, text: run.text, confirmed: acceptedLinks() });
        if (b.ok && run === last) { built = b.result; drawModel(built); drawApp(built); }
      }
    }).finally(() => { if (run === last) document.documentElement.dataset.decided = "done"; });
    return deciding.then(() => d);
  }
  function decideButtons(f, noWord) {
    const said = el("p", { class: "muted tiny check-decided", role: "status" }, saidFor(decisions.get(relWhat(f))));
    const yes = el("button", { type: "button", class: "btn secondary small", "data-decide": "accepted" }, "Accept");
    const no = el("button", { type: "button", class: "btn ghost small", "data-decide": "rejected" }, noWord);
    const go = async (decision) => { said.textContent = await decideRel(f, decision).then(saidFor); };
    yes.addEventListener("click", () => go("accepted")); no.addEventListener("click", () => go("rejected"));
    return el("div", { class: "check-decide" }, el("p", { class: "ctas" }, yes, no), said);
  }
  // The worker's report says "None recorded." under Decisions; with decisions taken here that section becomes their
  // table (evidence_report.markdown's columns) and the summary counts them. Without any, the report is the worker's, as is.
  const NONE = "## Decisions\n\nNone recorded.";
  function withDecisions(md) {
    if (!decisions.size) return md;
    const cell = (x) => String(x).replace(/\|/g, "\\|").replace(/\n/g, " ");
    const said = (d) => d.decision === "accepted" ? "accepted, in the plan as confirmed" : "rejected, the column stays unlinked";
    const accepted = [...decisions.values()].some((d) => d.decision === "accepted");
    const block = ["## Decisions", "",
      "Taken on /check in this browser, which sent and saved none of them; the time is the browser's clock."
        + (accepted ? " An accepted relationship is in the plan as confirmed (rule confirmed): it is among the relationships and the checks above, counted in the rows." : ""), "",
      "| What | Decision | By | When |", "| --- | --- | --- | --- |",
      ...[...decisions.values()].map((d) => "| " + cell(d.what) + " | " + said(d) + " | not recorded | " + cell(d.at) + " |")].join("\n");
    const out = md.includes(NONE) ? md.replace(NONE, () => block) : md.replace(/\n*$/, "\n\n" + block + "\n");
    return out.replace(/^(- \d+ open question\(s\), )0 decision\(s\)/m, (_, head) => head + decisions.size + " decision(s)");
  }

  // n79: the evidence report for a pilot's hand-over, written by the worker from the plan and validate_plan's counts
  function evidence(r) {
    const e = r.evidence_report, box = $("check-evidence");
    box.replaceChildren();
    if (!e || !r.tables.length) { box.hidden = true; return; }
    // n80: the same plan as RDF/XML for Microsoft's Ontology Playground, which reads RDF/XML and not Turtle; opened
    // there with a file import (there is no link that opens it there)
    const o = r.ontology_rdfxml;
    // n188: two tiles beside "Build a Power BI model" and "See it as an app": the ontology (lavender) and the evidence
    // report (mustard), each with its download; the status line under the grid
    const files = (o ? [{ what: "the ontology", status: o.status }] : []).concat([{ what: "the evidence report", status: e.status }]);
    const tile = (cls, id, title, item) => el("div", { class: "check-ex check-tile " + cls, id, role: "group", "aria-labelledby": id + "-h" },
      el("strong", { id: id + "-h" }, title), item);
    if (o) {
      const item = saveText(o.name, o.xml, "ontology", "For Microsoft's Ontology Playground (RDF/XML): " + o.entity_types + (o.entity_types === 1 ? " entity type" : " entity types")
        + " with their columns and " + o.relationship_types + (o.relationship_types === 1 ? " relationship" : " relationships") + ", the rule in each description; no row values. Open it there with Import / Export.", "application/rdf+xml");
      const t = tip("ontology");                         // n86b: the question mark next to "Download ontology"
      if (t.button) { const a = item.querySelector("a"), row = el("div", { class: "check-dl-row" }); a.replaceWith(row); row.append(a, t.button); row.after(t.body); }
      box.append(tile("lav", "check-tile-ontology", "Build a Fabric IQ ontology", item));
    }
    box.append(tile("mustard", "check-tile-evidence", "Hand over the evidence",
      saveText(e.name, () => withDecisions((lastResult && lastResult.evidence_report || e).markdown), "evidence report", "For a hand-over (Markdown): source, time, engine version, every key and relationship with its rule, "
      + (r.source && r.source.has_data ? "each check with its counts" : "every check marked not checked") + ", open questions and this page's decisions; no row values.", "text/markdown")));
    box.append(...statusLines(files));
    box.hidden = false;
  }

  // ------------------------------------------------------------------ n53: Ask Onto
  // Every answer is drawn from `r`, the result the worker returned; nothing here makes a request.
  function ask(r) {
    const box = $("check-ask"), listEl = $("check-ask-list"), answer = $("check-ask-answer");
    answer.hidden = true; answer.replaceChildren();
    if (map) map.highlight(null);
    if (!r.tables.length) { box.hidden = true; return; }
    const tags = (f) => el("p", { class: "tiny check-tags" }, code(f.check), ...f.rules.map((x) => code("rule " + x)));
    const doubled = doubledFinding(r);                 // the same finding the Power BI preview shows
    const keyless = r.tables.find((t) => !t.key.length);
    const qs = [];
    if (doubled) qs.push({ id: "total", q: "Why does this total come out twice?", a: () => {
      const a = doubled.amount;
      const rel = { source: a.line, target: a.header, source_cols: a.line_columns };
      const shown = a.on_map && map && map.highlight(rel);
      return [el("p", null, el("strong", null, a.header + "." + a.column), " is an amount on ", code(a.header), ", and ", code(a.line),
          " has rows that point at each ", code(a.header), " row (", code(a.line + "." + a.line_columns.join(" + ")), " → ", code(a.header), "). Summed over the joined rows, each header amount is counted once per line."),
        exampleRow(a),
        el("ul", { class: "check-kpis" },
          el("li", { class: "bad" }, el("span", { class: "check-kpi-v" }, fmt(a.wrong)), el("span", { class: "check-kpi-l" }, "Summed over the joined lines (" + a.line + ")")),
          el("li", { class: "ok" }, el("span", { class: "check-kpi-v" }, fmt(a.right)), el("span", { class: "check-kpi-l" }, "Summed once per header (" + a.header + ")"))),
        el("p", { class: "muted tiny" }, shown ? "The relationship is marked on the map. " : "", doubled.next),
        tags(doubled)];
    } });
    qs.push({ id: "first", q: "What should I check first?", a: () => {
      const f = r.findings[0] || r.suggestions[0];
      if (!f) return [el("p", null, "Nothing the engine counts as wrong or unclear, and nothing to decide on. " + (r.health || ""))];
      if (f.link && map) map.highlight(f.link); else if (map) map.highlight(f.table ? { table: f.table } : null);
      return [el("p", null, el("strong", null, f.title)), el("p", null, f.saw), f.next ? el("p", null, el("strong", null, "Next: "), f.next) : null,
        el("p", { class: "muted tiny" }, r.findings.length > 1 ? "It comes first in the list below, ordered by severity (" + f.severity + "); " + (r.findings.length - 1) + " more follow." : "Severity: " + f.severity + "."), tags(f)];
    } });
    if (keyless) qs.push({ id: "key", q: "Why is there no key on " + keyless.name + "?", a: () => {
      const f = r.findings.concat(r.suggestions).find((x) => x.check === "keyless" && x.table === keyless.name);
      if (map) map.highlight({ table: keyless.name });
      return [el("p", null, f ? f.saw : "No column of " + keyless.name + " is named like a key (rule K3)."),
        el("p", { class: "muted" }, f ? f.means : "The table can point at others, but nothing can point at it."),
        f && f.next ? el("p", null, el("strong", null, "Next: "), f.next) : null,
        el("p", { class: "muted tiny" }, "The table is marked on the map."), f ? tags(f) : el("p", { class: "tiny check-tags" }, code("rule K3"))];
    } });
    const chosen = domainsOf(r).find((d) => picked.includes(d.slug));               // n68: the domain chosen under the map, if any
    const product = chosen || domainsOf(r).find((d) => d.tables.length >= 2);
    if (product) qs.push({ id: "product", q: chosen ? "Package " + product.name + " as a data product?" : "These " + product.tables.length + " tables hang together as " + product.name + ". Package them as a data product?", a: () => {
      const yaml = (r.domains.contracts || {})[product.slug] || "";
      const rels = product.relationships || [], checks = product.checks || [];
      if (map) map.highlight({ table: product.tables[0] });
      return [el("p", null, "A data product is a set of tables one team owns and promises to others, with a contract that says what they can rely on."),
        el("p", { class: "muted tiny" }, "Why these belong together: " + product.name_reason + "."),
        el("p", null, el("strong", null, "Tables and keys")),
        el("ul", { class: "tiny" }, ...product.tables.map((t) => el("li", null, code(t), " ", ...((product.keys[t] || []).length ? ["key ", code(product.keys[t].join(" + "))] : ["no key"])))),
        el("p", null, el("strong", null, "Relationships inside it")),
        rels.length ? el("ul", { class: "tiny" }, ...rels.map((x) => el("li", null, code(x.source + "." + x.source_cols.join(" + ")), " → ", code(x.target), " (rule " + x.rule + ")")))
          : el("p", { class: "tiny" }, "None: its tables are linked through a shared parent."),
        el("p", null, el("strong", null, "What validate_plan counted")),
        checks.length ? el("ul", { class: "tiny" }, ...checks.map((c) => el("li", null, c.what + ": " + c.verdict)))
          : el("p", { class: "tiny" }, "No rows to count: a columns list gives the plan only."),
        el("p", { class: "muted tiny" }, "The contract (Open Data Contract Standard v3.2.0, YAML) is written in this browser from the plan: keys unique, no orphan rows, one foreign key per relationship. A draft to review; nothing is created."),
        ...statusLines([{ what: "the data contract", status: r.domains.status }]),
        el("div", { class: "ctas" }, saveText(product.slug + ".odcs.yaml", yaml, "data contract", "ODCS 3.2 YAML: schema, keys, relationships and " + (r.source && r.source.has_data ? "the checks that passed" : "the checks to run") + (doubledFinding(r) ? ", with the total that doubles" : "") + "."),
          el("a", { class: "btn primary small", href: "/start" }, "Connect Microsoft Fabric"))];
    } });
    qs.push({ id: "powerbi", q: "How do I get this into Power BI?", a: () => {
      setTimeout(() => openBuild("model"), 0);
      return [el("p", null, "Below the result: a simple report from your rows and the model as a Power BI project (.pbip) to download, made from the same plan in this browser. Creating the model in your own Fabric is a step in Claude (create_semantic_model).")];
    } });
    qs.push({ id: "own", q: "Can I ask my own questions?", a: () => [
      el("p", null, el("strong", null, "Yes, in Claude."), " Connect " + $("check-ask").dataset.product + " to Claude and ask about your own lakehouse; the answers come with the same rules and are checked against the rows. Here on /check nothing leaves the browser, so there is no question box."),
      el("p", { class: "ctas" }, el("a", { class: "btn primary small", href: "/start" }, "Connect Microsoft Fabric"))] });
    listEl.replaceChildren(...qs.map((x) => {
      const b = el("button", { type: "button", class: "check-ask-q", "aria-expanded": "false", "aria-controls": "check-ask-answer", "data-ask": x.id }, x.q);
      b.addEventListener("click", () => {
        const open = b.getAttribute("aria-expanded") === "true";
        listEl.querySelectorAll("button").forEach((o) => o.setAttribute("aria-expanded", "false"));
        if (open) { answer.hidden = true; answer.replaceChildren(); if (map) map.highlight(null); return; }
        b.setAttribute("aria-expanded", "true");
        fill(answer, el("p", { class: "check-ask-said" }, x.q), ...x.a());
        answer.hidden = false;
      });
      return el("li", null, b);
    }));
    box.hidden = false;
  }

  // n55: /check?example=sample starts that example at once (the start page's "Try the guided demo", the industry
  // examples on /use-cases); &guide=1 adds Onto's four steps over the same run. /demo and /explore redirect here.
  const query = new URLSearchParams(location.search);
  if (["sample", "sap", "crm", "billing"].includes(query.get("example"))) {
    guided = query.get("guide") === "1";
    intent = query.get("intent");
    if (guided) $("check-guide").hidden = false;
    start(query.get("example"));
  }
})();
