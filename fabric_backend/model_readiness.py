"""FA1: what a Power BI semantic model needs before an app is built from it in Power BI Desktop for Apps (preview).

Microsoft's app builder starts every app from an existing semantic model hosted in the Power BI service; its agent
writes DAX queries against the tables, columns and measures the model defines. These checks are deterministic rules
over the model's TMDL definition (read with Fabric's documented getDefinition, or passed as files). No AI model is
used, nothing is written, and nothing is guessed: what Krusgraph cannot read through a documented API is "unknown"
with the portal path.

Every check carries `basis`:
- "microsoft_learn": the requirement is stated on a Microsoft Learn page, cited in `source` (read on 19 November 2026,
  each page's own date in docs/APP-READINESS-MODEL.md);
- "krusgraph": Krusgraph's own rule for a model people can trust (keys and relationships), not a Microsoft requirement;
- "not_documented": Microsoft's pages do not say whether the app builder's agent reads it; shown as information only.
"""
from __future__ import annotations

import re

from .model_compare import from_tmdl

# Microsoft Learn pages these checks rest on (read 19 November 2026; dates in docs/APP-READINESS-MODEL.md)
LEARN = {
    "overview": "https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/overview",
    "setup": "https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/setup",
    "create": "https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/create-app",
    "publish": "https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/publish-app",
    "template": "https://learn.microsoft.com/fabric/apps/data-apps-template",
    "connectors": "https://learn.microsoft.com/fabric/apps/connectors",
    "tenant": "https://learn.microsoft.com/fabric/admin/service-admin-portal-copilot#power-bi-desktop-for-apps",
    "prep_ai": "https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai",
}
NEXT_STEP_TITLE = "Build an app in Power BI Desktop for Apps"

_OBJ = re.compile(r"^(\t*)(table|column|measure|role|relationship|partition|hierarchy|calculationGroup)\b\s*(.*)$")
_PROP = re.compile(r"^\t+(dataCategory)\s*:\s*(.+)$")


def _scan(parts: dict[str, str]) -> dict:
    """What from_tmdl does not keep: descriptions (/// lines above an object), the date table (dataCategory: Time),
    roles (row-level security) and linguistic metadata (cultures/*.tmdl)."""
    out = {"described": set(), "date_tables": [], "roles": [], "cultures": []}
    for path in sorted(parts):
        if not path.endswith(".tmdl"):
            continue
        if path.split("/")[-2:-1] == ["cultures"] and "linguisticMetadata" in parts[path]:
            out["cultures"].append(path.rsplit("/", 1)[-1][:-5])
        table = None
        pending_doc = False
        for raw in parts[path].splitlines():
            s = raw.strip()
            if s.startswith("///"):
                pending_doc = bool(s[3:].strip()) or pending_doc
                continue
            if not s:
                continue
            o = _OBJ.match(raw)
            if o:
                depth, kind, rest = len(o.group(1)), o.group(2), o.group(3)
                name = _name(rest)
                if depth == 0 and kind == "table":
                    table = name
                if depth == 0 and kind == "role":
                    out["roles"].append(name)
                if pending_doc and kind in ("table", "column", "measure"):
                    out["described"].add((kind, table if kind != "table" else name, name if kind != "table" else ""))
                pending_doc = False
                continue
            pending_doc = False
            p = _PROP.match(raw)
            if p and table and len(raw) - len(raw.lstrip("\t")) == 1 and p.group(2).strip() == "Time":
                out["date_tables"].append(table)
    return out


def _name(rest: str) -> str:
    rest = rest.strip()
    if rest.startswith("'"):
        end = rest.find("'", 1)
        while end != -1 and rest[end + 1:end + 2] == "'":
            end = rest.find("'", end + 2)
        return rest[1:end].replace("''", "'") if end != -1 else rest[1:]
    return re.split(r"\s|=", rest, maxsplit=1)[0]


def _check(check: str, status: str, basis: str, reason: str, detail: str = "", next_step: str = "", source: str = "") -> dict:
    return {"check": check, "status": status, "basis": basis, "reason": reason, "detail": detail, "next_step": next_step,
            "source": source}


def _few(names: list[str], n: int = 8) -> str:
    return ", ".join(names[:n]) + (f" and {len(names) - n} more" if len(names) > n else "")


def assess(parts: dict[str, str], model: str, hosted: bool = True) -> dict:
    """The checks for one semantic model's TMDL parts, each with status ok / missing / info / unknown, its basis and
    source, a plain reason and the next step; plus a one-line verdict and the next step card."""
    m = from_tmdl(parts)
    extra = _scan(parts)
    tables = m["tables"]
    data_tables = [t for t, v in tables.items() if v.get("columns") or v.get("measures")]
    measures = [(t, n, v) for t, tv in tables.items() for n, v in tv.get("measures", {}).items()]
    no_format = [f"{t}[{n}]" for t, n, v in measures if not v.get("format_string")]
    linked = {r.get("from_table") for r in m["relationships"]} | {r.get("to_table") for r in m["relationships"]}
    unlinked = sorted(t for t in data_tables if t not in linked) if len(data_tables) > 1 else []
    date_cols = sorted(f"{t}[{c}]" for t, tv in tables.items() for c, cv in tv.get("columns", {}).items()
                       if str(cv.get("data_type") or "").lower() == "datetime" and t not in extra["date_tables"])
    keyed = [t for t, tv in tables.items() if any(c.get("is_key") for c in tv.get("columns", {}).values())]
    described_tables = {k[1] for k in extra["described"] if k[0] == "table"}
    described_measures = {(k[1], k[2]) for k in extra["described"] if k[0] == "measure"}
    undescribed = [f"{t}[{n}]" for t, n, _ in measures if (t, n) not in described_measures]

    checks = [
        _check("hosted", "ok" if hosted else "info", "microsoft_learn",
               "Power BI Desktop for Apps only connects to semantic models hosted in the Power BI service; local models are not supported.",
               "read from the Fabric workspace" if hosted else "read from the TMDL files you passed, not from the service",
               "" if hosted else "Publish the model to a workspace first (create_semantic_model does that from a Krusgraph plan).",
               LEARN["overview"]),
        _check("tables", "ok" if data_tables else "missing", "microsoft_learn",
               "The app's agent queries the model's own tables, columns and measures; Microsoft's template tells it not to guess names.",
               f"{len(data_tables)} table(s)" if data_tables else "the definition has no tables",
               "" if data_tables else "Build the model's tables first (semantic_model_draft, then create_semantic_model).",
               LEARN["template"]),
        _check("measures", "ok" if measures else "missing", "microsoft_learn",
               "Microsoft's template uses the fields and measures that exist in the model. Without measures, each total in the app "
               "is a sum the app writes itself instead of one definition in the model.",
               f"{len(measures)} measure(s)" if measures else "no measures",
               "" if measures else "Add measures for the numbers the app must show (semantic_model_draft suggests them from the plan).",
               LEARN["template"]),
        _check("format_strings", ("ok" if not no_format else "missing") if measures else "info", "microsoft_learn",
               "Microsoft's template formats cards, charts, tooltips and grids with the model's format strings.",
               ("every measure has a format string" if not no_format else "no format string: " + _few(no_format)) if measures else "no measures to format",
               "" if not no_format else "Give each listed measure a formatString in the model (for example #,0 or 0.0%).",
               LEARN["template"]),
        _check("relationships", "ok" if not unlinked else "missing", "krusgraph",
               "A query that filters one table by another needs a relationship between them; without it the numbers do not follow the filter.",
               "every table is in at least one relationship" if not unlinked else "in no relationship: " + _few(unlinked),
               "" if not unlinked else "compare_semantic_model checks the model's links against a Krusgraph plan and the rows; add the ones that hold.",
               ""),
        _check("keys", "ok" if keyed else "info", "krusgraph",
               "A key column marked in the model is the one side of its relationships; Krusgraph proves keys unique on the rows before it marks them.",
               f"key column marked in {len(keyed)} table(s)" if keyed else "no key column is marked (isKey)",
               "" if keyed else "validate_plan counts the keys on the rows; create_semantic_model marks the proven ones.",
               ""),
        _check("date_table", "ok" if extra["date_tables"] else ("info" if date_cols else "ok"), "krusgraph",
               "A marked date table lets every measure be cut by month and year the same way in the app.",
               ("marked: " + ", ".join(extra["date_tables"])) if extra["date_tables"] else
               ("date columns but no table marked as the date table: " + _few(date_cols) if date_cols else "no date columns"),
               "" if extra["date_tables"] or not date_cols else "Mark a date table (dataCategory: Time); Krusgraph's semantic model draft adds one.",
               ""),
        _check("descriptions", "info", "not_documented",
               "Microsoft's pages do not say whether the app builder's agent reads descriptions; they help the people who maintain the app.",
               f"{len(described_tables)} of {len(data_tables)} table(s) and {len(measures) - len(undescribed)} of {len(measures)} measure(s) have a description",
               "", LEARN["overview"]),
        _check("row_level_security", "info", "microsoft_learn",
               "The semantic model connector uses delegated sign-in only: each app user queries as themselves and needs Read permission on the model.",
               (f"{len(extra['roles'])} role(s): " + _few(extra["roles"])) if extra["roles"] else "no roles in the definition",
               "Whether a role's filter applies inside the app was not tested by Krusgraph; test with a user who is in the role.",
               LEARN["connectors"]),
        _check("prep_data_for_ai", "info", "not_documented",
               "AI instructions, verified answers and the AI data schema are documented for Copilot in Power BI; Microsoft's pages do not say that "
               "Power BI Desktop for Apps reads them.",
               ("linguistic metadata in: " + ", ".join(extra["cultures"])) if extra["cultures"] else "no linguistic metadata in the definition",
               "", LEARN["prep_ai"]),
        _check("permissions", "unknown", "microsoft_learn",
               "Building the app needs Build permission on the model; each person who uses the app needs Read permission on it, besides access to the app.",
               "Fabric's REST API does not let Krusgraph read who holds Build or Read on a model",
               f"{model} -> Manage permissions: give the app's author Build and its users Read.", LEARN["publish"]),
        _check("tenant_settings", "unknown", "microsoft_learn",
               "Three tenant settings must be on: Fabric Apps, Users can use Power BI Desktop for Apps (on by default) and Semantic Model "
               "Execute Queries REST API.",
               "reading tenant settings needs a Fabric administrator",
               "Admin portal -> Tenant settings: check the three settings, or ask your Fabric administrator.", LEARN["tenant"]),
        _check("workspace_capacity", "unknown", "microsoft_learn",
               "Power BI Desktop for Apps publishes to a workspace on Fabric capacity; Microsoft says publishing to Pro workspaces is coming soon.",
               "the app's workspace is chosen when it is published", "Pick a workspace on Fabric capacity (or a trial) when you publish.",
               LEARN["publish"]),
    ]
    missing = [c["check"] for c in checks if c["status"] == "missing"]
    unknown = [c["check"] for c in checks if c["status"] == "unknown"]
    ok = [c["check"] for c in checks if c["status"] == "ok"]
    verdict = (f"{len(ok)} check(s) pass; " + (f"{len(missing)} need a step ({', '.join(missing)}); " if missing else "")
               + f"{len(unknown)} cannot be read through Fabric's API ({', '.join(unknown)}): confirm in the portal")
    return {
        "semantic_model": model, "for": "an app built from this model in Power BI Desktop for Apps (preview)",
        "checks": checks, "missing": missing, "unknown": unknown, "verdict": verdict,
        "next_step": {"title": NEXT_STEP_TITLE, "url": LEARN["overview"],
                      "says": "Microsoft's app builder (preview): pick this model, describe the app, review it, publish it to Fabric. "
                              "It needs Power BI Desktop (November 2026 or later) on Windows 11 and a GitHub Copilot licence. "
                              "Krusgraph does not build the app."},
        "note": "Computed by rules from the model's definition (TMDL); no AI, nothing changed. Unit-tested on synthetic models; "
                "not yet run against Power BI Desktop for Apps.",
    }
