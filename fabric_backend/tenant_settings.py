"""BL2 (21 November 2026, sprint item BL2, backlog C-29 and C-28): the Fabric tenant settings each output needs.

The first pilot or Marketplace tenant should learn before it starts which tenant settings its administrator must turn
on, rather than meet an HTTP 403 at Create. This module is the one source: `REQUIRED` maps each output Krusgraph can
build to the settings it needs, each with the Microsoft Learn page it was read on and the date it was read. A pairing
the Learn page does not state in so many words is marked "unverified".

Krusgraph does not read the live value of a tenant setting: that is the Fabric Admin API, which needs a Fabric
administrator's permission the app does not ask for. So every row says "could not be read; ask your admin".
Krusgraph never changes a tenant setting.

Deterministic: fixed tables, no model call. `getting_started_md()` is docs/GETTING-STARTED.md and `page_html()` the
body of /getting-started; tests/test_bl2_tenant_settings.py keeps the three equal.

BL53 (23 November 2026, backlog C-28): the same page opens with the steps for a first pilot tenant, in order (`STEPS`):
who does each, what it needs and the error `kind` a missing step answers with; the two ways to run Krusgraph today,
and what it never does. tests/test_bl53_pilot_getting_started.py keeps those tied to the code they describe.
Regenerate the doc with `python -m fabric_backend.tenant_settings --write`.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

READ_ON = "2026-11-21"                       # the day every Learn page below was opened and read (round BL2)
LIVE = "could not be read; ask your admin"   # the live value is never read (the Admin API needs admin permission)
CONFIRMED, UNVERIFIED = "confirmed", "unverified"

LEARN = "https://learn.microsoft.com/en-us/fabric/"

# id: (the setting's name as the admin portal shows it, Learn page, the page's own date, default, when it applies)
SETTINGS: dict[str, dict] = {
    "fabric_items": {
        "name": "Users can create Fabric items",
        "section": "Microsoft Fabric",
        "learn": LEARN + "admin/fabric-switch",
        "page_date": "2026-08-27",
        "default": "set by the tenant; can be overridden per capacity",
        "when": "always",
    },
    "ontology": {
        "name": "Users can create Ontology (preview) items",
        "section": "Microsoft Fabric",
        "learn": LEARN + "admin/service-admin-portal-microsoft-fabric-tenant-settings",
        "page_date": "2026-04-08",
        "default": "not stated on the page",
        "when": "always",
    },
    "copilot": {
        "name": "Users can use Copilot and other features powered by Azure OpenAI",
        "section": "Copilot and Azure OpenAI Service",
        "learn": LEARN + "data-science/data-agent-tenant-settings",
        "page_date": "2026-04-20",
        "default": "on",
        "when": "always",
    },
    "copilot_capacity": {
        "name": "Capacities can be designated as Fabric Copilot capacities",
        "section": "Copilot and Azure OpenAI Service",
        "learn": LEARN + "data-science/data-agent-tenant-settings",
        "page_date": "2026-04-20",
        "default": "on",
        "when": "always",
    },
    "aoai_process": {
        "name": "Data sent to Azure OpenAI can be processed outside your capacity's geographic region, compliance "
                "boundary, or national cloud instance",
        "section": "Copilot and Azure OpenAI Service",
        "learn": LEARN + "data-science/data-agent-tenant-settings",
        "page_date": "2026-04-20",
        "default": "off",
        "when": "only when the capacity's region is outside the EU data boundary and the US",
    },
    "aoai_store": {
        "name": "Data sent to Azure OpenAI can be stored outside your capacity's geographic region, compliance "
                "boundary, or national cloud instance",
        "section": "Copilot and Azure OpenAI Service",
        "learn": LEARN + "data-science/data-agent-tenant-settings",
        "page_date": "2026-04-20",
        "default": "off",
        "when": "only when the capacity's region is outside the EU data boundary and the US",
    },
}

# The outputs, in the order a build usually makes them, with a label for people.
OUTPUTS: dict[str, str] = {
    "lakehouse": "Lakehouse",
    "notebook": "Notebook",
    "pipeline": "Pipeline",
    "semantic_model": "Semantic model",
    "report": "Report",
    "ontology": "Ontology",
    "data_agent": "Data agent",
    "graphql_api": "API for GraphQL",
    "catalog_write": "OneLake catalog write",
}

_POWER_BI = ("Learn: turning off \"Users can create Fabric items\" doesn't affect users' ability to create Power BI items; "
             "no other tenant setting for creating it was found")

# output: [(setting id or None, status, why)]. None means no tenant setting is needed (or none was found).
REQUIRED: dict[str, list[tuple[str | None, str, str]]] = {
    "lakehouse": [("fabric_items", CONFIRMED, "Learn names lakehouses among the Fabric items this setting allows")],
    "notebook": [("fabric_items", CONFIRMED, "Learn names notebooks among the Fabric items this setting allows")],
    "pipeline": [("fabric_items", UNVERIFIED, "a pipeline is a Fabric item, not a Power BI item; Learn does not name "
                                              "pipelines on this page")],
    "semantic_model": [(None, CONFIRMED, _POWER_BI + "; a Direct Lake model still needs the workspace on a Fabric capacity")],
    "report": [(None, CONFIRMED, _POWER_BI)],
    "ontology": [("ontology", CONFIRMED, "the setting for Ontology (preview) items; Create answers HTTP 403 "
                                         "FeatureNotAvailable while it is off (docs/LIVE-TEST.md, section 6)"),
                 ("fabric_items", UNVERIFIED, "an ontology is a Fabric item; Learn does not say whether this setting "
                                              "also applies to it")],
    "data_agent": [("fabric_items", UNVERIFIED, "a data agent is a Fabric item; Learn does not name it on this page"),
                   ("copilot", CONFIRMED, "listed as required for a Fabric data agent"),
                   ("copilot_capacity", CONFIRMED, "listed as required for a Fabric data agent"),
                   ("aoai_process", CONFIRMED, "listed as required outside the EU data boundary and the US"),
                   ("aoai_store", CONFIRMED, "listed as required outside the EU data boundary and the US")],
    "graphql_api": [("fabric_items", UNVERIFIED, "an API for GraphQL is a Fabric item; Learn's overview of it names no "
                                                 "tenant setting")],
    "catalog_write": [(None, UNVERIFIED, "no tenant setting found for setting item descriptions or adding existing tags; "
                                         "new tags and domains need a Fabric administrator (docs/CATALOG-ACCELERATOR.md)")],
}

GRAPHQL_OVERVIEW = LEARN + "data-engineering/api-graphql-overview"
CATALOG_DOC = "https://github.com/Krusmaster/fabric-backend/blob/main/docs/CATALOG-ACCELERATOR.md"
_NO_SETTING_LEARN = {"semantic_model": SETTINGS["fabric_items"]["learn"], "report": SETTINGS["fabric_items"]["learn"],
                     "catalog_write": CATALOG_DOC}


def _check_outputs(outputs) -> list[str]:
    out = []
    for o in outputs:
        key = str(o).strip().lower().replace(" ", "_").replace("-", "_")
        if key not in OUTPUTS:
            raise ValueError(f"unknown output {o!r}; known: {', '.join(OUTPUTS)}")
        if key not in out:
            out.append(key)
    return out


def rows() -> list[dict]:
    """Every (output, setting) pair, one dict each: the full table."""
    out = []
    for o, needs in REQUIRED.items():
        for sid, status, why in needs:
            s = SETTINGS.get(sid, {}) if sid else {}
            out.append({"output": o, "output_label": OUTPUTS[o], "setting": s.get("name"), "setting_id": sid,
                        "status": status, "why": why, "when": s.get("when", ""), "default": s.get("default", ""),
                        "learn": s.get("learn") or _NO_SETTING_LEARN.get(o) or GRAPHQL_OVERVIEW,
                        "page_date": s.get("page_date", ""), "read_on": READ_ON,
                        "live": LIVE if sid else "nothing to read"})
    return out


def for_outputs(outputs) -> list[dict]:
    """What to ask the admin for, in order: one row per distinct setting the given outputs need, first needed first.
    Outputs that need no setting are left out. Unknown outputs raise ValueError."""
    keys = _check_outputs(outputs)
    seen: dict[str, dict] = {}
    for o in keys:
        for sid, status, why in REQUIRED[o]:
            if sid is None:
                continue
            if sid not in seen:
                s = SETTINGS[sid]
                seen[sid] = {"setting": s["name"], "setting_id": sid, "section": s["section"], "learn": s["learn"],
                             "page_date": s["page_date"], "read_on": READ_ON, "default": s["default"], "when": s["when"],
                             "status": status, "outputs": [], "live": LIVE}
            row = seen[sid]
            row["outputs"].append(OUTPUTS[o])
            if status == CONFIRMED:                                  # confirmed for one output is confirmed
                row["status"] = CONFIRMED
    return list(seen.values())


# BL40: the short names the dry run's one line uses (the full names are in SETTINGS and the admin request).
SHORT = {"fabric_items": "Fabric items", "ontology": "Ontology (preview)", "copilot": "Copilot",
         "copilot_capacity": "Copilot capacities", "aoai_process": "Azure OpenAI processing",
         "aoai_store": "Azure OpenAI storage"}
# BL40: the outputs each creating tool of the guided path builds (start_flow.BUILDS)
TOOL_OUTPUTS = {"create_pipeline": ["notebook", "pipeline"], "create_semantic_model": ["semantic_model"],
                "create_report": ["report"], "create_backend": ["graphql_api"], "create_ontology": ["ontology"],
                "create_data_agent": ["data_agent"]}


def dry_run_line(outputs) -> str:
    """BL40 (C-29): the dry run's one line on tenant settings, at most 25 words: which settings the outputs need, and
    that their live value could not be read (it takes a Fabric admin). It never blocks the dry run."""
    names = [SHORT.get(r["setting_id"], r["setting"]) for r in for_outputs(outputs)]
    if not names:
        return "Needs no tenant setting."
    return f"Needs tenant settings: {', '.join(names)}. Not checked; ask your admin if Create fails."


def no_setting(outputs) -> list[str]:
    """The labels of the given outputs that need no tenant setting."""
    return [OUTPUTS[o] for o in _check_outputs(outputs) if all(sid is None for sid, _, _ in REQUIRED[o])]


def markdown(outputs) -> str:
    """The admin request for these outputs, as a numbered Markdown list."""
    asks = for_outputs(outputs)
    lines = ["Ask your Fabric administrator, in this order (Admin portal → Tenant settings):", ""]
    if not asks:
        lines.append("Nothing: these outputs need no tenant setting.")
    for i, a in enumerate(asks, 1):
        when = "" if a["when"] == "always" else f" ({a['when']})"
        flag = " **Unverified**." if a["status"] == UNVERIFIED else ""
        lines.append(f"{i}. **{a['setting']}** ({a['section']}){when}, for {', '.join(a['outputs'])}. "
                     f"[Microsoft Learn]({a['learn']}), read {a['read_on']}. Current value: {a['live']}.{flag}")
    free = no_setting(outputs)
    if free and asks:
        lines += ["", f"No tenant setting: {', '.join(free)}."]
    return "\n".join(lines)


# ------------------------------------------------------------------ the getting-started content -----------------------

def _limits() -> dict[str, str]:
    from .pages import _counting_limits
    return _counting_limits()


def _sections() -> list[tuple[str, str, list[str]]]:
    """(id, heading, paragraphs in Markdown-lite: `code`, **bold**, [text](url)). The table is inserted by id."""
    lim = _limits()
    return [
        ("before", "Before you start", [
            "A Microsoft work account, a workspace on a Fabric capacity (an F SKU, a P SKU or a trial capacity; "
            "Learn: per-user licences such as Power BI Pro and PPU don't provide Fabric capacity), and an "
            "administrator who approves the Krusgraph app in Microsoft Entra ID once (admin consent). "
            "The connection itself is on [the set-up guide](/start).",
        ]),
        ("paths", "Two ways to run it", [
            "**The hosted MCP server, available now.** Your AI client (Claude, or another MCP client) connects to "
            "Krusgraph and you work in chat; [the set-up guide](/start) has the address and the steps. Everything on "
            "this page works on this path.",
            "**The Krusgraph Model item inside Fabric.** The same engine as an item type in your workspace "
            "(+ New item → Krusgraph Model). Its listing in Fabric's Workload Hub is pending, so it cannot yet be added "
            "from the Hub. What your administrator does for it, and how to try it before then, is on "
            "[the Fabric pilot page](/pilot/fabric).",
        ]),
        ("steps", "Steps for a first pilot, in order", [
            "Who does what, from \"we have Fabric\" to the first items built. Each step says which error a missing "
            "step answers with: every error has a `kind`, a stable name, and a `hint` that says what fixes it.",
        ]),
        ("never", "What Krusgraph never does", [
            "**Shows no row values unless you ask.** The guided path and the check return counts, not row values. "
            "Rows come back only from a tool you ask for them: `sample_rows` (up to 20 rows of one table, with columns "
            "that look like personal data masked by name) or `query_graphql` (the query you ask for).",
            "**Deletes nothing.** No MCP tool deletes an item in Fabric, and the creating tools never write over the "
            "tables they read. In the Fabric item, only the data product page's Delete from Fabric deletes, after a dry "
            "run and the data product's name typed.",
            "**Uses only your permissions.** Every call runs as the signed-in person, with delegated permissions; the "
            "app has no application permissions, so it reaches nothing that person cannot already reach.",
            "**Creates nothing on its own.** Every creating tool answers with a dry run first; only `dry_run=false` "
            "creates, and the guided path asks you to confirm the names before that.",
            "**Leaves your settings alone.** It never reads or changes tenant settings, capacity settings or Entra "
            "settings.",
        ]),
        ("reads", "What Krusgraph reads, and with which permission", [
            "Planning reads names and types: the workspace's items, each source's schemas, tables and columns. "
            "Checking runs read-only counting queries (`COUNT`, `GROUP BY`) on the tables you check. "
            "Every call runs as the signed-in person with delegated permissions, so Krusgraph reaches nothing that "
            "person cannot already reach. Nothing is created until a creating tool is called with `dry_run=false`.",
            "The permissions, what each is used for and why, are listed for your IT department on [/it](/it#permissions).",
        ]),
        ("settings", "Tenant settings per output", [
            "What your Fabric administrator must turn on before you build each output. Krusgraph does not read the "
            "current value: that needs the Fabric Admin API and a Fabric administrator's permission, which the app does "
            "not ask for. Every row therefore says: " + LIVE + ". Krusgraph never changes a tenant setting. "
            "\"Unverified\" means the Learn page does not say it in so many words. Settings can take up to an hour to "
            "take effect after they are turned on (Learn, data agent tenant settings).",
        ]),
        ("schemas", "Every schema is listed", [
            "When `plan_backend` is called without a schema and the source has more than one, it lists every schema "
            "with its tables and plans nothing until you choose one.",
        ]),
        ("limits", "Limits", [
            f"`validate_plan` counts up to {lim['VALIDATE_MAX_ITEMS']} keys and links per call by default (200 at most), "
            "keys first, and lists what it did not count; call it again with `resume_from` for the rest.",
            f"Rule R5 in `plan_backend` reads the first {lim['R5_SAMPLE']} distinct values of a candidate column with at "
            f"most {lim['R5_MAX_QUERIES']} counting queries.",
            "`plan_backend` answers in full up to 60 tables and as a summary above that (`detail`).",
        ]),
        ("not-supported", "What is not supported", [
            "Reading or changing tenant settings, capacity settings or Entra settings. Application permissions "
            "(every call is a person's). Writing to a source table: the creating tools add new items and never write "
            "over the tables they read.",
        ]),
        ("scope", "How to scope to 20 tables", [
            "Name the tables, or a glob such as `sales_*`, in `tables`: `plan_backend` then shows only those, and "
            "`validate_plan` counts only their keys and links. Planning still reads the names and types of the whole "
            "schema, so a link to a table outside the 20 is not lost.",
            "Example: \"Plan the 20 tables `sales_*` and `customer` in the schema `dbo`, then check them.\"",
        ]),
        ("next", "In the dry run", [
            "The guided path's dry run names, in one line, the tenant settings its outputs need, and says that their "
            "value was not checked. For a chosen set of outputs, `fabric_backend.tenant_settings.markdown(outputs)` "
            "writes the request to your administrator in order.",
        ]),
    ]


# BL53 (C-28): the steps for a first pilot tenant, in order: who, what, the text, and the error kinds a missing step
# answers with. Every kind is a key of errors.HINTS; every tool named is an MCP tool (tests/test_bl53_pilot_getting_started.py).
FIRST_OUTPUTS = ["graphql_api", "semantic_model", "report"]


def _scopes_text() -> str:
    """The app's delegated permissions, from fabric_backend/access.py (read here, never changed)."""
    from . import access
    by: dict[str, list[str]] = {}
    for g in access.GRANTED:
        by.setdefault(g.resource, []).append(f"`{g.scope}`")
    return "; ".join(f"{r}: {', '.join(v)}" for r, v in by.items())


def steps() -> list[dict]:
    first = ", ".join(f"**{a['setting']}**" for a in for_outputs(FIRST_OUTPUTS)) or "none"
    return [
        {"who": "Entra administrator", "title": "Approve the app once (admin consent)", "kinds": ["consent"],
         "text": "A Global Administrator or Privileged Role Administrator grants admin consent for the Krusgraph app "
                 "in Microsoft Entra ID, once for the organisation. The permissions it asks for, all delegated: "
                 + _scopes_text() + ". Why each is needed, and how to revoke it: [For your IT department](/it#permissions)."},
        {"who": "Fabric administrator", "title": "A capacity, a workspace and a role", "kinds": ["capacity", "no_access"],
         "text": "A workspace on a Fabric capacity (F SKU, P SKU or trial), with a lakehouse or warehouse that has test "
                 "or sample tables. Viewer on the workspace is enough for the data lead to plan; creating items needs "
                 "Contributor."},
        {"who": "Fabric administrator", "title": "Turn on the tenant settings for the outputs you want",
         "kinds": ["feature_disabled", "fabric_refused"],
         "text": "Admin portal → Tenant settings, from the table under \"Tenant settings per output\" below. For a first "
                 "API for GraphQL, semantic model and report that is " + first + ". Krusgraph cannot read these "
                 "settings: when one is off, Create is refused (HTTP 403) and the answer quotes Fabric's own error code."},
        {"who": "Data lead", "title": "Connect, and try the synthetic sample first", "kinds": ["sign_in"],
         "text": "Add Krusgraph to your AI client as [the set-up guide](/start) says and sign in with your work "
                 "account. Then ask \"Show me on the synthetic shop sample\" (the `start` tool with `sample=true`): "
                 "the whole path on synthetic data, reading nothing in your Fabric. In the Fabric item, \"Is everything "
                 "ready? Check this workspace\" reads consent, capacity, workspace and lakehouse instead, and changes "
                 "nothing."},
        {"who": "Data lead", "title": "Choose your data and check it against the rows",
         "kinds": ["not_found", "schema_not_found"],
         "text": "Say \"start Krusgraph\". The `start` tool lists your workspaces, sources and schemas to choose from "
                 "(start with about 20 tables; see \"How to scope to 20 tables\" below). `plan_backend` proposes keys "
                 "and relationships, each with the rule that found it; `validate_plan` counts them against the rows: "
                 "unique keys, empty keys, references that find no row. You decide on each one."},
        {"who": "Data lead", "title": "Dry run, create, then verify", "kinds": ["consent", "feature_disabled"],
         "text": "The dry run shows every item that would be created, and the tenant settings it needs. Nothing is "
                 "created until you confirm the names (`dry_run=false`). Afterwards `verify_build` reads back what was "
                 "built and compares it with the dry run, by rules, not by AI."},
    ]


TITLE = "Getting started: what Krusgraph reads and what your admin turns on"
INTRO = ("Read this before the first pilot. It says who does what, in order, to try Krusgraph on your own Fabric data; "
         "what Krusgraph reads and with which permission, which Fabric tenant settings each output needs, the limits, "
         "and how to start with a small set of tables.")


def _table_md() -> str:
    out = ["| Output | Tenant setting | Status | Why | Learn page (read " + READ_ON + ") | Current value |",
           "| --- | --- | --- | --- | --- | --- |"]
    for r in rows():
        setting = r["setting"] or "none"
        if r["when"] not in ("", "always"):
            setting += f" ({r['when']})"
        out.append(f"| {r['output_label']} | {setting} | {r['status']} | {r['why']} | <{r['learn']}> | {r['live']} |")
    return "\n".join(out)


def _kinds(kinds: list[str]) -> str:
    return ", ".join(f"`{k}`" for k in kinds)


def _steps_md() -> str:
    return "\n".join(f"{i}. **{x['title']}** ({x['who']}). {x['text']} Errors that point here: {_kinds(x['kinds'])}."
                      for i, x in enumerate(steps(), 1))


def getting_started_md() -> str:
    parts = [f"> {READ_ON}, round BL2. Steps for a first pilot added 2026-11-23, round BL53. Generated by `python -m fabric_backend.tenant_settings --write` from "
             "`fabric_backend/tenant_settings.py`; edit the module, not this file.", "", f"# {TITLE}", "", INTRO, ""]
    for sid, heading, paras in _sections():
        parts += [f"## {heading}", ""]
        for p in paras:
            parts += [p, ""]
        if sid == "settings":
            parts += [_table_md(), "", "For a set of outputs, `tenant_settings.markdown([...])` writes the request in "
                      "order. For all of them:", "", markdown(list(OUTPUTS)), ""]
        if sid == "steps":
            parts += [_steps_md(), ""]
    return "\n".join(parts).rstrip() + "\n"


def _inline(text: str) -> str:
    import re
    t = html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{html.escape(m.group(2), quote=True)}"'
               + (' rel="noopener"' if m.group(2).startswith("http") else "") + f">{m.group(1)}</a>", t)
    return t


def _table_html() -> str:
    body = []
    for r in rows():
        setting = html.escape(r["setting"] or "none")
        if r["when"] not in ("", "always"):
            setting += f' <span class="muted tiny">({html.escape(r["when"])})</span>'
        body.append(f"<tr><td>{html.escape(r['output_label'])}</td><td>{setting}</td><td>{r['status']}</td>"
                    f"<td>{_inline(r['why'])}</td><td><a href=\"{html.escape(r['learn'], quote=True)}\" rel=\"noopener\">"
                    f"{'Microsoft Learn' if 'learn.microsoft.com' in r['learn'] else 'Krusgraph docs'}</a></td>"
                    f"<td>{html.escape(r['live'])}</td></tr>")
    return ('<div class="table-wrap" tabindex="0"><table class="gs-settings"><caption>Tenant settings per output, read '
            f'on Microsoft Learn on {READ_ON}</caption><thead><tr><th scope="col">Output</th><th scope="col">Tenant setting</th>'
            '<th scope="col">Status</th><th scope="col">Why</th><th scope="col">Source</th><th scope="col">Current value</th>'
            f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')


def _asks_html() -> str:
    items = []
    for a in for_outputs(list(OUTPUTS)):
        when = "" if a["when"] == "always" else f" ({html.escape(a['when'])})"
        flag = " <em>Unverified.</em>" if a["status"] == UNVERIFIED else ""
        items.append(f"<li><strong>{html.escape(a['setting'])}</strong> ({html.escape(a['section'])}){when}, for "
                     f"{html.escape(', '.join(a['outputs']))}.{flag}</li>")
    return f'<ol class="gs-asks">{"".join(items)}</ol>'


def _steps_html() -> str:
    items = [f'<li id="step-{i}"><strong>{html.escape(x["title"])}</strong> <span class="muted">({html.escape(x["who"])})</span>. '
             f'{_inline(x["text"])} Errors that point here: {_inline(_kinds(x["kinds"]))}.</li>'
             for i, x in enumerate(steps(), 1)]
    return f'<ol class="gs-steps">{"".join(items)}</ol>'


def page_html() -> str:
    """The body of /getting-started, from the same sections and rows as the doc."""
    out = []
    for sid, heading, paras in _sections():
        out.append(f'<h2 id="{sid}">{html.escape(heading)}</h2>')
        out += [f"<p>{_inline(p)}</p>" for p in paras]
        if sid == "settings":
            out += [_table_html(), "<p>For every output, ask your administrator in this order (Admin portal → Tenant "
                    "settings):</p>", _asks_html()]
        if sid == "steps":
            out.append(_steps_html())
    return "\n  ".join(out)


DOC = Path(__file__).resolve().parents[1] / "docs" / "GETTING-STARTED.md"


def main(argv: list[str]) -> int:
    if "--write" in argv:
        DOC.write_text(getting_started_md(), encoding="utf-8")
        print(f"wrote {DOC}")
        return 0
    outputs = [a for a in argv if not a.startswith("-")] or list(OUTPUTS)
    print(markdown(outputs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
