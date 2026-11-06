"""n86b: the Concepts pages of /docs (How it works, Ontologies, Data products, How they connect, Vision).

DOCS.md stays the one source of the text. Its Concepts section carries placeholders ({{CONCEPT_...}}) that are filled
here when the docs are rendered: the examples come from the engine run on the synthetic shop schema (seed.schema("shop"),
infer.plan, ontology, domains, semantic_model), and every status comes from tool_status, so nothing on these pages is
typed by hand that the engine or the status list already says. /docs.md, llms-full.txt and the HTML pages are the same
text; the HTML pages add a figure (HTML and inline SVG in the site's colour tokens, so dark mode follows) in place of the
Markdown between `<!-- figure:NAME -->` and `<!-- /figure -->`, which pages._md_to_html hands to `figures()`.

The tips (`TIPS`) are the two sentences the small question mark next to "ontology" and "data products" opens in place,
in the chat demo and on /check (site.js, window.KGTip); they say the same as the pages they link to.
"""
from __future__ import annotations

import html
import re
from functools import lru_cache

BASE = "/docs/concepts"
PAGES = {"how-it-works": BASE + "/how-it-works", "ontologies": BASE + "/ontologies", "data-products": BASE + "/data-products",
         "how-they-connect": BASE + "/how-they-connect", "where-it-runs": BASE + "/where-it-runs", "vision": BASE + "/vision"}

TIPS = {
    "ontology": {"label": "What is an ontology?", "href": PAGES["ontologies"], "more": "How ontologies work",
                 "text": "An ontology gives your tables and relationships business names: entity types with a key, and "
                         "relationship types between them. {P} drafts one from the reviewed plan, and Fabric IQ's ontology "
                         "item (preview) holds it."},
    "data-products": {"label": "What is a data product?", "href": PAGES["data-products"], "more": "How data products work",
                      "text": "A data product is a domain's tables with an owner, an interface others use and a contract that "
                              "says what they can rely on. {P} proposes the domains from the plan; your administrator creates "
                              "the Fabric domain, and you decide the owners."},
}


def tips(product: str) -> dict:
    """The tips with the product's name filled in, as site.js reads them (JSON in the page)."""
    return {k: {**v, "text": v["text"].replace("{P}", product)} for k, v in TIPS.items()}


def _listed(names) -> str:
    names = list(names)
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def _cols(cols) -> str:
    return " + ".join(cols)


# ------------------------------------------------------------------ the engine on the shop schema --------------------

@lru_cache(maxsize=1)
def shop() -> dict:
    """What the engine makes of the synthetic shop schema: the plan, the ontology's entity and relationship types, the
    domain proposal with its contracts, and the semantic model's active relationships. Deterministic, so cached."""
    from . import domains, ontology, seed, semantic_model
    from .infer import plan
    p = plan(seed.schema("shop"))
    entities = []
    for t, key, cols, rule in ontology._model(p, None):
        entities.append({"table": t.name, "entity": ontology.entity_name(t.name), "key": key, "cols": list(cols), "rule": rule})
    rel_types = [{"name": ontology._entity_relationship_name(r, p), "source": r.source, "source_cols": list(r.source_cols),
                  "target": r.target, "target_cols": list(r.target_cols), "rule": r.rule,
                  "from": ontology.entity_name(r.source), "to": ontology.entity_name(r.target)}
                 for r in p.relationships if len(r.source_cols) == 1 and len(r.target_cols) == 1]
    summary = ontology.summary(p)
    d = domains.draft(p, "shop", "shop_lh")
    active, inactive = semantic_model.active_relationships(p, list(p.relationships))
    keys = {t.name: list(p.keys[t.name][0]) for t in p.schema if p.keys.get(t.name) and p.keys[t.name][0]}
    return {"plan": p, "tables": [t.name for t in p.schema], "keys": keys, "entities": entities, "rel_types": rel_types,
            "summary": summary, "domains": d, "active": [(r.source, tuple(r.source_cols), r.target) for r in active],
            "inactive": [(r.source, tuple(r.source_cols), r.target) for r, _why in inactive]}


def interface() -> dict:
    """The relationship the pages follow through every output: the first interface between two proposed domains."""
    return shop()["domains"]["interfaces"][0]


def odcs_excerpt() -> str:
    """A short excerpt of the consuming domain's contract, cut from the contract the engine wrote: its header, then the
    referencing table's no-orphans rule and foreign key for the interface."""
    i = interface()
    text = shop()["domains"]["contracts"][i["consumer"]]
    lines = text.splitlines()
    head = []
    for ln in lines[1:]:
        if ln.startswith("description:"):
            break
        head.append(ln)
    start = lines.index(f"  - name: {i['source']}")
    block = lines[start:]
    nxt = next((n for n, ln in enumerate(block[1:], 1) if ln.startswith("  - name: ")), len(block))
    block = block[:nxt]
    rule_name = f"{i['source']}_{'_'.join(i['source_cols'])}_no_orphans".lower()
    r0 = block.index(f"      - name: {rule_name}")
    rule = [block[r0]] + [ln for ln in block[r0 + 1:r0 + 6] if re.match(r"^        (description|dimension|type|mustBe):", ln)]
    rel0 = block.index("    relationships:")
    fk = [n for n, ln in enumerate(block) if ln == f"        from: {i['source']}.{i['source_cols'][0]}"]
    rel = [block[rel0], block[fk[0] - 1], block[fk[0]], block[fk[0] + 1]] if fk else []
    out = head + ["# …", "schema:", block[0], "    # … columns, key, the other rules", "    quality:", *rule,
                  "      # …", *rel]
    return "\n".join(out)


# ------------------------------------------------------------------ status, from tool_status ----------------------

def _registration_on() -> bool:
    from . import pages
    return pages._registration_on()


def _item_tag(tool: str) -> str:
    """How far creating one Fabric item has gone, in tool_status's own short words (the API: updated in place)."""
    from . import tool_status as ts
    return "updated in place live; a new one: experimental" if ts.build_word(tool) == "updates" else ts.short(tool)


def clients() -> tuple[list[str], list[str]]:
    """(tested end to end, experimental): the MCP clients as tool_status records them for this server."""
    from . import tool_status as ts
    working = ts.clients_working(_registration_on())
    other = ([c.name for c in ts.CLIENTS if c.path == "/mcp/connect" and c.status != "Tested end to end"]
             if _registration_on() else [])
    return working, other


def sources() -> tuple[list[str], list[str]]:
    from . import tool_status as ts
    return [n for n, t in ts.SOURCES if t], [n for n, t in ts.SOURCES if not t]


def _operator_items() -> list[str]:
    from . import tool_status as ts
    return [n for n, tool in ts.BUILDS if ts.STATUS[tool].available == ts.OPERATOR]


# ------------------------------------------------------------------ the Markdown placeholders ---------------------

def parts_md() -> str:
    from . import tool_status as ts
    working, other = clients()
    tested, exp = sources()
    one = len(working) == 1
    at = [c for c in working if ts.CLIENTS_TESTED[c][0] == "/mcp/connect"]
    cl = (f"- **Clients**: where you ask. {_listed(working)} {'connects' if one else 'connect'} to {{{{PRODUCT}}}} through MCP and "
          f"{'signs' if one else 'sign'} in with your Microsoft work account"
          + (f" ({_listed(at)} at `/mcp/connect`)" if at else "")
          + f": tested end to end as {'a client' if one else 'clients'}."
          + (f" {_listed(other)} {'is' if len(other) == 1 else 'are'} experimental as {'a client' if len(other) == 1 else 'clients'}." if other else "")
          + " Lovable builds an app on the GraphQL API {{PRODUCT}} creates, not on {{PRODUCT}} itself.")
    kg = ("- **{{PRODUCT}}**: the MCP server in the middle. It makes the plan from table and column metadata (keys and "
          "relationships, each with the rule behind it), counts the checks as queries in Fabric and writes the drafts; it "
          "stores no table contents. Reading, planning and checking: " + ts.task_status(["plan_backend", "validate_plan"]) + ".")
    items = ", ".join(f"the {n if n != 'GraphQL API' else 'API for GraphQL'} ({_item_tag(tool)})" for n, tool in ts.BUILDS)
    ops = _operator_items()
    fab = (f"- **Fabric items**: what {{{{PRODUCT}}}} creates in your workspace when you ask, each from the same plan and each "
           f"with a dry run first. How far creating each one has gone: {items}."
           + (f" On the hosted service, the {_listed(ops)} need a permission the operator enables." if ops else ""))
    src = ("- **OneLake**: Fabric's storage, where your lakehouse and warehouse tables live (a SQL database in Fabric is "
           "replicated there). {{PRODUCT}} reads your tables where they are and copies none of them. "
           + (f"{_listed(tested)} {'is' if len(tested) == 1 else 'are'} tested end to end as a source" if tested else "")
           + (f"; {_listed(exp)} {'is' if len(exp) == 1 else 'are'} experimental." if exp else "."))
    return "\n".join([cl, kg, fab, src])


def entities_md() -> str:
    s = shop()
    rows = ["| Entity type | Table | Key |", "| --- | --- | --- |"]
    for e in s["entities"]:
        if e["key"]:
            k = f"`{e['key']}` (rule {e['rule']})"
        elif len(e["cols"]) > 1:
            k = f"none yet: the key `{_cols(e['cols'])}` is composite (rule {e['rule']}), so a person chooses"
        else:
            k = "none: no column is named like a key (rule K3), so nothing can point at it"
        rows.append(f"| `{e['entity']}` | `{e['table']}` | {k} |")
    return "\n".join(rows)


def rel_types_md() -> str:
    return "\n".join(f"- `{r['name']}`: `{r['from']}` → `{r['to']}`, from `{r['source']}.{_cols(r['source_cols'])}` → "
                     f"`{r['target']}.{_cols(r['target_cols'])}` (rule {r['rule']})" for r in shop()["rel_types"])


def ontology_counts_md() -> str:
    s = shop()["summary"]
    return (f"{s['entity_types']} entity types, {s['with_key']} of them with a key, and {s['relationship_types']} relationship "
            f"types")


def composite_md() -> str:
    e = next((e for e in shop()["entities"] if not e["key"] and len(e["cols"]) > 1), None)
    if not e:
        return "no table with a composite key"
    return f"`{e['table']}`, whose key is `{_cols(e['cols'])}`"


def domains_md() -> str:
    d = shop()["domains"]
    out = [f"- **{x['name']}**: {_listed(f'`{t}`' for t in x['tables'])}. Why the name: {x['name_reason']}." for x in d["domains"]]
    for i in d["interfaces"]:
        out.append(f"- **Interface**: `{i['source']}.{_cols(i['source_cols'])}` → `{i['target']}.{_cols(i['target_cols'])}` "
                   f"(rule {i['rule']}): {i['consumer']} uses the key {i['provider']} owns.")
    for u in d["unassigned"]:
        out.append(f"- **Unassigned**: `{u['table']}`, {u['reason']}.")
    return "\n".join(out)


def domain_names_md() -> str:
    return _listed(f"**{x['name']}**" for x in shop()["domains"]["domains"])


def trace_md() -> str:
    """One relationship, the interface, through every output the plan feeds."""
    s, i = shop(), interface()
    rel = f"`{i['source']}.{_cols(i['source_cols'])}` → `{i['target']}.{_cols(i['target_cols'])}`"
    rt = next((r for r in s["rel_types"] if r["source"] == i["source"] and r["source_cols"] == i["source_cols"] and r["target"] == i["target"]), None)
    key = (i["source"], tuple(i["source_cols"]), i["target"])
    sm = "an active relationship" if key in s["active"] else "an inactive relationship (it would close a cycle)"
    rule_name = f"{i['source']}_{'_'.join(i['source_cols'])}_no_orphans".lower()
    lines = [
        f"- **The plan**: {rel}, rule {i['rule']}; `validate_plan` counts the references with no matching row.",
        f"- **The API for GraphQL**: a relationship a query can nest, from `{i['source']}` to `{i['target']}`.",
        f"- **The Power BI semantic model**: {sm} from `{i['source']}` to `{i['target']}`.",
    ]
    if rt:
        lines.append(f"- **The ontology**: the relationship type `{rt['name']}`, from `{rt['from']}` to `{rt['to']}`.")
    lines += [
        f"- **The data products**: the interface between **{i['consumer']}** and **{i['provider']}**: {i['consumer']} holds "
        f"the reference, {i['provider']} owns the key.",
        f"- **The contract**: a `foreignKey` from `{i['source']}.{_cols(i['source_cols'])}` to "
        f"`{i['target']}.{_cols(i['target_cols'])}` and the rule `{rule_name}` (`mustBe: 0`).",
    ]
    return "\n".join(lines)


def plan_counts_md() -> str:
    s = shop()
    p = s["plan"]
    return (f"{len(s['tables'])} tables, {len(s['keys'])} with a key, and {len(p.relationships)} relationships")


def status_md() -> dict[str, str]:
    from . import tool_status as ts
    ont = ts.short("create_ontology")
    op = ts.STATUS["create_ontology"].available == ts.OPERATOR
    return {
        "CONCEPT_ONTOLOGY_STATUS": (f"Creating the ontology item from the plan: {ont}. The ontology item is in preview in Fabric, "
                                    f"and its definition format can change"
                                    + ("; on the hosted service, creating it needs a permission the operator enables." if op else ".")),
        "CONCEPT_RDFXML_STATUS": f"{ts.ONTOLOGY_RDFXML.lower()}; {ts.ONTOLOGY_RDFXML_TRIED}",
        "CONCEPT_DOMAIN_STATUS": f"`domain_draft`: {ts.label('domain_draft')}",
    }


def fill(md: str) -> str:
    """DOCS.md's {{CONCEPT_...}} placeholders, from the engine and tool_status."""
    if "{{CONCEPT_" not in md:
        return md
    i = interface()
    vals = {
        "CONCEPT_PARTS": parts_md, "CONCEPT_ENTITIES": entities_md, "CONCEPT_REL_TYPES": rel_types_md,
        "CONCEPT_ONTOLOGY_COUNTS": ontology_counts_md, "CONCEPT_COMPOSITE": composite_md, "CONCEPT_DOMAINS": domains_md,
        "CONCEPT_DOMAIN_NAMES": domain_names_md, "CONCEPT_TRACE": trace_md, "CONCEPT_PLAN_COUNTS": plan_counts_md,
        "CONCEPT_ODCS": odcs_excerpt, "CONCEPT_FLOW": connect_flow_md, "CONCEPT_HOSTING": hosting_md,
        "CONCEPT_WHERE": where_md, "CONCEPT_WHERE_NOTES": where_notes_md,
        "CONCEPT_INTERFACE": lambda: f"`{i['source']}.{_cols(i['source_cols'])}` → `{i['target']}.{_cols(i['target_cols'])}`",
        "CONCEPT_UNASSIGNED": lambda: _listed(f"`{u['table']}`" for u in shop()["domains"]["unassigned"]),
    }
    st = status_md()
    out = re.sub(r"\{\{(CONCEPT_\w+)\}\}", lambda m: vals[m.group(1)]() if m.group(1) in vals else st.get(m.group(1), m.group(0)), md)
    if "{{CONCEPT_" in out:
        raise ValueError("an unknown concept placeholder in DOCS.md: " + re.search(r"\{\{CONCEPT_\w+\}\}", out).group(0))
    return out


# ------------------------------------------------------------------ the figures (HTML and inline SVG) -------------

E = html.escape
_ARROW = ('<svg class="cx-arrow-svg" viewBox="0 0 48 16" aria-hidden="true" focusable="false"><path d="M2 8h40M34 2l8 6-8 6" '
          'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _product() -> str:
    from . import pages
    return pages._vars()["PRODUCT"]


def _layers(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
    """A node's column: the longest chain of references from it to a table that points at nothing (cycles cut)."""
    out: dict[str, int] = {}

    def depth(n: str, seen: tuple) -> int:
        if n in out:
            return out[n]
        targets = [b for a, b in edges if a == n and b != n and b not in seen]
        v = 0 if not targets else 1 + max(depth(b, seen + (n,)) for b in targets)
        out[n] = v
        return v
    for n in nodes:
        depth(n, ())
    return out


def _ontology_svg() -> str:
    s = shop()
    ents = {e["table"]: e for e in s["entities"]}
    edges = [(r["source"], r["target"]) for r in s["rel_types"]]
    level = _layers(list(ents), edges)
    cols: dict[int, list[str]] = {}
    for t in ents:
        cols.setdefault(level[t], []).append(t)
    pos: dict[str, tuple[float, float]] = {}
    W, H, GX, GY, X0, Y0 = 172, 54, 74, 22, 8, 8
    order: dict[str, float] = {}
    for c in sorted(cols):
        def bary(t: str) -> tuple:
            tg = [order[b] for a, b in edges if a == t and b in order]
            return (sum(tg) / len(tg) if tg else 0.0, t)
        cols[c].sort(key=bary)
        for n, t in enumerate(cols[c]):
            order[t] = n
    rows = max(len(v) for v in cols.values())
    height = Y0 * 2 + rows * H + (rows - 1) * GY
    for c, ts_ in cols.items():
        top = Y0 + (rows - len(ts_)) * (H + GY) / 2
        for n, t in enumerate(ts_):
            pos[t] = (X0 + c * (W + GX), top + n * (H + GY))
    width = X0 * 2 + (max(cols) + 1) * W + max(cols) * GX
    parts = []
    for r in s["rel_types"]:
        (sx, sy), (tx, ty) = pos[r["source"]], pos[r["target"]]
        x1, y1, x2, y2 = sx, sy + H / 2, tx + W, ty + H / 2
        mx = (x1 + x2) / 2
        parts.append(f'<path class="cx-edge" d="M{x1:.0f} {y1:.0f} C{mx:.0f} {y1:.0f} {mx:.0f} {y2:.0f} {x2 + 6:.0f} {y2:.0f}" '
                     f'marker-end="url(#cx-ah)"><title>{E(r["name"])}: {E(r["source"])}.{E(_cols(r["source_cols"]))} → '
                     f'{E(r["target"])}.{E(_cols(r["target_cols"]))}</title></path>')
    for t, e in ents.items():
        x, y = pos[t]
        cls = "cx-node" if e["key"] else "cx-node cx-nokey"
        sub = (f"key {e['key']}" if e["key"] else ("no key: composite" if len(e["cols"]) > 1 else "no key"))
        parts.append(f'<g class="{cls}"><rect x="{x:.0f}" y="{y:.0f}" width="{W}" height="{H}" rx="12"/>'
                     f'<text x="{x + 14:.0f}" y="{y + 23:.0f}" class="cx-n">{E(e["entity"])}</text>'
                     f'<text x="{x + 14:.0f}" y="{y + 42:.0f}" class="cx-s">{E(sub)}</text></g>')
    said = (f"The shop schema as an ontology: {ontology_counts_md()}. "
            + "; ".join(f"{r['from']} to {r['to']}" for r in s["rel_types"]) + ".")
    return (f'<svg class="cx-svg cx-svg-fit" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" role="img" aria-label="{E(said)}">'
            '<defs><marker id="cx-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0 0 10 5 0 10z" class="cx-ah"/></marker></defs>' + "".join(parts) + "</svg>")


def _ontology(inner: str) -> str:
    return (f'<figure class="cx-fig cx-onto"><div class="cx-frame"><div class="cx-wide">{_ontology_svg()}</div>'
            f'<div class="cx-narrow">{_ontology_list_svg()}</div></div><figcaption class="muted tiny">Generated by the engine from the '
            f'synthetic shop schema when this page was rendered. A solid frame has a key; a dashed frame has none yet. Arrows '
            f'point from the entity type that holds the reference to the one that owns the key.</figcaption></figure>' + inner)


def _domains_svg(stacked: bool = False) -> str:
    """The proposal as a picture: each domain a tinted group with its tables, the interfaces as arrows from the table that
    holds the reference to the table that owns the key, the unassigned tables below. Side by side for wide screens;
    `stacked` puts the domains under each other for a phone, with the interface arrows on the right."""
    d = shop()["domains"]
    W, H, GX, PAD, HEAD = 168, 34, 120, 14, 40
    pos: dict[str, tuple[float, float]] = {}
    parts = []
    gy, gx, bottom = 8, 8, 8
    rows = max(len(x["tables"]) for x in d["domains"])
    for n, x in enumerate(d["domains"]):
        gh = HEAD + (len(x["tables"]) if stacked else rows) * (H + 8) + PAD
        if not stacked:
            gx = 8 + n * (W + 2 * PAD + GX)
        tone = "a" if n % 2 == 0 else "b"
        parts.append(f'<g class="cx-dom cx-dom-{tone}"><rect x="{gx}" y="{gy}" width="{W + 2 * PAD}" height="{gh}" rx="18"/>'
                     f'<text x="{gx + PAD}" y="{gy + 27}" class="cx-n">{E(x["name"])}</text></g>')
        for k, t in enumerate(x["tables"]):
            tx, ty = gx + PAD, gy + HEAD + k * (H + 8)
            pos[t] = (tx, ty)
            parts.append(f'<g class="cx-tab"><rect x="{tx}" y="{ty}" width="{W}" height="{H}" rx="9"/>'
                         f'<text x="{tx + 12}" y="{ty + 22}" class="cx-s">{E(t)}</text></g>')
        bottom = max(bottom, gy + gh)
        if stacked:
            gy += gh + 24
    width = (8 * 2 + W + 2 * PAD + 96) if stacked else (8 * 2 + len(d["domains"]) * (W + 2 * PAD) + (len(d["domains"]) - 1) * GX)
    y = bottom + 22
    for u in d["unassigned"]:
        parts.append(f'<g class="cx-node cx-nokey"><rect x="8" y="{y}" width="{W + 2 * PAD}" height="{H + 8}" rx="12"/>'
                     f'<text x="{8 + 14}" y="{y + 26}" class="cx-s">{E(u["table"])}: unassigned, no key</text></g>')
        y += H + 18
    for i in d["interfaces"]:
        (sx, sy), (tx, ty) = pos[i["source"]], pos[i["target"]]
        y1, y2 = sy + H / 2, ty + H / 2
        if stacked:                                       # out of the right edge, round, and back into the target's right edge
            x1, x2, bend = sx + W, tx + W, sx + W + PAD + 70
            parts.append(f'<path class="cx-edge cx-if" d="M{x1} {y1:.0f} C{bend} {y1:.0f} {bend} {y2:.0f} {x2 + 6} {y2:.0f}" marker-end="url(#cx-ah2)"/>')
            parts.append(f'<text x="{bend - 10}" y="{(y1 + y2) / 2:.0f}" text-anchor="end" class="cx-s cx-if-l" '
                         f'transform="rotate(-90 {bend - 10} {(y1 + y2) / 2:.0f})">interface</text>')
            continue
        x1, x2 = (sx + W, tx) if sx < tx else (sx, tx + W)
        mx = (x1 + x2) / 2
        end = x2 - 6 if x2 > x1 else x2 + 6
        parts.append(f'<path class="cx-edge cx-if" d="M{x1} {y1:.0f} C{mx:.0f} {y1:.0f} {mx:.0f} {y2:.0f} {end} {y2:.0f}" marker-end="url(#cx-ah2)"/>')
        parts.append(f'<text x="{mx:.0f}" y="{min(y1, y2) - 8:.0f}" text-anchor="middle" class="cx-s cx-if-l">interface</text>')
    height = y + 4
    said = ("The proposed domains of the shop schema: "
            + "; ".join(f"{x['name']} with {_listed(x['tables'])}" for x in d["domains"])
            + ". " + " ".join(f"Interface: {i['source']}.{_cols(i['source_cols'])} to {i['target']}.{_cols(i['target_cols'])}."
                              for i in d["interfaces"])
            + " " + " ".join(f"Unassigned: {u['table']}, no key." for u in d["unassigned"]))
    mark = "cx-ah3" if stacked else "cx-ah2"
    svg = "".join(parts).replace("url(#cx-ah2)", f"url(#{mark})")
    return (f'<svg class="cx-svg cx-svg-fit" viewBox="0 0 {width} {height:.0f}" width="{width}" role="img" aria-label="{E(said.strip())}">'
            f'<defs><marker id="{mark}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0 0 10 5 0 10z" class="cx-ah"/></marker></defs>' + svg + "</svg>")


def _domains(inner: str) -> str:
    return (f'<figure class="cx-fig cx-doms"><div class="cx-frame"><div class="cx-wide">{_domains_svg()}</div>'
            f'<div class="cx-narrow">{_domains_svg(stacked=True)}</div></div><figcaption class="muted tiny">Generated by the engine '
            f'(<code>domain_draft</code>) from the synthetic shop schema when this page was rendered: a proposal to review. '
            f'The arrow is the interface, from the table that holds the reference to the table that owns the key.</figcaption></figure>' + inner)


def _vision(inner: str) -> str:
    """Gustav's vision text, verbatim (round n86b's brief): three cards, an arrow between them, the band under them."""
    p = E(_product())
    cards = [
        ("cx-v-now", "Available today", "Check and create",
         ["Map how your tables connect", "Count every link against the rows", "Create Fabric items when you ask"]),
        ("cx-v-next", "Next", "Check what comes in",
         ["See if incoming data matches its source", "Set up Fabric's own tools, with your approval"]),
        ("cx-v-vision", "Vision", "One place for the whole chain",
         ["From source system to report", "Any source, with the tool you choose"]),
    ]
    arrow = f'<li class="cx-v-arrow" aria-hidden="true">{_ARROW}</li>'
    lis = arrow.join(f'<li class="cx-v-card {cls}"><p class="cx-v-kicker">{E(k)}</p><h3 class="cx-v-h">{E(h)}</h3>'
                     f'<ul>{"".join(f"<li>{E(x)}</li>" for x in xs)}</ul></li>' for cls, k, h, xs in cards)
    return f"""<section class="cx-vision" aria-labelledby="cx-vision-h">
<h2 id="cx-vision-h" class="cx-v-title">One place for your Fabric data. Proof at every step.</h2>
<p class="cx-v-sub">Where {p} is today, and where it is going.</p>
<ol class="cx-v-row">{lis}</ol>
<div class="cx-v-band"><p class="cx-v-goal">The goal: nothing gets built on a link nobody counted.</p><p class="cx-v-note">Next and Vision are direction, not current features.</p></div>
</section>"""


def figures() -> dict:
    return {"how-it-works": _how_svg, "ontology": _ontology, "domains": _domains, "connect": _connect_svg, "vision": _vision,
            "hosting": _hosting, "where": _where}


# ------------------------------------------------------------------ n86b (Gustav's addition): architecture diagrams ----
# Three diagrams as inline SVG drawn in bands, one layer under the other, so the same picture reads at 1280 px and at
# 375 px: on a phone the items of a band wrap to two per row and nothing scrolls sideways. Each has a short text version
# for screen readers (aria-describedby a visually hidden paragraph), and /docs.md has the same facts as a list.

def _wrap(text: str, width: float, size: float) -> list[str]:
    """Words into lines that fit `width` px at font `size` (Nunito averages about 0.55 em a character; kept on the safe side)."""
    per = max(6, int(width / (size * 0.56)))
    lines, cur = [], ""
    words = []
    for w in text.split():
        while len(w) > per and "." in w[:per]:
            cut = w[:per].rindex(".") + 1
            words.append(w[:cut]); w = w[cut:]
        words.append(w)
    for w in words:
        if cur and len(cur) + 1 + len(w) > per:
            lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])


def _texts(x: float, y: float, lines: list[str], cls: str, step: float) -> str:
    return "".join(f'<text x="{x:.0f}" y="{y + n * step:.0f}" class="{cls}">{E(t)}</text>' for n, t in enumerate(lines))


def _bands_svg(bands: list[dict], links: list[dict], width: int, cols: int, label: str, desc_id: str,
               side: dict | None = None) -> str:
    """bands: [{"title", "sub", "items": [(name, tag, mark)], "tone"}]; links: one per gap between bands, {"text"};
    side: {"from": i, "to": j, "text", "edge": "left"|"right"}, an arrow along the margin from band i to band j."""
    M = 8 + (40 if side else 0)                         # room for the side arrow
    x0 = 8 + (40 if side and side["edge"] == "left" else 0)
    inner = width - M - 8 if side else width - 16
    PAD, GAP, TS, SS, NS, GS = 12, 8, 17, 13, 14, 12
    parts, mids, y = [], [], 8
    for n, b in enumerate(bands):
        top = y
        h = PAD + 20
        title = f'<text x="{x0 + PAD}" y="{top + PAD + 15}" class="cx-n">{E(b["title"])}</text>'
        sub = _wrap(b.get("sub", ""), inner - 2 * PAD, SS) if b.get("sub") else []
        body = _texts(x0 + PAD, top + h + 12, sub, "cx-s cx-sub", 17)
        h += len(sub) * 17 + (8 if sub else 0)
        items = b.get("items", [])
        c = max(1, min(1 if b.get("one_on_phone") and cols < 3 else cols, len(items))) if items else 1
        iw = (inner - 2 * PAD - (c - 1) * GAP) / c
        rows = [items[k:k + c] for k in range(0, len(items), c)]
        boxes = ""
        for row in rows:
            wrapped = [(_wrap(nm, iw - 20, NS), _wrap(tg, iw - 20, GS) if tg else []) for nm, tg, _m in row]
            rh = max(14 + len(a) * 18 + (len(t) * 15 + 6 if t else 0) for a, t in wrapped) + 4
            for k, ((nm, tg, mk), (a, t)) in enumerate(zip(row, wrapped)):
                ix = x0 + PAD + k * (iw + GAP)
                boxes += (f'<g class="cx-it cx-mk-{mk or "none"}"><rect x="{ix:.0f}" y="{top + h:.0f}" width="{iw:.0f}" height="{rh:.0f}" rx="9"/>'
                          + _texts(ix + 10, top + h + 20, a, "cx-it-n", 18)
                          + _texts(ix + 10, top + h + 20 + len(a) * 18 + 2, t, "cx-it-t", 15) + "</g>")
            h += rh + GAP
        h += PAD - (GAP if items else 0) + (0 if items else 4)
        parts.append(f'<g class="cx-band cx-band-{b.get("tone", "a")}"><rect x="{x0}" y="{top}" width="{inner:.0f}" height="{h:.0f}" rx="16"/>'
                     f'{title}{body}{boxes}</g>')
        mids.append((top, top + h))
        y = top + h
        if n < len(bands) - 1:
            lk = links[n]
            lines = _wrap(lk["text"], inner - 70, SS)
            gap = max(40, 14 + len(lines) * 17)
            cx = x0 + 34
            parts.append(f'<path class="cx-edge cx-flow" d="M{cx} {y + 2} V{y + gap - 4}" marker-end="url(#{desc_id}-ah)"/>'
                         + _texts(cx + 14, y + (gap - len(lines) * 17) / 2 + 12, lines, "cx-s cx-flow-l", 17))
            y += gap
    if side:
        (a0, a1), (b0, b1) = mids[side["from"]], mids[side["to"]]
        ya, yb = (a0 + a1) / 2, (b0 + b1) / 2
        if side["edge"] == "left":
            xs, xm = x0, x0 - 22
        else:
            xs, xm = x0 + inner, x0 + inner + 22
        d = f"M{xs:.0f} {ya:.0f} H{xm:.0f} V{yb:.0f} H{xs + (-6 if side['edge'] == 'right' else 6):.0f}"
        parts.append(f'<path class="cx-edge cx-flow cx-back" d="{d}" marker-end="url(#{desc_id}-ah)"/>')
        lx = xm - 6 if side["edge"] == "left" else xm + 14
        parts.append(f'<text x="{lx:.0f}" y="{(ya + yb) / 2:.0f}" text-anchor="middle" class="cx-s cx-flow-l" '
                     f'transform="rotate(-90 {lx:.0f} {(ya + yb) / 2:.0f})">{E(side["text"])}</text>')
    height = y + 8
    return (f'<svg class="cx-svg cx-svg-fit" viewBox="0 0 {width} {height:.0f}" width="{width}" role="img" aria-label="{E(label)}" '
            f'aria-describedby="{desc_id}"><defs><marker id="{desc_id}-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            'markerHeight="7" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" class="cx-ah"/></marker></defs>'
            + "".join(parts) + "</svg>")


def _two(name: str, make, said: str, caption: str, inner: str) -> str:
    """The wide and the phone drawing of one diagram, its text version for screen readers, and the Markdown under it."""
    wide, narrow = make(720, 3), make(360, 2)
    narrow = narrow.replace(f'id="{name}-ah"', f'id="{name}-n-ah"').replace(f'url(#{name}-ah)', f'url(#{name}-n-ah)')
    return (f'<figure class="cx-fig cx-arch" aria-labelledby="{name}-cap"><p class="visually-hidden" id="{name}">{E(said)}</p>'
            f'<div class="cx-frame"><div class="cx-wide">{wide}</div><div class="cx-narrow">{narrow}</div></div>'
            f'<figcaption id="{name}-cap" class="muted tiny">{caption}</figcaption></figure>' + inner)


# ---- how far each item has come, in tool_status's words: created live, dry run or draft

def mark(tool: str) -> tuple[str, str]:
    """(mark, words) for a creating or drafting tool: "live" (created or updated in place live), "dry" (only its dry run
    ran live) or "draft"."""
    from . import tool_status as ts
    s, bw = ts.STATUS[tool], ts.build_word(tool)
    if bw == "creates":
        return "live", ("created live" + ("; reviewed in Fabric" if tool in ts.REVIEWED else "")
                        + ("; not yet run in Fabric" if "not yet run in Fabric" in s.note else ""))
    if bw == "updates":
        return "live", "updated in place live"
    if s.kind == ts.CREATES and s.live and s.dry_run_only:
        return "dry", "dry run tested end to end; not yet created live"
    return "draft", "draft; creates nothing"


MARK_WORDS = {"live": "created live", "dry": "dry run", "draft": "draft"}
OUTPUTS = (("API for GraphQL", "create_backend"), ("Power BI semantic model", "create_semantic_model"),
           ("Fabric IQ ontology", "create_ontology"), ("Silver notebook", "create_silver_notebook"),
           ("Gold views notebook", "create_gold_views"), ("Drift monitor notebook and pipeline", "create_drift_monitor"),
           ("Views", "create_views"), ("Data agent", "create_data_agent"), ("Data products and contracts", "domain_draft"))


def _pipeline_words() -> str:
    from . import pipeline
    doc = " ".join(pipeline.__doc__.split())
    if "no tool creates or schedules it" not in doc:                  # the words below are the module's own
        raise ValueError("pipeline.py no longer says how its pipeline is made")
    return "draft; export_item_definitions gives it as files, no tool creates or schedules it"


def outputs() -> list[tuple[str, str, str]]:
    """(name, mark, words) for each thing the plan becomes, in the order of the diagram."""
    out = [(n, *mark(t)) for n, t in OUTPUTS]
    out.insert(6, ("Pipeline: silver, gold, then the check", "draft", _pipeline_words()))
    return out


def connect_flow_md() -> str:
    from . import tool_status as ts
    lines = ["How a plan becomes Fabric items, with how far each has come in the words of the [test status](#test-status):", "",
             f"1. **The plan**: keys and relationships, each with the rule behind it (`plan_backend`: {ts.task_status(['plan_backend'])}).",
             f"2. **Checked against the rows**: duplicate keys, empty keys and references with no matching row, counted in Fabric "
             f"(`validate_plan`: {ts.task_status(['validate_plan'])}); you correct the plan with `keys` and `confirmed`.",
             "3. **Drafts or created items**, each from that plan, as listed below.", "",
             "Each item, created live, a dry run or a draft:", ""]
    lines += [f"- {n}: {w}" for n, _m, w in outputs()]
    return "\n".join(lines)


# ---- the hosting page: the sign-in and request flow, in /it's and /privacy's own words

@lru_cache(maxsize=4)
def _it_facts(key: tuple) -> dict:
    from . import pages
    src = pages._fill(pages._conditional(pages._read("it.html"), pages._vars()))
    plain = lambda s: html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s))).strip()
    scopes = [(plain(a), b.strip(), plain(c)) for a, b, c in
              re.findall(r'<tr><td><code>([^<]+)</code> \(([^)]+)\)</td><td>(.*?)</td></tr>', src)]
    where = {plain(a): plain(b) for a, b in re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td></tr>", src) if "<code>" not in a[:7]}
    stored = {}
    for li in re.findall(r"<li>(.*?)</li>", src, re.S):
        m = re.match(r"<strong>(.*?)</strong>:?\s*(.*)", li.strip(), re.S)
        if m:
            stored[plain(m.group(1)).rstrip(".")] = plain(m.group(2))
        elif "records sign-ins" in li:
            stored["Entra"] = plain(li)
    host = re.search(r"<p[^>]*>([^<]*does not host your data[^<]*)</p>", src)
    return {"scopes": scopes, "where": where, "stored": stored, "host_note": plain(host.group(1)) if host else ""}


def it_facts() -> dict:
    """The permissions, where the data goes and what is stored, read from the /it page as it renders now."""
    from . import pages
    v = pages._vars()
    f = _it_facts(tuple(sorted(v.items())))
    need = ("No table contents", "Tokens", "A usage record per tool call", "Where", "Entra")
    if (not all(k in f["stored"] for k in need) or not f["scopes"] or not f["host_note"]
            or not any(k.startswith("Hosted") for k in f["where"])):
        raise ValueError("the /it page no longer has the facts the hosting diagram reads")
    return f


def _hosted_key(f: dict) -> str:
    return next(k for k in f["where"] if k.startswith("Hosted"))


def _low(t: str) -> str:
    return t[:1].lower() + t[1:]


def hosting_md() -> str:
    f = it_facts()
    s, w = f["stored"], f["where"]
    fab = [f"`{a}`" for a, api, _t in f["scopes"] if api == "Fabric"]
    sql = [f"`{a}`" for a, api, _t in f["scopes"] if api.startswith("Azure SQL")]
    graph = [f"`{a}`" for a, api, _t in f["scopes"] if api == "Microsoft Graph"]
    lines = ["How a request travels, in the words of [the page for your IT department](/it) and the [privacy policy](/privacy):", "",
             "1. **Your MCP client** (such as Claude): you sign in with your own Microsoft Entra work account"
             + (f" ({_listed(graph)})" if graph else "") + ".",
             "2. **Microsoft Entra ID**: an administrator approves the app once; all its permissions are delegated, so every "
             f"call runs as the signed-in person. {s['Entra']}",
             f"3. **{{{{PRODUCT}}}}'s server**. Hosted: {w[_hosted_key(f)]} In your own Azure: {_low(w['In your own Azure'])} "
             f"Your sign-in: {_low(s['Tokens'])}",
             f"4. **Fabric's REST API** ({_listed(fab)}) **and the SQL analytics endpoint** ({_listed(sql)}), called as you "
             "within these delegated permissions.",
             f"5. **Your OneLake**: your tables, read where they are. {f['host_note']}",
             f"6. **Back to your MCP client**, passing through and not kept: {_low(s['No table contents'])} Your AI client "
             f"{_low(w['Your AI client (such as Claude)'])}",
             "", f"What is kept: a usage record per tool call, {s['A usage record per tool call']} "
             f"Where: {_low(s['Where'])}"]
    return "\n".join(lines)


def _hosting(inner: str) -> str:
    f = it_facts()
    p = _product()
    w, s = f["where"], f["stored"]
    hosted = w[_hosted_key(f)].split(".")[0]                                # "Azure, Sweden Central"
    fab = [a for a, api, _t in f["scopes"] if api == "Fabric"]
    sql = [a for a, api, _t in f["scopes"] if api.startswith("Azure SQL")]
    graph = [a for a, api, _t in f["scopes"] if api == "Microsoft Graph"]

    def make(width: int, cols: int) -> str:
        bands = [
            {"title": "Your MCP client", "sub": "such as Claude; receives the answers", "tone": "c"},
            {"title": "Microsoft Entra ID", "sub": "sign in with your work account" + (f" ({', '.join(graph)})" if graph else "")
                                                   + "; delegated permissions only, every call runs as you", "tone": "d"},
            {"title": f"{p}'s server", "tone": "a", "items": [("Hosted", hosted, "none"), ("Or your own Azure", "your tenant, your region", "none"),
                                                              ("Passes through", "in memory, not kept after the request", "pass")]},
            {"title": "Fabric, called as you", "tone": "b", "one_on_phone": True, "items": [("Fabric REST API", ", ".join(fab), "none"),
                                                                      ("SQL analytics endpoint", ", ".join(sql) + " (Azure SQL)", "none")]},
            {"title": "Your OneLake", "sub": "your tables, in your own Fabric workspace", "tone": "e"},
        ]
        links = [{"text": "1 sign in"}, {"text": "2 your sign-in, exchanged on your behalf (OAuth 2.0 on-behalf-of)"},
                 {"text": "3 calls within the delegated permissions"}, {"text": "4 reads your tables where they are"}]
        side = {"from": 3, "to": 0, "edge": "left", "text": "5 answers pass back through memory; not kept"}
        return _bands_svg(bands, links, width, cols, f"The sign-in and request flow of {p}", "cx-host", side)
    said = (f"Your MCP client signs you in with Microsoft Entra ID. {p}'s server, hosted in {hosted} or in your own Azure, "
            f"exchanges your sign-in on your behalf and calls Fabric's REST API ({', '.join(fab)}) and the SQL analytics endpoint "
            f"({', '.join(sql)}) as you; they read your tables in your OneLake. {s['No table contents']}")
    return _two("cx-host", make, said, "Every fact in this picture is from <a href=\"/it\">the page for your IT department</a> "
                "and the <a href=\"/privacy\">privacy policy</a>; the list below says the same.", inner)


def _how_svg(inner: str) -> str:
    from . import tool_status as ts
    p = _product()
    working, other = clients()
    status = {c.name: c.status for c in ts.CLIENTS if c.path}
    tag = lambda w: "tested end to end" if w == "Tested end to end" else w.lower()
    lov = next(c for c in ts.CLIENTS if c.name == "Lovable" and not c.path)
    cl = [(c, tag(status[c]), "none") for c in working + other] + [("Lovable, on the API", tag(lov.status), "none")]
    items = [(n[:1].upper() + n[1:], _item_tag(t), "none") for n, t in ts.BUILDS]
    src = [(n, "tested end to end" if t else "experimental", "none") for n, t in ts.SOURCES]
    plan = ts.task_status(["plan_backend", "validate_plan"])

    def make(width: int, cols: int) -> str:
        bands = [{"title": "Clients", "sub": "where you ask", "items": cl, "tone": "c"},
                 {"title": p, "sub": "one plan: keys and relationships, each with its rule, counted against the rows",
                  "items": [("Plan and check", plan, "none")], "tone": "a"},
                 {"title": "Fabric items", "sub": "from the same plan, a dry run first", "items": items, "tone": "b"},
                 {"title": "OneLake", "sub": f"where your tables stay; {p} copies none of them", "items": src, "tone": "e"}]
        links = [{"text": "MCP, signed in as you"}, {"text": "creates when you ask"}, {"text": "built on your tables"}]
        side = {"from": 1, "to": 3, "edge": "right", "text": "reads metadata, counts rows"}
        return _bands_svg(bands, links, width, cols, f"How {p} works: clients, {p}, Fabric items and OneLake", "cx-how", side)
    said = (f"Four layers. Clients ({_listed(working + other)}, and Lovable on the API) connect through MCP to {p}, which makes one plan "
            f"and checks it ({plan}). {p} creates Fabric items from that plan when you ask, and reads metadata and counts rows in "
            f"OneLake, where your tables stay. The list below gives each part's status.")
    return _two("cx-how", make, said, "The four layers and how far each has been tested, from the same list as the "
                "<a href=\"/docs/reference/test-status#test-status\">test status</a>.", inner)


def _connect_svg(inner: str) -> str:
    from . import tool_status as ts
    p = _product()
    outs = outputs()

    def make(width: int, cols: int) -> str:
        bands = [{"title": "1  The plan", "sub": f"{plan_counts_md()} on the shop schema, each with its rule", "tone": "a",
                  "items": [("plan_backend", ts.task_status(["plan_backend"]), "none")]},
                 {"title": "2  Checked against the rows", "sub": "duplicate keys, empty keys, references with no matching row; you decide", "tone": "d",
                  "items": [("validate_plan", ts.task_status(["validate_plan"]), "none")]},
                 {"title": "3  Drafts or created items", "sub": "each from the same plan", "tone": "b",
                  "items": [(n, w if m == "live" else MARK_WORDS[m], m) for n, m, w in outs]}]
        links = [{"text": "counted in Fabric"}, {"text": "the reviewed plan"}]
        return _bands_svg(bands, links, width, cols, f"From plan to Fabric items with {p}", "cx-flow")
    said = ("The plan, checked against the rows, then drafts or created items: "
            + "; ".join(f"{n}, {w}" for n, _m, w in outs) + ".")
    legend = ('<span class="cx-legend"><span class="cx-lg cx-mk-live">created live</span><span class="cx-lg cx-mk-dry">dry run</span>'
              '<span class="cx-lg cx-mk-draft">draft</span></span>')
    return _two("cx-flow", make, said, legend + " The marks come from the "
                "<a href=\"/docs/reference/test-status#test-status\">test status</a>; the list below has each one in words.", inner)


def _ontology_list_svg() -> str:
    """The ontology for a phone: the entity types under each other, the relationship types as arcs on the right."""
    s = shop()
    ents = {e["table"]: e for e in s["entities"]}
    edges = [(r["source"], r["target"]) for r in s["rel_types"]]
    level = _layers(list(ents), edges)
    order = sorted(ents, key=lambda t: (level[t], t))
    W, H, G = 190, 46, 10
    pos = {t: (8, 8 + n * (H + G)) for n, t in enumerate(order)}
    parts = []
    for k, r in enumerate(sorted(s["rel_types"], key=lambda r: abs(order.index(r["source"]) - order.index(r["target"])))):
        (sx, sy), (tx, ty) = pos[r["source"]], pos[r["target"]]
        bend = 8 + W + 22 + k * 20
        parts.append(f'<path class="cx-edge" d="M{8 + W} {sy + H / 2 + 6:.0f} H{bend} V{ty + H / 2 - 6:.0f} H{8 + W + 6}" marker-end="url(#cx-ahn)">'
                     f'<title>{E(r["name"])}</title></path>')
    for t in order:
        e = ents[t]
        x, y = pos[t]
        cls = "cx-node" if e["key"] else "cx-node cx-nokey"
        sub = (f"key {e['key']}" if e["key"] else ("no key: composite" if len(e["cols"]) > 1 else "no key"))
        parts.append(f'<g class="{cls}"><rect x="{x}" y="{y}" width="{W}" height="{H}" rx="11"/>'
                     f'<text x="{x + 12}" y="{y + 20}" class="cx-n">{E(e["entity"])}</text>'
                     f'<text x="{x + 12}" y="{y + 37}" class="cx-s">{E(sub)}</text></g>')
    width = 8 + W + 22 + len(s["rel_types"]) * 20 + 8
    height = 8 + len(order) * (H + G)
    said = f"The shop schema as an ontology: {ontology_counts_md()}."
    return (f'<svg class="cx-svg cx-svg-fit" viewBox="0 0 {width} {height}" width="{width}" role="img" aria-label="{E(said)}">'
            '<defs><marker id="cx-ahn" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0 0 10 5 0 10z" class="cx-ah"/></marker></defs>' + "".join(parts) + "</svg>")


# ------------------------------------------------------------------ n117: Where it runs -------------------------------
# Four places an agent can use Krusgraph from, so that where it runs can follow where the data access is, and what each
# place can do with a task: check, draft, create and review. Every status and every capability is read from the code
# when the page renders (tool_status, LOCAL_TOOLS, the tools' dry_run defaults, the /it page's own table, what /check
# downloads); what the code cannot say is in WHERE_NOT_IN_CODE, once, with its date.

WHERE_AS_OF = "6 November 2026"
WHERE_NOT_IN_CODE = {
    "check_live": "/check is live",
    "tenant_not_run": "not yet run by a customer",
    "clients_not_tried": "Copilot Studio and Azure AI Foundry have not been tried as clients",
    "no_packaging": "there is no packaging per region and none per agent tier",
}
WHERE_COLS = (("browser", "In the browser"), ("computer", "On your own computer"), ("tenant", "In your own Azure tenant"),
              ("hosted", "Hosted by {P}"))
WHERE_ROWS = (("where", "Where it is", ""), ("status", "Status", ""),
              ("check", "Check", "keys, references with no matching row (orphans), totals a join repeats"),
              ("draft", "Draft", "model, ontology, dbt, notebooks, pipeline"),
              ("create", "Create and review", "Fabric items, and decisions on findings"))
# the drafts, in the row's order: (what, the hosted draft tool); the pipeline has no tool of its own (pipeline.py)
WHERE_DRAFTS = (("model", "semantic_model_draft"), ("ontology", "ontology_draft"), ("dbt", "dbt_schema"),
                ("silver notebook", "silver_notebook_draft"), ("gold views notebook", "gold_views_draft"),
                ("drift monitor notebook", "drift_monitor_draft"))


def _src(rel: str) -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parent / rel).read_text(encoding="utf-8")


def _default_dry_run(text: str, tool: str) -> bool:
    """Whether `tool`'s own signature in that module's source has dry_run with the default True (a call creates nothing
    unless dry_run=false is passed)."""
    m = re.search(rf"^def {tool}\((.*?)\)\s*(?:->[^:]*)?:", text, re.S | re.M)
    return bool(m) and bool(re.search(r"dry_run:[^=,]*=\s*True", m.group(1)))


@lru_cache(maxsize=1)
def _where_code() -> dict:
    """The facts the page reads from the code, checked so the page cannot outlive them."""
    import tomllib
    from pathlib import Path
    from . import browser_build, browser_check, tool_status as ts
    root = Path(__file__).resolve().parent.parent
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"] \
        if (root / "pyproject.toml").exists() else {"fabric-backend": "", "fabric-backend-mcp": ""}
    bc, bb = _src("browser_check.py"), _src("browser_build.py")
    js = _src("static/check.js") + _src("static/check-worker.js")
    local = _src("mcp_server.py")
    hosted = _src("server.py")
    downloads = {"model": "_model.zip" in bb and ".pbip" in bb, "ontology": "_ontology.rdf" in bc,
                 "app": "_app.zip" in bb, "evidence": "_evidence_report.md" in bc,
                 "dbt": "dbt" in bc + bb, "notebook": "notebook" in (bc + bb).lower()}
    creating = [t for t in ts.STATUS if ts.STATUS[t].kind == ts.CREATES]
    facts = {
        "scripts": [s for s in ("fabric-backend", "fabric-backend-mcp") if s in scripts],
        "browser_same_engine": "the exact engine the hosted service and the CLI run" in " ".join((browser_check.__doc__ or "").split()),
        "browser_counts": "validate_plan" in (browser_check.__doc__ or "") and "a total that doubles" in (browser_check.__doc__ or ""),
        "browser_writes_fabric": any(h in js + bc + bb for h in ("api.fabric.microsoft.com", "onelake.dfs", "database.windows.net")),
        "browser_decisions": "decisions" in js and "evidence report" in js,
        "downloads": downloads,
        "local_tools": [t for t in ts.LOCAL_TOOLS if re.search(rf"^def {t}\(", local, re.M)],
        "local_creating": [t for t in creating if t in ts.LOCAL_TOOLS and _default_dry_run(local, t)],
        "local_no_dry": [t for t in creating if t in ts.LOCAL_TOOLS and not _default_dry_run(local, t)],
        "hosted_creating": creating,
        "hosted_dry_default": [t for t in creating if _default_dry_run(re.sub(r"_p\.DryRun", "bool", hosted), t)],
        "deploy_script": (root / "deploy" / "krusgraph.sh").exists(),
        "location_key": '"location"' in (root / "deploy" / "krusgraph.example.json").read_text(encoding="utf-8")
                        if (root / "deploy" / "krusgraph.example.json").exists() else True,
    }
    if not (facts["browser_same_engine"] and facts["browser_counts"] and facts["browser_decisions"]
            and downloads["model"] and downloads["ontology"]) or facts["browser_writes_fabric"]:
        raise ValueError("/check's code no longer says what the Where it runs page reads from it")
    if not facts["deploy_script"] or not facts["location_key"] or len(facts["scripts"]) != 2:
        raise ValueError("the package or deploy/ no longer has what the Where it runs page names")
    return facts


def _fn(name: str) -> tuple[str, str, str]:
    from . import tool_status as ts
    return next((w, at, what) for n, w, at, what in ts.FUNCTIONS if n == name)


def _lowfirst(w: str) -> str:
    return w[:1].lower() + w[1:]


def where_cells() -> dict:
    """{(row, column): [items]}: Markdown items (backticks for code), each tool next to its own status words."""
    from . import pages, tool_status as ts
    c, v, f = _where_code(), pages._vars(), it_facts()
    w = f["where"]
    product = v["PRODUCT"]
    check_said = re.search(r'<p class="check-private"[^>]*><strong>(.*?)</strong>', _src("page_templates/check.html")).group(1)
    claude = next(x for x in ts.CLIENTS if x.name == "Claude")
    mcp_w, _at, mcp_what = _fn("`fabric-backend-mcp`")
    amt_w, amt_at, _what = _fn("`validate_plan` → `amount_levels`")
    hosted_where = w[_hosted_key(f)].split(".")[0]
    ops = [t for t in c["hosted_creating"] if ts.STATUS[t].available == ts.OPERATOR]
    d = c["downloads"]
    local_drafts = [t for _n, t in WHERE_DRAFTS if t in c["local_tools"]]
    not_local = [t for _n, t in WHERE_DRAFTS if t not in c["local_tools"]]
    cells: dict = {}
    # where it is
    cells["where", "browser"] = [f"[{v['DOMAIN']}/check](/check). {check_said}",
                                 f"The same engine as the hosted service and the CLI, run by the browser itself (Pyodide)."]
    cells["where", "computer"] = ["The open-source library, the CLI (`" + "`, `".join(c["scripts"][:1]) + "`) and the local MCP "
                                  "server over stdio (`" + c["scripts"][1] + "`), on your machine over ODBC: [run it locally](/local)."]
    cells["where", "tenant"] = [w["In your own Azure"].replace("deploy/krusgraph.sh", "`deploy/krusgraph.sh`"),
                                "The region is the one you choose: `location` in your `deploy/krusgraph.json`."]
    cells["where", "hosted"] = [f"{hosted_where}.", "Sign-in with your Microsoft Entra work account; every call runs as you."]
    # status
    cells["status", "browser"] = [f"Live ({WHERE_NOT_IN_CODE['check_live']} as of {WHERE_AS_OF})."]
    cells["status", "computer"] = ["Available in the open-source package (MIT).",
                                   f"`fabric-backend-mcp`: {_lowfirst(mcp_w)}; {mcp_what}."]
    cells["status", "tenant"] = [f"Available: `deploy/krusgraph.sh` deploys the same server.",
                                 f"{WHERE_NOT_IN_CODE['tenant_not_run'].capitalize()} (as of {WHERE_AS_OF})."]
    cells["status", "hosted"] = [f"Live: Claude as a client since {claude.works_since}; status per client and tool in the "
                                 f"[test status](#test-status)."]
    # check
    cells["check", "browser"] = ["Counted on your files' rows in the browser: duplicate and empty keys, references with no "
                                 "matching row, and header totals a join with its lines would repeat.",
                                 "A pasted columns list gives the plan without counts: there are no rows to count."]
    cells["check", "computer"] = ["`validate_plan` over ODBC, in the local stdio server and the library."]
    cells["check", "tenant"] = ["The same tools as hosted, against your Fabric, as the signed-in person."]
    cells["check", "hosted"] = [f"`validate_plan`: {ts.task_status(['validate_plan'])}."]
    for col in ("computer", "hosted"):
        cells["check", col].append(f"`validate_plan` → `amount_levels` (totals a join repeats): {_lowfirst(amt_w)}.")
    # draft
    files = [x for x, ok in (("the Power BI model as a project (.pbip)", d["model"]), ("the ontology as RDF/XML", d["ontology"]),
                             ("an app starter", d["app"]), ("an evidence report", d["evidence"])) if ok]
    missing = [x for x, ok in (("dbt", d["dbt"]), ("the notebooks", d["notebook"]), ("the pipeline", False)) if not ok]
    cells["draft", "browser"] = [f"Files to download: {_listed(files)}; drafts, nothing is created in Fabric."]
    if missing:
        cells["draft", "browser"].append(f"Not in the browser: {_listed(missing)}.")
    cells["draft", "computer"] = ["Local tools: " + ", ".join(f"`{t}`" for t in local_drafts) + "."]
    if not_local:
        cells["draft", "computer"].append("Hosted only: " + ", ".join(f"`{t}`" for t in not_local) + " and the pipeline.")
    cells["draft", "tenant"] = ["The same tools as hosted."]
    cells["draft", "hosted"] = [f"`{t}`: {ts.phrase(t)}." for _n, t in WHERE_DRAFTS]
    cells["draft", "hosted"].append(f"The pipeline: {_pipeline_words().replace('export_item_definitions', '`export_item_definitions`')}.")
    # create and review
    cells["create", "browser"] = ["Cannot write to Fabric: nothing on /check calls Fabric.",
                                  "Accept or reject on the guided demo's findings goes into the evidence report you download; "
                                  "the decisions stay in the browser."]
    cells["create", "computer"] = [", ".join(f"`{t}`" for t in c["local_creating"]) + ": a dry run unless you pass `dry_run=false`.",
                                   "`review_plan`: the plan with your decisions and its checks as a file for your own repository."]
    cells["create", "tenant"] = ["The same tools as hosted, each a dry run first.",
                                 (f"{_listed(f'`{t}`' for t in ops)} need a permission the hosted app does not ask for today; "
                                  "in your own tenant, you decide what your own Entra app may do.") if ops else ""]
    cells["create", "hosted"] = [f"`{t}`: {mark(t)[1]}." for t in c["hosted_creating"]]
    cells["create", "hosted"] += [f"Every creating tool is a dry run unless you pass `dry_run=false`.",
                                  f"`review_plan`: {ts.phrase('review_plan')}."]
    if set(c["hosted_dry_default"]) != set(c["hosted_creating"]) or c["local_no_dry"]:
        raise ValueError("a creating tool no longer defaults to a dry run; the Where it runs page says every one does")
    return {k: [x for x in items if x] for k, items in cells.items()}


def where_md() -> str:
    """The table as Markdown lists (for /docs.md and llms-full.txt): one list per task, one line per place."""
    p = _product()
    cells = where_cells()
    out = []
    for r, title, sub in WHERE_ROWS:
        out.append(f"**{title}**" + (f" ({sub})" if sub else "") + ":")
        out.append("")
        for col, name in WHERE_COLS:
            out.append(f"- {name.replace('{P}', p)}: " + " ".join(cells[r, col]))
        out.append("")
    return "\n".join(out).rstrip()


def where_notes_md() -> str:
    from . import tool_status as ts
    f = it_facts()
    working, other = clients()
    n = WHERE_NOT_IN_CODE
    lines = [
        "**Data access follows the signed-in person.** Hosted and in your own tenant, every call runs with the Microsoft "
        "Entra account that signed in, with delegated permissions only, so an agent reaches what that person can reach in "
        f"Fabric and no more. As the [privacy policy](/privacy) says: {_lowfirst(f['stored']['No table contents'])} On /check your "
        "files stay in the browser; on your own computer, [what leaves the machine](/local) is listed.",
        "",
        "**You pick the MCP client and the model.** {{PRODUCT}} itself calls no language model; the checks are counted with "
        "SQL, so a smaller model can drive them. The model is the one your MCP client uses, under your organisation's "
        "agreement with its provider. One tool writes for a model you run elsewhere: `create_data_agent` sets up a Fabric "
        "data agent's instructions and examples, and that agent answers with Fabric's own model; {{PRODUCT}} sends it no "
        f"questions. MCP clients that have signed in to the hosted service: "
        + _listed(f"{c} (at {ts.CLIENTS_TESTED[c][0]} since {ts.CLIENTS_TESTED[c][1]})" for c in working)
        + "." + (f" Experimental as {'a client' if len(other) == 1 else 'clients'}: {_listed(other)}." if other else "")
        + " Each client's status is in the [test status](#test-status).",
        "",
        f"**Not there yet, as of {WHERE_AS_OF}:** {n['clients_not_tried']}, and {n['no_packaging']}. "
        "{{PRODUCT}} is an independent open-source project of Kruse Consulting AB, not a Microsoft product.",
    ]
    return "\n".join(lines)


def _inline(md: str) -> str:
    """One item of where_cells as HTML: escaped, `code` and [text](href) kept."""
    s = E(md)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)


def _where(inner: str) -> str:
    """The table: places as columns, tasks as rows; under 700 px each task becomes a card with one labelled line per
    place, so nothing scrolls sideways at 375 px. A text version for screen readers comes before it."""
    p = _product()
    cells = where_cells()
    names = [(col, name.replace("{P}", p)) for col, name in WHERE_COLS]
    head = "".join(f'<th scope="col">{E(n)}</th>' for _c, n in names)
    body = []
    for r, title, sub in WHERE_ROWS:
        th = f'<th scope="row">{E(title)}' + (f'<span class="wr-sub">{E(sub)}</span>' if sub else "") + "</th>"
        tds = "".join(f'<td data-label="{E(n)}"><ul>' + "".join(f"<li>{_inline(x)}</li>" for x in cells[r, col]) + "</ul></td>"
                      for col, n in names)
        body.append(f'<tr class="wr-{r}">{th}{tds}</tr>')
    plain = lambda x: re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", x).replace("`", "")
    said = " ".join(f"{title}" + (f" ({sub})" if sub else "") + ": " + " ".join(
        f"{n}: " + " ".join(plain(x) for x in cells[r, col]) for col, n in names) for r, title, sub in WHERE_ROWS)
    return (f'<figure class="cx-fig wr-fig" aria-labelledby="wr-cap"><p class="visually-hidden" id="wr-said">{E(said)}</p>'
            f'<div class="wr-frame"><table class="wr-table" aria-describedby="wr-said"><caption id="wr-cap">Where {E(p)} runs, '
            f'and what each place does with a task</caption><thead><tr><td class="wr-corner"></td>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>'
            f'<figcaption class="muted tiny">Every status here is read from the code when this page is rendered (the same '
            f'list as the <a href="#test-status">test status</a>); what the code cannot say is dated, '
            f'once, under the table.</figcaption></figure>')
