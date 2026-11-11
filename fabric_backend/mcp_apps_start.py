"""MCP Apps, the Start Krusgraph card (round n219): the `start` tool's answer as a stepper.

Behind the n119 flag (KRUSGRAPH_MCP_APPS, off unless "1"): with the flag off nothing here reaches the server, and
`start` answers text only, as every client gets it.

What the card draws, all from the answer (start_flow.guide), never invented by the card:
- the path, nine steps, each marked done, now or later and "reads" or "writes";
- what was chosen so far, the step's sentence, and for the synthetic shop what the tool found there;
- the step's buttons. Each runs its tool through the host with n218's runner (mcp_apps_next NEXT_JS: `tools/call` when
  the host has serverTools, otherwise the button's `say` goes to the chat with `ui/message`), and the tool's answer is
  drawn under the button with n218's answerView (check rows, next steps). Only the tools in ALLOWED can be called;
  a creating tool only as a dry run (no dry_run argument: the tool's default is true), except on step 9 after the
  user's confirmation of exactly that name (the answer's confirmed_by_user), and even then it is armed by a first
  click and runs on the second, as n218's Create does;
- "Next": the `start` call in `after`. Its answer replaces the card's content, so the card walks the path in place.

The card shares the build card's look and host handling (mcp_apps_build: same tokens, same mascots, same
`ui/initialize`), and declares no domain: nothing is loaded.
"""
from __future__ import annotations

import json

from . import mcp_apps
from . import mcp_apps_mascots as mascots
from . import start_flow

CARD_URI = "ui://krusgraph/start-card.html"
READS = ("list_workspaces", "list_sources", "plan_backend", "validate_plan", "review_plan")
ALLOWED = {start_flow.TOOL: "call", **{t: "call" for t in READS}, **{t: "build" for t, _, _ in start_flow.BUILDS}}


def tool_meta(on: bool | None = None) -> dict | None:
    """`start`'s `_meta` when the flag is on, else None (no `_meta` at all)."""
    if not (mcp_apps.enabled() if on is None else on):
        return None
    return {"ui": {"resourceUri": CARD_URI}, "ui/resourceUri": CARD_URI}


def registration(on: bool | None = None) -> dict:
    """The tool decorator's extra arguments for `start`: its card when the flag is on, else none."""
    meta = tool_meta(on)
    return {"meta": meta} if meta else {}


def answer(text: str, on: bool | None = None):
    """With the flag on, the text answer plus the same answer as structuredContent (mcp_apps.call_result); else text."""
    if not (mcp_apps.enabled() if on is None else on):
        return text
    return mcp_apps.call_result(text)


def add_to(apps) -> None:
    apps.add_html_resource(CARD_URI, card_html(), name="start_card", title="Start Krusgraph",
                           description="The guided path as a stepper: where you are, what was chosen, and the next "
                                       "step as a button that asks the host to run an existing tool.",
                           prefers_border=True)


def card_html() -> str:
    from . import mcp_apps_next as nxt
    return (_HTML.replace("__PROTOCOL__", mcp_apps.PROTOCOL_VERSION)
            .replace("__ALLOWED__", json.dumps(ALLOWED, separators=(",", ":")))
            .replace("__READ_JS__", mcp_apps.READ_JS + mcp_apps.CALL_JS + mcp_apps.RESULT_JS + nxt.js())
            .replace("__MASCOT_CSS__", mascots.CSS).replace("__RESULT_CSS__", mcp_apps.RESULT_CSS + nxt.NEXT_CSS + START_CSS)
            .replace("__MASCOT_TOGGLE__", mascots.TOGGLE).replace("__MASCOTS__", mascots.section())
            .replace("__MASCOT_JS__", mascots.JS))


START_CSS = """
.st-path { list-style: none; padding: 0; margin: 0; display: grid; gap: 3px }
.st-path li { display: flex; gap: 8px; align-items: baseline; font-size: 14px; color: var(--kg-muted) }
.st-path li[data-state="now"] { color: var(--kg-ink); font-weight: 650 }
.st-path li[data-state="done"]::before { content: "\\2713"; color: var(--kg-ok) }
.st-path li[data-state="now"]::before { content: "\\25B6" }
.st-path li[data-state="later"]::before { content: "\\00B7" }
.st-does { font-size: 12px; border: 1px solid var(--kg-line); border-radius: 999px; padding: 0 7px }
.st-does[data-does="writes"] { color: var(--kg-warn); border-color: currentColor }
.st-acts { display: grid; gap: 8px; border-top: 1px solid var(--kg-line); padding-top: 8px }
.st-act { display: grid; gap: 4px }
.st-act .out { border-left: 3px solid var(--kg-line); padding-left: 8px; display: grid; gap: 6px }
button.st-create { background: var(--kg-ink); color: var(--kg-bg) }
"""

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Start Krusgraph</title>
<style>
:root {
  color-scheme: light dark;
  --kg-bg: var(--color-background-primary, light-dark(#ffffff, #1b1b1f));
  --kg-card: var(--color-background-secondary, light-dark(#f6f5fb, #26252c));
  --kg-ink: var(--color-text-primary, light-dark(#1b1b1f, #f3f2f7));
  --kg-muted: var(--color-text-secondary, light-dark(#55535e, #b9b6c4));
  --kg-line: var(--color-border-primary, light-dark(#d9d6e3, #3c3a44));
  --kg-ok: var(--color-text-success, light-dark(#1d6b3a, #8fd6a6));
  --kg-warn: var(--color-text-warning, light-dark(#8a4b00, #f2c27a));
  --kg-radius: var(--border-radius-lg, 14px);
  --kg-font: var(--font-sans, system-ui, -apple-system, "Segoe UI", sans-serif);
}
* { box-sizing: border-box }
[hidden] { display: none !important }
html, body { margin: 0; background: var(--kg-bg); color: var(--kg-ink); font: 15px/1.45 var(--kg-font) }
main { padding: 14px 16px; display: grid; gap: 12px }
h1 { margin: 0; font-size: 17px; font-weight: 650 }
p { margin: 0 }
.muted { color: var(--kg-muted); font-size: 13.5px }
ul { margin: 0; padding-left: 18px }
button { font: inherit; font-weight: 650; justify-self: start; color: var(--kg-ink); background: var(--kg-card);
  border: 1px solid var(--kg-line); border-radius: 999px; padding: 4px 14px; cursor: pointer; min-height: 32px }
button:disabled { cursor: default; opacity: .6 }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important } }
__MASCOT_CSS__
__RESULT_CSS__
</style>
</head>
<body>
<main>
  <div class="kg-head"><h1 id="title">Start Krusgraph</h1>__MASCOT_TOGGLE__</div>
  <p class="muted" role="status" id="verdict">Waiting for the tool's answer.</p>
  __MASCOTS__
  <ol class="st-path" id="path" aria-label="The steps"></ol>
  <div id="answer"></div>
  <div id="next"></div>
  <p class="muted" id="honest"></p>
</main>
<script>
(function () {
  "use strict";
  var ALLOWED = __ALLOWED__;
  var input = {}, tool = "";
  var nextId = 1, pending = {};
  function send(msg) { window.parent.postMessage(msg, "*"); }
  function request(method, params) {
    var id = nextId++;
    send({ jsonrpc: "2.0", id: id, method: method, params: params });
    return new Promise(function (resolve, reject) { pending[id] = { resolve: resolve, reject: reject }; });
  }
  function notify(method, params) { send({ jsonrpc: "2.0", method: method, params: params || {} }); }
__MASCOT_JS__
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = String(text); if (cls) e.className = cls; return e; }

__READ_JS__
  // A button the card may draw: a tool in ALLOWED; a creating tool as a dry run (no dry_run=false), or as Create only
  // for a name the user confirmed after the dry run (the answer's confirmed_by_user).
  function okButton(a, d) {
    if (!isObj(a) || typeof a.label !== "string" || typeof a.say !== "string" || !isObj(a.arguments)) return false;
    var kind = ALLOWED[a.tool];
    if (!kind) return false;
    if (a.arguments.dry_run === false) {
      return kind === "build" && a.kind === "create" && Array.isArray(d.confirmed_by_user) &&
             d.confirmed_by_user.indexOf(a.arguments.name) >= 0;
    }
    return a.kind !== "create";
  }
  function button(a, d, box) {
    var row = el("div", null, "st-act"), create = a.kind === "create";
    var b = el("button", a.label, create ? "st-create" : "nx-b"); b.type = "button"; b.setAttribute("data-tool", a.tool);
    var out = el("div", null, "out"); out.hidden = true;
    if (a.kind === "dry_run") row.appendChild(el("span", "Dry run: nothing is created.", "muted"));
    if (create) row.appendChild(el("span", "Creates " + a.arguments.name + " in Fabric. You confirmed this name after the dry run.", "muted"));
    var armed = false;
    b.addEventListener("click", function () {
      if (create && !armed) {                                 // never writes on the first click
        armed = true; b.textContent = "Yes, create " + a.arguments.name + " in Fabric"; b.setAttribute("data-armed", "true");
        out.hidden = false; out.textContent = "Press again to create " + a.arguments.name + ". Nothing has been created yet.";
        return;
      }
      var args = JSON.parse(JSON.stringify(a.arguments));
      if (a.tool === "start") runOrSay("start", args, a.say, out, b, function (r) { render(r); });
      else runOrSay(a.tool, args, a.say, out, b);
    });
    row.insertBefore(b, row.firstChild); row.appendChild(out); box.appendChild(row);
  }
  function listOf(items) { var ul = el("ul"); items.forEach(function (x) { if (readable(x)) ul.appendChild(el("li", x)); }); return ul; }
  function render(result) {
    var d = answerOf(result), verdict = document.getElementById("verdict"), path = document.getElementById("path");
    var answer = document.getElementById("answer"), next = document.getElementById("next");
    answer.textContent = ""; next.textContent = ""; path.textContent = ""; mascotsQuiet();
    if (!d) { verdict.textContent = "The card could not read the answer; it is in the text of the tool result."; return; }
    if (readable(d.error)) { verdict.textContent = d.error + (readable(d.hint) ? " " + d.hint : ""); return; }
    var st = isObj(d.step) ? d.step : {};
    document.getElementById("title").textContent = "Start Krusgraph" + (st.n ? ": step " + st.n + " of " + st.of : "") + (d.sample ? " (synthetic shop)" : "");
    (Array.isArray(d.path) ? d.path : []).filter(isObj).forEach(function (p) {
      var li = el("li"); li.setAttribute("data-state", p.state); li.setAttribute("data-key", p.key);
      li.appendChild(el("span", p.n + ". " + p.title));
      var does = el("span", p.does, "st-does"); does.setAttribute("data-does", p.does); li.appendChild(does);
      path.appendChild(li);
    });
    verdict.textContent = readable(d.say) || readable(d.summary) || "";
    if (isObj(d.chosen)) {
      var shown = ["workspace", "source", "schema"].filter(function (k) { return readable(d.chosen[k]); })
        .map(function (k) { return k + ": " + d.chosen[k]; });
      if (shown.length) answer.appendChild(el("p", "Chosen: " + shown.join(", "), "muted"));
    }
    if (isObj(d.found)) {
      var f = d.found, box = el("div", null, "res-box");
      if (readable(f.tool)) box.appendChild(el("p", f.tool, "muted"));
      ["summary", "question", "note"].forEach(function (k) { if (readable(f[k])) box.appendChild(el("p", f[k])); });
      if (Array.isArray(f.links)) box.appendChild(listOf(f.links));
      if (Array.isArray(f.doubled)) box.appendChild(listOf(f.doubled));
      if (Array.isArray(f.would_build)) box.appendChild(listOf(f.would_build.filter(isObj).map(function (w) { return w.name + ": " + w.what; })));
      answer.appendChild(box);
    }
    if (Array.isArray(d.would_build)) answer.appendChild(listOf(d.would_build.filter(isObj).map(function (w) { return w.name + ": " + w.what; })));
    var flow = Array.isArray(d.data_flow) ? d.data_flow : (isObj(d.found) && Array.isArray(d.found.data_flow) ? d.found.data_flow : null);
    if (flow) { answer.appendChild(el("p", "The data flow", "muted")); answer.appendChild(listOf(flow)); }
    var acts = el("section", null, "st-acts"); acts.setAttribute("aria-label", "This step");
    (Array.isArray(d.actions) ? d.actions : []).forEach(function (a) { if (okButton(a, d)) button(a, d, acts); });
    if (isObj(d.after) && !d.sample && okButton({ kind: "call", label: d.after.label, say: d.after.say, tool: d.after.tool, arguments: d.after.arguments }, d))
      button({ kind: "call", label: d.after.label, say: d.after.say, tool: "start", arguments: d.after.arguments }, d, acts);
    if (acts.childNodes.length) next.appendChild(acts);
    document.getElementById("honest").textContent = readable(d.honest) || "";
    mascots({ onto: [verdict.textContent, "point"] }, false);
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var m = event.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id != null && !m.method && pending[m.id]) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) p.reject(m.error); else p.resolve(m.result);
      return;
    }
    if (m.method === "ui/notifications/tool-input") input = (m.params && m.params.arguments) || {};
    else if (m.method === "ui/notifications/tool-result") render(m.params);
    else if (m.method === "ui/notifications/tool-cancelled") { document.getElementById("verdict").textContent = "The call was cancelled."; mascotsQuiet(); }
    else if (m.method === "ui/resource-teardown" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
    else if (m.method === "ping" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
  });

  var last = 0;
  function reportSize() {
    var h = Math.ceil(document.documentElement.scrollHeight), w = Math.ceil(document.documentElement.scrollWidth);
    if (h !== last) { last = h; notify("ui/notifications/size-changed", { width: w, height: h }); }
  }
  request("ui/initialize", {
    appInfo: { name: "Krusgraph start", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function (r) {
    hostStarted(r);
    if (isObj(r) && isObj(r.hostContext) && isObj(r.hostContext.toolInfo) && isObj(r.hostContext.toolInfo.tool)) tool = r.hostContext.toolInfo.tool.name || "";
    notify("ui/notifications/initialized");
    reportSize();
    if (window.ResizeObserver) new ResizeObserver(reportSize).observe(document.body);
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
