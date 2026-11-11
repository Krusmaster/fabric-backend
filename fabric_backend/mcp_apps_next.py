"""MCP Apps, cards that act (round n218): next steps as buttons on every card, the check card's rows, a short lead.

Founder, 11 November 2026, after his own session in Claude with the hosted connector: "the UI in the chat is not good.
It gives recommendations but I cannot click on any suggestion. It is mostly text." Behind the n119 flag
(KRUSGRAPH_MCP_APPS, off unless "1"); with the flag off nothing here reaches an answer or the listing.

What a card may do in Claude, and where that is documented (all read 11 November 2026; modelcontextprotocol.io could not
be opened from this round, so its extension pages are Unverified here):
- `tools/call` through the host: the specification's "Standard MCP Messages" and `hostCapabilities.serverTools`
  (modelcontextprotocol/ext-apps, specification/2026-01-26/apps.mdx, Status: Stable); Claude's "App tools" page
  (claude.com/docs/connectors/building/mcp-apps/app-tools) says a view's own calls to its server's tools run without a
  prompt to the user. A tool without `_meta.ui.visibility` is visible to the model and to the app.
- `ui/message`: params {role: "user", content}; the ext-apps SDK types `content` as an array of content blocks
  (src/spec.types.ts, McpUiMessageRequest), the specification's prose shows one block. Claude ("Send messages", same
  docs) takes text blocks up to 8 000 characters after a user gesture, and either asks the user or puts the text in the
  message box. The cards now send the array form and fall back to the single block (NEXT_JS).
- `ui/open-link` (`openLinks`), with Claude's "Open external link" confirmation.
- `ui/notifications/size-changed`; Claude offers the inline and fullscreen display modes.
- Theme: Claude passes `theme` and `--color-*` variables; the cards use them with light-dark() fallbacks.
- No network: without `_meta.ui.csp` the default is connect-src 'none'; the cards declare no domain.

What this module adds, all built on the server from the tool's own answer, never invented by the card:
- `steps(tool, args, answer)`: 2 to 4 next steps, each {label, tool, arguments, say}. None of them writes: the reads
  and drafts by name, a creating tool never (the build card's Create stays behind its dry run, mcp_apps_build).
  `say` is the exact message the card sends to the chat when the host does not run the tool from the card.
- `lead(tool, answer, steps)`: the answer's first lines in plain words, then the same next steps as a short list. With
  the flag on it is the first text content of the result; the JSON answer follows it unchanged, so a text-only client
  and the model still read every detail, and nothing depends on the card.
- `check_rows(plan, full)`: validate_plan's every key and link as passed, failed or not checked with its counts, and
  for a failure the SQL that counts it (evidence.key_sql / relationship_sql in T-SQL: the same counts as the check; the
  check itself may have run a combined statement for several links of one table). Counts and verdicts only, never a
  row value.
"""
from __future__ import annotations

from . import mcp_apps_words as words

MAX_STEPS = 4
# Next steps may name only these tools: they read or draft; none creates anything in Fabric.
STEP_TOOLS = ("validate_plan", "plan_backend", "review_plan", "semantic_model_draft", "list_tables", "join_path",
              "data_dictionary", "ontology_draft")
LABEL = {
    "check": "Check against the rows",
    "doubled": "Show the doubled totals",
    "model": "Draft a semantic model",
    "review": "Review keys and links",
    "fixes": "Propose a fix per failure",
    "replan": "Plan again",
    "ontology": "Draft an ontology",
}
CHECK_MAX = 200                                                      # rows on the check card


def _carried(args: dict, *keys) -> dict:
    return {k: args[k] for k in keys if args.get(k) not in (None, "", [], {})}


def _step(label: str, tool: str, arguments: dict, about: str = "") -> dict:
    shown = ", ".join(f"{k}={v!r}" for k, v in arguments.items() if k in ("source", "schema", "detail", "fixes", "validate", "name"))
    say = f"{label}{(' ' + about) if about else ''}: run {tool}" + (f" with {shown}" if shown else "") + "."
    return {"label": label, "tool": tool, "arguments": dict(arguments), "say": say}


def _source_args(args: dict, answer: dict) -> dict:
    out = _carried(args, "workspace", "source", "schema", "keys", "confirmed")
    chosen = answer.get("schema_chosen") if isinstance(answer, dict) else None
    if chosen and "schema" not in out:
        out["schema"] = chosen
    return out


def _has_amounts(answer: dict) -> bool:
    t = answer.get("totals") if isinstance(answer.get("totals"), dict) else {}
    a = t.get("amount_levels") if isinstance(t.get("amount_levels"), dict) else {}
    return bool(a.get("checked"))


def _failed(answer: dict) -> int:
    t = answer.get("totals") if isinstance(answer.get("totals"), dict) else {}
    return sum(int((v or {}).get("failed") or 0) for v in t.values() if isinstance(v, dict))


# n220 (d): an error or a refusal ends with 1 to 3 next steps too. A step may also be a dry run of a creating tool (it
# writes nothing; Create stays behind its own card), a link (ui/open-link), or a sentence sent to the chat.
DRY_RUN_TOOLS = ("create_report", "create_pipeline", "create_semantic_model", "create_ontology", "create_backend")
ERROR_MAX = 3


def _say_step(label: str, say: str) -> dict:
    return {"label": label, "say": str(say)[:600]}


def _from_answer(s: dict, call: dict) -> dict | None:
    """One of the answer's own next_steps ({label, tool, args, ask, url}) in the card's form, or None."""
    if not isinstance(s, dict) or not isinstance(s.get("label"), str) or not s["label"].strip():
        return None
    label = s["label"].strip()
    url = s.get("url")
    if isinstance(url, str) and url.startswith("https://"):
        return {"label": label, "url": url, "say": f"{label}: {url}"}
    t = s.get("tool")
    if t in STEP_TOOLS or t in DRY_RUN_TOOLS:
        arguments = dict(s.get("args") or {k: v for k, v in call.items() if k not in ("confirm_jobs",)})
        if t in DRY_RUN_TOOLS:
            arguments["dry_run"] = True                              # a step never writes
        return {"label": label, "tool": t, "arguments": arguments,
                "say": str(s.get("ask") or f"{label}: run {t} as a dry run.")}
    if isinstance(s.get("ask"), str) and s["ask"].strip():
        return _say_step(label, s["ask"])
    return None


def error_steps(tool: str, args: dict, answer: dict) -> list[dict]:
    """1 to 3 next steps for an error or a refusal: the answer's own next_steps first, then what fits its kind."""
    call = {k: v for k, v in (args or {}).items() if k != "ctx"}
    out = [x for x in (_from_answer(s, call) for s in answer.get("next_steps") or []) if x]
    err = str(answer.get("error") or "")[:200]
    kind = answer.get("kind")
    if not out and kind == "consent":
        scope = answer.get("scope") or "the permission"
        out.append(_say_step("What the admin must add", f"Which Entra steps give Krusgraph {scope}? The error was: {err}"))
    if not out and (tool in STEP_TOOLS or tool in DRY_RUN_TOOLS) and kind in ("timeout", "source_not_ready", "rate_limited",
                                                                                "fabric_error", None):
        again = dict(call)
        if tool in DRY_RUN_TOOLS:
            again["dry_run"] = True
        out.append({"label": "Try again", "tool": tool, "arguments": again,
                    "say": f"Try again: run {tool}" + (" as a dry run." if tool in DRY_RUN_TOOLS else ".")})
    if len(out) < ERROR_MAX:
        out.append(_say_step("Explain this and what to do", f"Explain Krusgraph's answer from {tool} and what I can do "
                                                            f"next: {err}"))
    return out[:ERROR_MAX]


def steps(tool: str, args: dict, answer: dict) -> list[dict]:
    """The card's next steps for one answer (2 to 4; 1 to 3 for an error or a refusal, n220; none for a question back
    to the user)."""
    if isinstance(answer, dict) and answer.get("error"):
        return error_steps(tool, args, answer)
    if not isinstance(answer, dict) or answer.get("choose_schema") or answer.get("ask"):
        return []
    args = {k: v for k, v in (args or {}).items() if k != "ctx"}
    if "workspace" not in args or "source" not in args:
        return []
    base = _source_args(args, answer)
    where = f"for {base.get('schema') or base['source']}"
    out: list[dict] = []
    if tool == "plan_backend":
        out = [_step(LABEL["check"], "validate_plan", base, where),
               _step(LABEL["doubled"], "validate_plan", {**base, "detail": "full"}, where),
               _step(LABEL["model"], "semantic_model_draft", {**base, "validate": True}, where),
               _step(LABEL["review"], "review_plan", base, where)]
    elif tool == "validate_plan":
        out = []
        if _failed(answer):
            out.append(_step(LABEL["fixes"], "validate_plan", {**base, "fixes": True}, where))
        out.append(_step(LABEL["review"], "review_plan", {**base, "validate": True}, where))
        if _has_amounts(answer) and not args.get("detail") == "full":
            out.append(_step(LABEL["doubled"], "validate_plan", {**base, "detail": "full"}, where))
        out.append(_step(LABEL["model"], "semantic_model_draft", {**base, "validate": True}, where))
    elif tool == "review_plan":
        out = [_step(LABEL["check"], "review_plan", {**_carried(args, "workspace", "source", "schema", "keys", "confirmed"),
                                                    "validate": True}, where),
               _step(LABEL["replan"], "plan_backend", base, where),
               _step(LABEL["model"], "semantic_model_draft", {**base, "validate": True}, where)]
    elif tool in ("create_semantic_model", "create_ontology", "create_backend", "ontology_draft", "domain_draft", "dbt_schema"):
        out = [_step(LABEL["check"], "validate_plan", base, where), _step(LABEL["review"], "review_plan", base, where)]
        if tool not in ("create_semantic_model",):
            out.append(_step(LABEL["model"], "semantic_model_draft", {**base, "validate": True}, where))
    return [s for s in out if s["tool"] in STEP_TOOLS][:MAX_STEPS]


def _first_lines(tool: str, answer: dict) -> list[str]:
    if answer.get("error"):
        return [str(answer["error"])] + ([str(answer["hint"])] if answer.get("hint") else [])
    if answer.get("choose_schema") or answer.get("ask"):
        return [str(answer.get("summary") or answer.get("ask"))]
    if tool == "validate_plan" and isinstance(answer.get("totals"), dict):
        return words.check_lines(answer)
    card = answer.get("kg_card") if isinstance(answer.get("kg_card"), dict) else {}
    lines = [x for x in card.get("lines") or [] if isinstance(x, str) and x.strip()]
    if lines:
        return lines
    s = answer.get("summary")
    if isinstance(s, str) and s.strip():
        return [s.strip()]
    if tool in ("create_semantic_model", "create_ontology", "create_backend", "create_report"):
        return ["Dry run: nothing was created." if answer.get("dry_run") is not False else "Done."]
    return []


def lead(tool: str, answer: dict, next_steps: list[dict], actions: list | None = None) -> str:
    """The result first, in a few short lines, then the next steps as a list naming the tool each runs."""
    lines = _first_lines(tool, answer) if isinstance(answer, dict) else []
    out = [" ".join(lines)[:600]] if lines else []
    todo = [f"- {s['label']} ({s['tool']}{', dry run' if s['tool'] in DRY_RUN_TOOLS else ''})" if s.get("tool") else
            f"- {s['label']}: {s['url']}" if s.get("url") else f"- {s['label']}: ask \u201c{s['say']}\u201d"
            for s in next_steps]
    for a in actions or []:
        if isinstance(a, dict) and a.get("kind") in ("dry_run", "create", "call") and a.get("tool"):
            text = f"- {a['label']}{(' ' + a['name']) if a.get('name') and a['kind'] != 'call' else ''} ({a['tool']}"
            text += ", dry run)" if a["kind"] == "dry_run" else ", creates it; only after you confirm)" if a["kind"] == "create" else ")"
            if text not in todo:
                todo.append(text)
    if todo:
        out.append("Next steps:\n" + "\n".join(todo[:6]))
    out.append("The full answer follows as JSON.")
    return "\n\n".join(out)


# ------------------------------------------------------------------ the check card's rows -----------------------------

def _rel_label(source: str, cols, target: str) -> str:
    return f"{source}.{'+'.join(cols)} → {target}"


def check_rows(plan, full: dict) -> dict:
    """{rows: [{kind, id, label, rule, state, counts, sql?}], counts: {passed, failed, not_checked}} for validate_plan's
    full answer `full` over `plan`. Keys and links max_items did not reach are listed as not checked."""
    from .evidence import _amount_items, _amount_status, _key_status, _rel_status, key_sql, relationship_sql
    schema = plan.schema.schema
    rows, seen_keys, seen_rels = [], set(), set()
    for k in full.get("keys") or []:
        state = _key_status(k)
        state = "not_checked" if state == "not_counted" else state
        dup = max(0, int(k.get("rows") or 0) - int(k.get("nulls") or 0) - int(k.get("distinct") or 0))
        row = {"kind": "key", "id": f"key:{k['table']}", "label": f"{k['table']} ({' + '.join(k['columns'])})",
               "rule": k.get("rule"), "state": state,
               "counts": f"{k.get('rows', 0)} rows, {k.get('nulls', 0)} empty, {dup} repeated"}
        if state == "failed":
            row["sql"] = key_sql(schema, k["table"], list(k["columns"]))
        rows.append(row)
        seen_keys.add(k["table"].lower())
    for r in full.get("relationships") or []:
        state = _rel_status(r)
        state = {"not_counted": "not_checked", "warning": "failed"}.get(state, state)
        n, o = int(r.get("rows_with_value") or 0), int(r.get("orphans") or 0)
        row = {"kind": "link", "id": f"rel:{r['source']}.{'+'.join(r['columns'])}>{r['target']}",
               "label": _rel_label(r["source"], r["columns"], r["target"]), "rule": r.get("rule"), "state": state,
               "counts": f"{o} of {n} point at nothing"}
        if state == "failed":
            row["sql"] = relationship_sql(schema, r["source"], list(r["columns"]), r["target"], list(r["target_columns"]))
        rows.append(row)
        seen_rels.add((r["source"].lower(), tuple(c.lower() for c in r["columns"]), r["target"].lower()))
    for f in _amount_items(full):
        state = {"not_counted": "not_checked"}.get(_amount_status(f), _amount_status(f))
        table = f.get("header") or f.get("table") or ""
        cols = f.get("amount_columns") or ([f["column"]] if f.get("column") else [])
        rows.append({"kind": "amount", "id": f"amount:{table}", "label": f"{table}: {', '.join(cols)}"
                     + (f" over {f['line']}" if f.get("line") else ""), "state": state,
                     "counts": "repeated on every line: do not sum over the lines" if state == "failed" else "on its own level"})
    for table, (cols, rule) in plan.keys.items():
        if table.lower() not in seen_keys:
            rows.append({"kind": "key", "id": f"key:{table}", "label": f"{table} ({' + '.join(cols)})", "rule": rule,
                         "state": "not_checked", "counts": "not counted: the check's budget (max_items) was used up"})
    for r in plan.relationships:
        if (r.source.lower(), tuple(c.lower() for c in r.source_cols), r.target.lower()) not in seen_rels:
            rows.append({"kind": "link", "id": f"rel:{r.source}.{'+'.join(r.source_cols)}>{r.target}",
                         "label": _rel_label(r.source, r.source_cols, r.target), "rule": r.rule, "state": "not_checked",
                         "counts": "not counted: the check's budget (max_items) was used up"})
    counts = {s: sum(1 for x in rows if x["state"] == s) for s in ("passed", "failed", "not_checked")}
    order = {"failed": 0, "not_checked": 1, "passed": 2}
    rows.sort(key=lambda x: (order.get(x["state"], 3), {"key": 0, "link": 1, "amount": 2}[x["kind"]], x["label"].lower()))
    out = {"rows": rows[:CHECK_MAX], "counts": counts}
    if len(rows) > CHECK_MAX:
        out["left_out"] = f"The card lists {CHECK_MAX} of {len(rows)} checks; the answer has them all."
    return out


# ------------------------------------------------------------------ the cards' script ---------------------------------
# Shared by the three cards. runOrSay(tool, args, say, out, done): tools/call when the host proxies it; otherwise, or
# when the host answers -32601, the `say` text with ui/message (the array form of the SDK's types, then the single block
# of the specification's prose); only when both are refused, the sentence to copy. renderNext(data, box) draws the
# answer's `next` steps, each button naming the tool it runs. renderChecks(data, box) draws the check card's rows.
NEXT_CSS = """
.nx { display: grid; gap: 6px }
.nx-h { margin: 0; font-size: 13.5px; font-weight: 650; color: var(--kg-muted) }
.nx-row { display: flex; flex-wrap: wrap; gap: 6px }
.nx-b { display: inline-flex; gap: 6px; align-items: baseline }
.nx-tool { font: 500 12px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--kg-muted) }
.nx-out:empty { display: none }
button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--kg-ink); outline-offset: 2px }
.ck { display: grid; gap: 6px }
.ck-sum { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none }
.ck-table { width: 100%; border-collapse: collapse; font-size: 13.5px }
.ck-table th { text-align: left; font-weight: 600; color: var(--kg-muted); padding: 4px 6px; border-bottom: 1px solid var(--kg-line) }
.ck-table td { padding: 4px 6px; border-bottom: 1px solid var(--kg-line); vertical-align: top; overflow-wrap: anywhere }
.pill { display: inline-block; border-radius: 999px; padding: 0 8px; font-size: 12.5px; font-weight: 650; border: 1px solid currentColor; white-space: nowrap }
.pill-passed { color: var(--kg-ok) }
.pill-failed { color: var(--kg-warn) }
.pill-not_checked { color: var(--kg-muted) }
.pill-rule { color: var(--kg-muted); font-weight: 500 }
.ck-sql { margin-top: 4px }
.dec { display: inline-flex; gap: 4px; margin-top: 4px }
.dec button[aria-pressed="true"] { background: var(--kg-ink); color: var(--kg-bg) }
"""

NEXT_JS = r"""
  function sendChat(text) {
    var t = String(text).slice(0, 8000);
    return request("ui/message", { role: "user", content: [{ type: "text", text: t }] }).catch(function (e) {
      if (isObj(e) && e.code === -32602) return request("ui/message", { role: "user", content: { type: "text", text: t } });
      throw e;
    });
  }
  function sayInChat(say, out, button) {
    out.textContent = "Sent to the chat: “" + say + "”";
    return sendChat(say).then(function () { if (button) button.disabled = false; }, function () {
      out.textContent = "This host runs neither tools nor messages from the card. Ask in the chat: “" + say + "”";
      if (button) button.disabled = false;
    });
  }
  function runOrSay(tool, args, say, out, button, done) {
    out.hidden = false;
    if (button) button.disabled = true;
    if (!canCallTools()) { sayInChat(say, out, button); return; }
    out.textContent = "Asked the host to run " + tool + "; it may ask you first.";
    callTool(tool, args, function () { out.textContent = stillWaiting(say); }).then(function (r) {
      out.textContent = "";
      if (done) done(r); else out.appendChild(answerView(tool, r));
      if (button) button.disabled = false;
    }, function (e) {
      if (e && e.kind === "unsupported") { sayInChat(say, out, button); return; }
      out.textContent = callProblem(e, tool, say);
      if (button) button.disabled = false;
    });
  }
  var NEXT_TOOLS = __NEXT_TOOLS__, DRY_TOOLS = __DRY_TOOLS__, LINKS = __LINKS__;
  function okStep(s) {
    if (!isObj(s) || typeof s.label !== "string" || typeof s.say !== "string") return false;
    if (s.tool === undefined && s.arguments === undefined) {                 // n220: a link, or a sentence for the chat
      return s.url === undefined || (LINKS && typeof s.url === "string" && /^https:[/][/]/.test(s.url));
    }
    if (!isObj(s.arguments)) return false;
    if (DRY_TOOLS.indexOf(s.tool) >= 0) return s.arguments.dry_run === true;  // a creating tool only as a dry run
    return NEXT_TOOLS.indexOf(s.tool) >= 0 && s.arguments.dry_run !== false;
  }
__OPEN_JS__
  function renderNext(data, box) {
    var list = (Array.isArray(data.next) ? data.next : []).filter(okStep).slice(0, 4);
    if (!list.length) return false;
    var wrap = el("section", null, "nx"); wrap.setAttribute("aria-label", "Next steps");
    wrap.appendChild(el("p", "Next steps", "nx-h"));
    var row = el("div", null, "nx-row"), out = el("div", null, "nx-out");
    list.forEach(function (s) {
      var b = el("button", null, "nx-b"); b.type = "button";
      b.appendChild(el("span", s.label));
      if (typeof s.url === "string") {                                         // n220: a link
        b.setAttribute("aria-label", s.label + " (opens a link)");
        b.addEventListener("click", function () { openOrShow(s.url, out, b); });
      } else if (!s.tool) {                                                    // n220: a sentence for the chat
        b.setAttribute("aria-label", s.label + " (asks in the chat)");
        b.addEventListener("click", function () { out.hidden = false; sayInChat(s.say, out, null); });
      } else {
        b.appendChild(el("span", s.tool, "nx-tool"));
        b.setAttribute("aria-label", s.label + " (runs " + s.tool + (s.arguments.dry_run === true ? ", dry run)" : ")"));
        b.setAttribute("data-tool", s.tool);
        b.addEventListener("click", function () { runOrSay(s.tool, JSON.parse(JSON.stringify(s.arguments)), s.say, out, b); });
      }
      row.appendChild(b);
    });
    wrap.appendChild(row); wrap.appendChild(out); box.appendChild(wrap);
    return true;
  }
  // A tool's answer drawn on the card: the check rows when it has them, its own next steps, else resultView.
  function answerView(tool, r) {
    var d = answerOf(r), box = el("div", null, "nx-res");
    if (isObj(d) && isObj(d.checks)) {
      var lines = isObj(d.kg_card) && Array.isArray(d.kg_card.lines) ? d.kg_card.lines.filter(readable) : [];
      var res = el("div", null, "res-box");
      res.appendChild(el("p", lines.length ? lines.join(" ") : (readable(d.summary) || tool + " answered.")));
      box.appendChild(res);
      renderChecks(d, box);
    } else {
      box.appendChild(resultView(tool, r));
    }
    if (isObj(d)) renderNext(d, box);
    return box;
  }
  var STATE_WORD = { passed: "passed", failed: "failed", not_checked: "not checked" };
  function renderChecks(data, box) {
    var c = isObj(data.checks) ? data.checks : null, rows = c && Array.isArray(c.rows) ? c.rows.filter(isObj) : [];
    if (!rows.length) return false;
    var wrap = el("section", null, "ck"); wrap.setAttribute("aria-label", "Every key and link");
    var sum = el("ul", null, "ck-sum"), n = isObj(c.counts) ? c.counts : {};
    ["passed", "failed", "not_checked"].forEach(function (s) {
      var li = el("li"); li.appendChild(el("span", (Number(n[s]) || 0) + " " + STATE_WORD[s], "pill pill-" + s)); sum.appendChild(li);
    });
    wrap.appendChild(sum);
    var t = el("table", null, "ck-table"), head = el("tr");
    ["What", "State", "In the rows"].forEach(function (h) { var th = el("th", h); th.scope = "col"; head.appendChild(th); });
    var thead = el("thead"); thead.appendChild(head); t.appendChild(thead);
    var tb = el("tbody");
    rows.forEach(function (x) {
      var tr = el("tr"); tr.setAttribute("data-check", String(x.id || ""));
      var what = el("td"); what.appendChild(el("span", (x.kind === "key" ? "Key " : x.kind === "link" ? "Link " : "Amount ") + String(x.label || "")));
      if (readable(x.rule)) { what.appendChild(document.createTextNode(" ")); what.appendChild(el("span", x.rule, "pill pill-rule")); }
      var st = STATE_WORD[x.state] ? x.state : "not_checked";
      var state = el("td"); state.appendChild(el("span", STATE_WORD[st], "pill pill-" + st));
      var counts = el("td", readable(x.counts) ? x.counts : "");
      if (st === "failed" && typeof x.sql === "string" && x.sql) {
        var b = el("button", "Show the SQL that counts it"); b.type = "button"; b.setAttribute("aria-expanded", "false");
        var pre = el("pre", x.sql, "ck-sql"); pre.hidden = true;
        b.addEventListener("click", function () { pre.hidden = !pre.hidden; b.setAttribute("aria-expanded", String(!pre.hidden)); });
        counts.appendChild(el("br")); counts.appendChild(b); counts.appendChild(pre);
      }
      tr.appendChild(what); tr.appendChild(state); tr.appendChild(counts); tb.appendChild(tr);
    });
    t.appendChild(tb); wrap.appendChild(t);
    if (readable(c.left_out)) wrap.appendChild(el("p", c.left_out, "muted"));
    box.appendChild(wrap);
    return true;
  }
"""


# n220: a link step opens with ui/open-link where the host offers it, else the address is shown. Left out of review_plan's
# card (js(links=False)), which loads nothing, opens nothing and names no creating tool (tests/test_n124_review_card.py).
OPEN_JS = r"""
  function openOrShow(url, out, button) {
    out.hidden = false;
    var show = function () { out.textContent = "Open this address: " + url; };
    if (!(isObj(hostCaps) && isObj(hostCaps.openLinks))) { show(); return; }
    request("ui/open-link", { url: url }).then(function () { out.textContent = "Opened in your browser."; }, show);
  }
"""


def js(links: bool = True) -> str:
    import json
    return (NEXT_JS.replace("__NEXT_TOOLS__", json.dumps(list(STEP_TOOLS)))
            .replace("__DRY_TOOLS__", json.dumps(list(DRY_RUN_TOOLS) if links else []))
            .replace("__LINKS__", "true" if links else "false").replace("__OPEN_JS__", OPEN_JS if links else ""))
