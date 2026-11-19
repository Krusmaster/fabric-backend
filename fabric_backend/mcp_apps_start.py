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

WB12 (Gustav's chat test in claude.ai, 18 November 2026, issues #66-#77), all drawn from the answer:
- steps 1-3 list what the account can open as buttons (`kind: "choose"`, each calls start with the choice set), with a
  search box when there are more than eight, and a disabled button with its reason (a schema without tables);
- step 6 draws each open decision with its counted evidence and its Accept, Reject and Skip buttons (`kind: "decide"`,
  each calls start with the decision in plan.decisions); Next is secondary while a decision is open;
- step 5 draws the proof tiles (rows counted, keys unique, links holding, orphans, duplicate keys) and the grain line;
- the rule codes are said in words once (`found.rules`); the finished steps fold into one line ("Done: 1-5");
- the "Steps 1-8 only read" sentence in full on the first card only, then "Only step 9 writes" that opens to it;
- before a choice, Next is shown disabled with its reason (`next_waits`);
- the card reports the height of its content, not of its frame. Before WB12 it sent
  `document.documentElement.scrollHeight`, which is never less than the frame's own height, so a frame the host had
  made tall never shrank (the blank space under steps 5-9). It now measures `main` and sends that with
  `ui/notifications/size-changed` ({width, height}) whenever a ResizeObserver on `main` fires. Sources: the MCP Apps
  specification, modelcontextprotocol/ext-apps specification/2026-01-26/apps.mdx, "ui/notifications/size-changed"
  (the view reports its size; the host may resize the frame), and Claude's MCP Apps docs
  (claude.com/docs/connectors/building/mcp-apps), as cited in mcp_apps.py and mcp_apps_next.py.

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
    from . import mcp_apps_pictures as pictures           # WB13 (#71): the small map, the review card's drawing
    from .mcp_apps_size import SIZE_JS                   # WB13 (#89)
    pic = pictures.html_parts()
    return (_HTML.replace("__SIZE_JS__", SIZE_JS).replace("__PROTOCOL__", mcp_apps.PROTOCOL_VERSION)
            .replace("__ALLOWED__", json.dumps(ALLOWED, separators=(",", ":"))).replace("__PICTURES__", pic["section"])
            .replace("__READ_JS__", mcp_apps.READ_JS + mcp_apps.CALL_JS + mcp_apps.RESULT_JS + nxt.js() + pic["js"])
            .replace("__MASCOT_CSS__", mascots.CSS).replace("__RESULT_CSS__", mcp_apps.RESULT_CSS + nxt.NEXT_CSS + pic["css"] + START_CSS)
            .replace("__MASCOT_TOGGLE__", mascots.TOGGLE).replace("__MASCOTS__", mascots.section())
            .replace("__MASCOT_JS__", mascots.JS))


START_CSS = """
.st-path { list-style: none; padding: 0; margin: 0; display: grid; gap: 3px }
.st-path li { display: flex; gap: 8px; align-items: baseline; font-size: 14px; color: var(--kg-muted) }
.st-path li[data-state="now"] { color: var(--kg-ink); font-weight: 650 }
.st-path li[data-state="done"]::before { content: "\\2713"; color: var(--kg-ok) }
.st-path li[data-state="now"]::before { content: "\\25B6" }
.st-path li[data-state="later"]::before { content: "\\00B7" }
.st-does { white-space: nowrap; flex: none; font-size: 12px; border: 1px solid var(--kg-line); border-radius: 999px; padding: 0 7px }
.st-does[data-does="writes"] { color: var(--kg-warn); border-color: currentColor }
.st-acts { display: grid; gap: 8px; border-top: 1px solid var(--kg-line); padding-top: 8px }
.st-act { display: grid; gap: 4px }
.st-act .out { border-left: 3px solid var(--kg-line); padding-left: 8px; display: grid; gap: 6px }
button.st-create { background: var(--kg-ink); color: var(--kg-bg) }
button.st-secondary { background: transparent; font-weight: 500; color: var(--kg-muted) }
.st-path li[data-state="skipped"]::before { content: "\2013" }
.st-path li[data-state="skipped"] { opacity: .8 }
details.st-done > summary, details.st-honest > summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px }
details.st-done[open] > summary { margin-bottom: 4px }
.st-tiles { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; grid-template-columns: repeat(auto-fit, minmax(92px, 1fr)) }
.st-tiles li { border: 1px solid var(--kg-line); border-radius: 10px; padding: 6px 8px; display: grid }
.st-tiles strong { font-size: 18px; font-variant-numeric: tabular-nums }
.st-tiles span { font-size: 12.5px; color: var(--kg-muted) }
.st-choices { display: flex; flex-wrap: wrap; gap: 6px }
.st-choices button { display: grid; text-align: left; justify-items: start; border-radius: 12px; max-width: 100%;
  overflow-wrap: anywhere }
.st-choices button small { font-weight: 400; color: var(--kg-muted); font-size: 12.5px }
.st-search { font: inherit; width: 100%; padding: 6px 10px; border: 1px solid var(--kg-line); border-radius: 10px;
  background: var(--kg-bg); color: var(--kg-ink) }
.st-decision { border: 1px solid var(--kg-line); border-radius: 12px; padding: 8px 10px; display: grid; gap: 6px }
.st-decision[data-state="accepted"] { border-color: var(--kg-ok) }
.st-decision .st-row { display: flex; flex-wrap: wrap; gap: 6px }
.st-wait { display: grid; gap: 2px }
.res-box, .st-acts, main { min-width: 0; overflow-wrap: anywhere }
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
<main id="main">
  <div class="kg-head"><h1 id="title">Start Krusgraph</h1>__MASCOT_TOGGLE__</div>
  <p class="muted" role="status" id="verdict">Waiting for the tool's answer.</p>
  <div id="next"></div>
  <div id="answer"></div>
  __PICTURES__
  __MASCOTS__
  <ol class="st-path" id="path" aria-label="The steps"></ol>
  <div class="muted" id="honest"></div>
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
    if ((a.kind === "choose" || a.kind === "decide") && a.tool !== "start") return false;     // WB12: only start calls
    if (a.arguments.dry_run === false) {
      return kind === "build" && a.kind === "create" && Array.isArray(d.confirmed_by_user) &&
             d.confirmed_by_user.indexOf(a.arguments.name) >= 0;
    }
    return a.kind !== "create";
  }
  function button(a, d, box) {
    var row = el("div", null, "st-act"), create = a.kind === "create";
    var b = el("button", a.label, create ? "st-create" : (a.secondary ? "nx-b st-secondary" : "nx-b")); b.type = "button"; b.setAttribute("data-tool", a.tool);
    if (a.kind) b.setAttribute("data-kind", a.kind);
    if (a.decision) b.setAttribute("data-decision", a.decision);
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
      var act = { kind: a.kind, label: a.label, name: a.arguments.name };        // n227: the progress state
      if (a.tool === "start") runOrSay("start", args, askOf(a), out, b, function (r) { render(r); }, act);
      else if (create) {                                      // n227: a Create is never sent twice from the card
        act.unknown = function (box) { statusRow(a, "name", box); };
        runOrSay(a.tool, args, askOf(a), out, b, function (r) {
          out.appendChild(answerView(a.tool, r));
          var d = answerOf(r), working = isObj(d) && isObj(d.started);
          if (working) statusRow(a, d.started.check, out);
          b.disabled = working || !(isObj(d) && readable(d.error));   // off for good unless the tool said nothing was created
        }, act);
      }
      else runOrSay(a.tool, args, askOf(a), out, b, null, act);
    });
    row.insertBefore(b, row.firstChild); row.appendChild(out); box.appendChild(row);
  }
  // n227 (9): Check status: the same tool with `check` set, which reads how the create went and creates nothing.
  function statusRow(a, check, box) {
    var sa = JSON.parse(JSON.stringify(a.arguments)); delete sa.dry_run; sa.check = typeof check === "string" && check ? check : "name";
    var row = el("div", null, "st-act"), b = el("button", "Check status", "nx-b"), out = el("div", null, "out"); b.type = "button"; out.hidden = true;
    b.setAttribute("data-kind", "status");
    row.appendChild(b); row.appendChild(el("span", "Only reads: looks whether " + a.arguments.name + " is in Fabric now. Nothing is created again.", "muted")); row.appendChild(out);
    b.addEventListener("click", function () {
      runOrSay(a.tool, sa, "Check whether " + a.arguments.name + " is in Fabric now, without creating anything.", out, b, function (r) {
        out.appendChild(answerView(a.tool, r));
        var d = answerOf(r);
        if (isObj(d) && isObj(d.started)) { b.disabled = false; } else { b.disabled = true; }
      }, { kind: "status", label: "Check status", name: a.arguments.name });
    });
    box.appendChild(row);
  }
  function listOf(items) { var ul = el("ul"); items.forEach(function (x) { if (readable(x)) ul.appendChild(el("li", x)); }); return ul; }
  function strings(x) { return Array.isArray(x) ? x.filter(readable) : []; }
  // WB12 (#73): the finished steps fold into one line that opens; the step now and the later ones stay listed
  function drawPath(d, path) {
    var steps = (Array.isArray(d.path) ? d.path : []).filter(isObj), folded = null;
    if (readable(d.done_line)) {
      folded = el("details", null, "st-done"); folded.appendChild(el("summary", d.done_line));
      var inner = el("ol", null, "st-path"); folded.appendChild(inner);
    }
    var later = steps.filter(function (p) { return p.state === "later"; }), laterBox = null;
    if (later.length > 1) {                                   // the later steps fold too: the list stays short on a phone
      laterBox = el("details", null, "st-done"); laterBox.setAttribute("data-fold", "later");
      laterBox.appendChild(el("summary", "Then: " + later[0].n + "-" + later[later.length - 1].n));
      var laterList = el("ol", null, "st-path"); laterBox.appendChild(laterList);
    }
    steps.forEach(function (p) {
      var li = el("li"); li.setAttribute("data-state", p.state); li.setAttribute("data-key", p.key);
      li.appendChild(el("span", p.n + ". " + p.title + (readable(p.note) ? " (" + p.note + ")" : "")));
      var does = el("span", p.does, "st-does"); does.setAttribute("data-does", p.does); li.appendChild(does);
      if (folded && (p.state === "done" || p.state === "skipped")) inner.appendChild(li);
      else if (laterBox && p.state === "later") laterList.appendChild(li);
      else path.appendChild(li);
    });
    if (folded) path.parentNode.insertBefore(folded, path);
    if (laterBox) path.parentNode.insertBefore(laterBox, path.nextSibling);
  }
  function tiles(proof) {
    var ul = el("ul", null, "st-tiles"); ul.setAttribute("aria-label", "What the check proved");
    (Array.isArray(proof.tiles) ? proof.tiles : []).forEach(function (t) {
      if (!Array.isArray(t) || t.length < 2) return;
      var li = el("li"); li.appendChild(el("strong", t[0])); li.appendChild(el("span", t[1])); ul.appendChild(li);
    });
    return ul;
  }
  // WB12 (#76): steps 1-3: what the account can open, as buttons; a search box when the list is long
  function drawChoices(d, acts, box) {
    var picks = acts.filter(function (a) { return a.kind === "choose" && okButton(a, d); });
    if (!picks.length) return;
    var wrap = el("section", null, "st-acts"); wrap.setAttribute("aria-label", "Choose");
    var list = el("div", null, "st-choices");
    if (isObj(d.choices) && d.choices.search) {
      var q = el("input", null, "st-search"); q.type = "search"; q.placeholder = "Search " + picks.length + " names";
      q.setAttribute("aria-label", "Search the list");
      q.addEventListener("input", function () {
        var t = q.value.toLowerCase();
        Array.prototype.forEach.call(list.childNodes, function (b) { b.hidden = t && b.getAttribute("data-name").toLowerCase().indexOf(t) < 0; });
      });
      wrap.appendChild(q);
    }
    var out = el("div", null, "out"); out.hidden = true;
    picks.forEach(function (a) {
      var b = el("button", null, "nx-b"); b.type = "button"; b.setAttribute("data-kind", "choose"); b.setAttribute("data-name", a.label);
      b.appendChild(el("span", a.label));
      var why = readable(a.disabled) ? a.disabled : (readable(a.hint) ? a.hint : "");
      if (why) b.appendChild(el("small", why));
      if (readable(a.disabled)) { b.disabled = true; b.title = a.disabled; }
      b.addEventListener("click", function () {
        runOrSay("start", JSON.parse(JSON.stringify(a.arguments)), askOf(a), out, b, function (r) { render(r); },
                 { kind: "call", label: a.label });
      });
      list.appendChild(b);
    });
    wrap.appendChild(list); wrap.appendChild(out); box.appendChild(wrap);
  }
  // WB12 (#66): each decision with its counted evidence and its own buttons
  function drawDecisions(d, f, box) {
    var acts = (Array.isArray(d.actions) ? d.actions : []).filter(function (a) { return a.kind === "decide" && okButton(a, d); });
    (Array.isArray(f.decisions) ? f.decisions : []).filter(isObj).forEach(function (x) {
      var card = el("div", null, "st-decision"); card.setAttribute("data-state", x.state || "open"); card.setAttribute("data-item", x.item || "");
      card.appendChild(el("p", x.question));
      var ev = strings(x.evidence);
      if (ev.length) card.appendChild(el("p", ev.join(" "), "muted"));
      if (x.state && x.state !== "open") card.appendChild(el("p", "Your decision: " + (x.state === "skipped" ? "skipped for now" : x.state) + ".", "muted"));
      var row = el("div", null, "st-row");
      acts.filter(function (a) { return a.item === x.item; }).forEach(function (a) { button(a, d, row); });
      if (row.childNodes.length) card.appendChild(row);
      box.appendChild(card);
    });
  }
  function render(result) {
    var d = answerOf(result), verdict = document.getElementById("verdict"), path = document.getElementById("path");
    var answer = document.getElementById("answer"), next = document.getElementById("next");
    answer.textContent = ""; next.textContent = ""; path.textContent = ""; mascotsQuiet();
    Array.prototype.forEach.call(document.querySelectorAll("details.st-done"), function (x) { x.remove(); });
    verdict.removeAttribute("data-echo"); verdict.removeAttribute("data-said"); verdict.hidden = false;
    var honest = document.getElementById("honest"); honest.textContent = "";
    if (!d) { verdict.textContent = "The card could not read the answer; it is in the text of the tool result."; return; }
    if (readable(d.error)) { verdict.textContent = d.error + (readable(d.hint) ? " " + d.hint : ""); return; }
    var st = isObj(d.step) ? d.step : {};
    document.getElementById("title").textContent = "Start Krusgraph" + (st.n ? ": step " + st.n + " of " + st.of : "") + (d.sample ? " (synthetic shop)" : "");
    drawPath(d, path);
    verdict.textContent = readable(d.say) || readable(d.summary) || "";
    // n227 (1): the sentence is shown once: in Onto's bubble while the mascots are on, here while they are off
    verdict.setAttribute("data-echo", "onto"); verdict.setAttribute("data-said", verdict.textContent);
    if (isObj(d.chosen)) {
      var shown = ["workspace", "source", "schema"].filter(function (k) { return readable(d.chosen[k]); })
        .map(function (k) { return k + ": " + d.chosen[k]; });
      if (shown.length) answer.appendChild(el("p", "Chosen: " + shown.join(", "), "muted"));
    }
    var actions = (Array.isArray(d.actions) ? d.actions : []);
    drawChoices(d, actions, answer);
    if (isObj(d.found)) {
      var f = d.found, box = el("div", null, "res-box");
      ["summary", "note"].forEach(function (k) { if (readable(f[k])) box.appendChild(el("p", f[k])); });
      if (readable(f.question) && !Array.isArray(f.decisions)) box.appendChild(el("p", f.question));
      if (isObj(f.proof)) { box.appendChild(tiles(f.proof)); if (readable(f.proof.grain)) box.appendChild(el("p", f.proof.grain)); }
      if (Array.isArray(f.links)) box.appendChild(listOf(f.links));
      if (strings(f.rules).length) box.appendChild(el("p", strings(f.rules).join(". ") + ".", "muted"));
      if (Array.isArray(f.decisions)) drawDecisions(d, f, box);
      if (Array.isArray(f.doubled)) box.appendChild(listOf(f.doubled));
      strings(f.advice).forEach(function (x) { box.appendChild(el("p", x)); });
      if (strings(f.decided).length) { box.appendChild(el("p", "Your decisions", "muted")); box.appendChild(listOf(strings(f.decided))); }
      if (Array.isArray(f.would_build)) box.appendChild(listOf(f.would_build.filter(isObj).map(function (w) { return w.name + ": " + w.what; })));
      if (box.childNodes.length) answer.appendChild(box);
    }
    if (strings(d.decided).length) { answer.appendChild(el("p", "Your decisions", "muted")); answer.appendChild(listOf(strings(d.decided))); }
    if (Array.isArray(d.would_build)) answer.appendChild(listOf(d.would_build.filter(isObj).map(function (w) { return w.name + ": " + w.what; })));
    if (typeof drawPictures === "function") drawPictures({ map: d.map, map_mini: d.map_mini }, {});   // WB13 (#71)
    var flow = Array.isArray(d.data_flow) ? d.data_flow : (isObj(d.found) && Array.isArray(d.found.data_flow) ? d.found.data_flow : null);
    if (flow) { answer.appendChild(el("p", "The data flow", "muted")); answer.appendChild(listOf(flow)); }
    var acts = el("section", null, "st-acts"); acts.setAttribute("aria-label", "This step");
    actions.forEach(function (a) { if (a.kind !== "choose" && a.kind !== "decide" && okButton(a, d)) button(a, d, acts); });
    if (isObj(d.after) && !d.sample && okButton({ kind: "call", label: d.after.label, say: d.after.say, tool: d.after.tool, arguments: d.after.arguments }, d))
      button({ kind: "call", label: d.after.label, say: d.after.say, ask: d.after.ask, tool: "start", arguments: d.after.arguments, secondary: !!d.after.secondary }, d, acts);
    if (isObj(d.after) && d.after.secondary && readable(d.after.why)) acts.appendChild(el("span", d.after.why, "muted"));
    if (isObj(d.next_waits) && readable(d.next_waits.label)) {            // WB12 (#77): no Next before the choice
      var w = el("div", null, "st-wait"), nb = el("button", d.next_waits.label, "nx-b st-secondary");
      nb.type = "button"; nb.disabled = true; nb.setAttribute("data-kind", "next-waits");
      w.appendChild(nb); if (readable(d.next_waits.why)) w.appendChild(el("span", d.next_waits.why, "muted")); acts.appendChild(w);
    }
    if (acts.childNodes.length) next.appendChild(acts);
    // WB13 (#93): the step's buttons come right after its sentence; on step 6 the decisions (each with its own buttons)
    // come first and Next, secondary until they are answered, after them
    var decides = isObj(d.found) && Array.isArray(d.found.decisions) && d.found.decisions.length;
    if (decides) next.parentNode.insertBefore(answer, next); else answer.parentNode.insertBefore(next, answer);
    if (readable(d.honest)) {                                             // WB12 (#72): in full once, then one line
      if (d.honest_open || !readable(d.honest_short)) honest.textContent = d.honest;
      else {
        var det = el("details", null, "st-honest"); det.appendChild(el("summary", d.honest_short)); det.appendChild(el("p", d.honest, "muted"));
        honest.appendChild(det);
      }
    }
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

__SIZE_JS__
  request("ui/initialize", {
    appInfo: { name: "Krusgraph start", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function (r) {
    hostStarted(r);
    if (isObj(r) && isObj(r.hostContext) && isObj(r.hostContext.toolInfo) && isObj(r.hostContext.toolInfo.tool)) tool = r.hostContext.toolInfo.tool.name || "";
    notify("ui/notifications/initialized");
    watchSize();
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
