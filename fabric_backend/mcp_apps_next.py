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
# n227: what the client model is asked to do after a card, in the result's lead and in the server's instructions. A
# request with its reason, never a threat: the model decides; the sentence says what helps the user.
AFTER_CARD = ("Where the client drew a card, the user has already read these lines and can press the steps, so repeating "
              "them is not needed; where it drew none, show the numbered list as it is. Please say only what the answer "
              "says: add no reason, source or name (for example where a key comes from, or what another vendor calls a "
              "link) that is not in it.")
# The same request for the server's instructions (server.py and mcp_server.py), where no card is in sight yet.
AFTER_RESULT = ("After a tool result: a client that draws the result as a card has already shown its lines and its next "
                "steps as buttons, so there is no need to repeat them in the reply; a client that draws no card gets the "
                "next steps as a numbered list to show as it is, and the user answers with a number. Say what the answer "
                "says and no more: please add no reason, source or name that is not in it (for example where a key comes "
                "from, or what another vendor calls a link); when the user asks for more than the answer holds, say that "
                "the answer does not tell.")
# Next steps may name only these tools: they read or draft; none creates anything in Fabric.
STEP_TOOLS = ("validate_plan", "plan_backend", "review_plan", "semantic_model_draft", "list_tables", "join_path",
              "data_dictionary", "ontology_draft", "gold_views_draft")    # WB13 (#91): the gold views' draft reads
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
# WB13 (#92): on Gustav's phone the ontology's Turtle was printed in the chat and ran off the screen. The card keeps a
# file behind a closed section; the lead asks the client model not to print it.
FILE_TOOLS = ("ontology_draft", "create_ontology", "dbt_schema")
FILES_STAY = (" Please do not print file contents from the JSON (the Turtle file, TMDL, SQL or YAML) in the reply: the "
              "card keeps them behind a closed section such as Show the ontology file, and they run off a phone's screen.")


def _carried(args: dict, *keys) -> dict:
    return {k: args[k] for k in keys if args.get(k) not in (None, "", [], {})}


def _step(label: str, tool: str, arguments: dict, about: str = "") -> dict:
    """`say` is what a text client reads (it names the tool and its arguments); `ask` is the same step in plain words,
    which the card shows and sends to the chat (n227: no tool name in what the user reads)."""
    shown = ", ".join(f"{k}={v!r}" for k, v in arguments.items() if k in ("source", "schema", "detail", "fixes", "validate", "name"))
    say = f"{label}{(' ' + about) if about else ''}: run {tool}" + (f" with {shown}" if shown else "") + "."
    return {"label": label, "tool": tool, "arguments": dict(arguments), "say": say,
            "ask": f"{label}{(' ' + about) if about else ''}."}


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
# The build card's creating tools (mcp_apps_build.BUILD_TOOLS); create_pipeline has no card, its answer's next_steps are read
# by the model from the JSON.
DRY_RUN_TOOLS = ("create_semantic_model", "create_ontology", "create_backend", "create_report",
                 "create_pipeline", "create_data_agent")   # WB15 (H): every dry run on the path runs from the card
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
                "say": str(s.get("ask") or f"{label}: run {t} as a dry run."), "ask": words.plain(str(s.get("ask") or label + "."))}
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
                    "say": f"Try again: run {tool}" + (" as a dry run." if tool in DRY_RUN_TOOLS else "."),
                    "ask": "Try that again" + (" as a dry run." if tool in DRY_RUN_TOOLS else ".")})
    if len(out) < ERROR_MAX:
        out.append(_say_step("Explain this and what to do", f"Explain Krusgraph's answer from {tool} and what I can do "
                                                            f"next: {err}"))
    return out[:ERROR_MAX]


def steps(tool: str, args: dict, answer: dict, checks: dict | None = None) -> list[dict]:
    """The card's next steps for one answer (2 to 4; 1 to 3 for an error or a refusal, n220; none for a question back
    to the user). WB13 (#91): after plan_backend the rules below; for every other tool next_rules.steps, the most useful
    step first, from the plan state (`checks`: validate_plan's check rows)."""
    if isinstance(answer, dict) and isinstance(answer.get("started"), dict):
        return []                                    # n227: Fabric is still working: the one step is Check status (an action)
    if isinstance(answer, dict) and answer.get("error"):
        return error_steps(tool, args, answer)
    if not isinstance(answer, dict) or answer.get("choose_schema") or answer.get("ask"):
        return []
    if tool == "requirements_draft":                                 # RQ1: its steps name the requirement ids they serve
        from .requirements_draft import next_steps
        return next_steps(args, answer)
    args = {k: v for k, v in (args or {}).items() if k != "ctx"}
    if "workspace" not in args or "source" not in args:
        return []
    base = _source_args(args, answer)
    where = f"for {base.get('schema') or base['source']}"
    out: list[dict] = []
    if tool == "plan_backend":
        # n227 (5): before the check, the card leads with one primary step, Check against the rows (an action,
        # mcp_apps_build.actions_for); nothing here repeats it or suggests a build. These two only read.
        out = [_step(LABEL["doubled"], "validate_plan", {**base, "detail": "full"}, where),
               _step(LABEL["review"], "review_plan", base, where)]
    elif tool in DRY_RUN_TOOLS and answer.get("dry_run") is False and isinstance(answer.get("next_steps"), list):
        out = []                                                     # n229: after a Create the data product's next steps are the
        #                                                              answer's own (after_create.py), drawn with its actions
    else:
        from . import next_rules                                     # WB13 (#91): one rule set, the most useful step first
        if tool not in next_rules.TOOLS:
            return []
        return next_rules.steps(tool, args, answer, checks, can_build=tool != "review_plan")
    return [s for s in out if s["tool"] in STEP_TOOLS][:MAX_STEPS]


def _first_lines(tool: str, answer: dict) -> list[str]:
    card0 = answer.get("kg_card") if isinstance(answer.get("kg_card"), dict) else {}
    if isinstance(answer.get("started"), dict) and card0.get("result"):
        return [str(card0["result"])]
    if answer.get("error"):
        return [str(answer["error"])] + ([str(answer["hint"])] if answer.get("hint") else [])
    if answer.get("choose_schema") or answer.get("ask"):
        return [str(answer.get("summary") or answer.get("ask"))]
    if tool == "validate_plan" and isinstance(answer.get("totals"), dict):
        own = (answer.get("kg_card") or {}).get("lines") if isinstance(answer.get("kg_card"), dict) else None
        return list(own) if own else words.check_lines(answer)       # WB13 (#90): the card's own lines, with the split
    card = answer.get("kg_card") if isinstance(answer.get("kg_card"), dict) else {}
    lines = [x for x in card.get("lines") or [] if isinstance(x, str) and x.strip()]
    if isinstance(card.get("result"), str) and card["result"].strip():     # n227: the one-line result, then the lines
        return [card["result"].strip()] + lines
    if lines:
        return lines
    s = answer.get("summary")
    if isinstance(s, str) and s.strip():
        return [s.strip()]
    if tool in ("create_semantic_model", "create_ontology", "create_backend", "create_report"):
        return ["Dry run: nothing was created." if answer.get("dry_run") is not False else "Done."]
    return []


def _for_assistant(tool: str, arguments: dict | None, dry_run: bool = False, create: bool = False) -> str:
    """Which call a numbered step is, for the client model only: the tool and what sets this call apart."""
    keep = {k: v for k, v in (arguments or {}).items() if k in ("detail", "fixes", "validate", "name", "model", "check")}
    told = ", ".join(f"{k}={v!r}" for k, v in keep.items())
    how = ", as a dry run" if dry_run else ", dry_run=false, only after the user confirms" if create else ""
    return f"{tool}" + (f" ({told})" if told else "") + how


def numbered(next_steps: list[dict], actions: list | None = None) -> list[tuple[str, str]]:
    """The steps a card would show as buttons, in the card's order: the actions (the one primary step first), then the
    next steps; each (plain label, the call for the assistant). At most seven (three builds and four next steps), none twice."""
    out: list[tuple[str, str]] = []
    seen = set()
    # n229: a created item's list (its next steps and what is already built) may be longer
    cap = 12 if any(isinstance(a, dict) and a.get("kind") in ("say", "done") for a in actions or []) else 7

    def add(label: str, call: str) -> None:
        if label not in seen and len(out) < cap:
            seen.add(label)
            out.append((label, call))
    first = [s for s in next_steps if s.get("primary")]                # WB13 (#91): the primary step comes first
    for s in first:
        if s.get("tool"):
            add(s["label"], _for_assistant(s["tool"], s.get("arguments"), s["tool"] in DRY_RUN_TOOLS))
        else:
            add(s["label"], f"the user asks \u201c{s.get('say')}\u201d")
    for a in actions or []:
        if not isinstance(a, dict) or not a.get("label"):
            continue
        if a.get("kind") == "done":                                   # n229: already built: listed, nothing to run
            add(f"{a['label']}: already built" + (f" ({a['name']})" if a.get("name") else ""), "already built, nothing to run")
            continue
        if a.get("kind") == "say":                                    # n229: a question for the chat
            add(a["label"] + (f" ({a['why']})" if a.get("why") else ""), f"the user asks \u201c{a.get('say')}\u201d")
            continue
        label = a["label"] + (f" ({a['name']})" if a.get("name") and a.get("kind") == "dry_run" else
                              f" {a['name']}" if a.get("name") and a.get("kind") == "create" else "")
        if a.get("kind") == "link" and a.get("url"):                  # the address itself: a client without cards shows it
            add(f"{label}: {a['url']}", "the user opens that address")
        elif a.get("kind") in ("dry_run", "create", "call", "status") and a.get("tool"):
            add(label, _for_assistant(a["tool"], a.get("arguments"), a["kind"] == "dry_run", a["kind"] == "create"))
    for s in next_steps:
        if s.get("tool"):
            add(s["label"], _for_assistant(s["tool"], s.get("arguments"), s["tool"] in DRY_RUN_TOOLS))
        elif s.get("url"):
            add(f"{s['label']}: {s['url']}", "the user opens that address")
        elif s.get("start"):                                          # WB13: a sentence that runs the start card's step
            add(s["label"], f"the user asks \u201c{s.get('say')}\u201d")
        else:
            add(s["label"], "answer it in the chat")
    return out


# WB12 (#69): under the start card Claude wrote the card's content again. The start answer's lead says the card shows
# it and asks for one short sentence and the step's question; the JSON after it stays complete for clients without cards.
START_AFTER_CARD = ("For the assistant, not for the user: where the client drew the Start Krusgraph card, the card already "
                    "shows this step with its mascot, its choices and its buttons, and a button there runs the next step "
                    "inside the same card. Please do not repeat, list or summarise what the card shows (no workspaces, "
                    "sources, schemas, links, counts or step lists); reply with one short sentence at most, then the "
                    "step's question: \u201c{q}\u201d. Name the step only as \u201c{head}\u201d. Where no card was drawn, "
                    "say the question and show the choices as a short numbered list in plain words, without tool names "
                    "or arguments.")


def start_lead(answer: dict) -> str:
    """The text a client model reads first after `start` (WB12, #69)."""
    q = answer.get("say") if isinstance(answer.get("say"), str) and answer.get("say").strip() else ""
    if not q:
        found = answer.get("found") if isinstance(answer.get("found"), dict) else {}
        q = found.get("question") if isinstance(found.get("question"), str) else ""
    if not q:
        q = (answer.get("after") or {}).get("label", "") if isinstance(answer.get("after"), dict) else ""
        q = f"Shall we go on? ({q})" if q else "Shall we go on?"
    st = answer.get("step") if isinstance(answer.get("step"), dict) else {}
    name = f"Step {st.get('n')} of {st.get('of')}: {st.get('short') or st.get('title')}" if st.get("n") else "Start Krusgraph"
    head = f"Start Krusgraph, {name[:1].lower() + name[1:]}." if st.get("n") else "Start Krusgraph."
    return "\n\n".join([head, START_AFTER_CARD.format(q=words.plain(q)[:300], head=name),
                         "The full answer follows as JSON."])


def lead(tool: str, answer: dict, next_steps: list[dict], actions: list | None = None) -> str:
    """The result first, in a few short lines, then the next steps as a numbered list in plain words (n227: a client
    that draws no card shows the list and the user replies with a number). The last paragraph is for the client model:
    which call each number is, and what not to add to the card."""
    if tool == "start" and isinstance(answer, dict) and not answer.get("error"):
        return start_lead(answer)
    lines = _first_lines(tool, answer) if isinstance(answer, dict) else []
    out = [" ".join(words.plain(x) for x in lines)[:600]] if lines else []
    todo = numbered(next_steps, actions)
    if todo:
        ns = [str(i) for i in range(1, len(todo) + 1)]
        reply = ns[0] if len(ns) == 1 else ", ".join(ns[:-1]) + " or " + ns[-1]
        out.append("Next steps:\n" + "\n".join(f"{i}. {label}" for i, (label, _) in enumerate(todo, 1))
                   + f"\nReply {reply}.")
        out.append("For the assistant, not for the user: " + "; ".join(f"{i} = {call}" for i, (_, call) in enumerate(todo, 1))
                   + ". The other arguments are in the JSON (actions, or the arguments of this call). " + AFTER_CARD
                   + (FILES_STAY if tool in FILE_TOOLS else ""))
    else:
        out.append("For the assistant, not for the user: " + AFTER_CARD + (FILES_STAY if tool in FILE_TOOLS else ""))
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
               "counts": f"{words._plural(int(k.get('rows') or 0), 'row')}, {k.get('nulls', 0)} empty, {dup} repeated"}
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
               "counts": f"{o} of {words._plural(n, 'row points', 'rows point')} at nothing"}
        if r.get("kind"):                                            # WB13 (#90): a join of plan.extended, not a key link
            row["other"] = True
        if state == "failed":
            row["sql"] = relationship_sql(schema, r["source"], list(r["columns"]), r["target"], list(r["target_columns"]))
        rows.append(row)
        seen_rels.add((r["source"].lower(), tuple(c.lower() for c in r["columns"]), r["target"].lower()))
    for f in _amount_items(full):
        state = {"not_counted": "not_checked"}.get(_amount_status(f), _amount_status(f))
        table = f.get("header") or f.get("table") or ""
        cols = f.get("amount_columns") or ([f["column"]] if f.get("column") else [])
        # LT1: one header amount can be checked over several line tables (VBAP over VBEP, LIPS and VBRP), so the id names
        # the line table too; amount:<table> alone repeated one id for different checks
        rows.append({"kind": "amount", "id": f"amount:{table}" + (f">{f['line']}" if f.get("line") else ""), "label": f"{table}: {', '.join(cols)}"
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
.nx-primary { background: var(--kg-ink); color: var(--kg-bg) }
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
details.ck-all > summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px }
.dec { display: inline-flex; gap: 4px; margin-top: 4px }
.dec button[aria-pressed="true"] { background: var(--kg-ink); color: var(--kg-bg) }
.nx-coach { display: grid; gap: 4px; margin: 0 }
.nx-stage { margin: 0; font-size: 13px; font-weight: 650; color: var(--kg-muted) }
.nx-coach .kg-say { margin: 0 }
html[data-mascots="off"] .nx-coach .kg-fig { display: none }
html[data-mascots="off"] .nx-coach .kg-say { grid-template-columns: minmax(0, 1fr) }
"""

NEXT_JS = r"""
  // WB15 (H): what a card puts in the chat is plain words. A tool's name with its arguments ("run create_data_agent
  // with source=...", "start(step=...)") made claude.ai warn about malicious content; only the label part is sent.
  var FN_SAID = /\b[a-z_]+=(?:"|'|\[|\{|true\b|false\b|\d)|\brun [a-z]+_?[a-z_]*\b(?: with| as)|\b[a-z]+_[a-z_]+\(/i;
  function plainAsk(text) {
    var t = String(text == null ? "" : text).trim();
    if (!FN_SAID.test(t)) return t;
    var head = t.split(/:\s*run\b/i)[0].split(/\s+run\s+[a-z_]+/i)[0].trim();
    head = head.replace(/[a-z_]+\([^)]*\)/gi, "").replace(/\b[a-z_]+=\S+/gi, "").replace(/[\s:,;]+$/, "").trim();
    return (head || "Go on with the next step") + ".";
  }
  function sendChat(text) {
    var t = plainAsk(text).slice(0, 8000);
    return request("ui/message", { role: "user", content: [{ type: "text", text: t }] }).catch(function (e) {
      if (isObj(e) && e.code === -32602) return request("ui/message", { role: "user", content: { type: "text", text: t } });
      throw e;
    });
  }
  // n227: the chat gets the step in plain words (`ask`), which is also what the card shows; `say` (with the tool's
  // name and arguments) stays in the answer for text clients.
  function sayInChat(say, out, button) {
    say = plainAsk(say);
    out.textContent = "Sent to the chat: “" + say + "”";
    return sendChat(say).then(function () { if (button) button.disabled = false; }, function () {
      out.textContent = "This host runs no steps from the card. Type this in the chat: “" + say + "”";
      if (button) button.disabled = false;
    });
  }
  // act (n227): {kind, label, name} of the step, for the progress state ("Builder: Creating shop_api_3 in Fabric…").
  function runOrSay(tool, args, say, out, button, done, act) {
    out.hidden = false;
    if (button) button.disabled = true;
    if (!canCallTools()) { sayInChat(say, out, button); return; }
    out.textContent = "";
    var wait = waitView(act || { label: button ? button.getAttribute("data-label") || button.textContent : "" });
    out.appendChild(wait.el);
    callTool(tool, args, function () { wait.note(stillWaiting(say)); }).then(function (r) {
      wait.stop(); out.textContent = "";
      if (done) done(r); else out.appendChild(answerView(tool, r));
      if (button) button.disabled = false;
    }, function (e) {
      wait.stop();
      if (e && e.kind === "unsupported") { sayInChat(say, out, button); return; }
      if (isObj(act) && act.kind === "create" && !(e && e.kind === "tool")) {
        // n227: the host stopped waiting, so the request may have reached Fabric: Create stays off, and the card
        // offers only to look (act.unknown draws Check status), so nothing is created or updated twice from here.
        var why = e && typeof e.message === "string" && e.message.trim() ? " (" + e.message.trim().slice(0, 120).replace(/[.\s]+$/, "") + ")" : "";
        out.textContent = "";
        out.appendChild(el("p", "The host stopped waiting" + why + ". Fabric may still be creating " + (act.name || "it") + ", so Create is not offered again here. Check its status instead; that only reads.", "warn"));
        if (typeof act.unknown === "function") act.unknown(out);
        return;
      }
      out.textContent = callProblem(e, tool, say);
      if (button) button.disabled = false;
    });
  }
  function askOf(s) { return readable(s.ask) || s.say; }             // plain words first
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
  // CO1 (coach.py): "Step N of 8: <stage>" and one mascot line in plain words, right under the card's title, as the
  // home page's demo chat says each step; the mascot's figure follows Mascots on/off, the words stay
  var COACH_WHO = { onto: "Onto", thinker: "Thinker", builder: "Builder" };
  function coachHead(data) {
    var c = isObj(data) && isObj(data.coach) ? data.coach : null;
    if (!c || !readable(c.title) || !readable(c.line) || !COACH_WHO[c.who]) return false;
    var old = document.querySelector(".nx-coach"); if (old) old.remove();
    var box = el("section", null, "nx-coach"); box.setAttribute("aria-label", "Where you are");
    box.setAttribute("data-stage", String(c.stage || ""));
    box.appendChild(el("p", "Step " + (Number(c.n) || 1) + " of " + (Number(c.of) || 9) + ": " + c.title, "nx-stage"));
    var say = el("div", null, "kg-say " + c.who), fig = el("span", null, "kg-fig");
    var src = document.querySelector('#kg-mascots [data-mascot="' + c.who + '"] svg');
    if (src) { var f = src.cloneNode(true); f.setAttribute("data-pose", String(c.pose || "point")); fig.appendChild(f); }
    var bub = el("div", null, "kg-bub"); bub.appendChild(el("p", COACH_WHO[c.who], "kg-who")); bub.appendChild(el("p", c.line, "nx-line"));
    say.appendChild(fig); say.appendChild(bub); box.appendChild(say);
    var head = document.querySelector("main .kg-head");
    if (head && head.parentNode) head.parentNode.insertBefore(box, head.nextSibling); else return false;
    document.documentElement.setAttribute("data-coach", "1");       // one mascot line: the summary's figures stay off
    var mb = document.getElementById("kg-mascots"); if (mb) { mb.hidden = true; if (typeof mascotsEcho === "function") mascotsEcho(); }
    return true;
  }
  function renderNext(data, box) {
    var coached = coachHead(data);
    var list = (Array.isArray(data.next) ? data.next : []).filter(okStep).slice(0, coached ? 3 : 4);   // CO1: 1 + 2
    if (!list.length) return false;
    var wrap = el("section", null, "nx"); wrap.setAttribute("aria-label", "Next steps");
    wrap.appendChild(el("p", "Next steps", "nx-h"));
    var row = el("div", null, "nx-row"), out = el("div", null, "nx-out");
    list.forEach(function (s) {
      var b = el("button", null, "nx-b" + (s.primary === true ? " nx-primary" : "")); b.type = "button";   // WB13 (#91)
      if (s.primary === true) b.setAttribute("data-primary", "true");
      b.appendChild(el("span", s.label));
      if (typeof s.url === "string") {                                         // n220: a link
        b.setAttribute("aria-label", s.label + " (opens a link)");
        b.addEventListener("click", function () { openOrShow(s.url, out, b); });
      } else if (!s.tool) {                                                    // n220: a sentence for the chat
        b.setAttribute("aria-label", s.label + " (asks in the chat)");
        b.addEventListener("click", function () { out.hidden = false; sayInChat(plainAsk(askOf(s)), out, null); });
      } else {                                                                 // n227: the label alone, no tool's name
        b.setAttribute("aria-label", s.label + (s.arguments.dry_run === true ? " (a dry run: nothing is created)" : ""));
        b.setAttribute("data-tool", s.tool); b.setAttribute("data-label", s.label);
        b.addEventListener("click", function () {
          runOrSay(s.tool, JSON.parse(JSON.stringify(s.arguments)), askOf(s), out, b, null,
                   { kind: s.arguments.dry_run === true ? "dry_run" : "call", label: s.label, name: s.arguments.name });
        });
      }
      row.appendChild(b);
    });
    wrap.appendChild(row);
    if (list[0].primary === true && readable(list[0].why)) wrap.appendChild(el("p", list[0].why, "muted nx-why"));   // WB13: why this one first
    wrap.appendChild(out); box.appendChild(wrap);
    return true;
  }
  // A tool's answer drawn on the card: the check rows when it has them, its own next steps, else resultView.
  function answerView(tool, r) {
    var d = answerOf(r), box = el("div", null, "nx-res");
    if (isObj(d) && isObj(d.checks)) {
      var lines = isObj(d.kg_card) && Array.isArray(d.kg_card.lines) ? d.kg_card.lines.filter(readable) : [];
      var res = el("div", null, "res-box");
      res.appendChild(el("p", lines.length ? lines.join(" ") : (readable(d.summary) || "The check answered.")));
      box.appendChild(res);
      renderNext(d, box);                                       // WB13 (#93): the next step before the long table
      renderChecks(d, box);
    } else {
      box.appendChild(resultView(tool, r));
      if (isObj(d)) renderNext(d, box);
    }
    return box;
  }
  var STATE_WORDS = { passed: "passed", failed: "failed", not_checked: "not checked" }, CK_LONG = 20;
  function renderChecks(data, box) {
    var c = isObj(data.checks) ? data.checks : null, rows = c && Array.isArray(c.rows) ? c.rows.filter(isObj) : [];
    if (!rows.length) return false;
    // n229: the verifier's rows say verified, differs, not checked (checks.words) and name what each row is (row.what)
    var STATE_WORD = {};
    Object.keys(STATE_WORDS).forEach(function (k) { STATE_WORD[k] = isObj(c.words) && readable(c.words[k]) ? String(c.words[k]) : STATE_WORDS[k]; });
    var wrap = el("section", null, "ck"); wrap.setAttribute("aria-label", readable(c.title) ? c.title : "Every key and link");
    if (readable(c.label)) wrap.appendChild(el("p", c.label, "muted ck-label"));
    if (rows.some(function (x) { return x.rule === "SAP pack"; })) sapNote(wrap, "SAP pack");   // n227: said once
    var sum = el("ul", null, "ck-sum"), n = isObj(c.counts) ? c.counts : {};
    ["passed", "failed", "not_checked"].forEach(function (s) {
      var li = el("li"); li.appendChild(el("span", (Number(n[s]) || 0) + " " + STATE_WORD[s], "pill pill-" + s)); sum.appendChild(li);
    });
    wrap.appendChild(sum);
    function table(list) {
    var t = el("table", null, "ck-table"), head = el("tr");
    ["What", "State", "In the rows"].forEach(function (h) { var th = el("th", h); th.scope = "col"; head.appendChild(th); });
    var thead = el("thead"); thead.appendChild(head); t.appendChild(thead);
    var tb = el("tbody");
    list.forEach(function (x) {
      var tr = el("tr"); tr.setAttribute("data-check", String(x.id || ""));
      var what = el("td"); what.appendChild(el("span", (readable(x.what) ? x.what + " " : x.kind === "key" ? "Key " : x.kind === "link" ? "Link " : "Amount ") + String(x.label || "")));
      if (readable(x.rule)) { what.appendChild(document.createTextNode(" ")); what.appendChild(el("span", x.rule, "pill pill-rule")); }
      var st = STATE_WORD[x.state] ? x.state : "not_checked";
      var state = el("td"); state.appendChild(el("span", STATE_WORD[st], "pill pill-" + st));
      var counts = el("td", readable(x.counts) ? x.counts : "");
      if ((st === "failed" || c.sql_for_all === true) && typeof x.sql === "string" && x.sql) {
        var b = el("button", c.sql_for_all === true ? "Show the SQL" : "Show the SQL that counts it"); b.type = "button"; b.setAttribute("aria-expanded", "false");
        var pre = el("pre", x.sql, "ck-sql"); pre.hidden = true;
        b.addEventListener("click", function () { pre.hidden = !pre.hidden; b.setAttribute("aria-expanded", String(!pre.hidden)); });
        counts.appendChild(el("br")); counts.appendChild(b); counts.appendChild(pre);
      }
      tr.appendChild(what); tr.appendChild(state); tr.appendChild(counts); tb.appendChild(tr);
    });
    t.appendChild(tb); return t;
    }
    // WB13 (#93): on a phone a long list of checks is a wall: what failed or was not checked first, every check behind
    // "Show every check", drawn the first time it opens
    if (rows.length > CK_LONG) {
      var first = rows.filter(function (x) { return x.state !== "passed"; }).slice(0, CK_LONG);
      if (first.length) wrap.appendChild(table(first));
      var all = el("details", null, "ck-all"), allBox = el("div");
      all.appendChild(el("summary", "Show every check (" + rows.length + ")")); all.appendChild(allBox);
      all.addEventListener("toggle", function () { if (all.open && !allBox.childNodes.length) allBox.appendChild(table(rows)); });
      wrap.appendChild(all);
    } else wrap.appendChild(table(rows));
    if (readable(c.left_out)) wrap.appendChild(el("p", c.left_out, "muted"));
    if (isObj(data.coach)) {                                    // CO1: the rows, with their rule names, under Details
      var det = el("details", null, "ck-all ck-details");
      det.appendChild(el("summary", "Details: every key and link (" + rows.length + ")")); det.appendChild(wrap);
      box.appendChild(det); return true;
    }
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
