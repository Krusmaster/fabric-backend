"""MCP Apps, the Start Krusgraph card (round n219): the `start` tool's answer as a stepper.

Behind the n119 flag (KRUSGRAPH_MCP_APPS, off unless "1"): with the flag off nothing here reaches the server, and
`start` answers text only, as every client gets it.

What the card draws, all from the answer (start_flow.guide), never invented by the card:
- the path, five steps (SM2: your data, check, decide, dry run, create), each marked done, now or later and "reads"
  or "writes";
- what was chosen so far, the step's sentence, and for the synthetic shop what the tool found there;
- the step's buttons. Each runs its tool through the host with n218's runner (mcp_apps_next NEXT_JS: `tools/call` when
  the host has serverTools, otherwise the button's `say` goes to the chat with `ui/message`), and the tool's answer is
  drawn under the button with n218's answerView (check rows, next steps). Only the tools in ALLOWED can be called;
  a creating tool only as a dry run (no dry_run argument: the tool's default is true), except on step 5 after the
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
- the "Steps 1-4 only read" sentence in full on the first card only, then "Only step 5 writes" that opens to it;
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
/* WB15: the coach on top, big and visible in light and dark, as the home page's demo chat */
.st-coach { margin: 0 }
.st-coach .kg-say.st-big { grid-template-columns: 72px minmax(0, 1fr); gap: 4px 10px; align-items: center }
.st-coach .kg-say.st-big .kg-fig { width: 72px; height: 72px }
.st-coach .kg-bub { border-radius: 4px 16px 16px 16px; padding: 8px 12px }
.st-line { font-size: 16px; line-height: 1.4; margin: 0 }
.kg-who { margin: 0; font-size: 13px; font-weight: 650; color: var(--kg-muted) }
html[data-mascots="off"] .st-coach .kg-fig { display: none }
html[data-mascots="off"] .st-coach .kg-say.st-big { grid-template-columns: minmax(0, 1fr) }
h1#title { font-size: 15px; color: var(--kg-muted) }
button.st-picked { border-color: var(--kg-ok); border-width: 2px }
.st-q { font-weight: 650 }
.st-count { font-variant-numeric: tabular-nums }
.st-mine { color: var(--kg-ok); font-weight: 600 }
details.st-details > summary, details.st-more > summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px }
details.st-details[open] { display: grid; gap: 8px }
.st-moreinfo { display: grid; gap: 6px; font-size: 13.5px }
.st-moved { margin: 0 }
.st-chosen { font-weight: 650; font-size: 16px }
.st-dry { margin: 0 }
.st-lines { display: grid; gap: 2px }
.st-dryout { display: grid; gap: 4px; border-top: 1px solid var(--kg-line); padding-top: 6px }
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
  <div class="kg-head"><h1 id="title">Start Krusgraph</h1></div>
  <section id="coach" class="st-coach" aria-label="Your coach" hidden></section>
  <p class="muted" role="status" id="verdict">Waiting for the tool's answer.</p>
  <div id="answer"></div>
  <div id="next"></div>
  __PICTURES__
  __MASCOTS__
  <details id="details" class="st-details" hidden><summary>Details</summary><div id="more" class="st-moreinfo"></div>
    <ol class="st-path" id="path" aria-label="The steps"></ol><p class="muted" id="honest"></p>
    __MASCOT_TOGGLE__</details>
  <p id="moved" class="muted st-moved" role="status" hidden></p>
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
    if (a.kind === "link") return typeof a.url === "string" && /^https:[/][/]/.test(a.url);       // SM2: Open in Fabric
    if (a.kind === "dry_run_all" && a.tool !== "start") {          // SM2: every run a dry run of a building tool
      return Array.isArray(a.runs) && a.runs.length > 0 && a.runs.every(function (r) {
        return isObj(r) && ALLOWED[r.tool] === "build" && isObj(r.arguments) && r.arguments.dry_run !== false; });
    }
    if ((a.kind === "choose" || a.kind === "decide" || a.kind === "confirm") && a.tool !== "start") return false;
    if (a.arguments.dry_run === false) {
      return kind === "build" && a.kind === "create" && Array.isArray(d.confirmed_by_user) &&
             d.confirmed_by_user.indexOf(a.arguments.name) >= 0;
    }
    return a.kind !== "create";
  }
  // WB15: one living card. Every start button runs here, one at a time (busy): the buttons that call start are off
  // while a call runs, so taps 1-2 s apart cannot overtake each other (Gustav's Accept, Reject, Accept); an answer older
  // than the one drawn (the server's seq) is not drawn. Where the host runs no tool from the card, the step goes to the
  // chat in plain words (never a tool's name or arguments) and this card folds to one line: Claude's answer brings the
  // next card.
  var busy = false, lastSeq = 0, myStep = 0, moved = false, CARD_ID = String(Math.random()).slice(2);
  var chan = null;
  try {
    chan = new BroadcastChannel("krusgraph-start");
    chan.onmessage = function (e) {
      var m = e.data;
      if (isObj(m) && m.id !== CARD_ID && typeof m.seq === "number" && m.seq > lastSeq) moveOn();
    };
  } catch (e) { chan = null; }
  function moveOn() {
    if (moved) return;
    moved = true;
    var main = document.getElementById("main"), line = document.getElementById("moved");
    Array.prototype.forEach.call(main.children, function (x) { if (x !== line) x.hidden = true; });
    line.textContent = "Moved on: step " + (myStep || 1) + ". The path goes on in the newest Krusgraph card.";
    line.hidden = false;
    if (typeof reportSize === "function") reportSize();
  }
  function setBusy(on) {
    Array.prototype.forEach.call(document.querySelectorAll("main button[data-start]"), function (x) {
      if (on) { x.setAttribute("data-was", x.disabled ? "1" : ""); x.disabled = true; }
      else { x.disabled = x.getAttribute("data-was") === "1"; x.removeAttribute("data-was"); }
    });
    document.documentElement.setAttribute("data-busy", on ? "1" : "");
  }
  function handOff(ask, out, b) {
    var text = plainAsk(ask);
    out.hidden = false; out.textContent = "Sent to the chat: “" + text + "”";
    var settled = false;
    var t = setTimeout(function () {                        // WB15 (A): the host never answered: say so, never nothing
      if (settled) return;
      out.textContent = "The chat did not take it. Type this in the chat: “" + text + "”";
      if (b) b.disabled = false;
    }, 6000);
    sendChat(text).then(function () { settled = true; clearTimeout(t); moveOn(); }, function () {
      settled = true; clearTimeout(t);
      out.textContent = "This host runs no steps from the card. Type this in the chat: “" + text + "”";
      if (b) b.disabled = false;
    });
  }
  function startCall(args, ask, out, b, act) {
    if (busy || moved) return;
    out.hidden = false; out.textContent = "";
    if (!canCallTools()) { if (b) b.disabled = true; handOff(ask, out, b); return; }
    busy = true; setBusy(true);
    var wait = waitView(act || { label: b ? b.textContent : "" }); out.appendChild(wait.el);
    callTool("start", JSON.parse(JSON.stringify(args)), function () { wait.note(stillWaiting(ask)); }).then(function (r) {
      wait.stop(); busy = false; setBusy(false); out.textContent = ""; out.hidden = true; render(r);
    }, function (e) {
      wait.stop(); busy = false; setBusy(false);
      if (e && e.kind === "unsupported") { handOff(ask, out, b); return; }
      out.textContent = callProblem(e, "start", plainAsk(ask));
    });
  }
  // A tool's answer inside this card: its few lines (kg_card), the long lists folded; never another coach or buttons
  function stepAnswer(tool, r) {
    var d = answerOf(r), box = el("div", null, "nx-res st-res");
    box.appendChild(resultView(tool, r));
    if (isObj(d) && isObj(d.checks)) {
      var all = el("details", null, "st-more"); all.appendChild(el("summary", "Every check"));
      renderChecks(d, all); if (all.childNodes.length > 1) box.appendChild(all);
    }
    return box;
  }
  function button(a, d, box) {
    var row = el("div", null, "st-act"), create = a.kind === "create";
    var cls = create ? "st-create" : (a.primary ? "nx-b nx-primary" : (a.secondary ? "nx-b st-secondary" : "nx-b"));
    var b = el("button", a.label, cls); b.type = "button"; b.setAttribute("data-tool", a.tool);
    if (a.primary) b.setAttribute("data-primary", "true");
    if (a.kind) b.setAttribute("data-kind", a.kind);
    if (a.tool === "start") b.setAttribute("data-start", "1");
    if (a.decision) b.setAttribute("data-decision", a.decision);
    var out = el("div", null, "out"); out.hidden = true;
    var armed = false;
    if (a.secondary && readable(a.why)) b.title = a.why;
    b.addEventListener("click", function () {
      if (a.kind === "link") { openOrShow(a.url, out, b); return; }
      if (a.kind === "chat") { out.hidden = false; sayInChat(askOf(a), out, b); return; }
      if (a.kind === "dry_run_all" && a.tool !== "start") { dryAll(a, out, b); return; }
      if (create && !armed) {                                 // never writes on the first click
        armed = true; b.textContent = "Yes, create " + a.arguments.name + " in Fabric"; b.setAttribute("data-armed", "true");
        out.hidden = false; out.textContent = "Tap again to create " + a.arguments.name + ". Nothing has been created yet.";
        return;
      }
      var args = JSON.parse(JSON.stringify(a.arguments));
      var act = { kind: a.kind, label: a.label, name: a.arguments.name };        // n227: the progress state
      if (a.tool === "start") { startCall(args, askOf(a), out, b, act); return; }
      if (create) {                                           // n227: a Create is never sent twice from the card
        act.unknown = function (box) { statusRow(a, "name", box); };
        runOrSay(a.tool, args, askOf(a), out, b, function (r) {
          out.appendChild(stepAnswer(a.tool, r));
          var dd = answerOf(r), working = isObj(dd) && isObj(dd.started);
          if (working) statusRow(a, dd.started.check, out);
          b.disabled = working || !(isObj(dd) && readable(dd.error));
        }, act);
        return;
      }
      runOrSay(a.tool, args, askOf(a), out, b, function (r) { out.appendChild(stepAnswer(a.tool, r)); }, act);
    });
    row.insertBefore(b, row.firstChild); row.appendChild(out); box.appendChild(row);
  }
  // SM2: Dry run everything. The dry runs one after the other in this card, each as one line ("✓ demo_lh_model");
  // each tool's answer goes under Details. Nothing is created: every run is a building tool without dry_run=false.
  function dryAll(a, out, b) {
    if (busy || moved) return;
    out.hidden = false; out.textContent = "";
    if (!canCallTools()) { b.disabled = true; sayInChat(askOf(a), out, b); return; }
    var runs = a.runs.slice(), more = document.getElementById("more"), details = document.getElementById("details");
    busy = true; setBusy(true); b.disabled = true;
    var list = el("div", null, "st-lines"); out.appendChild(list);
    function finish() {
      busy = false; setBusy(false); b.disabled = false; b.textContent = "Dry run again";
      b.className = "nx-b st-secondary"; b.removeAttribute("data-primary");
      var nb = document.querySelector('#next button[data-kind="next"]');
      if (nb) { nb.className = "nx-b nx-primary"; nb.setAttribute("data-primary", "true"); }
      if (typeof reportSize === "function") reportSize();
    }
    function one() {
      if (!runs.length) { finish(); return; }
      var r = runs.shift(), line = el("p", "\u2026 " + (r.name || r.label), "st-dry");
      line.setAttribute("data-tool", r.tool); list.appendChild(line);
      callTool(r.tool, JSON.parse(JSON.stringify(r.arguments))).then(function (res) {
        var dd = answerOf(res), bad = isObj(dd) && readable(dd.error);
        line.textContent = (bad ? "\u2717 " : "\u2713 ") + (r.name || r.label) + (bad ? ": " + String(dd.error).slice(0, 90) : "");
        line.setAttribute("data-ok", bad ? "false" : "true");
        var sec = el("section", null, "st-dryout"); sec.setAttribute("data-tool", r.tool);
        sec.appendChild(el("p", r.label, "st-q")); sec.appendChild(stepAnswer(r.tool, res));
        more.insertBefore(sec, more.firstChild); details.hidden = false;
        one();
      }, function (e) {
        line.textContent = "\u2717 " + (r.name || r.label) + ": " + callProblem(e, r.tool, r.label);
        line.setAttribute("data-ok", "false");
        one();
      });
    }
    one();
  }
  // n227 (9): Check status: the same tool with `check` set, which reads how the create went and creates nothing.
  function statusRow(a, check, box) {
    var sa = JSON.parse(JSON.stringify(a.arguments)); delete sa.dry_run; sa.check = typeof check === "string" && check ? check : "name";
    var row = el("div", null, "st-act"), b = el("button", "Check status", "nx-b"), out = el("div", null, "out"); b.type = "button"; out.hidden = true;
    b.setAttribute("data-kind", "status");
    row.appendChild(b); row.appendChild(el("span", "Only reads: is " + a.arguments.name + " in Fabric now?", "muted")); row.appendChild(out);
    b.addEventListener("click", function () {
      runOrSay(a.tool, sa, "Is " + a.arguments.name + " in Fabric now? Only look, create nothing.", out, b, function (r) {
        out.appendChild(stepAnswer(a.tool, r));
        var d = answerOf(r);
        b.disabled = !(isObj(d) && isObj(d.started));
      }, { kind: "status", label: "Check status", name: a.arguments.name });
    });
    box.appendChild(row);
  }
  function listOf(items) { var ul = el("ul"); items.forEach(function (x) { if (readable(x)) ul.appendChild(el("li", x)); }); return ul; }
  function strings(x) { return Array.isArray(x) ? x.filter(readable) : []; }
  // the steps of the path, under Details: the finished ones fold into one line, the later ones too
  function drawPath(d, path) {
    var steps = (Array.isArray(d.path) ? d.path : []).filter(isObj);
    steps.forEach(function (p) {
      var li = el("li"); li.setAttribute("data-state", p.state); li.setAttribute("data-key", p.key);
      li.appendChild(el("span", p.n + ". " + p.title + (readable(p.note) ? " (" + p.note + ")" : "")));
      var does = el("span", p.does, "st-does"); does.setAttribute("data-does", p.does); li.appendChild(does);
      path.appendChild(li);
    });
  }
  function tiles(proof) {
    var ul = el("ul", null, "st-tiles"); ul.setAttribute("aria-label", "What the check proved");
    (Array.isArray(proof.tiles) ? proof.tiles : []).forEach(function (t) {
      if (!Array.isArray(t) || t.length < 2) return;
      var li = el("li"); li.appendChild(el("strong", t[0])); li.appendChild(el("span", t[1])); ul.appendChild(li);
    });
    return ul;
  }
  // steps 1-3: what the account can open, as buttons; one usable option comes chosen (WB15, A)
  function drawChoices(d, acts, box) {
    var picks = acts.filter(function (a) { return a.kind === "choose" && okButton(a, d); });
    if (!picks.length) return;
    var wrap = el("section", null, "st-acts st-pick"); wrap.setAttribute("aria-label", "Choose");
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
      var b = el("button", null, "nx-b" + (a.selected ? " st-picked" : "")); b.type = "button";
      b.setAttribute("data-kind", "choose"); b.setAttribute("data-name", a.label); b.setAttribute("data-start", "1");
      b.setAttribute("aria-pressed", a.selected ? "true" : "false");
      b.appendChild(el("span", (a.selected ? "✓ " : "") + a.label));
      var why = readable(a.disabled) ? a.disabled : (readable(a.hint) ? a.hint : "");
      if (why) b.appendChild(el("small", why));
      if (readable(a.disabled)) { b.disabled = true; b.title = a.disabled; }
      b.addEventListener("click", function () { startCall(a.arguments, askOf(a), out, b, { kind: "call", label: a.label }); });
      list.appendChild(b);
    });
    wrap.appendChild(list); wrap.appendChild(out); box.appendChild(wrap);
  }
  // each open link with its count and its own buttons; the reasons under Why
  function drawDecisions(d, f, box) {
    var acts = (Array.isArray(d.actions) ? d.actions : []).filter(function (a) { return a.kind === "decide" && okButton(a, d); });
    (Array.isArray(f.decisions) ? f.decisions : []).filter(isObj).forEach(function (x) {
      var card = el("div", null, "st-decision"); card.setAttribute("data-state", x.state || "open"); card.setAttribute("data-item", x.item || "");
      var q = readable(x.question) ? String(x.question) : "";
      card.appendChild(el("p", q.indexOf("? ") > 0 ? q.slice(0, q.indexOf("? ") + 1) : q, "st-q"));
      var ev = strings(x.evidence);
      if (readable(x.count)) { card.appendChild(el("p", x.count, "st-count")); }        // SM2: "5 of 6 found (83%)"
      else if (ev.length) { card.appendChild(el("p", ev[0], "st-count")); ev = ev.slice(1).concat([ev[0]]); }
      if (x.state && x.state !== "open") card.appendChild(el("p", "Your decision: " + (x.state === "skipped" ? "skipped for now" : x.state) + ".", "st-mine"));
      var row = el("div", null, "st-row");
      acts.filter(function (a) { return a.item === x.item && a.decision !== "skipped"; }).forEach(function (a) { button(a, d, row); });
      if (row.childNodes.length) card.appendChild(row);
      var why = ev.concat(q.indexOf("? ") > 0 ? [q.slice(q.indexOf("? ") + 2)] : []).filter(readable);
      if (why.length) { var w = el("details", null, "st-more"); w.appendChild(el("summary", "Why")); w.appendChild(listOf(why)); card.appendChild(w); }
      box.appendChild(card);
    });
  }
  var WHO_NAME = { onto: "Onto", thinker: "Thinker", builder: "Builder" };
  // WB15: the mascot at the top of the step, big, with one sentence, as the home page's demo chat
  function drawCoach(d) {
    var box = document.getElementById("coach"); box.textContent = "";
    var c = isObj(d.coach) ? d.coach : {};
    var who = WHO_NAME[d.who] ? d.who : (WHO_NAME[c.who] ? c.who : "onto");
    var line = readable(d.say) || readable(c.line) || "";
    if (!line) { box.hidden = true; return false; }
    var say = el("div", null, "kg-say st-big " + who), fig = el("span", null, "kg-fig");
    var src = document.querySelector('#kg-mascots [data-mascot="' + who + '"] svg');
    if (src) { var f = src.cloneNode(true); f.setAttribute("data-pose", "point"); fig.appendChild(f); }
    var bub = el("div", null, "kg-bub"); bub.appendChild(el("p", WHO_NAME[who], "kg-who")); bub.appendChild(el("p", line, "st-line"));
    say.appendChild(fig); say.appendChild(bub); box.appendChild(say); box.hidden = false;
    box.setAttribute("data-who", who);
    return true;
  }
  function render(result) {
    if (moved) return;
    var d = answerOf(result);
    if (isObj(d) && typeof d.seq === "number" && d.seq > 0) {
      if (d.seq < lastSeq) return;                            // WB15 (E): an older answer never undoes a newer tap
      lastSeq = d.seq;
    }
    var verdict = document.getElementById("verdict"), path = document.getElementById("path");
    var answer = document.getElementById("answer"), next = document.getElementById("next"), more = document.getElementById("more");
    var keepPics = document.getElementById("pictures"), detailsBox = document.getElementById("details");
    if (keepPics && more.contains(keepPics)) detailsBox.parentNode.insertBefore(keepPics, detailsBox);   // kept, not cleared
    answer.textContent = ""; next.textContent = ""; path.textContent = ""; more.textContent = ""; mascotsQuiet();
    document.documentElement.setAttribute("data-coach", "1");
    var honest = document.getElementById("honest"); honest.textContent = "";
    var details = document.getElementById("details"); details.open = false; details.hidden = true;
    verdict.hidden = false;
    if (!d) { verdict.textContent = "The card could not read the answer; it is in the text of the tool result."; return; }
    if (readable(d.error)) { document.getElementById("coach").hidden = true; verdict.textContent = d.error + (readable(d.hint) ? " " + d.hint : ""); return; }
    var st = isObj(d.step) ? d.step : {};
    myStep = Number(st.n) || 0;
    document.getElementById("title").textContent = (st.n ? "Step " + st.n + " of " + st.of + ": " + (readable(st.short) || st.title) : "Start Krusgraph")
      + (d.sample ? " (sample)" : "");
    var coached = drawCoach(d);
    verdict.textContent = readable(d.say) || readable(d.summary) || "";
    verdict.hidden = coached;                                 // said once: in the mascot's bubble
    var actions = (Array.isArray(d.actions) ? d.actions : []);
    drawChoices(d, actions, answer);
    var f = isObj(d.found) ? d.found : {}, key = String(st.key || "");
    var box = el("div", null, "res-box");
    // SM2: one line each (the data you chose; the map, the rows and the totals); the evidence is under Details
    if (readable(d.line)) box.appendChild(el("p", d.line, "st-chosen"));
    strings(d.lines).forEach(function (x) { box.appendChild(el("p", x, "st-dry")); });
    if (isObj(f.proof)) { more.appendChild(tiles(f.proof)); if (readable(f.proof.grain)) more.appendChild(el("p", f.proof.grain)); }
    if (Array.isArray(f.decisions)) drawDecisions(d, f, box);
    if (Array.isArray(f.doubled)) more.appendChild(listOf(f.doubled));
    if (Array.isArray(f.dry_runs)) more.appendChild(listOf(f.dry_runs.filter(isObj).map(function (x) { return x.name + ": " + x.line; })));
    if (Array.isArray(d.would_create) && d.would_create.length && d.needs_confirmation) {
      box.appendChild(listOf(d.would_create.filter(isObj).map(function (w) { return w.name; })));
    }
    if (readable(f.summary) && key === "map") box.appendChild(el("p", f.summary));
    if (box.childNodes.length) answer.appendChild(box);
    // everything else is under Details
    ["summary", "note"].forEach(function (k) { if (readable(f[k]) && !(k === "summary" && key === "map")) more.appendChild(el("p", f[k])); });
    if (Array.isArray(f.links)) more.appendChild(listOf(f.links));
    if (strings(f.data_products).length) { more.appendChild(el("p", "Data products", "muted")); more.appendChild(listOf(strings(f.data_products))); }   // DP2
    if (strings(f.rules).length) more.appendChild(el("p", strings(f.rules).join(". ") + ".", "muted"));
    strings(f.advice).forEach(function (x) { more.appendChild(el("p", x)); });
    var decided = strings(d.decided).length ? strings(d.decided) : strings(f.decided);
    if (decided.length) { more.appendChild(el("p", "Your decisions", "muted")); more.appendChild(listOf(decided)); }
    var wb = Array.isArray(d.would_build) ? d.would_build : (Array.isArray(f.would_build) ? f.would_build : null);
    if (wb) more.appendChild(listOf(wb.filter(isObj).map(function (w) { return w.name + ": " + w.what; })));
    var flow = Array.isArray(d.data_flow) ? d.data_flow : (Array.isArray(f.data_flow) ? f.data_flow : null);
    if (flow) { more.appendChild(el("p", "The data flow", "muted")); more.appendChild(listOf(flow)); }
    if (isObj(d.chosen)) {
      var shown = ["workspace", "source", "schema"].filter(function (k) { return readable(d.chosen[k]); }).map(function (k) { return k + ": " + d.chosen[k]; });
      if (shown.length) more.appendChild(el("p", "Chosen: " + shown.join(", "), "muted"));
    }
    if (readable(d.note)) more.appendChild(el("p", d.note, "muted"));
    var pics = document.getElementById("pictures");
    if (typeof drawPictures === "function") drawPictures({ map: d.map, map_mini: d.map_mini }, {});
    if (pics) {                                               // the map on its own step; elsewhere under Details
      if (key === "map") next.parentNode.insertBefore(pics, details); else more.appendChild(pics);
    }
    var acts = el("section", null, "st-acts"); acts.setAttribute("aria-label", "This step");
    actions.forEach(function (a) {
      if (a.kind === "choose" || a.kind === "decide" || !okButton(a, d)) return;
      if (a.more) button(a, d, more); else button(a, d, acts);
    });
    if (isObj(d.after) && !d.sample && okButton({ kind: "call", label: d.after.label, say: d.after.say, tool: d.after.tool, arguments: d.after.arguments }, d))
      button({ kind: "next", label: d.after.label, say: d.after.say, ask: d.after.ask, tool: "start", arguments: d.after.arguments,
               secondary: !!d.after.secondary, why: d.after.why,
               primary: !d.after.secondary && !actions.some(function (a) { return a.primary && !a.more; }) }, d, acts);
    // SM2: the reason a Next is secondary is its tooltip, not another line on the step
    if (isObj(d.next_waits) && readable(d.next_waits.label)) {            // WB12 (#77): no Next before the choice
      var w = el("div", null, "st-wait"), nb = el("button", d.next_waits.label, "nx-b st-secondary");
      nb.type = "button"; nb.disabled = true; nb.setAttribute("data-kind", "next-waits");
      w.appendChild(nb); if (readable(d.next_waits.why)) w.appendChild(el("span", d.next_waits.why, "muted")); acts.appendChild(w);
    }
    if (acts.childNodes.length) next.appendChild(acts);
    drawPath(d, path);
    if (readable(d.honest)) honest.textContent = d.honest;
    details.hidden = !(more.childNodes.length || path.childNodes.length || honest.textContent);
    if (chan && lastSeq) { try { chan.postMessage({ id: CARD_ID, seq: lastSeq, n: myStep }); } catch (e) {} }
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
