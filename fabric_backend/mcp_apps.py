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
from . import mcp_apps_result as _result
from .evidence import NEXT_STEP_TOOLS

FLAG = "KRUSGRAPH_MCP_APPS"
CARD_URI = "ui://krusgraph/validate-plan-card.html"
APP_MIME_TYPE = "text/html;profile=mcp-app"           # the specification's MIME type; mcp.server.apps.APP_MIME_TYPE
PROTOCOL_VERSION = "2026-01-26"
TOOL = "validate_plan"
# n137: the tools whose answer is also returned as structuredContent; n169: and the build card's (mcp_apps_build.CARD_TOOLS)
STRUCTURED = ("validate_plan", "review_plan", "plan_backend", "create_semantic_model", "create_ontology", "create_backend",
              "create_report", "ontology_draft", "domain_draft",          # n170: and the two drafts with a picture
              "dbt_schema",                                                # n177: the dbt project's flow
              "start",                                                     # n219: Start Krusgraph's stepper card
              "requirements_draft")                                        # RQ1: the requirements on the build card

# The arguments a next step carries over from the validate_plan call, per tool: workspace, source and schema always;
# keys and confirmed only where the tool takes them. tests/test_n119_mcp_apps.py checks each against the tool's
# inputSchema in the hosted listing.
# n227: a next step's button says what it does, never the tool's name.
STEP_LABEL = {"sample_rows": "Show a few rows", "review_plan": "Review keys and links", "answer_query_draft": "Draft a query",
              "validate_plan": "Check against the rows", "suggest_relationships": "Suggest missing links",
              "semantic_model_draft": "Draft a semantic model", "ontology_draft": "Draft an ontology",
              "plan_backend": "Plan again", "list_tables": "List the tables"}
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


def call_result(text: str, extra: dict | None = None, lead: str | None = None, coach_text: str | None = None):
    """n137: a tool's text answer as a CallToolResult: the same text content every client gets, plus the answer as
    `structuredContent` when the text is a JSON object (an answer that is not one has no structuredContent). n170:
    `extra` (the pictures' data, mcp_apps_pictures.extras) goes into structuredContent only; the text is unchanged."""
    from mcp.types import CallToolResult, TextContent

    from . import directory                                  # DIR1: every text a host receives describes, never instructs
    text = directory.neutral(text) if not text.lstrip().startswith("{") else text
    extra = directory.neutral_value(extra) if extra else extra
    lead = directory.neutral(lead) if lead else lead
    coach_text = directory.neutral(coach_text) if coach_text else coach_text
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        data = None
    if isinstance(data, dict) and extra:
        data = {**data, **{k: v for k, v in extra.items() if k not in data}}
    content = [TextContent(type="text", text=text)]
    if lead and coach_text:                                  # CO1: the Coach block ends the lead; the JSON stays last
        tail = "The full answer follows as JSON."
        lead = (lead[:-len(tail)] + coach_text + "\n\n" + tail) if lead.endswith(tail) else lead + "\n\n" + coach_text
    elif coach_text:
        lead = coach_text
    if lead:                                                 # n218: the result and the next steps first, the JSON after
        content.insert(0, TextContent(type="text", text=lead))
    return CallToolResult(content=content, structured_content=data if isinstance(data, dict) else None)


LATEST_LEAD = ("Start Krusgraph: the card's own check whether a newer card has moved the path on. Nothing was recorded, "
               "and there is nothing to tell the user.")


def structured(fn, name: str | None = None):
    """n137: the registered form of a tool in STRUCTURED when the flag is on: the tool's own function, its answer
    wrapped by call_result. The module's function stays the one that returns text. n170: for a tool with a picture
    (mcp_apps_pictures.PICTURE_TOOLS) a stash is open while it runs, and what the tool kept there is drawn on the card."""
    from . import mcp_apps_pictures as pictures
    name = name or fn.__name__

    from . import mcp_apps_words as words                     # n172: the card's words, in plain English

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = pictures.begin()
        try:
            out = fn(*args, **kwargs)
        finally:
            stash = pictures.end(token)
        if not isinstance(out, str):
            return out
        from . import directory                                      # DIR1: options, not instructions; bounded in size
        out = directory.bounded(out)
        extra = {}
        try:
            answer = json.loads(out)
        except ValueError:
            return call_result(out)
        if name == "start" and isinstance(answer, dict) and "latest" in answer and "step" not in answer:
            # BL47 (#104): the card's own read-only "still the latest?" check: no coach, no step, no next steps
            return call_result(out, None, LATEST_LEAD)
        if name in pictures.PICTURE_TOOLS:
            try:
                extra.update(pictures.extras(name, answer, stash))
            except Exception:                                        # noqa: BLE001 - the answer stands without a picture
                pass
        if name == "dbt_schema" and isinstance(answer, dict) and isinstance(answer.get("files"), dict):
            try:                                                     # n177: the project's flow; the code stays in files
                from . import dbt_flow
                f = dbt_flow.flow(answer["files"])
                if f:
                    extra["dbt_flow"] = f
            except Exception:                                        # noqa: BLE001 - the answer stands without it
                pass
        call = {}
        try:                                                         # n227: the call's own arguments, for the card's words
            import inspect as _inspect
            call = {k: v for k, v in _inspect.signature(fn).bind_partial(*args, **kwargs).arguments.items() if k != "ctx"}
        except (TypeError, ValueError):
            call = {}
        try:
            extra.update(words.extras(name, answer, stash, call))
        except Exception:                                            # noqa: BLE001 - the card falls back to the answer's text
            pass
        if name == "propose_change" and isinstance(answer, dict):      # LFD8: the diff card (mcp_apps_change)
            from . import mcp_apps_change
            try:
                extra.update(mcp_apps_change.extras(answer, call))
            except Exception:                                        # noqa: BLE001 - the answer stands without the card's part
                pass
            return call_result(out, extra or None)
        lead = ctext = None
        if isinstance(answer, dict) and name not in STRUCTURED:      # n227: every other tool gets its kg_card, nothing else
            from . import mcp_apps_next as _nxt, next_rules          # WB13 (#91): a draft on the path gets its next steps
            todo = None
            if name in next_rules.TOOLS and not answer.get("error"):
                try:
                    todo = _nxt.steps(name, call, answer)
                    if todo:
                        extra["next"] = todo
                except Exception:                                    # noqa: BLE001 - the answer stands without them
                    pass
            ctext = _coach(name, call, answer, None, todo, extra)
            return call_result(out, extra or None, None, ctext)
        if isinstance(answer, dict):                                 # n218: next steps as buttons, the result first
            from . import mcp_apps_next as nxt
            try:
                import inspect as _inspect
                call = _inspect.signature(fn).bind_partial(*args, **kwargs).arguments
                todo = nxt.steps(name, call, answer, stash.get("checks") if name == "validate_plan" else None)
                if todo:
                    extra["next"] = todo
                if name == "validate_plan" and stash.get("checks"):
                    extra["checks"] = stash["checks"]
                ctext = _coach(name, call, answer, stash.get("checks") if name == "validate_plan" else None,
                               todo, extra)
                lead = nxt.lead(name, {**answer, **{k: v for k, v in extra.items() if k == "kg_card"}},
                                extra.get("next") or [], answer.get("actions"))
            except Exception:                                        # noqa: BLE001 - the answer stands without them
                lead = None
        return call_result(out, extra or None, lead, ctext)
    return wrapper


def _coach(name: str, call: dict, answer: dict, checks, todo, extra: dict) -> str | None:
    """CO1: the coach (coach.py) for one result: `coach` for the card (the stage, the mascot's line), `next` as ONE
    primary step and at most two secondary ones (start keeps its own buttons), and the Coach block's text."""
    from . import coach as _c
    try:
        c = _c.coach(name, call, answer, checks, todo)
    except Exception:                                                # noqa: BLE001 - the answer stands without it
        return None
    extra["coach"] = _c.card(c)
    if name == "requirements_draft":                         # RQ1: its own steps stay, each with its requirement ids
        todo = extra.get("next") or []
        return _c.text(c, todo[0], todo[1:1 + _c.SECONDARY]) if todo else c["text"]
    if name == "start":                                     # start draws its own buttons
        return c["text"]
    if "next" not in extra:                                 # SM4: never a dead end: a card without steps hands back to Start
        from . import tool_listing
        if "meta" in registration(name, on=True) and not tool_listing.forward(
                [a for a in answer.get("actions") or [] if isinstance(a, dict)]):
            extra["next"] = [tool_listing.hand_back(name, call, answer)]
        return c["text"]
    if _c.own_action(name, answer) is not None:              # the card's own action (Check, Create) is the primary
        extra["next"] = list(c["secondary"]) if not answer.get("error") else []
    else:
        extra["next"] = _c.next_steps(c)
    from . import tool_listing                              # SM4: a card whose steps lead nowhere listed hands back to Start
    acts = [a for a in answer.get("actions") or [] if isinstance(a, dict)]
    if "meta" in registration(name, on=True) and not tool_listing.forward(list(extra["next"]) + acts):
        extra["next"] = list(extra["next"]) + [tool_listing.hand_back(name, call, answer)]
    return c["text"]


def registration(name: str, on: bool | None = None) -> dict:
    """The extra arguments of the tool decorator for `name`: none with the flag off or for any other tool, else
    structured_output=False (no derived {"result": string} output schema, which would not describe the answer)."""
    if not (enabled() if on is None else on):
        return {}
    if name == "propose_change":                             # LFD8: the diff card, with KRUSGRAPH_CHANGES on too
        from . import mcp_apps_change, tool_listing
        meta = mcp_apps_change.tool_meta(on=tool_listing.changes_on())
        return {"structured_output": False, **({"meta": meta} if meta else {})}
    if name not in STRUCTURED:                               # n227: every tool's answer carries kg_card for a card that ran it
        return {"structured_output": False}
    if name == "start":                                      # n219: its own card, mcp_apps_start
        from . import mcp_apps_start
        return {"structured_output": False, "meta": mcp_apps_start.tool_meta(on=True)}
    from . import mcp_apps_build                             # n169: the build card's tools point at it
    if name in (mcp_apps_build.CARD_TOOLS + mcp_apps_build.PICTURE_CARD_TOOLS + mcp_apps_build.FLOW_CARD_TOOLS
                + mcp_apps_build.REQUIREMENT_CARD_TOOLS):
        return {"structured_output": False, "meta": mcp_apps_build.tool_meta(on=True)}
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
    from . import mcp_apps_build                             # n169: the build card, same flag
    mcp_apps_build.add_to(apps)
    from . import mcp_apps_start                             # n219: Start Krusgraph's card, same flag
    mcp_apps_start.add_to(apps)
    from . import mcp_apps_change                            # LFD8: the diff card, only with KRUSGRAPH_CHANGES on too
    mcp_apps_change.add_to(apps)
    return [apps]


def card_html() -> str:
    """The card: one self-contained HTML5 document. No src, href, url(), @import, fetch or other load; the data arrives
    only from the host. Since n136 the site's mascots are on it as inline SVG (mcp_apps_mascots): Onto says the summary
    (the counts), the Thinker the first thing that needs attention, the Builder the first next step, each word for word
    from the text answer and also on the card; glad only when every check passed; a button hides them."""
    from . import mcp_apps_build                             # n169: the Builder's and the Thinker's buttons (actions)
    allowed = json.dumps({t: list(CARRIED[t]) for t in NEXT_STEP_TOOLS}, separators=(",", ":"))
    from . import mcp_apps_pictures as pictures              # n170: the map, drawn the way the chat demo draws it
    pic = pictures.html_parts()
    from . import mcp_apps_next as nxt                       # n218: next steps as buttons, every key and link's state
    from .mcp_apps_size import SIZE_JS                   # WB13 (#89): the content's height, every card
    return (_HTML.replace("__SIZE_JS__", SIZE_JS).replace("__ALLOWED__", allowed).replace("__PROTOCOL__", PROTOCOL_VERSION)
            .replace("__STEP_LABEL__", json.dumps({t: STEP_LABEL[t] for t in NEXT_STEP_TOOLS}, separators=(",", ":"))).replace("__PICTURES__", pic["section"])
            .replace("__READ_JS__", READ_JS + CALL_JS + RESULT_JS + nxt.js() + mcp_apps_build.actions_js() + pic["js"])
            .replace("__MASCOT_CSS__", mascots.CSS).replace("__RESULT_CSS__", RESULT_CSS + nxt.NEXT_CSS + mcp_apps_build.ACTIONS_CSS + pic["css"]).replace("__MASCOT_TOGGLE__", mascots.TOGGLE)
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
  // n227: what the user reads names no tool: `ask` is the step in plain words (the action's or the step's `ask`).
  function callProblem(e, tool, ask) {
    var then = " Ask in the chat instead: “" + ask + "”";
    if (e && e.kind === "unsupported") return "This host does not run steps from the card." + then;
    if (e && e.kind === "tool") {
      var t = readable(e.text) ? e.text.slice(0, 300) : "no reason given";
      return "It answered with an error: " + t.replace(/[.\s]+$/, "") + ".";
    }
    var why = e && typeof e.message === "string" && e.message.trim() ? e.message.trim().slice(0, 200) : "no reason given";
    return "The host did not run this step: " + why.replace(/[.\s]+$/, "") + "." + then;
  }
  function stillWaiting(ask) {
    return "Still working. If the host asks you to allow it, answer there.";
  }
  function hostStarted(r) { hostCaps = isObj(r) && isObj(r.hostCapabilities) ? r.hostCapabilities : {}; }
"""


# n138 (Gustav, live in the Claude desktop app): a button's tool answer was shown as one large JSON block. RESULT_JS
# gives a short summary per tool, read only from names and counts in the answer (never a row value), with the whole
# answer behind a collapsed "Show details": semantic_model_draft its tables, relationships, measures and notes;
# ontology_draft its entity types with their keys, its relationship types and its notes as questions to the user;
# any other tool its `summary` (a sentence, or the numbers of a summary object). The form is chosen by the answer's
# shape, not by the tool's name, so the review card names no tool but review_plan. resultView(tool, result) gives the
# element; both cards use it.
RESULT_CSS = """
.res-file > summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px }
details.res-file pre.res-file-pre { white-space: pre; overflow-wrap: normal; word-break: normal; overflow: auto; max-height: 320px; max-width: 100%;
  margin-top: 4px; font-size: 12px }
.res-box { display: grid; gap: 4px; min-width: 0 }
.res-box .res { margin: 0; padding-left: 18px }
.res-box .res li { overflow-wrap: anywhere }
.res-box .res-k { font-weight: 650 }
.res-box .res-h { margin: 4px 0 0; font-size: 13.5px; font-weight: 650 }
.res-box .res-q li { margin: 4px 0 }
.res-box .res-why { display: block; color: var(--kg-muted); font-size: 13px }
.res-box details summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px; font-weight: 600 }
.res-box pre { margin: 4px 0 0; white-space: pre-wrap; word-break: break-word; font-size: 12.5px; max-height: 260px;
  overflow: auto; background: var(--kg-card); border-radius: 8px; padding: 6px 8px }
"""

RESULT_JS = r"""
  var LIST_MAX = 8;
  function arr(x) { return Array.isArray(x) ? x : []; }
  function some(xs, f) {
    var out = xs.slice(0, LIST_MAX).map(f).filter(Boolean);
    return out.join(", ") + (xs.length > LIST_MAX ? ", and " + (xs.length - LIST_MAX) + " more" : "");
  }
  function name(x) { return typeof x === "string" ? x : ""; }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }
  // n172: what the card shows a customer leaves out the maintainers' notes (how and when a tool was tested; they stay in
  // the tool's text answer and in docs/), and says the rule instead of a certainty number.
  var MAINTAINER = /unit-tested|unit tests|tested end to end|run live|tried live|created [^.]* live|live against|live run|synthetic data|docs\/[A-Z-]+\.md/i;
  function customer(t, rule) {
    if (!readable(t)) return "";
    t = String(t).replace(/;?\s*the active path has certainty [\d.]+, this link [\d.]+/i,
                          "; the other path stays active" + (rule ? " and this " + rule + " link is inactive" : ""))
                 .replace(/,?\s*\(?certainty [\d.]+\)?/gi, "");
    var kept = t.split(/(?<=[.!?])\s+(?=[A-Z0-9`])/).filter(function (x) { return !MAINTAINER.test(x); });
    return kept.join(" ").trim();
  }
  // { lines: [[label, text]], questions: [[question, why]] }, from names and counts only
  function summaryOf(tool, d) {
    var lines = [], questions = [], s = isObj(d.summary) ? d.summary : null;
    if (readable(d.error)) { lines.push(["Error", d.error + (readable(d.hint) ? " " + d.hint : "")]); return { lines: lines, questions: questions }; }
    if (Array.isArray(d.lines) && Array.isArray(d.result_lines)) {   // SC1
      var W = { "differs": "Differs", "not checked": "Not checked", "verified": "Verified" }, R = ["differs", "not checked", "verified"];
      R.forEach(function (st) { d.lines.forEach(function (x) { if (isObj(x) && x.state === st && readable(x.said)) lines.push([W[st], String(x.said).slice(0, 400)]); }); });
      arr(d.fixes).filter(isObj).forEach(function (f) { lines.push(["Fix", (name(f.item) ? f.item + ": " : "") + (f.label || f.said || f.ask || "")]); });
      if (readable(d.note)) lines.push(["Note", d.note]);
      return { lines: lines, questions: questions };
    }
    if (s && isObj(s.roles) && "relationships_active" in s) {          // a semantic model draft
      var roles = isObj(s.roles) ? s.roles : {}, by = {};
      Object.keys(roles).forEach(function (t) { (by[roles[t]] = by[roles[t]] || []).push(t); });
      lines.push(["Tables", String(Number(s.tables) || Object.keys(roles).length) +
        (Object.keys(by).length ? " (" + Object.keys(by).map(function (r) { return r + ": " + some(by[r], name); }).join("; ") + ")" : "")]);
      lines.push(["Relationships", (Number(s.relationships_active) || 0) + " active, " + (Number(s.relationships_inactive) || 0) + " inactive" +
        (Number(s.relationships_not_expressible) ? ", " + s.relationships_not_expressible + " not expressible" : "")]);
      var ms = [], seenM = {};
      arr(s.measures).concat(arr(isObj(s.order_amount) ? s.order_amount.measures : [])).forEach(function (m) {
        var k = isObj(m) ? m.table + "|" + m.name : ""; if (k && !seenM[k]) { seenM[k] = 1; ms.push(m); } });
      lines.push(["Measures", ms.length ? ms.length + ": " + some(ms, function (m) { return isObj(m) && name(m.name) ? m.name + (name(m.table) && m.name.indexOf("(" + m.table + ")") < 0 ? " (" + m.table + ")" : "") : ""; }) : "none"]);
      var notes = [];
      if (arr(s.keyless).length) notes.push("No key: " + some(arr(s.keyless), name) + ".");
      if (arr(s.composite_keys).length) notes.push("Composite key: " + some(arr(s.composite_keys), name) + ".");
      arr(s.inactive).forEach(function (r) { if (isObj(r)) notes.push("Inactive: " + r.source + "." + arr(r.columns).join("+") + " → " + r.target + (r.rule ? " (" + r.rule + ")" : "") + (customer(r.why, r.rule) ? ": " + customer(r.why, r.rule) : "") + "."); });
      arr(s.not_expressible).forEach(function (r) { if (isObj(r)) notes.push("Not expressible: " + r.source + " → " + r.target + (readable(r.why) ? ": " + r.why : "") + "."); });
      arr(s.header_amounts).forEach(function (h) { if (isObj(h)) notes.push("Header amount " + h.table + "." + h.column + " is not summed over " + arr(h.lines).join(", ") + "."); });
      var dt = isObj(s.date_table) ? s.date_table : null;
      if (dt && name(dt.name)) notes.push("Date table " + dt.name + (arr(dt.related).length ? ", related to " + some(arr(dt.related), function (r) { return isObj(r) ? r.fact + "." + r.column : ""; }) : "") +
        (arr(dt.not_related).length ? "; not related: " + some(arr(dt.not_related), function (r) { return isObj(r) ? r.fact + "." + r.column + (readable(r.why) ? " (" + r.why + ")" : "") : ""; }) : "") + ".");
      if (customer(d.note)) notes.push(customer(d.note));
      notes.forEach(function (n) { lines.push(["Note", n]); });
    } else if (s && Array.isArray(d.bindings) && "entity_types" in s) {   // an ontology draft
      var binds = arr(d.bindings).filter(isObj);
      lines.push(["Entity types", (Number(s.entity_types) || binds.length) + ", " + (Number(s.with_key) || 0) + " with a key"]);
      binds.slice(0, 2 * LIST_MAX).forEach(function (b) {
        var key = name(b.key) ? "key " + b.key : (arr(b.key_columns).length > 1 ? "no single key (" + arr(b.key_columns).join(" + ") + ")" : "no key");
        lines.push(["Entity", b.entity_type + ": " + key]);
      });
      var rels = [];
      binds.forEach(function (b) { arr(b.relationships).forEach(function (r) { if (isObj(r)) rels.push(b.entity_type + " → " + r.to + (name(r.name) ? " (" + r.name + ")" : "")); }); });
      lines.push(["Relationship types", (Number(s.relationship_types) || rels.length) + (rels.length ? ": " + some(rels, name) : "") +
        (Number(s.skipped_relationships) ? "; " + s.skipped_relationships + " skipped" : "")]);
      arr(s.notes).forEach(function (n) {
        if (!readable(n)) return;
        var who = (/^([A-Za-z_][\w]*):/.exec(n) || [])[1], b = binds.filter(function (x) { return x.entity_type === who; })[0], q;
        if (b && !name(b.key) && arr(b.key_columns).length > 1) q = "Which one property should be the key of " + who + "?";
        else if (b && !name(b.key)) q = "Does " + who + " have a key?";
        else q = (who ? who + ": is" : "Is") + " this right?";
        questions.push([q, n]);
      });
      if (customer(d.note)) lines.push(["Note", customer(d.note)]);
    } else if (readable(d.summary)) {
      lines.push(["Summary", d.summary]);
      plainLines(d).forEach(function (ln) { if (ln[0] !== "Summary") lines.push(ln); });
    } else if (s) {
      Object.keys(s).forEach(function (k) {
        var v = s[k];
        if (typeof v === "number" || typeof v === "boolean") lines.push([k.replace(/_/g, " "), String(v)]);
        else if (Array.isArray(v)) lines.push([k.replace(/_/g, " "), String(v.length)]);
      });
    }
    return { lines: lines, questions: questions };                // n227: an answer without these gets plainLines/oneLine
  }
  // n227: the card's words first (kg_card: result, lines, notes); summaryOf only for an answer without them. The
  // details hold readable lines first and the raw JSON last, behind a second toggle (mcp_apps_result.py).
  function resultView(tool, r, skipResult) {
    var box = el("div", null, "res-box"), d = answerOf(r), text = resultText(r), w = cardWords(d);
    var done = isObj(d) && d.dry_run === false && isObj(d.result) && d.result.status === "Succeeded";
    if (w) {
      box.appendChild(wordsView(w, skipResult, done));
    } else if (d) {
      var sm = summaryOf(tool, d), shown = sm.lines.filter(function (ln) { return ln[0] !== "Note"; });
      if (!skipResult && !readable(d.error)) box.appendChild(el("p", oneLine(d), "res-line"));
      if (readable(d.error) || !readable(d.summary)) {
        var ul = el("ul", null, "res");
        shown.slice(0, CARD_LINES).forEach(function (ln) { var li = el("li"); li.appendChild(el("span", ln[0] + ": ", "res-k")); li.appendChild(document.createTextNode(ln[1])); ul.appendChild(li); });
        if (ul.children.length) box.appendChild(ul);
      }
      groupedNotes(sm.lines).forEach(function (n) { box.appendChild(noteView(n)); });
      if (sm.questions.length) {
        box.appendChild(el("p", "Questions for you", "res-h"));
        var qs = el("ul", null, "res res-q");
        sm.questions.forEach(function (q) { var li = el("li", q[0]); li.appendChild(el("span", q[1], "res-why")); qs.appendChild(li); });
        box.appendChild(qs);
      }
    } else {
      box.appendChild(el("p", readable(text) ? (text.length > 400 ? text.slice(0, 400) + "…" : text) : "It answered; the answer is under Show details."));
    }
    if (isObj(d) && isObj(d.ontology)) {                       // WB13 (#71): a big ontology is drawn small first
      var fig = ontoSvg(isObj(d.ontology_mini) ? d.ontology_mini : d.ontology);
      if (fig) box.appendChild(fig);
      if (fig && isObj(d.ontology_mini) && typeof kgFull === "function") kgFull(box, d.ontology_mini, d.ontology, function (into, o) { return ontoSvg(o); }, "entity types");
    }
    if (isObj(d) && typeof d.ttl === "string" && d.ttl.trim()) {  // WB13 (#92): the Turtle file closed, scrolling sideways
      var tf = el("details", null, "res-file"), nl = d.ttl.split("\n").length;
      tf.appendChild(el("summary", "Show the ontology file (Turtle, " + nl + " lines)"));
      tf.appendChild(el("pre", d.ttl, "res-file-pre"));
      box.appendChild(tf);
    }
    if (text || d) box.appendChild(detailsView(tool, d, text));
    return box;
  }
"""

RESULT_JS += _result.js()                                  # n227: kg_card first, the progress state, the ontology picture
RESULT_CSS += _result.CSS

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
[hidden] { display: none !important }
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
.more summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px; font-weight: 600 }
.more { display: grid; gap: 6px }
.step { display: grid; gap: 4px; border: 1px solid var(--kg-line); border-radius: var(--kg-radius); padding: 8px 10px }
button { font: inherit; font-weight: 650; justify-self: start; color: var(--kg-ink); background: var(--kg-card);
  border: 1px solid var(--kg-line); border-radius: 999px; padding: 4px 14px; cursor: pointer }
button:disabled { cursor: default; opacity: .6 }
pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12.5px; max-height: 260px; overflow: auto;
  background: var(--kg-card); border-radius: 8px; padding: 6px 8px }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important } }
__MASCOT_CSS__
__RESULT_CSS__
</style>
</head>
<body>
<main>
  <div class="kg-head"><h1>Plan check</h1>__MASCOT_TOGGLE__</div>
  <p class="muted" role="status"><span id="verdict">Checking the plan against the rows…</span><span id="result" hidden></span></p>
  <section id="nextsteps" hidden></section>
  __MASCOTS__
  <dl id="counts" class="counts" hidden></dl>
  __PICTURES__
  <section id="checks" hidden></section>
  <section id="attention" hidden><h2 class="muted">Needs attention</h2><ul id="attention-list"></ul><p id="attention-none" hidden>Nothing needs attention.</p></section>
  <section id="build" hidden></section>
  <details id="next" class="more" hidden><summary>More</summary><p class="muted">Drafts that only read; nothing is created.</p><div id="steps" class="steps"></div></details>
  <p class="muted">The same answer is in the text of the tool result. A button asks the host to run that step; the host may ask you first.</p>
</main>
<script>
(function () {
  "use strict";
  var ALLOWED = __ALLOWED__;            // next-step tool -> the arguments carried over from this call
  var STEP_LABEL = __STEP_LABEL__;      // n227: what each of those steps is called on a button
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
    ["counts", "result", "attention", "next", "build", "nextsteps", "checks"].forEach(function (id) { document.getElementById(id).hidden = true; });
    if (!data || (!data.error && !data.summary && !data.totals)) { verdict.textContent = "The card could not read the check's answer; it is in the text of the tool result."; return; }
    if (data.error) { verdict.textContent = readable(data.error) + (readable(data.hint) ? " " + data.hint : "");
      var errBox = document.getElementById("nextsteps"); errBox.textContent = ""; errBox.hidden = !renderNext(data, errBox); return; }   // n220
    // n172: the card's words (mcp_apps_words.py): the summary as short sentences that Onto says once
    var words = isObj(data.kg_card) ? data.kg_card : {}, ontoSaid = readable(words.onto);
    var lines = Array.isArray(words.lines) ? words.lines.filter(readable) : [];
    verdict.textContent = lines.length ? lines.join(" ") : readable(data.summary);
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
    [verdict, counts].forEach(function (e) {                    // shown here only while Onto does not say it
      if (ontoSaid && lines.length) { e.setAttribute("data-echo", "onto"); e.setAttribute("data-said", ontoSaid); }
      else { e.removeAttribute("data-echo"); e.removeAttribute("data-said"); }
    });
    drawPictures(data, isObj(input) ? input : null);                 // n170: the map, as in the chat demo
    // n218: 2 to 4 next steps as buttons, each naming its tool; every key and link as passed, failed or not checked
    var nsBox = document.getElementById("nextsteps"); nsBox.textContent = ""; nsBox.hidden = !renderNext(data, nsBox);
    var ckBox = document.getElementById("checks"); ckBox.textContent = ""; ckBox.hidden = !renderChecks(data, ckBox);

    // n137: the overall result in words (an answer with nothing to attend to has one), never a JSON text. n138: it is
    // part of the summary line, once; the attention section then says only that nothing needs attention.
    var res = document.getElementById("result"), said = lines.length ? "" : readable(data.result);
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
    // n155: validate_plan with fixes=true: each proposed fix, or the decision it leaves to a person, as one line
    var fixes = isObj(data.fix_plan) && Array.isArray(data.fix_plan.fixes) ? data.fix_plan.fixes : [];
    fixes.forEach(function (x) {
      if (!isObj(x) || !readable(x.proposed_fix)) return;
      list.appendChild(el("li", (x.type === "mechanical" ? "Proposed fix, " : "To decide, ") + (x.id || x.table || "") + ": " + x.proposed_fix));
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
      var b = el("button", STEP_LABEL[s.tool] || "Run this step"); b.type = "button";   // n227: plain words, no tool's name
      b.setAttribute("data-tool", s.tool);
      var out = el("div", null, "out"); out.hidden = true;
      b.addEventListener("click", function () { run(s, b, out); });
      row.appendChild(b); row.appendChild(out); steps.appendChild(row);
    });
    document.getElementById("next").hidden = !steps.children.length;
    // n172: folded under "More" when the card has its own words and the Builder's builds; an answer without them (a
    // text result, an older server) keeps the drafts open, so the Builder's sentence stays on the card.
    // WB13 (#91): folded too when the card leads with its rule-based next steps
    document.getElementById("next").open = !readable(words.builder) && !(Array.isArray(data.next) && data.next.length);

    // n169: the Builder's buttons from the answer's `actions`: each build is a dry run first, Create only on its card
    var build = document.getElementById("build"); build.textContent = "";
    renderActions(data, build, null);
    build.hidden = !build.children.length;
    if (!firstStep && build.children.length && Array.isArray(data.actions) && isObj(data.actions[0])) firstStep = readable(data.actions[0].say);
    if (readable(words.builder)) firstStep = words.builder;         // n172: what can be built, not the next step's text

    // n136: Onto says the counts, the Thinker what needs attention, the Builder the next step; every sentence is a
    // string of the answer and is on the card above. Glad only when every check passed and nothing needs attention.
    var checked = 0, failed = 0;
    Object.keys(totals).forEach(function (k) { var t = isObj(totals[k]) ? totals[k] : {}; checked += t.checked || 0; failed += t.failed || 0; });
    var passed = checked > 0 && failed === 0 && !data.needs_attention && !firstWhat;
    mascots({ onto: [ontoSaid || readable(data.summary), passed ? "celebrate" : "point"],
              thinker: [readable(words.thinker) || firstWhat, "think"],
              builder: [firstStep, passed ? "heart" : "explain"] }, passed);
  }

  function run(step, button, out) {
    var args = {};
    (ALLOWED[step.tool] || []).forEach(function (k) { if (input[k] != null) args[k] = input[k]; });
    var own = step.arguments || {};
    Object.keys(own).forEach(function (k) { args[k] = own[k]; });
    var label = STEP_LABEL[step.tool] || "Run this step";
    var ask = label + ", with the same workspace, source and schema.";
    runOrSay(step.tool, args, ask, out, button, null, { kind: "call", label: label });   // n218: else the message goes into the chat
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

__SIZE_JS__
  request("ui/initialize", {
    appInfo: { name: "Krusgraph plan check", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function (r) {
    hostStarted(r);
    notify("ui/notifications/initialized");
    watchSize();
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
