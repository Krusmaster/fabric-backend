// /check: hand files to the engine in a Web Worker (check-worker.js) and draw what it reports, step by step: the
// left column lists each engine step as it finishes (its rules and its time), the right column builds the map from the
// same events. Files are read with the File API into memory and posted to the worker; the page itself makes no request
// with them (its CSP: connect-src 'none'). With prefers-reduced-motion the steps and the map appear at once, when done.
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

  worker.onmessage = (e) => {
    const d = e.data;
    if (d.step) { if (onStep) onStep(d.step); else bootSteps.push(d.step); return; }
    const p = pending.get(d.id); if (p) { pending.delete(d.id); p(d); }
  };
  worker.onerror = () => say("The engine could not start in this browser. It needs WebAssembly and module workers (a current Chrome, Edge, Firefox or Safari).");
  const call = (msg) => new Promise((resolve) => { const id = ++seq; pending.set(id, resolve); worker.postMessage({ id, ...msg }); });
  function say(text) { status.textContent = text; }
  const seconds = (ms) => (ms / 1000).toFixed(1) + " s";

  let booted = false;
  say("Loading the engine in this browser…");
  const boot = call({ kind: "boot" }).then((r) => {
    booted = r.ok;
    if (!busy) say(r.ok ? "The engine is ready. Nothing has been read yet." : "The engine could not start: " + r.error);
    return r;
  });

  const LABELS = { sample: "the example “A total that doubles”", sap: "the example “SAP sales tables”", crm: "the example “Salesforce + ERP”", columns: "the list of columns" };

  async function start(kind, files, text) {
    if (busy) return;
    busy = true;
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
      if (!r.ok) { say("The engine stopped: " + r.error); return; }
      if (still) { run.hidden = false; events.forEach(show); }
      draw(r.result);
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
