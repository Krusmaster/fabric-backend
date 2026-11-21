"""A catalog of classic data products and the knowledge packs' tables mapped to it (round DP1, 21 November 2026).

The catalog (`data_products/catalog.yaml`) lists about thirty data products a business usually wants, whatever its
systems: customer, sales order, invoice, journal entry, opportunity, subscription and so on. Per product it says what one
row is (the grain), which generic columns make a row unique (the business key), which conformed dimensions it joins,
its measures and their level, the traps a person falls into, and the questions it answers. It is written from general
data-modelling knowledge; it copies no licensed industry model.

The mapping (`data_products/mapping.yaml`) places every table of the four knowledge packs (sap, salesforce, dynamics365,
younium_salesforce; see docs/PACKS.md) in the catalog: which product, which role in it (header, line, master, version,
bridge ...), how the pack's key columns map to the product's business key, how sure the mapping is, and the evidence the
pack itself gives for the table (its sources read or not). A table that is no data product of its own is listed with a
reason. tests/test_dp1_data_product_catalog.py runs problems() so the mapping cannot drift from the pack manifests.

    load_catalog()             -> the catalog as a dict
    load_mapping()             -> the mapping as a dict
    catalog_problems(c)        -> what is malformed in a catalog (the rules of catalog.schema.json and more)
    mapping_problems(m, c)     -> what differs between a mapping and the catalog and the pack manifests
    tables(pack, m)            -> {table: [entries]} with the entries a pack inherits from another pack
    evidence(pack, table)      -> verified | partly_verified | unverified, from the pack's own sources
    coverage(source, m, c)     -> per product: full | partial | none | generated, the roles present and missing
    matrix(m, c)               -> {product: {source: state}}
    render_mapping(doc)        -> the mapping as text in the file's layout

Nothing here runs a query, reads rows or connects to anything; there is no matcher for unknown tables yet (a later
round; docs/DATA-PRODUCT-CATALOG.md describes it). Needs PyYAML to read the files (the test extra installs it).
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent / "data_products"
CATALOG = HERE / "catalog.yaml"
MAPPING = HERE / "mapping.yaml"
SCHEMA = HERE / "catalog.schema.json"
MAPPING_SCHEMA = HERE / "mapping.schema.json"

AREAS = ("master_data", "reference", "sales", "finance", "procurement", "supply_chain", "crm", "marketing", "service",
         "subscription", "hr", "planning")
KINDS = ("master", "transaction", "plan", "reference")
# A table's role in a product. header/line: a document and its lines; master: the product's own rows (or the rows of a
# master product); extension: a master's rows per organisation (company, sales area); text: one row per language;
# version: a row per validity period or change; bridge: a link table (partners, contact roles, members, clearing);
# schedule_line: dates and quantities below a line; status: a status table beside a document; flow: the links from one
# document to the next; snapshot: a state on a date.
ROLES = ("header", "line", "master", "extension", "text", "version", "bridge", "schedule_line", "status", "flow", "snapshot")
TRAP_KINDS = ("header_amount_per_line", "versions", "soft_delete", "multi_company", "currency", "status_filter", "double_count",
              "sign", "identity", "personal_data", "text_per_language", "leading_zeros", "hierarchy", "fiscal_calendar",
              "polymorphic", "other")
CONFIDENCE = ("high", "medium", "low")
EVIDENCE = ("verified", "partly_verified", "unverified")
NOT_KINDS = ("helper", "outside_catalog")
STATES = ("full", "partial", "none", "generated")
PRODUCT_FIELDS = ("id", "title", "area", "kind", "grain", "business_key", "dimensions", "measures", "traps", "questions", "roles")
ENTRY_FIELDS = ("product", "role", "key", "confidence", "evidence", "note")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")


# ------------------------------------------------------------------ reading -----------------------------------------

def _yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_catalog() -> dict:
    return _yaml(CATALOG)


def load_mapping() -> dict:
    return _yaml(MAPPING)


def products(catalog: dict | None = None) -> dict[str, dict]:
    """{id: product} in the catalog's order."""
    return {p["id"]: p for p in (catalog or load_catalog())["products"]}


# ------------------------------------------------------------------ the catalog's own check ---------------------------

def catalog_problems(catalog: dict) -> list[str]:
    """What is malformed in a catalog: missing or unknown fields, values outside the lists above, a repeated id, a
    dimension that is not a product of the catalog, two or three questions, a role list outside ROLES. The JSON schema
    (catalog.schema.json) says the same for a tool that reads JSON schemas; this check needs no library."""
    out = []
    if not re.fullmatch(r"\d+\.\d+\.\d+", str(catalog.get("version", ""))):
        out.append(f"version {catalog.get('version')!r} is not major.minor.patch")
    if catalog.get("review_status") not in ("proposed", "reviewed"):
        out.append(f"review_status {catalog.get('review_status')!r} is not proposed or reviewed")
    ps = catalog.get("products") or []
    ids = [p.get("id") for p in ps]
    if len(set(ids)) != len(ids):
        out.append("a product id is repeated")
    known = set(ids)
    for p in ps:
        pid = p.get("id")
        for f in PRODUCT_FIELDS:
            if f not in p:
                out.append(f"{pid}: {f} is missing")
        for f in set(p) - set(PRODUCT_FIELDS):
            out.append(f"{pid}: unknown field {f}")
        if not isinstance(pid, str) or not _ID.match(pid):
            out.append(f"{pid!r} is not a lower-case id")
        for f in ("title", "grain"):
            if not isinstance(p.get(f), str) or not p.get(f):
                out.append(f"{pid}: {f} is empty")
        if p.get("area") not in AREAS:
            out.append(f"{pid}: area {p.get('area')!r} is not one of {', '.join(AREAS)}")
        if p.get("kind") not in KINDS:
            out.append(f"{pid}: kind {p.get('kind')!r} is not one of {', '.join(KINDS)}")
        bk = p.get("business_key")
        if not isinstance(bk, list) or not bk or not all(isinstance(c, str) and _ID.match(c) for c in bk) or len(set(bk)) != len(bk):
            out.append(f"{pid}: business_key must be a non-empty list of distinct lower-case column names")
        for d in p.get("dimensions") or []:
            if d not in known or d == pid:
                out.append(f"{pid}: dimension {d!r} is not another product of the catalog")
        for m in p.get("measures") or []:
            if not m.get("name") or not m.get("level") or set(m) - {"name", "level", "note"}:
                out.append(f"{pid}: a measure needs name and level (and at most a note): {m}")
        traps = p.get("traps") or []
        if not traps:
            out.append(f"{pid}: no traps")
        for t in traps:
            if t.get("kind") not in TRAP_KINDS or not t.get("text") or set(t) - {"kind", "text"}:
                out.append(f"{pid}: a trap needs a kind of {', '.join(TRAP_KINDS)} and a text: {t}")
        q = p.get("questions") or []
        if not 1 <= len(q) <= 3 or not all(isinstance(s, str) and s.endswith("?") for s in q):
            out.append(f"{pid}: one to three questions, each ending in a question mark")
        roles = p.get("roles") or {}
        if set(roles) != {"required", "optional"}:
            out.append(f"{pid}: roles needs required and optional")
        for r in (roles.get("required") or []) + (roles.get("optional") or []):
            if r not in ROLES:
                out.append(f"{pid}: role {r!r} is not one of {', '.join(ROLES)}")
        if set(roles.get("required") or []) & set(roles.get("optional") or []):
            out.append(f"{pid}: a role is both required and optional")
    return out


# ------------------------------------------------------------------ the packs ---------------------------------------

@functools.lru_cache(maxsize=None)
def _manifest(pack: str) -> dict:
    """A pack's manifest, read once per process (the files do not change while it runs; callers do not change it)."""
    from . import pack_manifest
    return pack_manifest.load(pack)


def _entities(pack: str) -> dict[str, dict]:
    return {e["name"]: e for e in _manifest(pack)["entities"]}


def known_columns(pack: str) -> dict[str, set[str]]:
    """The columns a pack names per table: its key, unique keys, amounts and the columns of its relationships."""
    from . import pack_manifest
    m = _manifest(pack)
    cols: dict[str, set[str]] = {}
    for e in m["entities"]:
        c = cols.setdefault(e["name"], set())
        c.update(e["key"])
        for u in e.get("unique_keys") or []:
            c.update(u)
        c.update(a["column"] for a in e.get("amounts") or [])
    for r in m["candidate_relationships"]:
        for side in ("from", "to"):
            t, cs = pack_manifest.parse_ref(r[side])
            cols.setdefault(t, set()).update(cs)
    return cols


def evidence(pack: str, table: str, manifest: dict | None = None) -> str:
    """What the pack says about its own sources for a table: verified when every source it cites was opened and read
    (for example a Microsoft Learn or Salesforce developer page), unverified when none was, partly_verified otherwise.
    Read is not tested: no table here has been checked on a customer system."""
    m = manifest or _manifest(pack)
    read = {s["id"]: bool(s["verified"]) for s in m["sources"]}
    e = next(e for e in m["entities"] if e["name"] == table)
    flags = [read.get(s, False) for s in e["sources"]]
    return "verified" if flags and all(flags) else "unverified" if not any(flags) else "partly_verified"


def tables(pack: str, mapping: dict | None = None) -> dict[str, list[dict]]:
    """A pack's mapped tables: its own and, for a module it reads from another pack (younium_salesforce reads the
    Salesforce objects from the salesforce pack), the other pack's entries for the tables of that module."""
    mapping = mapping or load_mapping()
    p = mapping["packs"][pack]
    out = dict(p.get("tables") or {})
    ents = _entities(pack)
    for module, other in (p.get("inherit") or {}).items():
        theirs = mapping["packs"][other].get("tables") or {}
        for name, e in ents.items():
            if e["module"] == module and name in theirs:
                out[name] = theirs[name]
    return out


def not_products(pack: str, mapping: dict | None = None) -> dict[str, dict]:
    mapping = mapping or load_mapping()
    p = mapping["packs"][pack]
    out = dict(p.get("not_a_data_product") or {})
    ents = _entities(pack)
    for module, other in (p.get("inherit") or {}).items():
        theirs = mapping["packs"][other].get("not_a_data_product") or {}
        out.update({n: v for n, v in theirs.items() if n in ents and ents[n]["module"] == module})
    return out


def mapping_problems(mapping: dict, catalog: dict | None = None) -> list[str]:
    """What differs between the mapping, the catalog and the pack manifests. Empty when they are in step:
    - every mapped table is a table of the pack's manifest, and every table of the manifest is mapped or listed as not
      a data product (with a reason), never both;
    - every product is in the catalog and every role in ROLES; the key maps only names of the product's business key
      to columns the pack names for that table;
    - the evidence written per entry is what the pack's own sources say (evidence());
    - every source names a pack and modules that exist."""
    from . import pack_manifest
    catalog = catalog or load_catalog()
    prods = products(catalog)
    out = []
    packs = mapping.get("packs") or {}
    if set(packs) != set(pack_manifest.available()):
        out.append(f"packs {sorted(packs)} are not the packs with a manifest {pack_manifest.available()}")
    for pack in sorted(packs):
        if pack not in pack_manifest.available():
            continue
        m = _manifest(pack)
        ents = {e["name"]: e for e in m["entities"]}
        cols = known_columns(pack)
        own = packs[pack].get("tables") or {}
        nots = packs[pack].get("not_a_data_product") or {}
        for module, other in (packs[pack].get("inherit") or {}).items():
            if other not in packs or module not in {e["module"] for e in ents.values()}:
                out.append(f"{pack}: inherit {module} from {other}: no such module or pack")
            for name, e in ents.items():
                if e["module"] == module and name in own:
                    out.append(f"{pack}.{name}: mapped here and inherited from {other}")
        allm = tables(pack, mapping)
        alln = not_products(pack, mapping)
        for name in sorted(set(own) | set(nots)):
            if name not in ents:
                out.append(f"{pack}.{name}: not a table of the {pack} manifest")
        for name in sorted(ents):
            if name not in allm and name not in alln:
                out.append(f"{pack}.{name}: in the manifest but neither mapped nor listed as not a data product")
            if name in allm and name in alln:
                out.append(f"{pack}.{name}: both mapped and listed as not a data product")
        for name, v in sorted(nots.items()):
            if v.get("kind") not in NOT_KINDS or not v.get("reason"):
                out.append(f"{pack}.{name}: not_a_data_product needs a kind of {', '.join(NOT_KINDS)} and a reason")
        for name, entries in sorted(own.items()):
            if name not in ents:
                continue
            if not entries:
                out.append(f"{pack}.{name}: no entries")
            seen = set()
            for e in entries:
                where = f"{pack}.{name} -> {e.get('product')}"
                for f in set(e) - set(ENTRY_FIELDS):
                    out.append(f"{where}: unknown field {f}")
                if e.get("product") not in prods:
                    out.append(f"{where}: not a product of the catalog")
                    continue
                if (e["product"], e.get("role")) in seen:
                    out.append(f"{where}: the same product and role twice")
                seen.add((e["product"], e.get("role")))
                if e.get("role") not in ROLES:
                    out.append(f"{where}: role {e.get('role')!r} is not one of {', '.join(ROLES)}")
                if e.get("confidence") not in CONFIDENCE:
                    out.append(f"{where}: confidence {e.get('confidence')!r} is not one of {', '.join(CONFIDENCE)}")
                want = evidence(pack, name, m)
                if e.get("evidence") != want:
                    out.append(f"{where}: evidence {e.get('evidence')!r}, the pack's sources say {want!r}")
                key = e.get("key")
                if not isinstance(key, dict):
                    out.append(f"{where}: key must be a mapping of business-key names to the pack's columns")
                    continue
                bk = prods[e["product"]]["business_key"]
                for generic, col in key.items():
                    if generic not in bk:
                        out.append(f"{where}: {generic!r} is not in the business key {bk}")
                    if col not in cols.get(name, set()):
                        out.append(f"{where}: {col!r} is not a column the pack names for {name}")
    for sid, s in sorted((mapping.get("sources") or {}).items()):
        if s.get("pack") not in packs:
            out.append(f"source {sid}: pack {s.get('pack')!r} is not mapped")
            continue
        mods = {e["module"] for e in _manifest(s["pack"])["entities"]}
        for mod in s.get("modules") or []:
            if mod not in mods:
                out.append(f"source {sid}: module {mod!r} is not a module of {s['pack']}")
        if not s.get("title") or not s.get("modules"):
            out.append(f"source {sid}: needs a title and modules")
    for sid, hints in sorted((mapping.get("not_in_pack") or {}).items()):
        if sid not in (mapping.get("sources") or {}):
            out.append(f"not_in_pack: {sid} is not a source")
        for pid in hints:
            if pid not in prods:
                out.append(f"not_in_pack: {sid}.{pid} is not a product of the catalog")
    return out


# ------------------------------------------------------------------ coverage ----------------------------------------

def coverage(source: str, mapping: dict | None = None, catalog: dict | None = None) -> dict[str, dict]:
    """Per product of the catalog, how far one source's tables (a pack's modules) cover it:
    full       every required role has a table mapped with high confidence (optional roles missing are listed);
    partial    some tables, but a required role has none (missing_required), or only tables mapped with medium or low
               confidence (weak_required: a user table standing in for employees, a clearing link for payments);
    none       no table of the source maps to the product;
    generated  the product needs no table of a source (the date table is generated).
    `tables` lists the source's tables per role; `hint` what the mapping says is outside the pack, if anything."""
    mapping = mapping or load_mapping()
    catalog = catalog or load_catalog()
    s = mapping["sources"][source]
    pack, modules = s["pack"], set(s["modules"])
    ents = _entities(pack)
    mapped = tables(pack, mapping)
    hints = (mapping.get("not_in_pack") or {}).get(source) or {}
    out = {}
    for pid, p in products(catalog).items():
        by_role: dict[str, list[str]] = {}
        strong: set[str] = set()
        for name, entries in sorted(mapped.items()):
            if ents[name]["module"] not in modules:
                continue
            for e in entries:
                if e["product"] == pid:
                    by_role.setdefault(e["role"], []).append(name)
                    if e["confidence"] == "high":
                        strong.add(e["role"])
        req, opt = p["roles"]["required"], p["roles"]["optional"]
        present = set(by_role)
        if not req and not present:
            state = "generated"
        elif not present:
            state = "none"
        elif set(req) <= strong:
            state = "full"
        else:
            state = "partial"
        row = {"state": state, "tables": {r: by_role[r] for r in ROLES if r in by_role},
               "missing_required": [r for r in req if r not in present],
               "weak_required": [r for r in req if r in present and r not in strong],
               "missing_optional": [r for r in opt if r not in present] if present else []}
        if pid in hints:
            row["hint"] = hints[pid]
        out[pid] = row
    return out


def matrix(mapping: dict | None = None, catalog: dict | None = None) -> dict[str, dict[str, str]]:
    """{product: {source: state}} over every source of the mapping."""
    mapping = mapping or load_mapping()
    catalog = catalog or load_catalog()
    cov = {sid: coverage(sid, mapping, catalog) for sid in mapping["sources"]}
    return {pid: {sid: cov[sid][pid]["state"] for sid in mapping["sources"]} for pid in products(catalog)}


# ------------------------------------------------------------------ writing -----------------------------------------

def _flow(v) -> str:
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {_flow(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(_flow(x) for x in v) + "]"
    if isinstance(v, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", v) and v.lower() not in ("yes", "no", "true", "false", "null", "on", "off"):
        return v
    return json.dumps(v, ensure_ascii=False)


HEADER = """# The four knowledge packs' tables mapped to the catalog of data products (round DP1). Format: mapping.schema.json;
# loader and check: fabric_backend/data_product_catalog.py (mapping_problems); report: docs/DATA-PRODUCT-CATALOG.md.
#
# Per pack table: the catalog product(s) it belongs to, its role there, how the pack's key columns map to the product's
# business key (generic name: the pack's column), the confidence of the mapping, and the evidence the pack itself gives
# for the table (verified: every source the pack cites for it was opened and read; unverified: none was). A table that
# is no data product of its own is listed under not_a_data_product with a reason. Everything here rests on public
# documentation and synthetic demos; nothing has been checked on a customer system.
"""


def render_mapping(doc: dict) -> str:
    """The mapping as text: sources and not_in_pack first, then per pack one line per table entry. Fills in evidence
    from the packs, so a written file always says what the packs say."""
    lines = [HEADER.rstrip("\n"), f"version: {doc.get('version', '0.1.0')}", "sources:"]
    for sid, s in doc["sources"].items():
        lines.append(f"  {sid}: {_flow(s)}")
    lines.append("not_in_pack:")
    for sid, hints in doc.get("not_in_pack", {}).items():
        lines.append(f"  {sid}:")
        lines += [f"    {pid}: {_flow(t)}" for pid, t in hints.items()]
    lines.append("packs:")
    for pack, p in doc["packs"].items():
        m = _manifest(pack)
        lines.append(f"  {pack}:")
        if p.get("inherit"):
            lines.append(f"    inherit: {_flow(p['inherit'])}")
        lines.append("    tables:")
        for name in sorted(p["tables"]):
            lines.append(f"      {name}:")
            for e in p["tables"][name]:
                e = {k: e[k] for k in ("product", "role", "key", "confidence") if k in e} | {"evidence": evidence(pack, name, m)} \
                    | ({"note": e["note"]} if e.get("note") else {})
                lines.append(f"      - {_flow(e)}")
        nots = p.get("not_a_data_product") or {}
        lines.append("    not_a_data_product:" + ("" if nots else " {}"))
        for name in sorted(nots):
            lines.append(f"      {name}: {_flow(nots[name])}")
    return "\n".join(lines) + "\n"


SHORT = {"full": "full", "partial": "partial", "none": "–", "generated": "generated"}


def matrix_markdown(mapping: dict | None = None, catalog: dict | None = None) -> str:
    """The coverage matrix as a Markdown table, products down, sources across; a partial cell names what is missing
    (a role with no table, or a role only weakly mapped). docs/DATA-PRODUCT-CATALOG.md carries this table and the test
    checks it is the same."""
    mapping = mapping or load_mapping()
    catalog = catalog or load_catalog()
    srcs = list(mapping["sources"])
    cov = {s: coverage(s, mapping, catalog) for s in srcs}
    lines = ["| Product | " + " | ".join(mapping["sources"][s]["title"] for s in srcs) + " |",
             "| --- |" + " --- |" * len(srcs)]
    for pid, p in products(catalog).items():
        cells = []
        for s in srcs:
            c = cov[s][pid]
            cell = SHORT[c["state"]]
            if c["state"] == "partial":
                why = [f"no {r}" for r in c["missing_required"]] + [f"{r} weak" for r in c["weak_required"]]
                cell += " (" + ", ".join(why) + ")"
            cells.append(cell)
        lines.append(f"| {p['title']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
