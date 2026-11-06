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
  reports its height with `ui/notifications/size-changed`.
- Reading the CallToolResult (n137). Seen live in Claude on the web and in the desktop app on 6 November 2026: the
  card got the answer as `{"result": "<JSON text>"}`, the SDK's wrapping of a tool that returns `str`, and listed that
  JSON string as one line under "Needs attention", with no mascots and no buttons. The cards now read the result in
  every form the specification lets a host deliver (READ_JS): `structuredContent` when it holds the answer, otherwise
  the text content parsed as JSON; a `{"result": "<JSON text>"}` wrapper is unwrapped in either place. What cannot be
  read gives a short sentence, never a raw dump. With the flag on, validate_plan and review_plan also return the answer
  as `structuredContent` (structured() below; the specification's "structuredContent: structured data optimized for
  UI rendering"), with the text content unchanged. They are then registered without an output schema, because the
  SDK's derived one ({"result": string}) would not describe that data.
- A button sends `tools/call` to the host, which the host may forward to this server or put to the user first. Only the
  tools in evidence.NEXT_STEP_TOOLS (n103: they read or draft, none creates) can be called, and only with the arguments
  the step names plus workspace, source, schema and, where the tool takes them, keys and confirmed from this call.
  Since n138 (CALL_JS) the request is sent only to a host whose `ui/initialize` answer has
  `hostCapabilities.serverTools`; otherwise, and on a JSON-RPC error, an `isError` result or no answer after 20 s, the
  card says so in a sentence and names what to ask in the chat instead.
- Graceful degradation: the tool's text answer is not changed, so a client without MCP Apps sees what it saw before.
  The SDK's `client_supports_apps` is not used to vary the listing: the hosted server is stateless, and a host that
  does not render MCP Apps ignores `_meta.ui` (the specification's "tool behaves as standard tool").
"""
from __future__ import annotations

import functools
import json
import os

from . import mcp_apps_mascots as mascots
from .evidence import NEXT_STEP_TOOLS

FLAG = "KRUSGRAPH_MCP_APPS"
CARD_URI = "ui://krusgraph/validate-plan-card.html"
APP_MIME_TYPE = "text/html;profile=mcp-app"           # the specification's MIME type; mcp.server.apps.APP_MIME_TYPE
PROTOCOL_VERSION = "2026-01-26"
TOOL = "validate_plan"
STRUCTURED = ("validate_plan", "review_plan")        # n137: the tools whose answer is also returned as structuredContent

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


def call_result(text: str):
    """n137: a tool's text answer as a CallToolResult: the same text content every client gets, plus the answer as
    `structuredContent` when the text is a JSON object (an answer that is not one has no structuredContent)."""
    from mcp.types import CallToolResult, TextContent
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        data = None
    return CallToolResult(content=[TextContent(type="text", text=text)],
                          structured_content=data if isinstance(data, dict) else None)


def structured(fn):
    """n137: the registered form of a tool in STRUCTURED when the flag is on: the tool's own function, its answer
    wrapped by call_result. The module's function stays the one that returns text."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        out = fn(*args, **kwargs)
        return call_result(out) if isinstance(out, str) else out
    return wrapper


def registration(name: str, on: bool | None = None) -> dict:
    """The extra arguments of the tool decorator for `name`: none with the flag off or for any other tool, else
    structured_output=False (no derived {"result": string} output schema, which would not describe the answer)."""
    if name not in STRUCTURED or not (enabled() if on is None else on):
        return {}
    return {"structured_output": False}


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
    """The card: one self-contained HTML5 document. No src, href, url(), @import, fetch or other load; the data arrives
    only from the host. Since n136 the site's mascots are on it as inline SVG (mcp_apps_mascots): Onto says the summary
    (the counts), the Thinker the first thing that needs attention, the Builder the first next step, each word for word
    from the text answer and also on the card; glad only when every check passed; a button hides them."""
    allowed = json.dumps({t: list(CARRIED[t]) for t in NEXT_STEP_TOOLS}, separators=(",", ":"))
    return (_HTML.replace("__ALLOWED__", allowed).replace("__PROTOCOL__", PROTOCOL_VERSION).replace("__READ_JS__", READ_JS + CALL_JS)
            .replace("__MASCOT_CSS__", mascots.CSS).replace("__MASCOT_TOGGLE__", mascots.TOGGLE)
            .replace("__MASCOTS__", mascots.section()).replace("__MASCOT_JS__", mascots.JS))


# n137: how both cards read a CallToolResult, in every form the specification lets a host deliver it. answerOf(result)
# gives the answer object or null: `structuredContent` when it holds the answer; otherwise the first text content that
# parses as a JSON object; a {"result": "<JSON text>"} wrapper (the SDK's wrapping of a `str` tool, seen live) is
# unwrapped in either place, as is a host that hands over the wrapper itself. resultText(result) gives readable text
# for a tool a button ran: its text content, or its structuredContent as indented JSON.
READ_JS = r"""
  function looksJson(t) { return typeof t === "string" && /^\s*[\[{]/.test(t); }
  function parseJson(t) { if (!looksJson(t)) return null; try { return JSON.parse(t); } catch (e) { return null; } }
  function isObj(x) { return !!x && typeof x === "object" && !Array.isArray(x); }
  function unwrap(d) {
    for (var i = 0; i < 4 && isObj(d); i++) {
      var ks = Object.keys(d);
      if (ks.length !== 1 || ks[0] !== "result") return d;
      var inner = isObj(d.result) ? d.result : parseJson(d.result);
      if (!isObj(inner)) return null;            // {"result": "<a sentence>"} holds no answer object
      d = inner;
    }
    return isObj(d) ? d : null;
  }
  function textParts(result) {
    var parts = (result && Array.isArray(result.content)) ? result.content : [], out = [];
    for (var i = 0; i < parts.length; i++) if (parts[i] && parts[i].type === "text" && typeof parts[i].text === "string") out.push(parts[i].text);
    return out;
  }
  function answerOf(result) {
    if (!isObj(result)) return null;
    var d = isObj(result.structuredContent) ? unwrap(result.structuredContent) : null;
    if (d) return d;
    var texts = textParts(result);
    for (var i = 0; i < texts.length; i++) { d = unwrap(parseJson(texts[i])); if (d) return d; }
    if (!("content" in result) && !("structuredContent" in result)) return unwrap(result);   // the wrapper itself
    return null;
  }
  function resultText(result) {
    var texts = textParts(result);
    if (texts.length) return texts.join("\n");
    var d = isObj(result) && isObj(result.structuredContent) ? unwrap(result.structuredContent) : null;
    return d ? JSON.stringify(d, null, 2) : "";
  }
  function readable(s) { return typeof s === "string" && s.trim() && !looksJson(s) ? s : ""; }
"""


# n138: how both cards ask the host to run a tool, checked against the specification read above. The request is the
# standard MCP `tools/call` (JSON-RPC 2.0: jsonrpc, id, method, params {name, arguments}); the host says in its
# `ui/initialize` answer whether it runs such calls for the view (`hostCapabilities.serverTools`, "Host can proxy tool
# calls to the MCP server"). A host without it is not asked: the button says so in a sentence and names what to ask in
# the chat. A JSON-RPC error (-32601 "method not found" is a host that does not take the call), a result with
# `isError`, and a host that has not answered after WAIT_MS each give a sentence too; nothing fails silently.
CALL_JS = r"""
  var hostCaps = null, WAIT_MS = 20000;
  function canCallTools() { return isObj(hostCaps) && isObj(hostCaps.serverTools); }
  function callTool(name, args, onWait) {
    if (!canCallTools()) return Promise.reject({ kind: "unsupported" });
    var timer = setTimeout(onWait, WAIT_MS);
    return request("tools/call", { name: name, arguments: args }).then(function (r) {
      clearTimeout(timer);
      if (isObj(r) && r.isError === true) throw { kind: "tool", text: resultText(r) };
      return r;
    }, function (e) {
      clearTimeout(timer);
      throw { kind: isObj(e) && e.code === -32601 ? "unsupported" : "host", message: isObj(e) ? e.message : "" };
    });
  }
  function callProblem(e, tool, ask) {
    var then = " Ask in the chat instead: “" + ask + "”";
    if (e && e.kind === "unsupported") return "This host does not run tools from the card." + then;
    if (e && e.kind === "tool") {
      var t = readable(e.text) ? e.text.slice(0, 300) : "no reason given";
      return tool + " answered with an error: " + t.replace(/[.\s]+$/, "") + ".";
    }
    var why = e && typeof e.message === "string" && e.message.trim() ? e.message.trim().slice(0, 200) : "no reason given";
    return "The host did not run " + tool + ": " + why.replace(/[.\s]+$/, "") + "." + then;
  }
  function stillWaiting(ask) {
    return "No answer from the host yet; it may be asking you first. If nothing happens, ask in the chat instead: “" + ask + "”";
  }
  function hostStarted(r) { hostCaps = isObj(r) && isObj(r.hostCapabilities) ? r.hostCapabilities : {}; }
"""

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
__MASCOT_CSS__
</style>
</head>
<body>
<main>
  <div class="kg-head"><h1>Plan check</h1>__MASCOT_TOGGLE__</div>
  <p class="muted" role="status"><span id="verdict">Waiting for validate_plan's answer.</span><span id="result" hidden></span></p>
  __MASCOTS__
  <dl id="counts" class="counts" hidden></dl>
  <section id="attention" hidden><h2 class="muted">Needs attention</h2><ul id="attention-list"></ul><p id="attention-none" hidden>Nothing needs attention.</p></section>
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
__MASCOT_JS__
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = String(text); if (cls) e.className = cls; return e; }

__READ_JS__
  function render(result) {
    var data = answerOf(result);
    var verdict = document.getElementById("verdict");
    mascotsQuiet();
    ["counts", "result", "attention", "next"].forEach(function (id) { document.getElementById(id).hidden = true; });
    if (!data || (!data.error && !data.summary && !data.totals)) { verdict.textContent = "The card could not read validate_plan's answer; it is in the text of the tool result."; return; }
    if (data.error) { verdict.textContent = readable(data.error) + (readable(data.hint) ? " " + data.hint : ""); return; }
    verdict.textContent = readable(data.summary);
    var counts = document.getElementById("counts"); counts.textContent = "";
    var totals = data.totals || {};
    [["keys", "Keys"], ["relationships", "Relationships"], ["amount_levels", "Header amounts"]].forEach(function (k) {
      var t = totals[k[0]]; if (!isObj(t) || !t.checked) return;
      var box = el("div"); box.appendChild(el("dt", k[1]));
      box.appendChild(el("dd", t.passed + " of " + t.checked + " passed", t.failed ? "warn" : "ok"));
      counts.appendChild(box);
    });
    var box = el("div"); box.appendChild(el("dt", "Needs attention"));
    box.appendChild(el("dd", String(Number(data.needs_attention) || 0), data.needs_attention ? "warn" : "ok"));
    counts.appendChild(box);
    counts.hidden = false;

    // n137: the overall result in words (an answer with nothing to attend to has one), never a JSON text. n138: it is
    // part of the summary line, once; the attention section then says only that nothing needs attention.
    var res = document.getElementById("result"), said = readable(data.result);
    res.textContent = said ? (verdict.textContent ? ". " : "") + said : ""; res.hidden = !said;

    var list = document.getElementById("attention-list"); list.textContent = "";
    var att = isObj(data.attention) ? data.attention : {}, firstWhat = "", firstStep = "";
    Object.keys(att).forEach(function (kind) {
      (Array.isArray(att[kind]) ? att[kind] : []).forEach(function (x) {
        if (typeof x === "string") { if (readable(x)) { if (!firstWhat) firstWhat = x; list.appendChild(el("li", x)); } return; }
        if (!isObj(x)) return;
        var what = readable(x.verdict) || readable(x.do_instead) || readable(x.explanation) ||
          [x.table || x.source || x.header, x.target || x.line].filter(Boolean).join(" \\u2192 ");
        var who = x.table || (x.source ? x.source + " \\u2192 " + x.target : (x.header ? x.header + " / " + x.line : kind));
        if (!what) return;
        if (!firstWhat) firstWhat = what;
        list.appendChild(el("li", who + ": " + what));
      });
    });
    document.getElementById("attention-none").hidden = !!list.children.length;
    document.getElementById("attention").hidden = false;

    var steps = document.getElementById("steps"); steps.textContent = "";
    (Array.isArray(data.next_steps) ? data.next_steps : []).forEach(function (s) {
      if (!isObj(s) || !Object.prototype.hasOwnProperty.call(ALLOWED, s.tool)) return;   // only read and draft tools
      var row = el("div", null, "step");
      var why = readable(s.why) || readable(s.text);
      if (!firstStep) firstStep = why;
      row.appendChild(el("p", why));
      var b = el("button", "Run " + s.tool); b.type = "button";
      var out = el("pre"); out.hidden = true;
      b.addEventListener("click", function () { run(s, b, out); });
      row.appendChild(b); row.appendChild(out); steps.appendChild(row);
    });
    document.getElementById("next").hidden = !steps.children.length;

    // n136: Onto says the counts, the Thinker what needs attention, the Builder the next step; every sentence is a
    // string of the answer and is on the card above. Glad only when every check passed and nothing needs attention.
    var checked = 0, failed = 0;
    Object.keys(totals).forEach(function (k) { var t = isObj(totals[k]) ? totals[k] : {}; checked += t.checked || 0; failed += t.failed || 0; });
    var passed = checked > 0 && failed === 0 && !data.needs_attention && !firstWhat;
    mascots({ onto: [readable(data.summary), passed ? "celebrate" : "point"],
              thinker: [firstWhat, "think"],
              builder: [firstStep, passed ? "heart" : "explain"] }, passed);
  }

  function run(step, button, out) {
    var args = {};
    (ALLOWED[step.tool] || []).forEach(function (k) { if (input[k] != null) args[k] = input[k]; });
    var own = step.arguments || {};
    Object.keys(own).forEach(function (k) { args[k] = own[k]; });
    var ask = "Run " + step.tool + " with the same workspace, source and schema.";
    out.hidden = false;
    if (!canCallTools()) { out.textContent = callProblem({ kind: "unsupported" }, step.tool, ask); return; }
    button.disabled = true; out.textContent = "Asked the host to run " + step.tool + ".";
    callTool(step.tool, args, function () { out.textContent = stillWaiting(ask); }).then(function (r) {
      var t = resultText(r); out.textContent = t.length > 4000 ? t.slice(0, 4000) + "\\n\\u2026 (the rest is in the tool's own answer)" : t;
    }, function (e) {
      out.textContent = callProblem(e, step.tool, ask);
    }).then(function () { button.disabled = false; });
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
    else if (m.method === "ui/notifications/tool-cancelled") { document.getElementById("verdict").textContent = "The check was cancelled."; mascotsQuiet(); }
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
  }).then(function (r) {
    hostStarted(r);
    notify("ui/notifications/initialized");
    reportSize();
    if (window.ResizeObserver) new ResizeObserver(reportSize).observe(document.body);
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
