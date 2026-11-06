"""MCP Apps prototype (round n119): validate_plan's summary as a card in hosts that render MCP Apps.

Off by default. The hosted server turns it on only when the environment variable KRUSGRAPH_MCP_APPS is "1"; with the
flag off nothing here reaches the server: no extension, no resource, no `_meta` on any tool, and the tool listing is
byte for byte what it was.

What the specification asks for, and where it is done here. Source: modelcontextprotocol/ext-apps,
specification/2026-01-26/apps.mdx ("SEP-1865: MCP Apps", Status: Stable (2026-01-26)), read on 6 November 2026 at
commit 19256f52cad5517ba8272581ed2e11d6a81273d5. Only the specification was read to learn the protocol; no code from
that repository is copied.

- Extension identifier `io.modelcontextprotocol/ui`: the server advertises it through the Python SDK's own `Apps`
  extension (mcp 2.3.0, `mcp.server.apps`), which puts it under the server's capabilities.extensions.
- A UI resource uses the `ui://` scheme and the MIME type `text/html;profile=mcp-app`, its content a valid HTML5
  document as `text`: `CARD_URI` and `APP_MIME_TYPE`, served by `Apps.add_html_resource`.
- A tool points at it with `_meta.ui.resourceUri`; the flat `_meta["ui/resourceUri"]` is the deprecated form, which the
  ext-apps SDK's registerAppTool still writes for older hosts, so `tool_meta()` writes both.
- Without `_meta.ui.csp` the host applies its restrictive default (default-src 'none'; scripts and styles inline only;
  connect-src 'none'). The card declares no domain at all: everything it needs is inline.
- The view talks to the host with JSON-RPC 2.0 over postMessage: `ui/initialize` (appInfo, appCapabilities,
  protocolVersion "2026-01-26"), then the notification `ui/notifications/initialized`. The host then sends
  `ui/notifications/tool-input` (the call's arguments) and `ui/notifications/tool-result` (a CallToolResult). The card
  reads the summary JSON from the result's text content, the same text every other client gets, and reports its height
  with `ui/notifications/size-changed`.
- A button sends `tools/call` to the host, which the host may forward to this server or put to the user first. Only the
  tools in evidence.NEXT_STEP_TOOLS (n103: they read or draft, none creates) can be called, and only with the arguments
  the step names plus workspace, source, schema and, where the tool takes them, keys and confirmed from this call.
- Graceful degradation: the tool's text answer is not changed, so a client without MCP Apps sees what it saw before.
  The SDK's `client_supports_apps` is not used to vary the listing: the hosted server is stateless, and a host that
  does not render MCP Apps ignores `_meta.ui` (the specification's "tool behaves as standard tool").
"""
from __future__ import annotations

import json
import os

from .evidence import NEXT_STEP_TOOLS

FLAG = "KRUSGRAPH_MCP_APPS"
CARD_URI = "ui://krusgraph/validate-plan-card.html"
APP_MIME_TYPE = "text/html;profile=mcp-app"           # the specification's MIME type; mcp.server.apps.APP_MIME_TYPE
PROTOCOL_VERSION = "2026-01-26"
TOOL = "validate_plan"

# The arguments a next step carries over from the validate_plan call, per tool: workspace, source and schema always;
# keys and confirmed only where the tool takes them. tests/test_n119_mcp_apps.py checks each against the tool's
# inputSchema in the hosted listing.
SHARED = ("workspace", "source", "schema")
WITH_PLAN = ("keys", "confirmed")
CARRIED = {t: SHARED + (() if t in ("sample_rows", "list_tables") else WITH_PLAN) for t in NEXT_STEP_TOOLS}


def enabled(environ=None) -> bool:
    """True only when KRUSGRAPH_MCP_APPS is "1" (the hosted server reads it once, at start)."""
    return (os.environ if environ is None else environ).get(FLAG, "").strip() == "1"


def tool_meta(on: bool | None = None) -> dict | None:
    """validate_plan's `_meta` when the flag is on, else None (the decorator's default: no `_meta` at all)."""
    if not (enabled() if on is None else on):
        return None
    return {"ui": {"resourceUri": CARD_URI}, "ui/resourceUri": CARD_URI}


def extensions(on: bool | None = None) -> list:
    """The MCPServer extensions: the SDK's Apps extension with the card when the flag is on, else none."""
    if not (enabled() if on is None else on):
        return []
    from mcp.server.apps import Apps
    apps = Apps()
    apps.add_html_resource(CARD_URI, card_html(), name="validate_plan_card", title="Plan check",
                           description="validate_plan's summary as a card: counts, what needs attention and the next "
                                       "steps as buttons that ask the host to run a read or draft tool.",
                           prefers_border=True)
    from . import mcp_apps_review                            # n124: review_plan's card, same flag
    mcp_apps_review.add_to(apps)
    return [apps]


def card_html() -> str:
    """The card: one self-contained HTML5 document. No src, href, url(), @import, fetch or other load; every word on
    it is text (no pictures, no mascots); the data arrives only from the host."""
    allowed = json.dumps({t: list(CARRIED[t]) for t in NEXT_STEP_TOOLS}, separators=(",", ":"))
    return _HTML.replace("__ALLOWED__", allowed).replace("__PROTOCOL__", PROTOCOL_VERSION)


_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plan check</title>
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
html, body { margin: 0; background: var(--kg-bg); color: var(--kg-ink); font: 15px/1.45 var(--kg-font) }
main { padding: 14px 16px; display: grid; gap: 12px }
h1 { margin: 0; font-size: 17px; font-weight: 650 }
p { margin: 0 }
.muted { color: var(--kg-muted); font-size: 13.5px }
.counts { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin: 0 }
.counts div { background: var(--kg-card); border: 1px solid var(--kg-line); border-radius: var(--kg-radius); padding: 8px 10px }
.counts dt { font-size: 13px; color: var(--kg-muted) }
.counts dd { margin: 2px 0 0; font-size: 18px; font-weight: 650 }
.ok { color: var(--kg-ok) }
.warn { color: var(--kg-warn) }
ul { margin: 0; padding-left: 18px }
li { margin: 2px 0 }
.steps { display: grid; gap: 8px }
.step { display: grid; gap: 4px; border: 1px solid var(--kg-line); border-radius: var(--kg-radius); padding: 8px 10px }
button { font: inherit; font-weight: 650; justify-self: start; color: var(--kg-ink); background: var(--kg-card);
  border: 1px solid var(--kg-line); border-radius: 999px; padding: 4px 14px; cursor: pointer }
button:disabled { cursor: default; opacity: .6 }
pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12.5px; max-height: 260px; overflow: auto;
  background: var(--kg-card); border-radius: 8px; padding: 6px 8px }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important } }
</style>
</head>
<body>
<main>
  <h1>Plan check</h1>
  <p id="verdict" class="muted" role="status">Waiting for validate_plan's answer.</p>
  <dl id="counts" class="counts" hidden></dl>
  <section id="attention" hidden><h2 class="muted">Needs attention</h2><ul id="attention-list"></ul></section>
  <section id="next" hidden><h2 class="muted">Next steps (each reads or drafts; nothing is created)</h2><div id="steps" class="steps"></div></section>
  <p class="muted">The same answer is in the text of the tool result. A button asks the host to run that tool; the host may ask you first.</p>
</main>
<script>
(function () {
  "use strict";
  var ALLOWED = __ALLOWED__;            // next-step tool -> the arguments carried over from this call
  var input = {};                       // validate_plan's arguments, from ui/notifications/tool-input
  var nextId = 1, pending = {};
  function send(msg) { window.parent.postMessage(msg, "*"); }
  function request(method, params) {
    var id = nextId++;
    send({ jsonrpc: "2.0", id: id, method: method, params: params });
    return new Promise(function (resolve, reject) { pending[id] = { resolve: resolve, reject: reject }; });
  }
  function notify(method, params) { send({ jsonrpc: "2.0", method: method, params: params || {} }); }
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = String(text); if (cls) e.className = cls; return e; }

  function textOf(result) {
    var parts = (result && result.content) || [];
    for (var i = 0; i < parts.length; i++) if (parts[i] && parts[i].type === "text") return parts[i].text;
    return "";
  }

  function render(result) {
    var data;
    try { data = JSON.parse(textOf(result)); } catch (e) { data = null; }
    var verdict = document.getElementById("verdict");
    if (!data || typeof data !== "object") { verdict.textContent = "The answer is not a validate_plan summary; it is in the text of the tool result."; return; }
    if (data.error) { verdict.textContent = data.error + (data.hint ? " " + data.hint : ""); return; }
    verdict.textContent = data.summary || "";
    var counts = document.getElementById("counts"); counts.textContent = "";
    var totals = data.totals || {};
    [["keys", "Keys"], ["relationships", "Relationships"], ["amount_levels", "Header amounts"]].forEach(function (k) {
      var t = totals[k[0]]; if (!t || !t.checked) return;
      var box = el("div"); box.appendChild(el("dt", k[1]));
      box.appendChild(el("dd", t.passed + " of " + t.checked + " passed", t.failed ? "warn" : "ok"));
      counts.appendChild(box);
    });
    var box = el("div"); box.appendChild(el("dt", "Needs attention"));
    box.appendChild(el("dd", String(data.needs_attention || 0), data.needs_attention ? "warn" : "ok"));
    counts.appendChild(box);
    counts.hidden = false;

    var list = document.getElementById("attention-list"); list.textContent = "";
    var att = data.attention || {};
    Object.keys(att).forEach(function (kind) {
      (att[kind] || []).forEach(function (x) {
        var what = x.verdict || x.do_instead || x.explanation ||
          [x.table || x.source || x.header, x.target || x.line].filter(Boolean).join(" \\u2192 ");
        var who = x.table || (x.source ? x.source + " \\u2192 " + x.target : (x.header ? x.header + " / " + x.line : kind));
        list.appendChild(el("li", who + ": " + what));
      });
    });
    document.getElementById("attention").hidden = !list.children.length;
    if (!list.children.length && data.result) { list.appendChild(el("li", data.result)); document.getElementById("attention").hidden = false; }

    var steps = document.getElementById("steps"); steps.textContent = "";
    (data.next_steps || []).forEach(function (s) {
      if (!s || !Object.prototype.hasOwnProperty.call(ALLOWED, s.tool)) return;   // only read and draft tools
      var row = el("div", null, "step");
      row.appendChild(el("p", s.why || s.text || ""));
      var b = el("button", "Run " + s.tool); b.type = "button";
      var out = el("pre"); out.hidden = true;
      b.addEventListener("click", function () { run(s, b, out); });
      row.appendChild(b); row.appendChild(out); steps.appendChild(row);
    });
    document.getElementById("next").hidden = !steps.children.length;
  }

  function run(step, button, out) {
    var args = {};
    (ALLOWED[step.tool] || []).forEach(function (k) { if (input[k] != null) args[k] = input[k]; });
    var own = step.arguments || {};
    Object.keys(own).forEach(function (k) { args[k] = own[k]; });
    button.disabled = true; out.hidden = false; out.textContent = "Asked the host to run " + step.tool + ".";
    request("tools/call", { name: step.tool, arguments: args }).then(function (r) {
      var t = textOf(r); out.textContent = t.length > 4000 ? t.slice(0, 4000) + "\\n\\u2026 (the rest is in the tool's own answer)" : t;
    }, function (e) {
      out.textContent = "The host did not run " + step.tool + ": " + (e && e.message ? e.message : "no reason given") + ".";
    }).then(function () { button.disabled = false; });
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var m = event.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id != null && !m.method && pending[m.id]) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) p.reject(new Error(m.error.message || "error")); else p.resolve(m.result);
      return;
    }
    if (m.method === "ui/notifications/tool-input") input = (m.params && m.params.arguments) || {};
    else if (m.method === "ui/notifications/tool-result") render(m.params);
    else if (m.method === "ui/notifications/tool-cancelled") document.getElementById("verdict").textContent = "The check was cancelled.";
    else if (m.method === "ui/resource-teardown" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
    else if (m.method === "ping" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
  });

  var last = 0;
  function reportSize() {
    var h = Math.ceil(document.documentElement.scrollHeight), w = Math.ceil(document.documentElement.scrollWidth);
    if (h !== last) { last = h; notify("ui/notifications/size-changed", { width: w, height: h }); }
  }
  request("ui/initialize", {
    appInfo: { name: "Krusgraph plan check", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function () {
    notify("ui/notifications/initialized");
    reportSize();
    if (window.ResizeObserver) new ResizeObserver(reportSize).observe(document.body);
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
