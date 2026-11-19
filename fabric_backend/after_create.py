"""After a Create: the next steps of the data product, and the gate before a build that would be of no use (round n229).

The founder, 12 November 2026, in Claude with the hosted connector: "no more suggestions after we built what was
proposed", and, on the SAP-shaped sample: the semantic model's dry run said "Relationships: 0 active, 0 inactive, 24
not expressible" and the card still offered "Yes, create demo_lh_model_3 in Fabric" as its first button; he pressed it.

Two pure functions over what the tools already know; nothing here reads Fabric and nothing uses an AI model.

`next_steps(...)`  the guided path after a Create, in the order of what the data product still lacks:
    1 verify what was built (verify_build, read-only)      5 the data agent (experimental)
    2 refresh the model once                               6 the Rayfin App (an empty App item and one package command)
    3 the pipeline: silver, gold, check; Run once/Schedule 7 a drift monitor
    4 the report                                           8 register as a data product (owner, contract)
  and under More, labelled as a draft: "Download a dbt project draft" (S1 froze the dbt drafts, docs/SCOPE-REVIEW.md).
  Each step has one sentence from the mascot who would say it (the Thinker checks, the Builder builds, Onto names
  things) and one way to take it: a read-only tool, a dry run of a creating tool, or a sentence for the chat. No step
  writes. A step whose item already exists from this plan is not suggested again: it is listed as "already built".

`gate(...)`  for a dry run: when it has no relationship the model can express (or most are not), when the model reads
  silver tables that are not there yet, or when most of an ontology's entity types have no key, one sentence says so and
  the step that fixes it comes first; Create stays, second, as "Create anyway".
"""
from __future__ import annotations

import re

ALREADY = "already built"
MOST = 0.5                      # "most": more than half
# kind -> (Fabric item type, the words Krusgraph writes into the description of an item of that kind)
BUILT_BY = {
    "semantic_model": ("SemanticModel", r"created by krusgraph from "),
    "ontology": ("Ontology", r"created by krusgraph from "),
    "report": ("Report", r"created by krusgraph on the semantic model "),
    "pipeline": ("DataPipeline", r"krusgraph pipeline for "),
    "drift_monitor": ("DataPipeline", r"krusgraph drift monitor for "),
    "data_agent": ("DataAgent", r"krusgraph"),
    "api": ("GraphQLApi", r"krusgraph"),
    "app": ("AppBackend", r"krusgraph"),
}
ORDER = ("verify", "refresh", "pipeline", "report", "data_agent", "app", "drift_monitor", "data_product")
MORE = ("dbt",)
LABEL = {
    "verify": "Verify what was built",
    "refresh": "Refresh the model once",
    "pipeline": "Build the pipeline (silver, gold, check)",
    "report": "Create a report on it",
    "data_agent": "Create a data agent (experimental)",
    "app": "A Rayfin App (preview)",
    "drift_monitor": "Add a drift monitor",
    "data_product": "Register it as a data product",
    "dbt": "Download a dbt project draft",
}
WHO = {"verify": "thinker", "refresh": "builder", "pipeline": "builder", "report": "builder", "data_agent": "builder",
       "app": "builder", "drift_monitor": "thinker", "data_product": "onto", "dbt": "builder"}
WHY = {
    "verify": "I read back what Fabric holds and count the figures again from the rows, so you know it is what the dry run showed.",
    "refresh": "A new Direct Lake model shows no data until it is refreshed once; one refresh frames its tables.",
    "pipeline": "Nothing keeps the silver tables and the gold views up to date yet; the pipeline does, and its check fails the run when a key or a sum breaks.",
    "report": "The model has measures and no page that shows them; I draw one page from its own measures.",
    "data_agent": "Krusgraph checks the joins once, with evidence and your approval; your data agent then reuses them in "
                  "topics and templates, so people can ask the data in words (experimental: try its questions first).",
    "app": "Honest: I make an empty App item and a package with one command; the App opens inside Fabric only.",
    "drift_monitor": "Tables and columns change; a nightly monitor tells you when the plan no longer matches the source.",
    "data_product": "It has items and no owner or contract yet; with those, others know whom to ask and what is promised.",
    "dbt": "A draft only: the dbt drafts are frozen, and the project has not run against your warehouse.",
}
# what each step needs to have been built first, by kind
NEEDS = {"refresh": "semantic_model", "report": "semantic_model"}
BUILDS = {"pipeline": "pipeline", "report": "report", "data_agent": "data_agent", "app": "app", "drift_monitor": "drift_monitor"}
VERIFY_KINDS = ("semantic_model", "report", "ontology", "api", "pipeline", "app")


def built_from_plan(items, source: str, schema: str, source_name: str | None = None) -> dict[str, list[str]]:
    """{kind: [names]} of the workspace's items that Krusgraph built from this source and schema, read from the item
    type and the description Krusgraph writes ("Created by Krusgraph from demo_lh (shop)", "Krusgraph pipeline for
    demo_lh.shop", ...). A report names its model, not the source, so it counts when its model is one of these. An item
    without such a description is someone else's and is never taken for built."""
    names = {str(n).lower() for n in (source, source_name) if n}
    sch = str(schema or "").lower()
    out: dict[str, list[str]] = {}

    def mine(text: str) -> bool:
        low = text.lower()
        return any(re.search(rf"\b{re.escape(n)}\s*[.(]\s*{re.escape(sch)}\b", low) for n in names) if sch else any(n in low for n in names)
    rows = [i for i in items or [] if isinstance(i, dict) and i.get("displayName")]
    for kind, (typ, words) in BUILT_BY.items():
        if kind == "report":
            continue
        for i in rows:
            d = str(i.get("description") or "")
            if str(i.get("type")) == typ and re.search(words, d.lower()) and mine(d):
                out.setdefault(kind, []).append(i["displayName"])
    models = {m.lower() for m in out.get("semantic_model", [])}
    for i in rows:
        d = str(i.get("description") or "").lower()
        m = re.search(BUILT_BY["report"][1] + r"(.+)$", d)
        if str(i.get("type")) == "Report" and m and m.group(1).strip().rstrip(".") in models:
            out.setdefault("report", []).append(i["displayName"])
    return out


def _shown(args: dict) -> str:
    import json
    return ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in args.items())


def _base(source: str, schema: str | None) -> str:
    raw = schema if schema and str(schema).lower() != "dbo" else source
    base = re.sub(r"[^A-Za-z0-9_]+", "_", str(raw or "")).strip("_") or "krusgraph"
    return ("kg_" + base if base[0].isdigit() else base)[:60]


def next_steps(created: str, args: dict, built: dict[str, list[str]] | None = None, name: str | None = None,
               lakehouse: bool = True, taken=None) -> dict:
    """{"next_steps": [...], "more": [...], "already_built": [...]} after a Create of kind `created` (semantic_model,
    report, ontology, api, pipeline, data_agent, drift_monitor) named `name`. `args`: the call's workspace, source,
    schema, keys and confirmed. `built`: built_from_plan's answer (None: the workspace could not be listed; then only
    the item just created counts as built). `taken`: the workspace's item names, for the names the steps suggest."""
    import json
    built = {k: list(v) for k, v in (built or {}).items()}
    if name and name.lower() not in {n.lower() for n in built.get(created, [])}:
        built.setdefault(created, []).append(name)
    common = {k: args[k] for k in ("workspace", "source", "schema", "keys", "confirmed") if args.get(k) not in (None, "", [], {})}
    schema = common.get("schema")
    base = _base(str(args.get("source") or ""), schema)
    low = {str(t).lower() for t in taken or []} | {n.lower() for v in built.values() for n in v}

    def free(wanted: str) -> str:
        cand, i = wanted, 1
        while cand.lower() in low and i < 200:
            i += 1
            cand = f"{wanted}_{i}"
        return cand
    model = (built.get("semantic_model") or [None])[-1]
    items = {k: built[k][-1] for k in VERIFY_KINDS if built.get(k)}
    steps, done = [], []

    def step(key: str, **how) -> None:
        steps.append({"step": key, "label": LABEL[key], "who": WHO[key], "why": WHY[key], **how})
    for key in ORDER:
        kind = BUILDS.get(key)
        if kind and built.get(kind):
            done.append({"step": key, "label": LABEL[key], "state": ALREADY, "name": built[kind][-1]})
            continue
        need = NEEDS.get(key)
        if need and not built.get(need):
            continue
        if key == "verify":
            if items:
                va = {**common, "items": items}
                step(key, tool="verify_build", args=va, ask=f"Verify what was built: run verify_build with {_shown(va)}.")
        elif key == "refresh":
            ra = {**common, "name": model, "refresh": True, "dry_run": False}
            step(key, ask=f"Refresh the semantic model {model} once: run create_semantic_model with {_shown(ra)}. It updates "
                          "the model in place with the same definition and then refreshes it once; ask me to confirm first.")
        elif key == "pipeline":
            if not lakehouse:
                steps.append({"step": key, "label": LABEL[key], "who": WHO[key], "state": "not available",
                              "why": "The pipeline writes silver tables into a lakehouse; this source is not one, so there is none to build."})
                continue
            pa = {**common, "name": free(f"pipeline_{base}"), "dry_run": True}
            step(key, ask=f"Show the pipeline as a dry run: run create_pipeline with {_shown(pa)}. Then offer me the two choices "
                          "for the Create: Run once (run_once=true) and a Schedule (schedule), both off unless I choose them.",
                 choices=["Run once", "Schedule"])
        elif key == "report":
            ra = {"workspace": args.get("workspace"), "model": model, "name": free(f"{model}_report"), "dry_run": True}
            step(key, tool="create_report", args=ra, ask=f"Show a report on {model} as a dry run: run create_report with {_shown(ra)}.")
        elif key == "data_agent":
            aa = {**common, "name": free(f"{base}_agent"), "dry_run": True}
            step(key, ask=f"Show a data agent as a dry run: run create_data_agent with {_shown(aa)}. Say that it is experimental.")
        elif key == "app":
            step(key, ask="What does the Rayfin App (preview) take? Say it plainly: Krusgraph for Fabric makes an empty App item "
                          "and a package with one command, and the App opens inside Fabric only. From this chat, rayfin_connector "
                          f"gives the connector's entities for {_shown({k: v for k, v in common.items() if k in ('workspace', 'source', 'schema')})}.")
        elif key == "drift_monitor":
            if not lakehouse:
                continue
            da = {**common, "name": free(f"drift_monitor_{base}"), "dry_run": True}
            da.pop("keys", None), da.pop("confirmed", None)
            step(key, ask=f"Show a drift monitor as a dry run: run create_drift_monitor with {_shown(da)}.")
        elif key == "data_product":
            pa = {k: v for k, v in common.items() if k != "keys"}
            step(key, ask=f"Draft the data product with an owner and a contract: run domain_draft with {_shown(pa)}, then ask me "
                          "who owns it.")
    da = {k: v for k, v in common.items() if k in ("workspace", "source", "schema", "keys", "confirmed")}
    more = [{"step": "dbt", "label": LABEL["dbt"], "who": WHO["dbt"], "why": WHY["dbt"], "draft": True,
             "ask": f"Give me the dbt project as a draft, labelled as a draft: run dbt_schema with {_shown({**da, 'project': True})}."}]
    for i, s in enumerate(steps, start=1):
        s["order"] = i
    return {"next_steps": steps, "more": more, "already_built": done,
            "next_steps_note": "By rules, in the order of what the data product still lacks. No step writes: each is a read, a "
                               "dry run or a question; a Create comes only from its own dry run."}


# ------------------------------------------------------------------ the gate ------------------------------------------

def _fix_pipeline(args: dict, why: str, lakehouse: bool = True) -> dict:
    common = {k: args[k] for k in ("workspace", "source", "schema", "keys", "confirmed") if args.get(k) not in (None, "", [], {})}
    base = _base(str(args.get("source") or ""), common.get("schema"))
    pa = {**common, "name": f"pipeline_{base}", "dry_run": True}
    return {"step": "pipeline", "label": "Build the silver step first", "who": "builder", "why": why,
            "ask": f"Show the pipeline as a dry run first: run create_pipeline with {_shown(pa)}. Its silver step writes the "
                   "combined key columns; after it has run, build the semantic model again."}


def model_gate(summary: dict, args: dict, lakehouse: bool = True, silver_there: bool | None = None, name: str | None = None) -> dict | None:
    """The gate for a semantic model's dry run, or None when Create is the right first button. `summary` is
    semantic_model.draft's; `silver_there`: whether the silver tables the model would read exist (None: not known)."""
    a, i, n = (int(summary.get(k) or 0) for k in ("relationships_active", "relationships_inactive", "relationships_not_expressible"))
    total = a + i + n
    what = name or "this model"
    if n and (a + i == 0 or n / total > MOST):
        said = (f"{n} of the plan's {total} relationship(s) cannot be expressed in the model as the tables stand"
                + (" and none can" if a + i == 0 else "") + f": {what} would be tables side by side, with nothing to slice by.")
        composite = any(len(r.get("columns") or []) > 1 or len(r.get("target_columns") or []) > 1 for r in summary.get("not_expressible") or [])
        if lakehouse:
            first = _fix_pipeline(args, "The relationships need one combined key column per composite key; my silver step writes "
                                        "them, and the model then relates on them.")
        else:
            first = {"step": "keys", "label": "Add combined key columns first", "who": "builder",
                     "why": "A relationship takes one column per side; this source is not a lakehouse, so I cannot write the "
                            "combined key columns for you.",
                     "ask": "Which relationships are not expressible and why? Run semantic_model_draft for the same source and list "
                            "summary.not_expressible; then show the combined key column each needs (in a view or a table of the source)."}
        return {"gate": "relationships", "said": said + (" They use several columns per side (a composite key)." if composite else ""),
                "first": first, "create": "Create anyway", "counts": {"active": a, "inactive": i, "not_expressible": n}}
    reads = summary.get("reads") if isinstance(summary.get("reads"), dict) else None
    if reads and reads.get("layer") == "silver" and silver_there is False:
        cols = len(summary.get("combined_key_columns") or [])
        said = (f"{what} would read the silver tables ({reads.get('schema') or 'silver'}), which are not there yet: its "
                f"{a + i} relationship(s) rest on {cols} combined key column(s) that only the silver step writes, so the model "
                "would show errors until that step has run.")
        return {"gate": "silver_missing", "said": said, "create": "Create anyway",
                "first": _fix_pipeline(args, "The model reads my silver tables and they do not exist yet; the pipeline writes them, "
                                             "with the combined key columns the relationships need."),
                "counts": {"active": a, "inactive": i, "not_expressible": n}}
    return None


def ontology_gate(summary: dict, args: dict, lakehouse: bool = True, name: str | None = None) -> dict | None:
    """The gate for an ontology's dry run: most entity types without a key (nothing can point at a keyless entity)."""
    total, keyed = int(summary.get("entity_types") or 0), int(summary.get("with_key") or 0)
    if not total or (total - keyed) / total <= MOST:
        return None
    said = (f"{total - keyed} of the {total} entity types have no key, so nothing can point at them and "
            f"{int(summary.get('skipped_relationships') or 0)} relationship(s) are left out: {name or 'this ontology'} would be a "
            "list of entities without links.")
    if lakehouse:
        first = _fix_pipeline(args, "An ontology key is one string or integer property; my silver step writes one combined key "
                                    "column per composite key, and the ontology then uses it.")
    else:
        first = {"step": "keys", "label": "Give the keys first", "who": "thinker",
                 "why": "Without a key an entity is only a list of properties; tell me the key of each table and I use it.",
                 "ask": "Which tables have no key in the plan? Run plan_backend for the same source and list them, then ask me for each key "
                        "(the keys argument)."}
    return {"gate": "keyless", "said": said, "first": first, "create": "Create anyway",
            "counts": {"entity_types": total, "with_key": keyed}}
