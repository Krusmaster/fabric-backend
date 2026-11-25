"""MCP Apps, the diff card (round LFD8, 25 November 2026): propose_change's answer as one card (docs/CHANGES.md, "The diff
card (LFD8)").

Behind two settings: the card exists only when KRUSGRAPH_MCP_APPS=1 (every card's flag, mcp_apps.enabled) and
KRUSGRAPH_CHANGES=1 (tool_listing.changes_on: propose_change itself is registered only then). With either off nothing
here reaches the server: no resource, no `_meta`, and the listings are what they were. It follows mcp_apps.py and the
specification read there (modelcontextprotocol/ext-apps, specification/2026-01-26/apps.mdx): a `ui://` resource served
as `text/html;profile=mcp-app` through the SDK's Apps extension, `_meta.ui.resourceUri` on the tool, no `_meta.ui.csp`
(nothing is loaded: no script, style, font or image from anywhere), JSON-RPC 2.0 over postMessage.

What the card shows, all of it from the answer (change_diff.propose) and `change_card`, which extras() adds to the
structuredContent (never to the text every client gets):

- ok: one sentence that says what the change does, and three folds, closed: Plan (keys, links, filters, columns and
  measures added or taken out), Items (each item "update in place" with its summary and its unified diff behind a
  second fold, or "unchanged") and Numbers (before → after with the difference; "not counted yet" when the layer is not
  counted). Then Yes, the only primary button, which asks the host to call apply_change with the propose call's
  arguments and the answer's confirm token; No, which calls nothing and folds the card to "Nothing changed"; and Undo,
  when the list holds earlier changes, which proposes a `revert` of the last one (a new proposal, nothing applied).
- question: a short question per kind (the contract's full question in a closed fold) and one button per candidate,
  each a new propose_change with the candidate filled in. A question chooses nothing, so no choice is primary.
- denied: the reason (its first sentence; the whole reason in a closed fold) and a hand-back to Start.
- replan: the earlier changes need a link the plan does not hold; one button proposes again with it confirmed.

Rules the card keeps (tests/test_lfd8_card.py and tests/lfd8_card_click.js, measured with
`python tools/smooth_measure.py --change`):

- a button only for a tool the listing holds (tool_listing.listed); Yes only when apply_change is also registered on
  this server (round LFD6 adds it); otherwise Yes is shown disabled with a short reason, and nothing is called;
- Yes only with the confirm token of the answer on screen; No, Undo and the choices never write;
- Undo only when changes.py knows the type `revert` (round LFD7 builds on it);
- at most 25 words outside the buttons in every state, one primary button at most (exactly one on an ok answer), no
  state without a way on, nothing wider than 390 px, light and dark from the host's tokens with light-dark() fallbacks.
"""
from __future__ import annotations

import json
import sys

from . import mcp_apps
from .mcp_apps_size import SIZE_JS

CARD_URI = "ui://krusgraph/change-card.html"
TOOL = "propose_change"
TOOLS = (TOOL,)
APPLY = "apply_change"                     # round LFD6's tool; the card never assumes it exists
REVERT = "revert"                          # changes.TYPES; round LFD7's versions build on it
CARRIED = ("workspace", "source", "schema", "applied", "confirmed")
MAX_WORDS = 25                             # SMOOTH: words a person reads outside the buttons, every state
SENTENCE_WORDS = 15
MAX_ROWS = 12                              # numbers shown in the fold; the rest are counted
NOT_COUNTED = "not counted yet"
NOT_READY = "Yes is not available yet."           # Yes, while apply_change is not registered


def enabled(environ=None) -> bool:
    """The card's two settings: KRUSGRAPH_MCP_APPS=1 and KRUSGRAPH_CHANGES=1."""
    from . import tool_listing
    return mcp_apps.enabled(environ) and tool_listing.changes_on(environ)


def tool_meta(on: bool | None = None) -> dict | None:
    """propose_change's `_meta` when the card is on, else None (no `_meta` at all)."""
    if not (enabled() if on is None else on):
        return None
    return {"ui": {"resourceUri": CARD_URI}, "ui/resourceUri": CARD_URI}


def add_to(apps) -> None:
    """Registers the card on the Apps extension mcp_apps.extensions() builds, only when KRUSGRAPH_CHANGES is on."""
    from . import tool_listing
    if not tool_listing.changes_on():
        return
    apps.add_html_resource(CARD_URI, card_html(), name="change_card", title="Proposed change",
                           description="propose_change's answer as a card: what the change does, its plan, items and "
                                       "numbers in folds, and Yes or No.", prefers_border=True)


# ------------------------------------------------------------------ what the card is told -----------------------------

def apply_tool() -> dict | None:
    """apply_change when the listing holds it and this server registered it: {"properties": its argument names or None}.
    None otherwise: the card then shows Yes disabled and calls nothing."""
    from . import tool_listing
    if not tool_listing.listed(APPLY):
        return None
    srv = sys.modules.get("fabric_backend.server")
    if srv is None or not callable(getattr(srv, APPLY, None)):
        return None
    try:
        props = set((srv.mcp._tool_manager.get_tool(APPLY).parameters or {}).get("properties") or {})
    except Exception:                                        # noqa: BLE001 - the SDK's inside; carry every argument then
        props = None
    return {"properties": props or None}


def revert_known() -> bool:
    from . import changes
    return REVERT in changes.TYPES


def _words(text: str) -> int:
    return len(str(text or "").split())


def _cut(text: str, n: int) -> str:
    w = str(text or "").split()
    return " ".join(w) if len(w) <= n else " ".join(w[:n]).rstrip(",;:") + "…"


def _cols(c: dict) -> str:
    return "+".join(c.get("columns") or [])


def _link(x: dict) -> str:
    if "from" in x and isinstance(x["from"], dict):
        return f"{x['from']['table']}.{_cols(x['from'])} → {x['to']['table']}"
    return f"{x.get('source')}.{'+'.join(x.get('source_cols') or [])} → {x.get('target')}"


def sentence(answer: dict) -> str:
    """One sentence that says what the change does (ok), what is asked (question), why not (denied) or what is missing
    (replan). Fixed words around the answer's own names; never more than SENTENCE_WORDS words, except a denial's reason,
    which is cut at MAX_WORDS - 2."""
    r = answer.get("result")
    if r == "denied":
        reason = str(answer.get("reason") or "no reason given").strip()
        first = reason.split(". ")[0].rstrip(".")
        if _words(first) > MAX_WORDS - 8:                    # the clause before a colon, a semicolon or a bracket
            import re
            head = re.split(r":\s|;\s|\s\(", first)[0]
            first = head if _words(head) >= 3 else first
        said = _cut(first, MAX_WORDS - 8)
        return "Not allowed: " + said + ("" if said.endswith("…") else ".")
    if r == "replan":
        return "The earlier changes need a link the plan does not hold yet."
    if r == "question":
        return question_line(answer)
    c = answer.get("change") or {}
    t = c.get("type")
    if t == "filter_rows":
        from . import changes
        try:
            where = changes.said(c["drop_where"])
        except (KeyError, TypeError):
            where = "a condition holds"
        if _words(where) > 6:
            where = "the condition holds"
        n = len(c.get("cascade") or [])
        s = f"Removes {c.get('table')} rows where {where}" + (f", and their rows in {n} tables" if n > 1 else
                                                               f", and their rows in {c['cascade'][0]}" if n else "") + "."
    elif t == "add_column":
        s = f"Adds {', '.join(c.get('columns') or [])} from {c.get('from')} to {c.get('table')}."
    elif t == "add_link":
        s = f"Links {_link(c)}."
    elif t == "add_measure":
        s = f"Adds the measure {c.get('name')}."
    elif t == REVERT:
        plan = (answer.get("diff") or {}).get("plan") or {}
        gone = [(k, x) for k in ("filters_removed", "columns_removed", "measures_removed") for x in plan.get(k) or []]
        if gone and gone[0][0] == "filters_removed":
            s = f"Takes out the filter on {gone[0][1].get('table')}."
        elif gone and gone[0][0] == "columns_removed":
            s = f"Takes out {', '.join(gone[0][1].get('columns') or [])} on {gone[0][1].get('table')}."
        elif gone:
            s = f"Takes out the measure {gone[0][1].get('name')}."
        else:
            s = "Takes out an earlier change."
    else:
        s = "Changes the data product."
    return _cut(s, SENTENCE_WORDS)


def question_line(answer: dict) -> str:
    """The question in a few words, per kind; the contract's own question goes in a closed fold."""
    kind, cands = answer.get("kind"), answer.get("candidates") or []
    ch = answer.get("asked_change") or {}
    table = ch.get("table") or "the table"
    if kind == "filter_column":
        return f"Which column marks the {table} rows to remove?" if cands else f"Which column marks the {table} rows?"
    if kind == "cascade":
        return f"{len(cands)} tables point at {table}. Remove their rows too?"
    if kind == "path":
        return f"Which path should {', '.join(ch.get('columns') or ['the columns'])} come over?"
    if kind == "link":
        return f"Which column links {table} to {ch.get('from') or 'the other table'}?"
    if kind == "link_direction":
        return "Should the link point the other way?"
    return _cut(str(answer.get("question") or "Which one?"), SENTENCE_WORDS)


def _carried(call: dict) -> dict:
    return {k: call[k] for k in CARRIED if call.get(k) is not None}


def _asked(answer: dict, call: dict) -> tuple[dict | None, int | None]:
    """The change a question or denial is about: the new one (at == len(applied)) or an earlier entry of `applied`."""
    applied = list(call.get("applied") or [])
    at = answer.get("at")
    if not isinstance(at, int) or at >= len(applied):
        return (call.get("change") if isinstance(call.get("change"), dict) else None), None
    entry = applied[at]
    entry = entry.get("change", entry) if isinstance(entry, dict) and entry.get("result") == "ok" else entry
    return (entry if isinstance(entry, dict) else None), at


def _propose(call: dict, change: dict, at: int | None = None, **over) -> dict:
    """The arguments of a new propose_change: the call's own, with the change (or the earlier entry `at`) replaced."""
    args = {**_carried(call), "change": call.get("change")}
    if at is None:
        args["change"] = change
    else:
        applied = list(call.get("applied") or [])
        applied[at] = change
        args["applied"] = applied
    args.update({k: v for k, v in over.items() if v is not None})
    return {k: v for k, v in args.items() if v is not None}


def choices(answer: dict, call: dict) -> list[dict]:
    """A question's candidates as buttons, each a new propose_change with the candidate filled in. None is primary."""
    asked, at = _asked(answer, call)
    if asked is None:
        return []
    kind, out = answer.get("kind"), []
    for c in answer.get("candidates") or []:
        if not isinstance(c, dict):
            continue
        if kind == "filter_column" and isinstance(c.get("drop_where"), dict):
            out.append({"label": c.get("column") or "this column", "change": {**asked, "drop_where": c["drop_where"]}})
        elif kind == "path" and isinstance(c.get("via"), list):
            out.append({"label": " → ".join(c.get("tables") or []) or "this path", "change": {**asked, "via": c["via"]}})
        elif kind in ("link", "link_direction") and isinstance(c.get("change"), dict):
            out.append({"label": _link(c["change"]), "change": c["change"]})
    if kind == "cascade":
        tables = [c["table"] for c in answer.get("candidates") or [] if isinstance(c, dict) and c.get("table")]
        out = [{"label": f"Yes, from all {len(tables)}", "change": {**asked, "cascade": tables}},
               {"label": "No, keep their rows", "change": {**asked, "cascade": []}}]
    return [{"label": x["label"], "tool": TOOL, "arguments": _propose(call, x["change"], at),
             "ask": f"Propose the change again with this answer: {x['label']}."} for x in out]


def plan_lines(plan: dict) -> list[str]:
    out = []
    for x in plan.get("links_added") or []:
        out.append(f"Link added: {_link(x)}")
    for x in plan.get("links_removed") or []:
        out.append(f"Link taken out: {_link(x)}")
    for x in plan.get("keys_changed") or []:
        out.append(f"Key changed: {x.get('table', x) if isinstance(x, dict) else x}")
    for k, verb in (("added", "added"), ("removed", "taken out")):
        for x in plan.get(f"filters_{k}") or []:
            cas = x.get("cascade") or []
            out.append(f"Filter {verb}: {x.get('table')} where {x.get('drop_where')}" + (f" (and {', '.join(cas)})" if cas else ""))
        for x in plan.get(f"columns_{k}") or []:
            out.append(f"Column {verb}: {', '.join(x.get('columns') or [])} from {x.get('from')} on {x.get('table')}")
        for x in plan.get(f"measures_{k}") or []:
            out.append(f"Measure {verb}: {x.get('name')}")
    return out or ["The plan is the same."]


def _label(n: dict) -> str:
    what = n.get("what")
    if what == "rows":
        return f"{n.get('table')} rows"
    if what == "distinct":
        return f"{n.get('table')}.{n.get('column')} distinct"
    if what in ("sum", "measure"):
        return str(n.get("name") or n.get("item"))
    if what == "missing":
        return f"{n.get('column')} without a value"
    return str(n.get("what") or n.get("item") or "number").replace("_", " ")


def _difference(before, after, given=None) -> str:
    if given is not None:
        g = str(given)
        return g if g.startswith(("-", "+")) or g in ("0", "0.00") else "+" + g
    try:
        d = float(after) - float(before)
    except (TypeError, ValueError):
        return ""
    if d == int(d):
        return f"{int(d):+d}"
    return f"{d:+.2f}"


def number_rows(layer: dict, change_id: str | None = None) -> dict:
    """The numbers layer for the fold: {"status", "rows": [{label, before, after, difference}], "more"}. A number that
    was not counted says "not counted yet" instead of a value. Reads change_numbers.count's shape (the new change's
    numbers), a {"before": {...}, "after": {...}} map, or any list of numbers with before and after."""
    layer = layer if isinstance(layer, dict) else {}
    if layer.get("status") != "counted":
        return {"status": NOT_COUNTED, "rows": []}
    counted = layer.get("counted")
    rows: list[dict] = []

    def add(label, before, after, diff=None, counted_=True):
        if not counted_ or before is None and after is None:
            rows.append({"label": label, "before": NOT_COUNTED, "after": "", "difference": ""})
        else:
            rows.append({"label": label, "before": "" if before is None else str(before),
                         "after": "" if after is None else str(after), "difference": _difference(before, after, diff)})

    def walk(x):
        if isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, dict):
            if isinstance(x.get("before"), dict) and isinstance(x.get("after"), dict):
                for k, v in x["before"].items():
                    if k in x["after"]:
                        add(str(k), v, x["after"][k])
                return
            if "what" in x and ("before" in x or "value" in x or "state" in x):
                ok = x.get("state", "counted") == "counted"
                if x.get("what") == "measure":
                    add(_label(x), x.get("on_source", x.get("value")), x.get("value"), None, ok)
                else:
                    add(_label(x), x.get("before"), x.get("after"), x.get("difference"), ok)
                return
            for k, v in x.items():
                if k not in ("receipt", "statements", "plan", "said", "doubling"):
                    walk(v)

    if isinstance(counted, dict) and isinstance(counted.get("changes"), list):
        mine = [c for c in counted["changes"] if isinstance(c, dict) and c.get("id") == change_id]
        walk([c.get("numbers") for c in (mine or counted["changes"]) if isinstance(c, dict)])
    else:
        walk(counted)
    return {"status": "counted", "rows": rows[:MAX_ROWS], "more": max(0, len(rows) - MAX_ROWS)}


def card(answer: dict, call: dict) -> dict:
    """What the card draws besides the answer itself: the sentence, the folds' plan lines and numbers, and the buttons
    (Yes, No, Undo, the choices, the hand-back) with the arguments each sends."""
    from . import tool_listing
    call = {k: v for k, v in (call or {}).items() if k != "ctx"}
    r = answer.get("result")
    asked, _ = _asked(answer, call)
    shown = {**answer, "asked_change": asked} if r == "question" else answer
    out: dict = {"result": r, "sentence": sentence(shown), "back": tool_listing.hand_back(TOOL, call, answer)}
    listed = tool_listing.listed(TOOL)
    if r == "ok":
        d = answer.get("diff") or {}
        out["plan"] = plan_lines(d.get("plan") or {})
        out["numbers"] = number_rows(d.get("numbers") or {}, answer.get("id"))
        tool = apply_tool()
        confirm = answer.get("confirm")
        if tool is not None and isinstance(confirm, str) and confirm:
            args = {**_carried(call), "change": call.get("change"), "confirm": confirm}
            if tool["properties"]:
                args = {k: v for k, v in args.items() if k in tool["properties"] or k == "confirm"}
            out["yes"] = {"tool": APPLY, "arguments": {k: v for k, v in args.items() if v is not None},
                          "ask": "Yes, apply this change."}
        else:
            out["yes"] = {"disabled": NOT_READY}
        earlier = [i for i in answer.get("changes") or [] if i != answer.get("id")]
        c = answer.get("change") or {}
        if earlier and listed and revert_known() and c.get("type") != REVERT:
            out["undo"] = {"tool": TOOL, "arguments": {**_carried(call), "change": {"type": REVERT, "change": earlier[-1]}},
                           "ask": "Propose undoing the last applied change."}
    elif r == "question":
        out["question"] = str(answer.get("question") or "")
        out["choices"] = choices(answer, call) if listed else []
    elif r == "replan":
        links = list(call.get("confirmed") or []) + [x for x in answer.get("confirmed") or []
                                                     if x not in (call.get("confirmed") or [])]
        out["choices"] = [{"label": "Plan again with the link", "tool": TOOL, "primary": True,
                           "ask": "Propose the change again with the link the earlier changes need.",
                           "arguments": {**_carried(call), "change": call.get("change"), "confirmed": links}}] if listed else []
    elif r == "denied":
        out["why"] = str(answer.get("reason") or "")
    return out


def extras(answer: dict, call: dict) -> dict:
    """structuredContent's `change_card` for one propose_change answer; nothing for an error answer."""
    if not isinstance(answer, dict) or answer.get("error") or answer.get("result") not in ("ok", "question", "denied", "replan"):
        return {}
    return {"change_card": card(answer, call)}


def result(text: str, call: dict):
    """The CallToolResult the hosted server returns with the card on: the text unchanged, the answer and change_card
    as structuredContent (mcp_apps.call_result)."""
    try:
        answer = json.loads(text)
    except (TypeError, ValueError):
        return mcp_apps.call_result(text)
    return mcp_apps.call_result(text, extras(answer, call) or None)


# ------------------------------------------------------------------ the card -------------------------------------------

def card_html() -> str:
    """One self-contained HTML5 document: no src, href, url(), @import, fetch or other load; the data arrives only from
    the host."""
    allowed = json.dumps([TOOL, APPLY])
    return (_HTML.replace("__READ_JS__", mcp_apps.READ_JS + mcp_apps.CALL_JS).replace("__SIZE_JS__", SIZE_JS)
            .replace("__ALLOWED__", allowed).replace("__PROTOCOL__", mcp_apps.PROTOCOL_VERSION)
            .replace("__NOT_COUNTED__", json.dumps(NOT_COUNTED)))


_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Proposed change</title>
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
  --kg-font: var(--font-sans, system-ui, -apple-system, "Segoe UI", sans-serif);
  --kg-mono: var(--font-mono, ui-monospace, "SFMono-Regular", Consolas, monospace);
}
* { box-sizing: border-box }
[hidden] { display: none !important }
html, body { margin: 0; background: var(--kg-bg); color: var(--kg-ink); font: 15px/1.45 var(--kg-font) }
main { padding: 14px 16px; display: grid; gap: 10px; max-width: 100%; min-width: 0 }
p { margin: 0 }
.ch-line { font-size: 16px; font-weight: 650; overflow-wrap: anywhere }
.muted { color: var(--kg-muted); font-size: 13.5px }
ul { margin: 0; padding-left: 18px }
li { overflow-wrap: anywhere }
details { border: 1px solid var(--kg-line); border-radius: 12px; padding: 6px 10px; min-width: 0 }
details > summary { cursor: pointer; font-weight: 650; min-height: 28px; line-height: 28px }
details details { border: 0; padding: 0 }
details details > summary { font-weight: 500; color: var(--kg-muted); font-size: 13.5px; min-height: 24px; line-height: 24px }
.ch-items { list-style: none; padding: 0; display: grid; gap: 8px; margin-top: 4px }
.ch-item { display: grid; gap: 2px; min-width: 0 }
.ch-tag { font-size: 12px; border: 1px solid var(--kg-line); border-radius: 999px; padding: 0 7px; white-space: nowrap; margin-left: 6px }
.ch-tag[data-status="update in place"] { color: var(--kg-warn); border-color: currentColor }
.ch-tag[data-status="unchanged"] { color: var(--kg-muted) }
pre.ch-diff { margin: 4px 0 0; white-space: pre; overflow: auto; max-height: 300px; max-width: 100%; font: 12px/1.4 var(--kg-mono);
  background: var(--kg-card); border-radius: 8px; padding: 6px 8px }
.ch-add { color: var(--kg-ok) } .ch-del { color: var(--kg-warn) }
table.ch-num { border-collapse: collapse; width: 100%; font-size: 13.5px; margin-top: 4px }
table.ch-num td { padding: 3px 4px; border-top: 1px solid var(--kg-line); overflow-wrap: break-word; word-break: normal; vertical-align: top }
table.ch-num td.n { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums }
table.ch-num td.n small { display: block; color: var(--kg-muted); font-size: 12.5px }
.ch-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center }
button { font: inherit; font-weight: 650; color: var(--kg-ink); background: var(--kg-card); border: 1px solid var(--kg-line);
  border-radius: 999px; padding: 4px 14px; cursor: pointer; min-height: 36px; max-width: 100%; overflow-wrap: anywhere }
button.ch-primary { background: var(--kg-ink); color: var(--kg-bg); border-color: var(--kg-ink) }
button.ch-quiet { background: transparent; font-weight: 500; color: var(--kg-muted) }
button:disabled { cursor: default; opacity: .55 }
.ch-why { font-size: 13px; color: var(--kg-muted) }
.ch-out { border-left: 3px solid var(--kg-line); padding-left: 8px; font-size: 13.5px; overflow-wrap: anywhere }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important } }
</style>
</head>
<body>
<main id="main" aria-live="polite">
  <p class="ch-line" id="line" role="status">Waiting for the proposal.</p>
  <div id="body"></div>
  <div class="ch-row" id="buttons"></div>
  <p class="ch-out" id="out" hidden></p>
</main>
<script>
(function () {
  "use strict";
  var ALLOWED = __ALLOWED__, NOT_COUNTED = __NOT_COUNTED__;
  var nextId = 1, pending = {}, busy = false, shown = null;
  function send(msg) { window.parent.postMessage(msg, "*"); }
  function request(method, params) {
    var id = nextId++;
    send({ jsonrpc: "2.0", id: id, method: method, params: params });
    return new Promise(function (resolve, reject) { pending[id] = { resolve: resolve, reject: reject }; });
  }
  function notify(method, params) { send({ jsonrpc: "2.0", method: method, params: params || {} }); }
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = String(text); if (cls) e.className = cls; return e; }
__READ_JS__
  function $(id) { return document.getElementById(id); }
  function fold(title, fill) {
    var d = el("details"); d.appendChild(el("summary", title)); fill(d); return d;
  }
  function sendChat(text) {
    return request("ui/message", { role: "user", content: [{ type: "text", text: text }] }).catch(function (e) {
      if (isObj(e) && e.code === -32602) return request("ui/message", { role: "user", content: { type: "text", text: text } });
      throw e;
    });
  }
  function setBusy(on) {
    busy = on; document.documentElement.setAttribute("data-busy", on ? "1" : "0");
    Array.prototype.forEach.call(document.querySelectorAll("#buttons button"), function (b) {
      if (on) { b.setAttribute("data-was", b.disabled ? "1" : "0"); b.disabled = true; }
      else { b.disabled = b.getAttribute("data-was") === "1"; }
    });
  }
  function say(text) { var o = $("out"); o.textContent = text; o.hidden = !text; }
  // A button for a step: a tools/call to an allowed tool through the host, or the step's words in the chat.
  function button(label, kind, opts) {
    var b = el("button", label, opts.primary ? "ch-primary" : (opts.quiet ? "ch-quiet" : ""));
    b.type = "button"; b.setAttribute("data-kind", kind);
    if (opts.primary) b.setAttribute("data-primary", "true");
    if (opts.disabled) { b.disabled = true; b.title = opts.disabled; }
    b.addEventListener("click", function () { if (!busy && !b.disabled) opts.run(b); });
    $("buttons").appendChild(b);
    return b;
  }
  function run(step, then) {
    if (!isObj(step) || ALLOWED.indexOf(step.tool) < 0 || !isObj(step.arguments)) return;
    setBusy(true); say("");
    callTool(step.tool, step.arguments, function () { say("Still working. If the host asks you to allow it, answer there."); })
      .then(function (r) { setBusy(false); then(r); }, function (e) {
        setBusy(false);
        if (e && e.kind === "unsupported" && step.ask) { sendChat(step.ask).then(function () { moved(step.ask); }, function () { say(callProblem(e, step.tool, step.ask)); }); return; }
        say(callProblem(e, step.tool, step.ask || step.label || ""));
      });
  }
  function moved(text) { $("body").textContent = ""; $("buttons").textContent = ""; $("line").textContent = "Sent to the chat."; say(""); backButton(); }
  function backButton() {
    var back = shown && isObj(shown.card) ? shown.card.back : null;
    if (!isObj(back)) return;
    button(back.label || "Back to Start", "back", { quiet: false, run: function () {
      sendChat(back.ask || back.say).then(function () { say("Sent to the chat."); }, function () { say("Ask in the chat: “" + (back.ask || back.say) + "”"); });
    } });
  }
  function itemsFold(d, items) {
    var ul = el("ul", null, "ch-items");
    items.forEach(function (x) {
      if (!isObj(x)) return;
      var li = el("li", null, "ch-item"), head = el("div");
      head.appendChild(el("span", x.label || x.item)); var tag = el("span", x.status, "ch-tag"); tag.setAttribute("data-status", x.status);
      head.appendChild(tag); li.appendChild(head);
      if (x.summary) li.appendChild(el("span", x.summary, "muted"));
      if (x.reason) li.appendChild(el("span", x.reason, "muted"));
      if (typeof x.diff === "string" && x.diff) {
        li.appendChild(fold("Show the diff", function (dd) {
          var pre = el("pre", null, "ch-diff");
          x.diff.split("\n").forEach(function (line, i) {
            var cls = /^\+(?!\+\+)/.test(line) ? "ch-add" : (/^-(?!--)/.test(line) ? "ch-del" : "");
            pre.appendChild(el("span", line + "\n", cls));
          });
          dd.appendChild(pre);
        }));
      } else if (x.diff_omitted) li.appendChild(el("span", x.diff_omitted, "muted"));
      ul.appendChild(li);
    });
    d.appendChild(ul);
  }
  function numbersFold(d, n) {
    if (!isObj(n) || n.status !== "counted" || !Array.isArray(n.rows) || !n.rows.length) { d.appendChild(el("p", "The numbers are " + NOT_COUNTED + ".", "muted")); return; }
    var t = el("table", null, "ch-num");
    n.rows.forEach(function (r) {
      var tr = el("tr");
      tr.appendChild(el("td", r.label));
      var v = el("td", r.before === NOT_COUNTED ? NOT_COUNTED : r.before + " → " + r.after, "n");
      if (r.before !== NOT_COUNTED && r.difference) v.appendChild(el("small", "(" + r.difference + ")"));
      tr.appendChild(v);
      t.appendChild(tr);
    });
    d.appendChild(t);
    if (n.more) d.appendChild(el("p", n.more + " more in the answer.", "muted"));
  }
  function render(result) {
    var d = answerOf(result);
    $("body").textContent = ""; $("buttons").textContent = ""; say("");
    if (!isObj(d) || !isObj(d.change_card)) {
      $("line").textContent = isObj(d) && readable(d.error) ? d.error : "The answer is in the chat.";
      return;
    }
    var c = d.change_card; shown = { answer: d, card: c };
    document.documentElement.setAttribute("data-result", c.result || "");
    $("line").textContent = c.sentence || "";
    var body = $("body");
    if (c.result === "ok") {
      var diff = isObj(d.diff) ? d.diff : {};
      body.appendChild(fold("Plan", function (f) { var ul = el("ul"); (c.plan || []).forEach(function (s) { ul.appendChild(el("li", s)); }); f.appendChild(ul); }));
      body.appendChild(fold("Items", function (f) { itemsFold(f, Array.isArray(diff.items) ? diff.items : []); }));
      body.appendChild(fold("Numbers", function (f) { numbersFold(f, c.numbers); }));
      var yes = isObj(c.yes) ? c.yes : { disabled: "Not available yet." };
      var ok = yes.tool === "apply_change" && isObj(yes.arguments) && typeof d.confirm === "string" && yes.arguments.confirm === d.confirm;
      button("Yes", "yes", { primary: true, disabled: ok ? "" : (yes.disabled || "Not available yet."), run: function () {
        run(yes, function (r) {
          var a = answerOf(r);
          $("body").textContent = ""; $("buttons").textContent = "";
          $("line").textContent = isObj(a) && readable(a.error) ? "Not applied: " + a.error : "Applied.";
          var s = isObj(a) && readable(a.summary) ? a.summary : (isObj(a) ? "" : resultText(r));
          say(String(s || "").slice(0, 300)); backButton();
        });
      } });
      if (!ok) body.appendChild(el("p", yes.disabled || "Not available yet.", "ch-why")).setAttribute("data-why", "yes");
      button("No", "no", { run: function () {
        $("body").textContent = ""; $("buttons").textContent = ""; $("line").textContent = "Nothing changed."; say(""); backButton();
      } });
      if (isObj(c.undo)) button("Undo the last change", "undo", { quiet: true, run: function () { run(c.undo, render); } });
    } else if (c.result === "question" || c.result === "replan") {
      if (c.question) body.appendChild(fold("Details", function (f) { f.appendChild(el("p", c.question, "muted")); }));
      (c.choices || []).forEach(function (s) { button(s.label, "choice", { primary: s.primary === true, run: function () { run(s, render); } }); });
      if (!(c.choices || []).length) backButton();
    } else {
      if (c.why && c.why !== c.sentence) body.appendChild(fold("Why", function (f) { f.appendChild(el("p", c.why, "muted")); }));
      backButton();
    }
    if (!body.childNodes.length) body.hidden = true; else body.hidden = false;
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
    if (m.method === "ui/notifications/tool-result") render(m.params);
    else if (m.method === "ui/notifications/tool-cancelled") $("line").textContent = "The proposal was cancelled.";
    else if (m.method === "ui/resource-teardown" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
    else if (m.method === "ping" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
  });
__SIZE_JS__
  request("ui/initialize", {
    appInfo: { name: "Krusgraph proposed change", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function (r) { hostStarted(r); notify("ui/notifications/initialized"); watchSize(); },
          function () { $("line").textContent = "The host did not start the card; the answer is in the chat."; });
})();
</script>
</body>
</html>
"""
