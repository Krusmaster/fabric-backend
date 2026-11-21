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
        ("next", "Next step", [
            "Showing these settings in the dry-run card before Create, with the outputs that card would build, comes "
            "after the start card's current work (docs/SMOOTH/PLAN.md); until then this page and "
            "`fabric_backend.tenant_settings.markdown(outputs)` say it.",
        ]),
    ]


TITLE = "Getting started: what Krusgraph reads and what your admin turns on"
INTRO = ("Read this before the first build. It says what Krusgraph reads and with which permission, which Fabric "
         "tenant settings each output needs, the limits, and how to start with a small set of tables.")


def _table_md() -> str:
    out = ["| Output | Tenant setting | Status | Why | Learn page (read " + READ_ON + ") | Current value |",
           "| --- | --- | --- | --- | --- | --- |"]
    for r in rows():
        setting = r["setting"] or "none"
        if r["when"] not in ("", "always"):
            setting += f" ({r['when']})"
        out.append(f"| {r['output_label']} | {setting} | {r['status']} | {r['why']} | <{r['learn']}> | {r['live']} |")
    return "\n".join(out)


def getting_started_md() -> str:
    parts = [f"> {READ_ON}, round BL2. Generated by `python -m fabric_backend.tenant_settings --write` from "
             "`fabric_backend/tenant_settings.py`; edit the module, not this file.", "", f"# {TITLE}", "", INTRO, ""]
    for sid, heading, paras in _sections():
        parts += [f"## {heading}", ""]
        for p in paras:
            parts += [p, ""]
        if sid == "settings":
            parts += [_table_md(), "", "For a set of outputs, `tenant_settings.markdown([...])` writes the request in "
                      "order. For all of them:", "", markdown(list(OUTPUTS)), ""]
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


def page_html() -> str:
    """The body of /getting-started, from the same sections and rows as the doc."""
    out = []
    for sid, heading, paras in _sections():
        out.append(f'<h2 id="{sid}">{html.escape(heading)}</h2>')
        out += [f"<p>{_inline(p)}</p>" for p in paras]
        if sid == "settings":
            out += [_table_html(), "<p>For every output, ask your administrator in this order (Admin portal → Tenant "
                    "settings):</p>", _asks_html()]
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
