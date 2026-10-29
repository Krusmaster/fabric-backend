// /check: hand files to the engine in a Web Worker (check-worker.js) and draw what it reports, step by step: the
// left column lists each engine step as it finishes (its rules and its time), the right column builds the map from the
// same events. Files are read with the File API into memory and posted to the worker; the page itself makes no request
// with them (its CSP: connect-src 'none'). With prefers-reduced-motion the steps and the map appear at once, when done.
// n49: while the engine loads or runs, Onto hops beside the step under way (still, with reduced motion; hidden with the
// mascots switched off); under the result, a Power BI model and an app from the same input, previewed on the rows and
// downloaded as zips made in the worker and saved from a Blob: no request carries them either.
// n51: the two choices sit in the map column, under the legend, once the run is done (the empty space beside the long
// steps column); the preview they open stays full width under the result, and the click scrolls to its heading.
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

  let booted = false, last = null, built = null;
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
    const map = new MapView($("check-map"));
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
  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => start(b.dataset.example)));
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
    let svg = null, edges = null, nodes = null, pos = {}, W = 760, H = 460;
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

  function draw(r) {
    result.hidden = false;
    $("check-verdict").replaceChildren(
      el("p", { class: "check-state check-" + r.verdict.headline.state }, el("strong", null, r.verdict.headline.title), " ", r.verdict.headline.text),
      ...(r.verdict.items.length ? [el("ul", null, ...r.verdict.items.map((i) => el("li", null, el("strong", null, i.title), " ", i.text)))] : []));
    if (r.tables.length) $("check-map-summary").textContent = r.tables.length + " tables, " + r.relationships.length + " relationships. " + r.health;
    const list = (items) => items.map((f) => el("li", { class: "check-finding sev-" + f.severity },
      el("p", { class: "check-finding-title" }, el("strong", null, f.title)),
      el("p", { class: "tiny check-tags" }, code(f.check), ...f.rules.map((x) => code("rule " + x)), " ", f.severity),
      el("p", null, f.saw), el("p", { class: "muted" }, f.means), f.next ? el("p", null, el("strong", null, "Next: "), f.next) : null,
      f.sql ? el("details", null, el("summary", null, "SQL to look for yourself"), el("pre", null, f.sql)) : null));
    $("check-findings").replaceChildren(...(r.findings.length ? list(r.findings) : [el("li", null, r.tables.length ? "Nothing the engine counts as wrong or unclear." : "Nothing could be read.")]));
    $("check-suggestions-box").hidden = !r.suggestions.length;
    $("check-suggestions").replaceChildren(...list(r.suggestions));
    $("check-tables").replaceChildren(...r.tables.map((t) => el("p", { class: "tiny" }, el("strong", null, t.name), " ",
      ...(t.key.length ? ["key ", code(t.key.join(" + ")), " (rule " + t.key_rule + ")"] : ["no key (rule K3)"]))));
    $("check-notes").replaceChildren(...((r.source && r.source.notes) || []).map((n) => el("li", null, n)));
  }
})();
