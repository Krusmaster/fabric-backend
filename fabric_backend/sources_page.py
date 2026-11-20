"""SRC1 (20 November 2026): the public pages /sources, /sources/salesforce and /sources/dynamics365.

Which raw tables Krusgraph knows for SAP, Salesforce and Dynamics 365 (Dataverse and Business Central), how they reach
Fabric, and which data products the engine proposes from them. Nothing here is a hand-typed list of tables:

- the tables, their level, plain-word title and key, the applied relationships and the traps are read from each pack's
  manifest (fabric_backend/packs/<pack>/manifest.yaml, regenerated from the module files by pack_manifest);
- the data products are what the engine computes on each pack's synthetic demo, now: domains.draft on sap_demo,
  salesforce_demo.report() and dynamics_demo.products(). tests/test_src1_sources_page.py compares them with the outputs
  the other tests pin (tests/golden/pk2_dynamics_products.json, the generated section of docs/SALESFORCE.md and
  tests/test_domains.py for SAP);
- the routes into Fabric are hand-kept (they are not in the manifests), each naming the manifest sources it rests on,
  with the status the docs give it (docs/SAP.md, docs/SAP-CDS.md, docs/SALESFORCE.md, docs/DYNAMICS365.md). The test
  checks that every source it names exists and was opened.

Hand-written here, and checked by the tests to match the engine: the question each proposed data product answers.
"""
from __future__ import annotations

import html
from functools import lru_cache
from pathlib import Path

import yaml

PACKS = Path(__file__).resolve().parent / "packs"

# The sentences the page must carry (Gustav, 20 November 2026). tests/test_src1_sources_page.py looks for each.
HONESTY = (
    "The packs are built from public documentation.",
    "The data products shown are what the engine proposes on synthetic demo data.",
    "Nothing has been verified against a customer's SAP, Salesforce or Dynamics 365 system yet.",
)
INDEPENDENT = "Krusgraph is independent and is not affiliated with SAP, Salesforce or Microsoft; the product names are used only as names."

LEVELS = {"header": "document header", "item": "document line", "schedule_line": "schedule line", "master": "master data",
          "organization": "organisation", "partner": "partner roles", "status": "status", "text": "text",
          "document_flow": "document flow"}

# key, display name, the pack, the page with the details, the demo module and the mascot's role (Onto says the numbers)
SOURCES = (
    {"key": "sap", "name": "SAP", "pack": "sap", "page": "/sources#sap", "keys_page": "/sap", "demo": "sap_demo"},
    {"key": "salesforce", "name": "Salesforce", "pack": "salesforce", "page": "/sources/salesforce", "demo": "salesforce_demo"},
    {"key": "dynamics365", "name": "Dynamics 365", "pack": "dynamics365", "page": "/sources/dynamics365", "demo": "dynamics_demo"},
)

# How the data reaches Fabric. Status words: "read" (the page was opened and says this), "unverified" (no page read
# says it), "not read by the pack". `sources` are manifest source ids; the test checks each exists and was opened.
ROUTES = {
    "sap": [
        {"route": "Fabric mirroring of SAP, through an SAP Datasphere replication flow",
         "lands": "A mirrored database, merged from the files the replication flow writes; sources S/4HANA, ECC, BW/4HANA, BW.",
         "status": "read", "note": "Microsoft's pages name no tables: how tables and columns are named in OneLake is unverified.",
         "sources": ["ms_fabric_mirroring_sap", "cds_ms_mirroring_sap"]},
        {"route": "Copy job in Fabric Data Factory, reading what a Datasphere replication flow landed",
         "lands": "Tables in a lakehouse, with inserts, updates and deletions.",
         "status": "read", "note": "The same naming question as mirroring: unverified.", "sources": ["cds_ms_mirroring_sap"]},
        {"route": "SAP Table and SAP HANA connectors in Data Factory",
         "lands": "Tables with the technical names and the client column.",
         "status": "read", "note": "The connector overview lists no SAP CDC connector for Fabric.", "sources": ["ms_fabric_connectors"]},
        {"route": "Released CDS views of S/4HANA, through a replication flow",
         "lands": "Tables named after the views, columns after the view's fields, no client column.",
         "status": "unverified", "note": "Which views a flow can read was read in SAP Datasphere's documentation; the landed names were not seen.",
         "sources": ["sap_datasphere_replication"]},
    ],
    "salesforce": [
        {"route": "Copy job with the Salesforce objects connector",
         "lands": "One table per object (Account, OpportunityLineItem), the field API names as columns.",
         "status": "read", "note": "That the tables are named after the objects is our reading of two pages together: unverified until seen in a workspace.",
         "sources": ["ms_sf_objects_connector", "ms_copy_job_create", "ms_sf_copy_activity"]},
        {"route": "Dataflow Gen2 with the Salesforce Objects connector",
         "lands": "A table per query, named after the query.",
         "status": "unverified", "note": "The query names and the relationship columns Power Query adds were not seen.",
         "sources": ["ms_pq_salesforce_objects", "ms_dataflow_destinations"]},
        {"route": "Database mirroring",
         "lands": "Not available: the mirroring overview lists no Salesforce source.",
         "status": "read", "note": "", "sources": ["ms_mirroring_overview"]},
        {"route": "Open mirroring tools from other vendors",
         "lands": "What each tool writes into an open mirrored database.",
         "status": "unverified", "note": "Their table and column naming is theirs.", "sources": ["ms_open_mirroring_partners"]},
    ],
    "dynamics365": [
        {"route": "Dataverse: Link to Microsoft Fabric",
         "lands": "Tables by logical name (salesorderdetail) in a lakehouse, with system columns such as IsDelete and SinkModifiedOn.",
         "status": "read", "note": "That every lookup column keeps its logical name in the lakehouse: unverified.",
         "sources": ["fabric_link", "fabric_link_platform", "synapse_link_columns"]},
        {"route": "Business Central: Fabric mirroring (preview)",
         "lands": "An open mirrored database.",
         "status": "not read by the pack", "note": "Table and column naming and the company column are not documented on the pages read.",
         "sources": ["bc_fabric_mirroring"]},
        {"route": "Business Central: bc2adls export (archived, unsupported)",
         "lands": "Tables named <Table>-<id> (SalesHeader-36), columns <Field>-<id>, a $Company column.",
         "status": "read", "note": "Read in its source code.", "sources": ["bc2adls"]},
        {"route": "Business Central: a copy of the SQL database (on premises)",
         "lands": "One table per company: <company>$<table>$<app id>.",
         "status": "read", "note": "", "sources": ["bc_sql_names"]},
    ],
}

# The question each proposed data product answers, keyed by the name the engine gives it. The test fails when the engine
# proposes a product without a question here, or a question names a product the engine no longer proposes.
QUESTIONS = {
    "sap": {
        "order-to-cash": "What did we sell, deliver and invoice, per customer and per month?",
        "customer master": "Who is the customer, where are they, and whom do we talk to there?",
    },
    "salesforce": {
        "marketing": "Which campaigns bring leads, and which leads become customers?",
        "sales": "What is in the pipeline, what was won, and what was ordered or put under contract?",
        "sales and product catalog": "Which products, at which price, are on our opportunities, quotes and orders?",
        "activities and customers": "What happens around each customer: contacts, assets, cases and activities?",
    },
    "dynamics365": {
        "lead_to_cash": "From lead to invoice: what was quoted, ordered and invoiced, per account?",
        "order_to_cash": "What did we sell and invoice in Business Central, and what is still open per customer?",
        "customer_360": "What do we know about one account: contacts, activities, opportunities, orders, invoices and cases?",
        "service_cases": "How many cases per account and product, and who handles them?",
    },
}

CROSS_NOT_BUILT = ("Not built: one plan across several lakehouses, warehouses or databases (a design note only), and any pack "
                   "that links SAP, Salesforce and Dynamics 365 records to each other, such as the same customer in SAP and in Salesforce.")
CROSS_SHORTCUTS = ("Several sources in one lakehouse work today: tables a lakehouse holds as OneLake shortcuts are listed by its SQL "
                   "analytics endpoint like its own, so they are planned, checked and joined as one source.")


@lru_cache(maxsize=None)
def manifest(pack: str) -> dict:
    return yaml.safe_load((PACKS / pack / "manifest.yaml").read_text(encoding="utf-8"))


def _entities(pack: str) -> dict[str, dict]:
    return {e["name"]: e for e in manifest(pack)["entities"]}


def _source_ids(pack: str) -> dict[str, dict]:
    return {s["id"]: s for s in manifest(pack)["sources"]}


@lru_cache(maxsize=None)
def _api_names() -> dict[str, str]:
    """Salesforce objects by their API name (Account, OpportunityLineItem), as the demo lands them."""
    from . import salesforce_demo, sap_pack
    return {sap_pack.pack_table(n, "salesforce"): n for n in salesforce_demo.tables()}


def display_name(pack: str, name: str) -> str:
    """How a pack table is shown: SAP by its table name, Salesforce by its API name, Dataverse by its logical name,
    Business Central by its plain name and number ("Sales Header (36)")."""
    e = _entities(pack)[name]
    if pack == "salesforce":
        return _api_names().get(name, name)
    if pack == "dynamics365":
        return e["title"].split(":")[0] if e["module"] == "business_central" else name.lower()
    return name


def module_name(mid: str) -> str:
    """accounting_document -> accounting document; cds_order_to_cash -> CDS views, order to cash."""
    words = mid.replace("_", " ")
    return "CDS views, " + words[4:] if mid.startswith("cds_") else words


def _table(e: dict) -> dict:
    return {"name": e["name"], "level": LEVELS.get(e.get("level", ""), e.get("level", "")), "title": e.get("title", ""),
            "key": list(e.get("key", [])), "variants": list(e.get("variants", []))}


def modules(pack: str) -> list[dict]:
    """Per module of a pack: its title, tables (level, plain-word title, key), the applied relationships between two
    different tables and the traps by title. All read from the manifest."""
    m = manifest(pack)
    out = []
    for mod in m["modules"]:
        mid = mod["module"]
        tables = [_table(e) for e in m["entities"] if e.get("module") == mid]
        seen, rels = set(), []
        for r in m["candidate_relationships"]:
            if r.get("module") != mid or not r.get("applied"):
                continue
            a, b = r["from"].split(".")[0], r["to"].split(".")[0]
            if a == b or (a, b) in seen:
                continue
            seen.add((a, b))
            rels.append({"from": a, "to": b, "role": (r.get("role") or "").replace("_", " ")})
        traps = [{"title": t["title"]} for t in m["traps"] if t.get("module") == mid]
        out.append({"module": mid, "title": mod["title"], "tables": tables, "relationships": rels, "traps": traps})
    return out


def sources_read(pack: str) -> tuple[int, int]:
    """(opened, not opened) among the public sources the pack cites."""
    v = [bool(s.get("verified")) for s in manifest(pack)["sources"]]
    return sum(v), len(v) - sum(v)


# ---------------------------------------------------------------- the data products, from the engine

@lru_cache(maxsize=None)
def products(key: str) -> tuple[dict, ...]:
    """The data products the engine proposes on the source's synthetic demo, computed now. Each: name (the engine's),
    title, tables (pack table names, in the demo's order), question."""
    from . import sap_pack
    q = QUESTIONS[key]
    if key == "sap":
        from . import domains, evidence, sap_demo
        from .infer import plan
        schema, execute = sap_demo.sqlite()
        p = plan(schema)
        d = domains.draft(p, "sap", "sap demo", validation=evidence.validate(p, execute, max_items=200))
        found = [(x["name"], x["name"], sorted(x["tables"])) for x in d["domains"]]
    elif key == "salesforce":
        from . import salesforce_demo
        found = [(x["name"], x["name"], x["tables"]) for x in salesforce_demo.report()["domains"]]
    else:
        from . import dynamics_demo
        got = dynamics_demo.products()
        found = [(pid, got[pid]["title"], dynamics_demo.PRODUCTS[pid]["tables"]) for pid in got]
    pack = next(s["pack"] for s in SOURCES if s["key"] == key)
    return tuple({"name": name, "title": title, "tables": [sap_pack.pack_table(t, pack) or t for t in tables],
                  "question": q.get(name, "")} for name, title, tables in found)


@lru_cache(maxsize=None)
def demo_tables(key: str) -> int:
    from importlib import import_module
    demo = next(s["demo"] for s in SOURCES if s["key"] == key)
    return len(import_module(f"fabric_backend.{demo}").tables())


def summary() -> list[dict]:
    """One row per source for the overview: the numbers Onto says and the table source -> raw tables -> data products."""
    out = []
    for s in SOURCES:
        m = manifest(s["pack"])
        opened, not_opened = sources_read(s["pack"])
        out.append({**s, "tables": len(m["entities"]), "modules": len(m["modules"]),
                    "relationships": sum(1 for r in m["candidate_relationships"] if r.get("applied")),
                    "traps": len(m["traps"]), "demo_tables": demo_tables(s["key"]), "products": list(products(s["key"])),
                    "sources_opened": opened, "sources_not_opened": not_opened, "review_status": m.get("review_status", ""),
                    "version": m.get("version", "")})
    return out


def cross_source() -> dict:
    """What exists across sources today: the younium_salesforce pack's one link between the systems (from its manifest)."""
    m = manifest("younium_salesforce")
    link = next(r for r in m["candidate_relationships"] if r.get("applied") and r["from"].endswith("EXTERNAL_CRM_ID"))
    younium = [s for s in m["sources"] if s["id"].startswith("younium")]
    return {"from": link["from"], "to": link["to"], "younium_sources": len(younium),
            "younium_opened": sum(1 for s in younium if s.get("verified")),
            "trap": next(t["title"] for t in m["traps"] if t["name"] == "salesforce_id_length")}


# ---------------------------------------------------------------- HTML

e = html.escape


def _code(pack: str, name: str) -> str:
    """A table on the page: the name shown, and the manifest's name in data-pack-table (the test reads it)."""
    title = _entities(pack)[name].get("title", "")
    return f'<code data-pack="{e(pack)}" data-pack-table="{e(name)}" title="{e(title)}">{e(display_name(pack, name))}</code>'


def _wrap(head: tuple[str, ...], rows: list[list[str]], label: str) -> str:
    """A table that stacks into labelled blocks on a phone (each cell carries its column's name in data-label)."""
    body = "".join("<tr>" + "".join((f'<th scope="row" data-label="{e(head[i])}">{c}</th>' if i == 0 else
                                     f'<td data-label="{e(head[i])}">{c}</td>') for i, c in enumerate(r)) + "</tr>" for r in rows)
    return (f'<div class="table-wrap src-stack" role="region" aria-label="{e(label)}"><table><thead><tr>'
            + "".join(f'<th scope="col">{h}</th>' for h in head) + f"</tr></thead><tbody>{body}</tbody></table></div>")


def products_html(key: str) -> str:
    pack = next(s["pack"] for s in SOURCES if s["key"] == key)
    rows = [[e(p["title"]), " ".join(_code(pack, t) for t in p["tables"]), e(p["question"])] for p in products(key)]
    return _wrap(("Data product", "Tables it uses", "The question it answers"), rows, "Data products the engine proposes")


def routes_html(key: str) -> str:
    pack = next(s["pack"] for s in SOURCES if s["key"] == key)
    src = _source_ids(pack)
    word = {"read": "Read in the documentation", "unverified": "Unverified", "not read by the pack": "Not read by the pack yet"}
    rows = []
    for r in ROUTES[key]:
        cited = [i for i in r["sources"] if src[i].get("url")]
        links = ", ".join(f'<a href="{e(src[i]["url"])}" target="_blank" rel="noopener" title="{e(src[i]["title"])}">'
                          f'{e(src[i].get("publisher", "source"))}{" " + str(n) if len(cited) > 1 else ""}</a>' for n, i in enumerate(cited, 1))
        rows.append([e(r["route"]), e(r["lands"]), f'<span class="pill src-{r["status"].split()[0]}">{word[r["status"]]}</span> {e(r["note"])}', links])
    return _wrap(("Route", "What lands in Fabric", "Status", "Source"), rows, "How the data reaches Fabric")


def tables_html(key: str) -> str:
    pack = next(s["pack"] for s in SOURCES if s["key"] == key)
    out = []
    for i, mod in enumerate(modules(pack)):
        rows = [[_code(pack, t["name"]), e(t["title"]), e(t["level"]), ", ".join(f"<code>{e(k)}</code>" for k in t["key"])]
                for t in mod["tables"]]
        rels = "".join(f'<li>{_code(pack, r["from"])} → {_code(pack, r["to"])}{" (" + e(r["role"]) + ")" if r["role"] else ""}</li>'
                       for r in mod["relationships"])
        traps = "".join(f'<li>{e(t["title"])}</li>' for t in mod["traps"])
        out.append(
            f'<details class="src-mod"{" open" if i == 0 else ""}><summary><span class="src-mod-t">{e(mod["title"])}</span> '
            f'<span class="pill">{len(mod["tables"])} tables</span></summary>'
            + _wrap(("Table", "In plain words", "Level", "Key"), rows, "Tables of " + mod["module"])
            + (f'<h4>Main links ({len(mod["relationships"])} applied)</h4><ul class="src-rels">{rels}</ul>' if rels else "")
            + (f'<h4>Traps</h4><ul class="src-traps">{traps}</ul>' if traps else "")
            + "</details>")
    return "".join(out)


def honesty_html(key: str | None = None) -> str:
    items = list(HONESTY)
    for s in summary():
        if key and s["key"] != key:
            continue
        items.append(f'{s["name"]}: {s["sources_opened"]} of {s["sources_opened"] + s["sources_not_opened"]} public sources the pack cites '
                     f'were opened when it was written. {VERIFIED[s["key"]]}')
    items.append(INDEPENDENT)
    return '<ul class="src-honest">' + "".join(f"<li>{e(x)}</li>" for x in items) + "</ul>"


# What each source's docs say is verified (docs/SAP.md "Sources, and what is verified", docs/SALESFORCE.md "Verified,
# and what is not", docs/DYNAMICS365.md "Sources, and what is verified").
VERIFIED = {
    "sap": ("The SAP Help pages were not opened (outside the session's network) and are to be re-checked; verified against "
            "data: nothing yet. Tried on synthetic SAP-shaped tables only, never on an SAP system."),
    "salesforce": ("Salesforce's Object Reference and Field Reference were read for all 21 objects on 17 November 2026; one "
                   "Help article on queues could not be read. No org was read: that the pack is right about a real org is not verified."),
    "dynamics365": ("The Microsoft Learn pages were opened on 17 November 2026, Business Central keys in Microsoft's source code; "
                    "nothing has been checked against a real environment's or company's rows."),
}


def overview_html() -> tuple[str, str]:
    rows = []
    cards = ""
    for s in summary():
        pack = s["pack"]
        say = (f'The {s["name"]} pack knows {s["tables"]} tables in {s["modules"]} '
               f'{"module" if s["modules"] == 1 else "modules"}; on the {s["demo_tables"]}-table demo the engine proposes '
               f'{len(s["products"])} data products.')
        cards += (f'<li class="card src-card" id="card-{s["key"]}"><div class="src-say"><span class="src-fig" aria-hidden="true">'
                  f'<span data-mascot="onto" data-pose="point" data-label=""></span></span>'
                  f'<p><span class="visually-hidden">Onto says: </span>{e(say)}</p></div>'
                  f'<h3>{e(s["name"])}</h3><p class="muted">{e(manifest(pack)["title"])}</p>'
                  f'<p class="src-go"><a class="btn secondary small" href="{e(s["page"])}">{e(s["name"])} tables and products</a></p></li>')
        mods = "; ".join(e(module_name(m["module"])) + f' ({len(m["tables"])})' for m in modules(pack))
        prods = "".join(f'<li><strong>{e(p["title"])}</strong>: {" ".join(_code(pack, t) for t in p["tables"])}'
                        f'<br><span class="muted">{e(p["question"])}</span></li>' for p in s["products"])
        rows.append([f'<a href="{e(s["page"])}">{e(s["name"])}</a>',
                     f'<strong>{s["tables"]} tables</strong>, {s["relationships"]} applied links, {s["traps"]} traps. {mods}.',
                     f'<ul class="src-prods">{prods}</ul>'])
    return ('<ul class="src-cards">' + cards + "</ul>",
            _wrap(("Source", "Raw tables in the pack", "Data products the engine proposes on the demo"), rows,
                  "Source, raw tables and data products"))


def cross_html() -> str:
    c = cross_source()
    a, b = c["from"].split("."), c["to"].split(".")
    return ("<ul class=\"src-cross\">"
            f"<li><strong>Younium beside Salesforce.</strong> The <code>younium_salesforce</code> pack links a Younium account's "
            f"<code>{e(a[1])}</code> to the Salesforce <code>{e(b[0].title())}.{e(b[1].title())}</code>, and warns: {e(c['trap'])}. "
            f"{c['younium_opened']} of its {c['younium_sources']} Younium sources could be opened, so the Younium side is unverified.</li>"
            f"<li>{e(CROSS_SHORTCUTS)}</li><li>{e(CROSS_NOT_BUILT)}</li></ul>")


STYLE = """<style>
.src-cards{list-style:none;padding:0;margin:18px 0 0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
@media (max-width:860px){.src-cards{grid-template-columns:minmax(0,1fr)}}
.src-card{display:flex;flex-direction:column;gap:6px;padding:22px}
.src-card h3{margin:6px 0 0}
.src-card .muted{margin:0;font-size:15px}
.src-go{margin:auto 0 0;padding-top:10px}
.src-say{display:grid;grid-template-columns:64px minmax(0,1fr);gap:12px;align-items:center}
.src-say p{margin:0;background:var(--card-2);border:1px solid var(--line);border-radius:14px;padding:10px 12px;font-weight:600;font-size:15px}
.src-fig .mascot{width:64px;height:64px}
html[data-mascots="off"] .src-say{grid-template-columns:minmax(0,1fr)}
html[data-mascots="off"] .src-fig{display:none}
.src-prods,.src-rels,.src-traps,.src-cross,.src-honest{margin:0;padding-left:18px}
.src-prods li{margin:0 0 8px}
.src-tables code,.src-prods code,.src-rels code{display:inline-block;margin:0 2px 2px 0;overflow-wrap:anywhere}
.src-mod{border:1px solid var(--line);border-radius:var(--radius-s);background:var(--card);padding:10px 14px;margin:0 0 10px}
.src-mod summary{cursor:pointer;font-weight:700;min-height:44px;display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.src-mod-t{flex:1 1 220px;min-width:0}
.src-mod h4{margin:14px 0 6px}
.src-honest-box{border-left:4px solid var(--sage, var(--line))}
.src-honest-box p{margin:0}
.src-ctas{display:flex;flex-wrap:wrap;gap:12px}
.pill.src-read{color:var(--ink)}
.src-stack table{width:100%}
.src-stack tbody th{min-width:5em}
.src-rels{display:flex;flex-wrap:wrap;gap:4px 14px;list-style:none;padding-left:0}
.src-stack td{overflow-wrap:break-word}
@media (max-width:640px){
.src-stack{overflow:visible;border:0;background:none}
.src-stack thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.src-stack table,.src-stack tbody,.src-stack tr,.src-stack th,.src-stack td{display:block;width:auto;min-width:0}
.src-stack tr{border:1px solid var(--line);border-radius:var(--radius-s);background:var(--card);margin:0 0 10px;padding:6px 0}
.src-stack tbody th,.src-stack td{border:0;padding:4px 12px;white-space:normal;text-align:left}
.src-stack td::before{content:attr(data-label);display:block;font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
}
</style>"""


def page_vars(path: str) -> dict[str, str]:
    cards, table = overview_html()
    out = {"SRC_CARDS": cards, "SRC_TABLE": table, "SRC_CROSS": cross_html(), "SRC_HONEST": honesty_html(), "SRC_STYLE": STYLE,
           "SRC_HONEST_TOP": " ".join(e(x) for x in HONESTY)}
    for s in SOURCES:
        k = s["key"].upper()
        out[f"SRC_{k}_TABLES"] = tables_html(s["key"])
        out[f"SRC_{k}_ROUTES"] = routes_html(s["key"])
        out[f"SRC_{k}_PRODUCTS"] = products_html(s["key"])
        out[f"SRC_{k}_HONEST"] = honesty_html(s["key"])
        out[f"SRC_{k}_COUNT"] = str(len(manifest(s["pack"])["entities"]))
        out[f"SRC_{k}_DEMO"] = str(demo_tables(s["key"]))
    return out
