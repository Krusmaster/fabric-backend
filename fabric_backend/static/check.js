// /check: hand files to the engine in a Web Worker (check-worker.js) and draw what it answers. Files are read with the
// File API into memory and posted to the worker; the page itself makes no request with them (its CSP: connect-src 'none').
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const script = document.currentScript || document.querySelector("script[data-worker]");
  const status = $("check-status"), result = $("check-result");
  const worker = new Worker(script.dataset.worker, { type: "module" });
  const pending = new Map();
  let seq = 0, busy = false;

  worker.onmessage = (e) => { const p = pending.get(e.data.id); if (p) { pending.delete(e.data.id); p(e.data); } };
  worker.onerror = () => say("The engine could not start in this browser. It needs WebAssembly and module workers (a current Chrome, Edge, Firefox or Safari).");
  const call = (msg) => new Promise((resolve) => { const id = ++seq; pending.set(id, resolve); worker.postMessage({ id, ...msg }); });

  function say(text) { status.textContent = text; }
  const seconds = (ms) => (ms / 1000).toFixed(1).replace(/\.0$/, "") + " s";

  let booted = false;
  say("Loading the engine in this browser…");
  const boot = call({ kind: "boot" }).then((r) => {
    booted = r.ok;
    if (!busy) say(r.ok ? "The engine is ready. Nothing has been read yet." : "The engine could not start: " + r.error);
    return r;
  });

  async function run(kind, files, text) {
    if (busy) return;
    busy = true;
    document.documentElement.dataset.check = "running";
    const what = kind === "sample" ? "the shop example" : kind === "columns" ? "the list of columns" : files.length + (files.length === 1 ? " file" : " files");
    say((booted ? "Reading " : "Loading the engine, then reading ") + what + " in this browser…");
    try {
      await boot;
      const r = await call({ kind, files, text });
      if (!r.ok) { say("The engine stopped: " + r.error); return; }
      draw(r.result);
      const ms = Math.round(performance.now());
      document.documentElement.dataset.checkMs = String(ms);
      say("Done: " + what + ", read in this browser. The result showed " + seconds(ms) + " after the page opened; nothing was uploaded.");
      result.focus({ preventScroll: true });
      result.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    } finally {
      busy = false;
      document.documentElement.dataset.check = "done";
    }
  }

  async function readFiles(list) {
    const files = [];
    for (const f of list) files.push({ name: f.name, bytes: await f.arrayBuffer() });
    return files;
  }

  $("check-files").addEventListener("change", async (e) => { if (e.target.files.length) run("files", await readFiles(e.target.files)); });
  $("check-sample").addEventListener("click", () => run("sample"));
  $("check-columns-run").addEventListener("click", () => {
    const text = $("check-columns").value.trim();
    if (!text) { say("Paste a list of columns first: one table.column per line."); $("check-columns").focus(); return; }
    run("columns", [], text);
  });
  const drop = $("check-drop");
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
  drop.addEventListener("drop", async (e) => { e.preventDefault(); if (e.dataTransfer.files.length) run("files", await readFiles(e.dataTransfer.files)); });
  // a file dropped next to the box would make the browser open it; keep it on the page
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => e.preventDefault());

  // ------------------------------------------------------------------ drawing (textContent only: names come from files)
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) n.setAttribute(k, v);
    for (const k of kids) if (k != null) n.append(k);
    return n;
  }
  const code = (t) => el("code", null, t);

  function draw(r) {
    result.hidden = false;
    const v = $("check-verdict");
    v.replaceChildren(
      el("p", { class: "check-state check-" + r.verdict.headline.state }, el("strong", null, r.verdict.headline.title), " ", r.verdict.headline.text),
      ...(r.verdict.items.length ? [el("ul", null, ...r.verdict.items.map((i) => el("li", null, el("strong", null, i.title), " ", i.text)))] : []));
    $("check-map-summary").textContent = r.tables.length
      ? r.tables.length + " tables, " + r.relationships.length + " relationships. " + (r.source && r.source.has_data ? r.health : "From names only: a list of columns has no rows to check.")
      : "";
    drawMap(r);
    $("check-tables").replaceChildren(...r.tables.map((t) => table(t, r)));
    const list = (items) => items.map((f) => el("li", { class: "check-finding sev-" + f.severity },
      el("p", { class: "check-finding-title" }, el("strong", null, f.title)),
      el("p", { class: "tiny check-tags" }, code(f.check), ...f.rules.map((x) => code("rule " + x)), " ", f.severity),
      el("p", null, f.saw), el("p", { class: "muted" }, f.means), f.next ? el("p", null, el("strong", null, "Next: "), f.next) : null,
      f.sql ? el("details", null, el("summary", null, "SQL to look for yourself"), el("pre", null, f.sql)) : null));
    $("check-findings").replaceChildren(...(r.findings.length ? list(r.findings) : [el("li", null, r.tables.length ? "Nothing the engine counts as wrong or unclear." : "Nothing could be read.")]));
    $("check-suggestions-box").hidden = !r.suggestions.length;
    $("check-suggestions").replaceChildren(...list(r.suggestions));
    $("check-notes").replaceChildren(...((r.source && r.source.notes) || []).map((n) => el("li", null, n)));
  }

  function table(t, r) {
    const out = r.relationships.filter((x) => x.source === t.name), inn = r.relationships.filter((x) => x.target === t.name);
    return el("article", { class: "card soft check-table" },
      el("h4", null, t.name),
      el("p", { class: "tiny" }, ...(t.key.length ? [el("strong", null, "Key: "), code(t.key.join(" + ")), " rule " + t.key_rule] : [el("strong", null, "No key"), " (rule K3)"])),
      ...out.map((x) => el("p", { class: "tiny" }, "→ ", code(x.source_cols.join("+")), " points at ", el("strong", null, x.target), " (rule " + x.rule + ")")),
      ...inn.map((x) => el("p", { class: "tiny muted" }, "← ", el("strong", null, x.source), " via ", code(x.source_cols.join("+")), " (rule " + x.rule + ")")));
  }

  function drawMap(r) {
    const box = $("check-map"), n = r.tables.length, NS = "http://www.w3.org/2000/svg";
    box.replaceChildren();
    if (!n) return;
    const W = 720, H = n > 8 ? 520 : 400, R = Math.min(W, H) / 2 - 60, pos = {};
    r.tables.forEach((t, i) => {
      const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
      pos[t.name] = n === 1 ? [W / 2, H / 2] : [W / 2 + R * 1.45 * Math.cos(a), H / 2 + R * Math.sin(a)];
    });
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("aria-hidden", "true");
    const add = (parent, tag, attrs, text) => { const x = document.createElementNS(NS, tag); for (const k in attrs) x.setAttribute(k, attrs[k]); if (text != null) x.textContent = text; parent.append(x); return x; };
    for (const x of r.relationships) {
      const [a, b] = [pos[x.source], pos[x.target]];
      if (!a || !b) continue;
      add(svg, "line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: "m-edge" });
      add(svg, "text", { x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2 - 4, class: "m-rule", "text-anchor": "middle" }, x.rule);
    }
    for (const t of r.tables) {
      const [x, y] = pos[t.name], w = Math.max(90, Math.min(200, 9 * t.name.length + 24));
      const g = add(svg, "g", { class: t.key.length ? "m-node" : "m-node m-nokey" });
      add(g, "rect", { x: x - w / 2, y: y - 22, width: w, height: 44, rx: 12 });
      add(g, "text", { x, y: y - 3, "text-anchor": "middle", class: "m-name" }, t.name.length > 22 ? t.name.slice(0, 21) + "…" : t.name);
      add(g, "text", { x, y: y + 14, "text-anchor": "middle", class: "m-key" }, t.key.length ? "key " + t.key_rule : "no key");
    }
    box.append(svg);
  }
})();
