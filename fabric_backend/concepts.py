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
         "how-they-connect": BASE + "/how-they-connect", "vision": BASE + "/vision"}

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
        "CONCEPT_ODCS": odcs_excerpt,
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


def _how(inner: str) -> str:
    from . import tool_status as ts
    p = E(_product())
    working, other = clients()
    tested, exp = sources()
    tag = lambda w: "tested end to end" if w == "Tested end to end" else w.lower()
    status = {c.name: c.status for c in ts.CLIENTS if c.path}
    cl = "".join(f'<li><span>{E(c)}</span><span class="cx-tag">{E(tag(status[c]))}</span></li>' for c in working + other)
    lov = next(c for c in ts.CLIENTS if c.name == "Lovable" and not c.path)
    cl += f'<li><span>Lovable, on the API</span><span class="cx-tag">{E(tag(lov.status))}</span></li>'
    items = "".join(f'<li><span>{E(n)}</span><span class="cx-tag">{E(_item_tag(tool))}</span></li>' for n, tool in ts.BUILDS)
    src = "".join(f'<li><span>{E(n)}</span><span class="cx-tag">{"tested end to end" if t else "experimental"}</span></li>'
                  for n, t in ts.SOURCES)
    plan_tag = E(ts.task_status(["plan_backend", "validate_plan"]))
    fig = f"""<figure class="cx-fig cx-how" aria-labelledby="cx-how-cap">
<div class="cx-how-grid">
<div class="cx-part cx-cli"><p class="cx-part-h">Clients</p><p class="cx-part-what">Where you ask</p><ul class="cx-list cx-tags">{cl}</ul></div>
<div class="cx-link cx-a1"><span class="cx-link-word">MCP</span>{_ARROW}</div>
<div class="cx-part cx-kg"><p class="cx-part-h">{p}</p><p class="cx-part-what">One plan: keys and relationships, each with its rule, counted against the rows</p><ul class="cx-list cx-tags"><li><span>Plan and check</span><span class="cx-tag">{plan_tag}</span></li></ul></div>
<div class="cx-link cx-a2"><span class="cx-link-word">creates when you ask</span>{_ARROW}</div>
<div class="cx-part cx-fab"><p class="cx-part-h">Fabric items</p><p class="cx-part-what">From the same plan, a dry run first</p><ul class="cx-list cx-tags">{items}</ul></div>
<div class="cx-link cx-d1"><span class="cx-link-word">reads metadata, counts rows</span>{_ARROW}</div>
<div class="cx-link cx-d2"><span class="cx-link-word">built on your tables</span>{_ARROW}</div>
<div class="cx-part cx-one"><p class="cx-part-h">OneLake</p><p class="cx-part-what">Where your tables stay; {p} copies none of them</p><ul class="cx-list cx-tags">{src}</ul></div>
</div>
<figcaption id="cx-how-cap" class="muted tiny">The four parts and how far each has been tested, from the same list as the <a href="/docs/reference/test-status#test-status">test status</a>.</figcaption>
</figure>"""
    return fig + inner


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
    return (f'<div class="cx-scroll" role="region" aria-label="Diagram: the shop as an ontology" tabindex="0">'
            f'<svg class="cx-svg" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" role="img" aria-label="{E(said)}">'
            '<defs><marker id="cx-ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0 0 10 5 0 10z" class="cx-ah"/></marker></defs>' + "".join(parts) + "</svg></div>")


def _ontology(inner: str) -> str:
    return (f'<figure class="cx-fig cx-onto">{_ontology_svg()}<p class="cx-hint muted tiny">Swipe the diagram sideways to see all of it; the table below says the same.</p><figcaption class="muted tiny">Generated by the engine from the '
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


def _connect(inner: str) -> str:
    from . import tool_status as ts
    s, i = shop(), interface()
    p = E(_product())
    rel = f"{i['source']}.{_cols(i['source_cols'])} → {i['target']}.{_cols(i['target_cols'])}"
    outs = [("API for GraphQL", _item_tag("create_backend")), ("Power BI semantic model", _item_tag("create_semantic_model")),
            ("Fabric IQ ontology", _item_tag("create_ontology")), ("Data products and contracts", ts.word("domain_draft").lower())]
    cards = "".join(f'<li><span class="cx-out-h">{E(n)}</span><span class="cx-tag">{E(t)}</span></li>' for n, t in outs)
    fig = f"""<figure class="cx-fig cx-connect" aria-labelledby="cx-connect-cap">
<div class="cx-connect-grid">
<div class="cx-part cx-plan"><p class="cx-part-h">One reviewed plan</p><p class="cx-part-what">{E(plan_counts_md())} on the shop schema, each with its rule, counted against the rows and decided by you</p><p class="cx-rel"><code>{E(rel)}</code></p></div>
<div class="cx-link cx-fan">{_ARROW}</div>
<ul class="cx-outs">{cards}</ul>
</div>
<figcaption id="cx-connect-cap" class="muted tiny">Every output is written from the same plan by {p}; the list below follows one relationship, <code>{E(rel)}</code>, through each of them.</figcaption>
</figure>"""
    return fig + inner


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
    return {"how-it-works": _how, "ontology": _ontology, "domains": _domains, "connect": _connect, "vision": _vision}
