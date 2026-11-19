"""Which lakehouse schemas hold the silver tables and the gold views an output reads (round WB2, issues #54 and #55).

LT1, 17-18 November 2026, demo workspace, synthetic SAP tables: the pipeline sap_lt1_pipeline wrote its silver tables to
sap_silver and its gold views to sap_gold. A semantic model built from the same plan read silver.<table> (empty, or not
there at all), and verify_build rebuilt the pipeline's notebooks with silver and gold and called them "differs" for that
reason alone.

One rule for every output that reads silver or gold (semantic model, ontology, data agent, gold views, verify_build), by
the first that names a schema:

  1 the call's arguments (silver_schema, gold_schema), or the Model editor's build request, which passes them the same
    way to the dry run and to Create;
  2 the pipeline named by the call's `pipeline` argument: its notebooks' parameters (SILVER_SCHEMA = ..., GOLD_SCHEMA = ...);
  3 the one Krusgraph pipeline built from this source and schema in the build's workspace (its description "Krusgraph
    pipeline for <source>.<schema>"), read the same way; when several such pipelines disagree, none is guessed;
  4 the defaults, silver and gold.

Each answer says where its schemas came from (`said`). Reading a pipeline uses Fabric's documented Get Item Definition
(POST /v1/workspaces/{ws}/dataPipelines/{id}/getDefinition and .../notebooks/{id}/getDefinition); nothing is written.
No AI: a regular expression over the notebooks' parameter cell.
"""
from __future__ import annotations

import ast
import re

from .infer import PlanInputError

DEFAULT_SILVER, DEFAULT_GOLD = "silver", "gold"
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
# the parameter cell the silver, gold and check notebooks write (silver.py, gold.py, pipeline.py): NAME = "value"  # ...
_CONST = re.compile(r"^[ \t]*(SILVER_SCHEMA|GOLD_SCHEMA)[ \t]*=[ \t]*(\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*')", re.M)
PIPELINE_MARK = re.compile(r"krusgraph pipeline for (.+?)\s*$", re.I)


class LayerSchemaError(PlanInputError):
    """A schema name that cannot be a lakehouse schema (answered kind bad_input)."""


def check(name: str, what: str) -> str:
    value = (name or "").strip()
    if not _IDENT.match(value):
        raise LayerSchemaError(f"{what}: letters, digits and underscores, starting with a letter (for example "
                               f"{DEFAULT_SILVER if what.startswith('silver') else DEFAULT_GOLD!r}); got {name!r}")
    return value


def from_notebook(text: str) -> dict:
    """{"silver": ..., "gold": ...} as the notebook's parameter cell sets them; a constant it does not set is left out."""
    out = {}
    for m in _CONST.finditer(text or ""):
        key = "silver" if m.group(1) == "SILVER_SCHEMA" else "gold"
        if key in out:
            continue
        try:
            value = ast.literal_eval(m.group(2))
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, str) and _IDENT.match(value):
            out[key] = value
    return out


def from_notebooks(texts) -> dict:
    """The schemas the pipeline's notebooks set, the first notebook that sets each one wins (silver, gold, check)."""
    out: dict = {}
    for t in texts:
        for k, v in from_notebook(t).items():
            out.setdefault(k, v)
    return out


def resolve(silver: str | None = None, gold: str | None = None, *, found: dict | None = None, found_from: str = "") -> dict:
    """{silver, gold, from: {silver, gold}, said}: the call's arguments first, then `found` (a pipeline's notebooks),
    then the defaults. `found_from` names where `found` was read ("the pipeline sap_lt1_pipeline")."""
    out, src = {}, {}
    for key, given, default in (("silver", silver, DEFAULT_SILVER), ("gold", gold, DEFAULT_GOLD)):
        if (given or "").strip():
            out[key], src[key] = check(given, f"{key}_schema"), "the call's arguments"
        elif (found or {}).get(key):
            out[key], src[key] = found[key], found_from or "the pipeline's notebooks"
        else:
            out[key], src[key] = default, "the default"
    return {**out, "from": src, "said": said(out, src)}


def said(schemas: dict, src: dict) -> str:
    if src["silver"] == src["gold"]:
        return f"Silver tables in {schemas['silver']}, gold views in {schemas['gold']} (from {src['silver']})."
    return (f"Silver tables in {schemas['silver']} (from {src['silver']}), gold views in {schemas['gold']} "
            f"(from {src['gold']}).")


def pipeline_label(description: str | None) -> str | None:
    """"<source>.<schema>" from a Krusgraph pipeline's description, or None."""
    m = PIPELINE_MARK.search(str(description or "").strip())
    return m.group(1).strip().rstrip(".") if m else None


def pipelines_of(listing, label: str) -> list[dict]:
    """The workspace's Krusgraph pipelines built for this source and schema (label "<source>.<schema>"), not a drift
    monitor (whose description says "drift monitor")."""
    want = (label or "").lower()
    return [i for i in listing or [] if isinstance(i, dict) and i.get("type") == "DataPipeline"
            and (pipeline_label(i.get("description")) or "").lower() == want]


def notebook_ids(pipeline_content: dict) -> list[str]:
    """The notebook ids a pipeline runs, in the order of its activities (silver, gold, check)."""
    ids = []
    for a in (pipeline_content or {}).get("properties", {}).get("activities", []) or []:
        tp = a.get("typeProperties") or {}
        nid = tp.get("notebookId")
        if nid and str(nid) not in ids:
            ids.append(str(nid))
    return ids


def read_pipeline(pipeline: dict, read_parts) -> dict:
    """{"silver": ..., "gold": ...} from a pipeline item: its definition's notebook ids, then each notebook's parameter
    cell. read_parts(kind, id) -> {path: text} (Get Item Definition). The check notebook sets both; any one is enough."""
    import json
    content = json.loads((read_parts("dataPipelines", pipeline["id"]) or {}).get("pipeline-content.json") or "{}")
    out: dict = {}
    for nid in reversed(notebook_ids(content)):                    # the check notebook first: it sets both
        out = {**from_notebook((read_parts("notebooks", nid) or {}).get("notebook-content.py") or ""), **out}
        if "silver" in out and "gold" in out:
            break
    return out


def discover(listing, label: str, read_parts, name: str = "") -> tuple[dict, str, str]:
    """(found, found_from, note) for a call without schema arguments: the pipeline named `name`, else the one Krusgraph
    pipeline of this source and schema. found is {} when there is none, when it could not be read, or when several
    pipelines set different schemas (then nothing is guessed and the note says so)."""
    if name:
        hit = next((i for i in listing or [] if i.get("type") == "DataPipeline"
                    and name.lower() in (str(i.get("displayName") or "").lower(), str(i.get("id") or "").lower())), None)
        if not hit:
            return {}, "", f"No pipeline named {name} in the workspace; the default schemas are used."
        cands = [hit]
    else:
        cands = pipelines_of(listing, label)
        if not cands:
            return {}, "", ""
    seen = []
    for c in cands:
        try:
            got = read_pipeline(c, read_parts)
        except Exception as e:                                     # noqa: BLE001 - not read is said, never guessed
            return {}, "", (f"The pipeline {c.get('displayName')} could not be read ({type(e).__name__}); the default "
                            "schemas are used. Pass silver_schema and gold_schema to be sure.")
        if got:
            seen.append((c.get("displayName") or c.get("id"), got))
    if not seen:
        return {}, "", ""
    if len({tuple(sorted(g.items())) for _, g in seen}) > 1:
        names = ", ".join(f"{n} ({g.get('silver', '?')}/{g.get('gold', '?')})" for n, g in seen)
        return {}, "", (f"Several Krusgraph pipelines of this source set different schemas: {names}. None is guessed; "
                        "pass pipeline= or silver_schema and gold_schema.")
    n, got = seen[0]
    return got, f"the pipeline {n} (its notebooks' parameters)" + ("" if len(seen) == 1 else f" and {len(seen) - 1} more that agree"), ""
