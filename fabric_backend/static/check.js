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

  let booted = false, last = null, built = null, map = null;
  say("Loading the engine in this browser…");
  hop("Starting the Python runtime…");
  const boot = call({ kind: "boot" }).then((r) => {
    booted = r.ok;
    if (!busy) landed();
    if (r.ok) ping("loaded");
    if (!busy) say(r.ok ? "The engine is ready. Nothing has been read yet." : "The engine could not start: " + r.error);
    return r;
  });

  const LABELS = { sample: "the example “A total that doubles”", sap: "the example “SAP sales tables”", crm: "the example “Salesforce + ERP”", columns: "the list of columns" };

  async function start(kind, files, text) {
    if (busy) return;
    busy = true;
    last = { kind, files: files || [], text: text || "" };
    built = null;
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
      draw(r.result);
      if (guided) guide(r.result);
      $("check-build-head").hidden = !r.result.tables.length;
      ping("done");
      const ms = Math.round(performance.now());
      document.documentElement.dataset.checkMs = String(ms);
      say("Done: " + what + ", read in this browser in " + seconds(performance.now() - t0) + ". The result showed " + seconds(ms) + " after the page opened; nothing was uploaded.");
      run.focus({ preventScroll: true });
      run.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
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
        const r = await call({ kind: "build", input: last.kind, files: last.files, text: last.text });
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
  function download(name, b64, label) {
    const a = el("a", { class: "btn primary small", href: "#", download: name }, label);
    a.addEventListener("click", (e) => {               // the zip was made in the worker; a Blob saves it, nothing is fetched
      const bin = atob(b64), bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const url = URL.createObjectURL(new Blob([bytes], { type: "application/zip" }));
      a.href = url; setTimeout(() => { URL.revokeObjectURL(url); a.href = "#"; }, 1000);
    });
    return a;
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
  function drawModel(b) {
    const r = b.report;
    const kids = [el("h3", { id: "check-model-h", tabindex: "-1" }, "A simple report from your rows"),
      el("p", { class: "tiny" }, tag(b.status.report), " The report preview is drawn here: Krusgraph has no report tool. The model: ", tag(b.status.model), " (semantic_model_draft).")];
    if (!r.has_data) kids.push(noRows());
    else {
      kids.push(figures(r.measures));
      if (r.doubled) kids.push(el("div", { class: "check-doubled" },
        el("p", null, el("strong", null, "The total that doubles: " + r.doubled.column)),
        el("ul", { class: "check-kpis" }, el("li", { class: "bad" }, el("span", { class: "check-kpi-v" }, fmt(r.doubled.wrong)), el("span", { class: "check-kpi-l" }, "Summed over the joined lines (" + r.doubled.line + ")")),
          el("li", { class: "ok" }, el("span", { class: "check-kpi-v" }, fmt(r.doubled.right)), el("span", { class: "check-kpi-l" }, "Summed once per header (" + r.doubled.header + ")"))),
        el("p", { class: "muted tiny" }, r.doubled.why + " The model's measure sums it the right way.")));
      kids.push(bars(r.chart));
    }
    const zip = Object.keys(b.downloads).find((n) => n.endsWith("_model.zip"));
    kids.push(el("h3", null, "The model as a Power BI project"),
      el("p", null, r.tables + " tables and " + r.relationships + " relationships from the plan, as TMDL (Direct Lake) in a Power BI project (.pbip) with an empty report page. Before it shows data, the tables have to be in a Fabric lakehouse; the README in the zip says what to fill in. Opening it in Power BI Desktop has not been tried yet."),
      el("p", { class: "ctas" }, download(zip, b.downloads[zip], "Download " + zip)),
      el("p", { class: "muted tiny" }, "Creating the model in Fabric (create_semantic_model): ", tag(b.status.create_model), "."));
    panels.model.replaceChildren(...kids);
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
      el("p", null, "Rayfin connector entities with the plan's keys and relationships, and a Lovable prompt, GraphQL queries and a Supabase edge function for an API over the same plan. The API does not exist until you create it in your own Fabric; the README in the zip says what to fill in."),
      el("p", { class: "ctas" }, download(zip, b.downloads[zip], "Download " + zip)));
    panels.app.replaceChildren(...kids);
  }

  // ------------------------------------------------------------------ drawing (textContent only: names come from files)
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
    for (const k of kids) if (k != null) n.append(k);
    return n;
  }
  const code = (t) => el("code", null, t);

  function addStep(s) {
    $("check-steps").append(el("li", { class: "check-step" + (still ? "" : " in") },
      el("span", { class: "check-step-ms mono" }, s.ms < 1000 ? s.ms + " ms" : seconds(s.ms)),
      el("strong", null, s.title), el("span", { class: "check-step-detail" }, s.detail)));
  }

  function MapView(box) {
    const NS = "http://www.w3.org/2000/svg";
    let svg = null, edges = null, nodes = null, pos = {}, W = 760, H = 460, lit = [];
    const groups = {};
    box.replaceChildren();
    const add = (parent, tag, attrs, text) => { const x = document.createElementNS(NS, tag); for (const k in attrs) x.setAttribute(k, attrs[k]); if (text != null) x.textContent = text; parent.append(x); return x; };
    const key = (s, t, c) => s + "|" + (c || []).join("+").toLowerCase() + "|" + t;
    const lines = {};
    function edge(x, cls) {
      const a = pos[x.source], b = pos[x.target];
      if (!a || !b || lines[key(x.source, x.target, x.source_cols)]) return;
      const g = add(edges, "g", { class: "m-edge-g " + cls + (still ? "" : " in") });
      add(g, "line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: "m-edge" });
      if (x.rule) add(g, "text", { x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2 - 5, class: "m-rule", "text-anchor": "middle" }, x.rule);
      lines[key(x.source, x.target, x.source_cols)] = g;
    }
    // n53: mark one relationship (source, target, columns) or one table; returns whether it is on the map
    this.highlight = (x) => {
      lit.forEach((g) => g.classList.remove("m-hl")); lit = [];
      const g = !x ? null : x.table ? groups[x.table] : lines[key(x.source, x.target, x.source_cols)];
      if (g) { g.classList.add("m-hl"); lit.push(g); }
      return !!g;
    };
    this.update = (s) => {
      if (s.step === "keys") {
        const n = s.tables.length;
        H = n > 10 ? 560 : 440;
        svg = document.createElementNS(NS, "svg");
        svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
        svg.setAttribute("aria-hidden", "true");
        edges = add(svg, "g", {}); nodes = add(svg, "g", {});
        box.replaceChildren(svg);
        const rx = W / 2 - 90, ry = H / 2 - 40;
        s.tables.forEach((t, i) => {
          const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
          pos[t.name] = n === 1 ? [W / 2, H / 2] : [W / 2 + rx * Math.cos(a), H / 2 + ry * Math.sin(a)];
          const [x, y] = pos[t.name], label = t.name.length > 18 ? t.name.slice(0, 17) + "…" : t.name, w = Math.max(84, Math.min(170, 8.4 * label.length + 22));
          const g = add(nodes, "g", { class: (t.key.length ? "m-node" : "m-node m-nokey") + (still ? "" : " in"), style: still ? "" : `animation-delay:${Math.min(i * 40, 600)}ms` });
          groups[t.name] = g;
          add(g, "rect", { x: x - w / 2, y: y - 21, width: w, height: 42, rx: 12 });
          add(g, "text", { x, y: y - 3, "text-anchor": "middle", class: "m-name" }, label);
          add(g, "text", { x, y: y + 13, "text-anchor": "middle", class: "m-key" }, t.key.length ? "key " + t.key_rule : "no key · K3");
        });
        $("check-map-summary").textContent = n + " tables.";
      } else if (s.step === "relationships" && svg) {
        s.relationships.forEach((x) => edge(x, ""));
        $("check-map-summary").textContent = Object.keys(pos).length + " tables, " + s.relationships.length + " relationships found from names.";
      } else if (s.step === "validate" && svg) {
        (s.orphans || []).forEach((x) => { const g = lines[key(x.source, x.target, x.source_cols)]; if (g) g.classList.add("m-bad"); });
      } else if (s.step === "suggest" && svg) {
        (s.suggested || []).forEach((x) => edge({ ...x, rule: "?" }, "m-sug"));
      }
    };
  }

  // n55: the map first. Under it one line with the state and the count, the most important finding, and every item
  // folded into "Show all N findings"; selecting a finding's title marks its relationship or table on the map.
  // where a finding is on the map, most precise first: its relationship, the amount's lines → header, its table
  function where(f) {
    const a = f.amount;
    return [f.link, a && { source: a.line, target: a.header, source_cols: a.line_columns }, a && { table: a.header }, f.table && { table: f.table }].filter(Boolean);
  }
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
      top ? el("p", { class: "check-top" }, el("span", { class: "muted" }, "Most important: "), findingButton(top, "check-finding-link")) : el("p", { class: "muted" }, r.verdict.headline.text));
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
      f.sql ? el("details", null, el("summary", null, "SQL to look for yourself"), el("pre", null, f.sql)) : null));
    $("check-findings").replaceChildren(...(r.findings.length ? list(r.findings) : [el("li", null, r.tables.length ? "Nothing the engine counts as wrong or unclear." : "Nothing could be read.")]));
    $("check-suggestions-h").hidden = !r.suggestions.length;
    $("check-suggestions").replaceChildren(...list(r.suggestions));
    $("check-tables").replaceChildren(...r.tables.map((t) => el("p", { class: "tiny" }, el("strong", null, t.name), " ",
      ...(t.key.length ? ["key ", code(t.key.join(" + ")), " (rule " + t.key_rule + ")"] : ["no key (rule K3)"]))));
    $("check-notes").replaceChildren(...((r.source && r.source.notes) || []).map((n) => el("li", null, n)));
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
      const decide = (yes) => { said.textContent = yes ? "Accepted on this page. In Claude, the review keeps your decision and its reason." : "Rejected on this page: the column stays unlinked."; };
      const yes = el("button", { type: "button", class: "btn secondary small" }, "Accept"), no = el("button", { type: "button", class: "btn ghost small" }, "Reject");
      yes.addEventListener("click", () => decide(true)); no.addEventListener("click", () => decide(false));
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

  // ------------------------------------------------------------------ n53: Ask Onto
  // Every answer is drawn from `r`, the result the worker returned; nothing here makes a request.
  function ask(r) {
    const box = $("check-ask"), listEl = $("check-ask-list"), answer = $("check-ask-answer");
    answer.hidden = true; answer.replaceChildren();
    if (map) map.highlight(null);
    if (!r.tables.length) { box.hidden = true; return; }
    const tags = (f) => el("p", { class: "tiny check-tags" }, code(f.check), ...f.rules.map((x) => code("rule " + x)));
    const amounts = r.findings.filter((f) => f.check === "amount_level" && f.amount);
    const doubled = amounts.find((f) => Number(f.amount.wrong) > Number(f.amount.right)) || amounts[0];
    const keyless = r.tables.find((t) => !t.key.length);
    const qs = [];
    if (doubled) qs.push({ id: "total", q: "Why does this total come out twice?", a: () => {
      const a = doubled.amount;
      const rel = { source: a.line, target: a.header, source_cols: a.line_columns };
      const shown = a.on_map && map && map.highlight(rel);
      return [el("p", null, el("strong", null, a.header + "." + a.column), " is an amount on ", code(a.header), ", and ", code(a.line),
          " has rows that point at each ", code(a.header), " row (", code(a.line + "." + a.line_columns.join(" + ")), " → ", code(a.header), "). Summed over the joined rows, each header amount is counted once per line."),
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
    qs.push({ id: "powerbi", q: "How do I get this into Power BI?", a: () => {
      setTimeout(() => openBuild("model"), 0);
      return [el("p", null, "Below the result: a simple report from your rows and the model as a Power BI project (.pbip) to download, made from the same plan in this browser. Creating the model in your own Fabric is a step in Claude (create_semantic_model).")];
    } });
    qs.push({ id: "own", q: "Can I ask my own questions?", a: () => [
      el("p", null, el("strong", null, "Yes, in Claude."), " Connect " + $("check-ask").dataset.product + " to Claude and ask about your own lakehouse; the answers come with the same rules and are checked against the rows. Here on /check nothing leaves the browser, so there is no question box."),
      el("p", { class: "ctas" }, el("a", { class: "btn primary small", href: "/start" }, "Connect to Claude"))] });
    listEl.replaceChildren(...qs.map((x) => {
      const b = el("button", { type: "button", class: "check-ask-q", "aria-expanded": "false", "aria-controls": "check-ask-answer", "data-ask": x.id }, x.q);
      b.addEventListener("click", () => {
        const open = b.getAttribute("aria-expanded") === "true";
        listEl.querySelectorAll("button").forEach((o) => o.setAttribute("aria-expanded", "false"));
        if (open) { answer.hidden = true; answer.replaceChildren(); if (map) map.highlight(null); return; }
        b.setAttribute("aria-expanded", "true");
        answer.replaceChildren(el("p", { class: "check-ask-said" }, x.q), ...x.a());
        answer.hidden = false;
      });
      return el("li", null, b);
    }));
    box.hidden = false;
  }

  // n55: /check?example=sample starts that example at once (the start page's "Try the guided demo", the industry
  // examples on /use-cases); &guide=1 adds Onto's four steps over the same run. /demo and /explore redirect here.
  const query = new URLSearchParams(location.search);
  if (["sample", "sap", "crm"].includes(query.get("example"))) {
    guided = query.get("guide") === "1";
    if (guided) $("check-guide").hidden = false;
    start(query.get("example"));
  }
})();
