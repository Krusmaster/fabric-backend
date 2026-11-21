"""Knowledge packs: the keys and relationships of a known source system, read from declarative files.

General naming rules cannot read SAP: `VBAP.VBELN` names the order it belongs to, `LIPS.VBELN` a delivery and
`VBRP.VBELN` an invoice, every key starts with the client `MANDT`, and the names are German abbreviations. A pack
says it outright, per table and per relationship, with the public source it rests on.

The files are in `fabric_backend/packs/<pack>/<module>.json` and follow `packs/pack.schema.json`. They describe
tables, not a tool: the same pack serves a Fabric mirror, a Databricks catalog, a Data API builder config or a
pipeline's table list (exports.py). Nothing here connects to anything.

    load("sap")                    -> the merged pack (all modules)
    problems(pack)                 -> what is inconsistent in it (the test runs this on every file)
    match(schema, "sap")           -> which tables of a schema the pack knows, their keys and the relationships it can
                                      apply, with what is missing; None when fewer than two tables match
    match_any(schema)              -> the pack that recognises most tables, of those with a table of their own among
                                      them (what the engine, infer._pack, reads)
    match(schema, "sap", mirror=m) -> the same, with the keys and descriptions a mirrored SAP source declares winning over
                                      the pack's (rule "SAP mirror metadata", round n129; m comes from sap_mirror.read)

A table matches on its name without case, schema or a leading `sap_`/`raw_`/`stg_`/`bronze_` word (`VBAK`, `vbak`,
`sap_vbak`, `bronze.SAP_VBAK`), and only when its key columns are there. Since round n230 the name is compared without
underscores too, and a table can list `aliases`: a released CDS view is written `I_SALES_DOCUMENT` in the pack and is
found as `I_SalesDocument`, `i_salesdocument`, `I_SALES_DOCUMENT`, `cds_i_salesdocument` and, by its alias, as
`SalesDocument` (pack_table). Columns were always compared that way (`SalesDocumentItem` is `SALES_DOCUMENT_ITEM`). When an extract has dropped the client
column, the client is left out of keys and relationships on both sides, and the match says so.
Since round BL8 a known SAP table is also found with landing words before or after its name (`P01_VBAK`, `VBAK_800`,
`ecc_VBAK`; Match.name_reasons says why), a table under an unknown name with a pack table's key columns is reported as
a suggestion (recognise, Match.by_key_columns; not applied), and two tables pointing at one pack table are reported in
Match.ambiguous, never guessed.
A pack is a suggestion with a source, not evidence: validate_plan checks its relationships against the rows.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PACKS = Path(__file__).parent / "packs"
RULE = "SAP pack"
MIRROR_RULE = "SAP mirror metadata"       # n129: keys (and descriptions) a mirrored source declares; see sap_mirror.py
CLIENT_COLUMNS = ("MANDT", "RCLNT", "CLIENT", "COMPANY")   # BUT000 and the CVI link tables name it CLIENT; COMPANY is
# Business Central's `$Company` column, which an export adds to per-company tables (bc2adls) and a per-company SQL
# table (`<company>$<table>$<app id>`) does not have: like SAP's client it is left out of keys and relationships on both
# sides when the table lacks it (round PK2, packs/dynamics365)
# words a landing puts in front of a source table's name: a layer (raw, bronze) or the system (sap, younium, sf)
_LEADING = ("sap", "raw", "stg", "src", "bronze", "landing", "mirror", "mirrored", "ext", "extract", "younium", "sf", "salesforce", "crm",
            "cds", "s4", "s4hana")


def available() -> list[str]:
    return sorted(p.name for p in PACKS.iterdir() if p.is_dir())


INCLUDE = ".include"      # PK1: packs/<pack>/<module>.include names a module of another pack to read, not copy


def _included(spec_file: Path) -> tuple[dict, str]:
    """A module of another pack, cut to the tables an `.include` file names (round PK1). The file is JSON:
    {"pack": "salesforce", "module": "salesforce", "tables": [...], "traps": [...]}. The module keeps its own text and
    sources; relationships are taken where both tables are named, traps by id, sources where a kept claim cites them.
    The including pack's own modules set the rule, so the engine's label of the including pack does not change."""
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    src = PACKS / spec["pack"] / f"{spec['module']}.json"
    m = json.loads(src.read_text(encoding="utf-8"))
    keep = set(spec["tables"])
    unknown = keep - {t["name"] for t in m["tables"]}
    if unknown:
        raise KeyError(f"{spec_file.name}: the {spec['pack']} pack does not describe {', '.join(sorted(unknown))}")
    m["tables"] = [t for t in m["tables"] if t["name"] in keep]
    m["relationships"] = [r for r in m["relationships"] if r["source"] in keep and r["target"] in keep]
    m["traps"] = [t for t in m.get("traps", []) if t["id"] in set(spec.get("traps", []))]
    cited = {s for x in m["tables"] + m["relationships"] + m["traps"] for s in x["sources"]}
    m["sources"] = {k: v for k, v in m["sources"].items() if k in cited}
    return m, f"packs/{spec['pack']}/{src.name}"


@lru_cache(maxsize=None)
def _load(pack: str) -> str:
    files = sorted(list((PACKS / pack).glob("*.json")) + list((PACKS / pack).glob("*" + INCLUDE)), key=lambda f: f.stem)
    if not files:
        raise KeyError(f"no pack named {pack!r}; available: {', '.join(available())}")
    merged: dict = {"pack": pack, "modules": [], "variants": {}, "sources": {}, "tables": {}, "relationships": [], "traps": []}
    rule = None
    for f in files:
        if f.suffix == INCLUDE:
            m, file = _included(f)
        else:
            m, file = json.loads(f.read_text(encoding="utf-8")), f"packs/{pack}/{f.name}"
            rule = rule or m["rule"]
        merged["modules"].append({"module": m["module"], "title": m["title"], "status": m["status"], "file": file})
        merged["rule"] = m["rule"]
        merged["variants"].update(m["variants"])
        for sid, s in m["sources"].items():
            merged["sources"][sid] = s
        for t in m["tables"]:
            merged["tables"][t["name"]] = {**t, "module": m["module"]}
        merged["relationships"] += [{**r, "module": m["module"]} for r in m["relationships"]]
        merged["traps"] += [{**t, "module": m["module"]} for t in m.get("traps", [])]
    merged["rule"] = rule or merged["rule"]
    return json.dumps(merged)


def load(pack: str = "sap") -> dict:
    """The pack with all its modules merged: tables by name, relationships, sources, traps."""
    return json.loads(_load(pack))


def problems(pack: dict) -> list[str]:
    """Inconsistencies the JSON schema cannot see: unknown sources, relationships to tables or columns the pack does
    not describe, column lists of different length, a target that is not the target's key."""
    out = []
    tables = pack["tables"]
    sources = pack["sources"]
    for t in tables.values():
        for s in t["sources"]:
            if s not in sources:
                out.append(f"{t['name']}: unknown source {s!r}")
        for v in t.get("variants", []):
            if v not in pack["variants"]:
                out.append(f"{t['name']}: unknown variant {v!r}")
        if len(set(t["key"])) != len(t["key"]):
            out.append(f"{t['name']}: a key column is repeated")
        c = t.get("corresponds_to")                                      # n230: the table a CDS view reads (I_SalesDocument ~ VBAK)
        if c:
            if c["table"] not in tables:
                out.append(f"{t['name']}: corresponds_to names {c['table']!r}, a table the pack does not describe")
            out += [f"{t['name']}: corresponds_to: unknown source {s!r}" for s in c["sources"] if s not in sources]
        if t.get("source_columns"):                                      # n230: the source's own spelling of the columns
            spelled = {_norm(c) for c in t["source_columns"]}
            named = set(t["key"]) | {a["column"] for a in t.get("amounts", []) + t.get("quantities", [])}
            for f in ("number_columns", "delta", "currency_columns", "unit_columns"):
                named |= set(t.get(f, []))
            named |= {x["column"] for x in t.get("personal", [])}
            for r in pack["relationships"]:
                named |= set(r["source_cols"]) if r["source"] == t["name"] else set()
                named |= set(r["target_cols"]) if r["target"] == t["name"] else set()
            out += [f"{t['name']}: column {c} is not among its source_columns" for c in sorted(named) if _norm(c) not in spelled]
    seen: dict[str, str] = {}
    for t in tables.values():                                            # n230: names and aliases are compared without underscores
        for n in [t["name"]] + list(t.get("aliases", [])):
            if seen.setdefault(_norm(n), t["name"]) != t["name"]:
                out.append(f"{t['name']}: the name or alias {n} is also {seen[_norm(n)]}'s (compared without underscores)")
    for r in pack["relationships"]:
        name = f"{r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}"
        for s in r["sources"]:
            if s not in sources:
                out.append(f"{name}: unknown source {s!r}")
        if r["source"] not in tables or r["target"] not in tables:
            out.append(f"{name}: a table the pack does not describe")
            continue
        if len(r["source_cols"]) != len(r["target_cols"]):
            out.append(f"{name}: {len(r['source_cols'])} source column(s) against {len(r['target_cols'])} target column(s)")
        kind, target = r.get("kind", "key"), tables[r["target"]]
        if kind == "unique":                                             # VBAK.KNUMV: a unique column set the table declares
            if list(r["target_cols"]) not in [list(u) for u in target.get("unique_keys", [])]:
                out.append(f"{name}: the target columns are not a unique key {r['target']} declares (unique_keys)")
        elif kind == "valid_on":                                         # CSKS: the key without its valid-to column, plus a date
            v = r.get("valid_on") or {}
            # the key is the join columns, one end of the period (CSKS: DATBI, ADRC: DATE_FROM) and any target column a
            # filter fixes to one value or to blank (ADRC.NATION)
            fixed = [w["column"] for w in r.get("where", []) if w["side"] == "target" and (w.get("blank") or len(w.get("in", [])) == 1)]
            if not {"target_from", "target_to"} <= set(v) or not (v.get("source_date") or v.get("on") == "today"):
                out.append(f"{name}: valid_on needs target_from, target_to and a source_date or on: today")
            elif not any(sorted(list(r["target_cols"]) + [end] + fixed) == sorted(target["key"]) for end in (v["target_to"], v["target_from"])):
                out.append(f"{name}: the target columns, one end of the period and the fixed filters are not {r['target']}'s key")
        elif r["cardinality"] != "many-to-many" and r.get("apply") is not False:
            # a key join that is only listed may point elsewhere (a conditional link); an applied one never. A target-side
            # filter to one value completes the key: KONV.KAPPL+KSCHL -> T685 where T685.KVEWE = 'A'
            fixed = [w["column"] for w in r.get("where", []) if w["side"] == "target" and (w.get("blank") or len(w.get("in", [])) == 1)]
            if sorted(list(r["target_cols"]) + fixed) != sorted(target["key"]) or (not fixed and list(r["target_cols"]) != list(target["key"])):
                out.append(f"{name}: the target columns are not {r['target']}'s key")
        for w in r.get("where", []):
            if w.get("side") not in ("source", "target") or not (w.get("in") or w.get("blank")):
                out.append(f"{name}: a where entry needs side source or target and at least one value, or blank")
        for v in r.get("variants", []):
            if v not in pack["variants"]:
                out.append(f"{name}: unknown variant {v!r}")
    for tr in pack["traps"]:
        for s in tr["sources"]:
            if s not in sources:
                out.append(f"trap {tr['id']}: unknown source {s!r}")
    return out


_BC_SUFFIX = re.compile(r"^(.*[A-Za-z].*)-\d+$")     # bc2adls: `SalesHeader-36` (table), `No-3` (field); round PK2


def _bc_name(name: str) -> str:
    """A Business Central name without what its landing adds (round PK2): the company and the app id of a per-company SQL
    table (`Example AB$Sales Header$437dbf0e-...` -> `Sales Header`; schema prefixes go with the company), and the
    table or field number bc2adls appends (`SalesHeader-36` -> `SalesHeader`). Other names are returned as they are."""
    if "$" in name:
        parts = name.split("$")
        if len(parts) >= 2 and parts[1].strip():
            name = parts[1]
    m = _BC_SUFFIX.match(name)
    return m.group(1) if m else name


def table_name(name: str) -> str:
    """The name a pack would know a table by: `bronze.SAP_VBAK` -> `VBAK`; `CRONUS$Sales Header$<app id>` and
    `SalesHeader-36` -> `SALES_HEADER`/`SALESHEADER` (Business Central, round PK2; compared without underscores)."""
    name = _bc_name(name.split(".")[-1] if "$" not in name else name)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name.split(".")[-1]) if w]
    while len(words) > 1 and words[0].lower() in _LEADING:
        words = words[1:]
    return "_".join(words).upper()


@lru_cache(maxsize=None)
def _names(pack: str) -> dict[str, tuple[str, bool]]:
    """Every name a pack's tables answer to, without case and underscores -> (the pack's name, whether it is an alias)."""
    out: dict[str, tuple[str, bool]] = {}
    tables = load(pack)["tables"]
    for n in tables:
        out[_norm(n)] = (n, False)
    for n, t in tables.items():
        for a in t.get("aliases", []):
            out.setdefault(_norm(a), (n, True))
    return out


def pack_table(name: str, pack: str = "sap") -> str | None:
    """The pack table a schema table's name means, or None: `bronze.SAP_VBAK` -> `VBAK`, `I_SalesDocument` and
    `SalesDocument` -> `I_SALES_DOCUMENT` (round n230: without underscores, and by the aliases a table lists)."""
    found = _names(pack).get(_norm(table_name(name)))
    if found:
        return found[0]
    affixed = _affixed(name, pack)            # round BL8: `P01_VBAK`, `VBAK_800`, `ecc-VBAK` -> VBAK (the SAP pack only)
    return affixed[0] if affixed else None


# ---------------------------------------------------------------- round BL8: names with a prefix or suffix, key columns
# A landed SAP table often carries the system id (`P01_VBAK`, SAP's SID: three characters, a letter first), the client
# (`VBAK_800`), a landing word (`ecc_VBAK`, `bronze.sap_VBAK_prd`) or a date or version (`VBAK_20261121`, `VBAK_v2`).
# Such a word is stripped from either end when what is left is a pack table's own name (never an alias: `dim_Customer`
# is not I_CUSTOMER) and the table then needs the pack's key columns, as every match does. The SAP pack only: the other
# packs' tables have ordinary names (Account, Contact) a prefix rule would find everywhere.
AFFIX_PACKS = ("sap",)
_AFFIX_WORDS = frozenset(_LEADING) | frozenset(("ecc", "erp", "r3", "bw", "prd", "prod", "dev", "qas", "qa", "tst", "test",
                                                "hist", "history", "copy", "full", "delta", "current", "snapshot"))
_SID = re.compile(r"[A-Za-z][A-Za-z0-9]{2}")       # an SAP system id: P01, PRD, ECC, S4H
_VERSION = re.compile(r"[vV]\d+")
KEY_RULE = "key columns"                            # how a table under an unknown name is recognised (reported only)


def _affix_word(word: str) -> bool:
    """A word a landing puts before or after an SAP table's name: a client or a date (digits), a system id, a version,
    or a landing word."""
    return word.isdigit() or bool(_SID.fullmatch(word) or _VERSION.fullmatch(word)) or word.lower() in _AFFIX_WORDS


@lru_cache(maxsize=None)
def _own_names(pack: str) -> dict[str, str]:
    return {_norm(n): n for n in load(pack)["tables"]}


def _affixed(name: str, pack: str = "sap") -> tuple[str, str, str] | None:
    """(pack table, prefix, suffix) when name is a pack table's own name with landing words before or after it, the
    separators `_`, `.` and `-` kept in prefix and suffix: `P01_VBAK` -> ("VBAK", "P01_", ""), `vbak_800` ->
    ("VBAK", "", "_800"). The longest name wins (`VBAK_800` is VBAK, not a table called 800). None otherwise."""
    if pack not in AFFIX_PACKS:
        return None
    spans = [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z0-9]+", name)]
    words = [name[a:b] for a, b in spans]
    own = _own_names(pack)
    for size in range(len(words) - 1, 0, -1):
        for i in range(0, len(words) - size + 1):
            j = i + size
            if not all(_affix_word(w) for w in words[:i] + words[j:]):
                continue
            core = own.get(_norm("".join(words[i:j])))
            if core:
                return core, name[:spans[i][0]], name[spans[j - 1][1]:]
    return None


def _affix_reason(table: str, pack_name: str, prefix: str, suffix: str) -> str:
    parts = ([f"prefix {prefix}"] if prefix else []) + ([f"suffix {suffix}"] if suffix else [])
    return f"{pack_name} matched as {table}, {' and '.join(parts)}"


def _known_columns(pt: dict) -> set[str]:
    """The columns a pack table names besides its key: number, date, amount, currency, quantity and unit columns."""
    out = set(pt.get("number_columns", [])) | set(pt.get("delta", [])) | set(pt.get("currency_columns", [])) \
        | set(pt.get("unit_columns", [])) | {c for u in pt.get("unique_keys", []) for c in u}
    for a in pt.get("amounts", []) + pt.get("quantities", []):
        out |= {a[k] for k in ("column", "currency", "unit") if a.get(k)}
    return {_norm(c) for c in out} - {_norm(c) for c in pt["key"]}


def _by_key(table, pack: str, variant: str | None = None) -> dict:
    """What a table under a name the pack does not know is by its columns: the pack tables whose whole key, the client
    first, the table carries (MANDT + VBELN, MANDT + KUNNR), the longest key first, then the one with most of its other
    known columns there. {"pack_table": name, "reason": ...} when one table is left, {"candidates": [...]} when several
    are (reported, not guessed), {} when none."""
    if pack not in AFFIX_PACKS:
        return {}
    have = _cols(table)
    tables = load(pack)["tables"]
    fits = [n for n, t in tables.items() if len(t["key"]) >= 2 and t["key"][0] in _BLANK_EXEMPT
            and all(_norm(c) in have for c in t["key"])
            and not (variant and t.get("variants") and variant not in t["variants"])]
    if not fits:
        return {}
    longest = max(len(tables[n]["key"]) for n in fits)
    fits = [n for n in fits if len(tables[n]["key"]) == longest]
    score = {n: len(_known_columns(tables[n]) & set(have)) for n in fits}
    best = max(score.values())
    fits = sorted(n for n in fits if score[n] == best)
    if len(fits) > 1:
        return {"candidates": fits}
    n = fits[0]
    known = sorted(have[c] for c in _known_columns(tables[n]) & set(have))
    return {"pack_table": n, "reason": f"{KEY_RULE}: {table.name} carries {n}'s key {' + '.join(tables[n]['key'])}"
                                       + (f" and its columns {', '.join(known)}" if known else "")}


def recognise(schema, pack: str = "sap", variant: str | None = None) -> list[dict]:
    """Round BL8: per schema table, which pack table it is and why, in the schema's order. `how` is "name" (as since the
    pack began), "alias" (n230), "prefix or suffix", "key columns" (a suggestion: the name says nothing, so match does
    not apply it), "ambiguous" (two or more tables point at one pack table, or one table's key fits several: reported,
    never guessed; `candidates` lists them) or None. A table matched by name still needs its key columns to be taken
    by match; this answers what its name or columns say."""
    out: list[dict] = []
    names = _names(pack)
    for t in schema:
        hit = names.get(_norm(table_name(t.name)))
        if hit:
            out.append({"table": t.name, "pack_table": hit[0], "how": "alias" if hit[1] else "name",
                        "reason": f"{hit[0]} by its {'alias' if hit[1] else 'name'}"})
            continue
        affixed = _affixed(t.name, pack)
        if affixed:
            out.append({"table": t.name, "pack_table": affixed[0], "how": "prefix or suffix",
                        "reason": _affix_reason(t.name, *affixed)})
            continue
        k = _by_key(t, pack, variant)
        if "candidates" in k:
            out.append({"table": t.name, "pack_table": None, "how": "ambiguous", "candidates": k["candidates"],
                        "reason": f"{KEY_RULE}: {t.name} carries the key of {', '.join(k['candidates'])}; not guessed"})
        elif k:
            out.append({"table": t.name, "pack_table": k["pack_table"], "how": KEY_RULE, "reason": k["reason"]})
        else:
            out.append({"table": t.name, "pack_table": None, "how": None, "reason": ""})
    by: dict[str, list[dict]] = {}
    for r in out:
        if r["pack_table"]:
            by.setdefault(r["pack_table"], []).append(r)
    tier = {"name": 0, "alias": 0, "prefix or suffix": 1, KEY_RULE: 2}
    for pt, rs in by.items():
        top = min(tier[r["how"]] for r in rs)
        first = [r for r in rs if tier[r["how"]] == top]
        if top == 0:                       # its own name wins (several by name: match takes the first, as before BL8)
            for r in rs:
                if tier[r["how"]] > 0:
                    r.update(how="ambiguous", candidates=[pt], pack_table=None,
                             reason=f"{pt} is there by its name ({first[0]['table']}); {r['table']} also points at it and "
                                    f"is not used")
            continue
        for r in rs:
            if r not in first:             # a name with a prefix wins over key columns
                r.update(how="ambiguous", candidates=[pt], pack_table=None,
                         reason=f"{pt} is there as {first[0]['table']}; {r['table']} also points at it and is not used")
            elif len(first) > 1:           # two landings of one table: not guessed
                r.update(how="ambiguous", candidates=[pt], pack_table=None,
                         reason=f"{', '.join(x['table'] for x in first)} all point at {pt}; not guessed")
    return out


_BLANK_EXEMPT = ("MANDT", "RCLNT", "CLIENT")   # the client: validate_plan never counted its blank as no reference


@lru_cache(maxsize=None)
def _optional_links(pack: str) -> frozenset:
    return frozenset((r["source"], tuple(_norm(c) for c in r["source_cols"]), r["target"])
                     for r in load(pack)["relationships"] if r.get("optional"))


def initial_columns(source: str, source_cols: list[str], target: str, pack: str = "sap") -> list[str]:
    """AP2: the source columns of a pack relationship marked "optional" whose value of zeros only is SAP's initial value
    ("no partner for this row", like a blank): VBPA.KUNNR of a contact-person row, VBPA.ADRNR without a document address.
    The client column is left out. [] when the pack does not mark the relationship (or does not know the tables): then
    only NULL and blank count as no reference, and a value of zeros is a value that must find its row."""
    s, t = pack_table(source, pack), pack_table(target, pack)
    if not s or not t or (s, tuple(_norm(c) for c in source_cols), t) not in _optional_links(pack):
        return []
    return [c for c in source_cols if c.upper() not in _BLANK_EXEMPT]


def blank_columns(source_cols: list[str]) -> list[str]:
    """AP2: the columns of a reference whose blank ('' or spaces, SAP's initial value) means no reference, as validate_plan
    has counted SAP pack links since it began: every column but the client."""
    return [c for c in source_cols if c.upper() not in _BLANK_EXEMPT]


@dataclass
class Match:
    pack: str
    tables: dict[str, str]                                  # schema table -> pack table
    keys: dict[str, list[str]]                              # schema table -> key columns, in the schema's spelling
    relationships: list[dict]                               # applied: source, source_cols, target, target_cols (schema spelling) + pack fields
    not_applied: list[dict] = field(default_factory=list)   # pack relationships between matched tables that are not applied, with why
    missing_tables: list[str] = field(default_factory=list) # pack tables a relationship of a matched table needs and the schema lacks
    missing_columns: list[dict] = field(default_factory=list)
    client_dropped: list[str] = field(default_factory=list) # matched tables without their client column
    variant_hint: str = ""
    unmatched_keyless: list[str] = field(default_factory=list)  # names a pack knows whose key columns are not all there
    key_rules: dict[str, str] = field(default_factory=dict)     # schema table -> RULE or MIRROR_RULE (n129)
    mirror: dict[str, dict] = field(default_factory=dict)       # schema table -> its entry of the mirror metadata (n129)
    mirror_problems: list[dict] = field(default_factory=list)   # mirror metadata that could not be used, with why (n129)
    columns: dict[str, dict[str, str]] = field(default_factory=dict)   # schema table -> normalised column -> the schema's spelling (n230)
    by_alias: list[str] = field(default_factory=list)           # schema tables recognised by an alias, not the pack's own name (n230)
    name_reasons: dict[str, str] = field(default_factory=dict)  # schema table -> why its name is a pack table, when it carries a prefix or suffix (BL8)
    by_key_columns: list[dict] = field(default_factory=list)    # tables whose unknown name hides a pack table by its key columns: suggested, not applied (BL8)
    ambiguous: list[dict] = field(default_factory=list)         # tables pointing at one pack table, or a key fitting several: reported, not guessed (BL8)

    def source_of(self, ids: list[str]) -> list[dict]:
        pack = load(self.pack)
        return [{"id": i, **{k: pack["sources"][i][k] for k in ("title", "url", "fetched")}} for i in ids]


def _norm(column: str) -> str:
    """A column name as a pack compares it: without case and underscores, so a pack written in snake case (EXTERNAL_CRM_ID)
    reads a camelCase landing (externalCrmId) and a snake-case one (external_crm_id) alike. SAP names have no such
    doubles (VBTYP_N is only ever VBTYP_N). Since round PK2 every character that is not a letter or a digit is left out,
    so Business Central's `Document No.` reads `Document No_` (its SQL spelling), `DOCUMENT_NO` and `$Company` reads
    `COMPANY`."""
    return re.sub(r"[^A-Z0-9]", "", column.upper())


def column_key(column: str) -> str:
    """A column as the loader compares it, in its plain spelling (round PK2): `_parentaccountid_value` and
    `parentaccountid` -> PARENTACCOUNTID, `DocumentNo-3` and `Document No_` -> DOCUMENTNO."""
    lookup = re.fullmatch(r"_(.+)_value", column)
    bc = _BC_SUFFIX.match(column)
    return _norm(lookup.group(1) if lookup else bc.group(1) if bc else column)


def _cols(table) -> dict[str, str]:
    """Normalised column name -> the schema's spelling. When two columns differ only by underscores or case, the first wins."""
    out: dict[str, str] = {}
    for c in table.column_names:
        out.setdefault(_norm(c), c)
    for c in table.column_names:                     # round PK2: other spellings of a column, when the plain one is absent
        lookup = re.fullmatch(r"_(.+)_value", c)     # Dataverse Web API lookups: `_parentaccountid_value` is parentaccountid
        bc = _BC_SUFFIX.match(c)                     # bc2adls fields: `No-3` is No.
        for other in ((lookup.group(1),) if lookup else ()) + ((bc.group(1),) if bc else ()):
            out.setdefault(_norm(other), c)
    return out


def _mirror_entry(mirror: dict | None, table: str, pack_name: str) -> dict | None:
    """The mirror metadata of a schema table: by its own name, without case, or by the name the pack knows it by."""
    if not mirror:
        return None
    by = {k.lower(): v for k, v in mirror.items()}
    return by.get(table.lower()) or by.get(table.split(".")[-1].lower()) or by.get(pack_name.lower())


def match(schema, pack: str = "sap", variant: str | None = None, mirror: dict | None = None) -> Match | None:
    """The pack's view of a schema; None when fewer than two of its tables are recognised (then nothing changes).

    mirror (round n129): metadata a mirrored SAP source declares, as sap_mirror.read returns it. Where a table's entry
    names key columns the table has, those are its key (rule MIRROR_RULE) instead of the pack's, also when the pack's
    own key columns are not all there; a pack key relationship into such a table is applied only when its target
    columns are that key, and is listed as not applied, with why, when they are not. Each relationship says which rule
    decided its target key (`decided_by`). Without mirror the match is exactly what it was."""
    p = load(pack)
    key_rules: dict[str, str] = {}
    entries: dict[str, dict] = {}
    mirror_problems: list[dict] = []
    found: dict[str, str] = {}
    cols: dict[str, dict[str, str]] = {}
    keys: dict[str, list[str]] = {}
    dropped: list[str] = []
    keyless: list[str] = []
    taken: set[str] = set()
    names = _names(pack)
    by_alias: list[str] = []
    recognised = recognise(schema, pack, variant)                          # BL8: prefix or suffix, key columns, ambiguity
    affix = {r["table"]: r for r in recognised if r["how"] == "prefix or suffix"}
    reasons: dict[str, str] = {}
    by_name: dict[str, list[str]] = {}
    for r in recognised:
        if r["how"] in ("name", "alias"):
            by_name.setdefault(r["pack_table"], []).append(r["table"])
    grouped: dict[str, dict] = {}                                          # one entry per reason: two landings of VBAK are one
    for r in recognised:
        if r["how"] == "ambiguous":
            grouped.setdefault(r["reason"], {"tables": [], "candidates": r["candidates"], "why": r["reason"]})["tables"].append(r["table"])
    ambiguous = list(grouped.values())
    ambiguous += [{"tables": ts, "candidates": [n], "why": f"{', '.join(ts)} all point at {n} by name; the first with its key "
                                                         f"columns is used, as before round BL8"} for n, ts in by_name.items() if len(ts) > 1]
    for t in schema:
        name, alias = names.get(_norm(table_name(t.name)), (None, False))
        if name is None and t.name in affix:
            name = affix[t.name]["pack_table"]
            reasons[t.name] = affix[t.name]["reason"]
        pt = p["tables"].get(name)
        if pt is None or name in taken:
            continue
        if variant and pt.get("variants") and variant not in pt["variants"]:
            continue
        have = _cols(t)
        entry = _mirror_entry(mirror, t.name, name)
        if entry is not None:
            entries[t.name] = entry
            mk = entry.get("keys") or []
            lacking = [c for c in mk if _norm(c) not in have]
            if mk and not lacking:
                taken.add(name)
                found[t.name] = name
                cols[t.name] = have
                keys[t.name] = [have[_norm(c)] for c in mk]
                key_rules[t.name] = MIRROR_RULE
                by_alias += [t.name] if alias else []
                continue
            if lacking:
                mirror_problems.append({"table": t.name, "why": f"the mirror metadata names key column(s) the table lacks: {', '.join(lacking)}; "
                                                                 f"the {pack} pack's key is used"})
        key = [c for c in pt["key"] if _norm(c) in have or c not in CLIENT_COLUMNS]
        if not all(_norm(c) in have for c in key) or len(key) == 0:
            keyless.append(t.name)
            continue
        taken.add(name)
        found[t.name] = name
        cols[t.name] = have
        if len(key) < len(pt["key"]):
            dropped.append(t.name)
        keys[t.name] = [have[_norm(c)] for c in key]
        key_rules[t.name] = RULE
        by_alias += [t.name] if alias else []
    if len(found) < 2:
        return None
    reasons = {t: r for t, r in reasons.items() if t in found}
    by_key = [{"table": r["table"], "pack_table": r["pack_table"], "reason": r["reason"]} for r in recognised
              if r["how"] == KEY_RULE and r["pack_table"] not in found.values()]
    by_pack = {v: k for k, v in found.items()}
    applied, not_applied, missing_cols = [], [], []
    missing_tables: set[str] = set()
    for r in p["relationships"]:
        s, g = by_pack.get(r["source"]), by_pack.get(r["target"])
        if s is None and g is None:
            continue
        if s is None or g is None:
            missing_tables.add(r["target"] if s else r["source"])
            continue
        if variant and r.get("variants") and variant not in r["variants"]:
            continue
        pairs = []
        lost = []
        for a, b in zip(r["source_cols"], r["target_cols"]):
            ha, hb = cols[s].get(_norm(a)), cols[g].get(_norm(b))
            if ha and hb:
                pairs.append((ha, hb))
            elif a in CLIENT_COLUMNS or b in CLIENT_COLUMNS:
                continue                                                  # the client dropped on one side: dropped on both
            else:
                lost.append((s, a) if not ha else (g, b))
        kind = r.get("kind", "key")
        valid = None
        if kind == "valid_on":                                            # the date and the period columns must be there too
            v = r["valid_on"]
            tf, tt = cols[g].get(_norm(v["target_from"])), cols[g].get(_norm(v["target_to"]))
            need = [(g, v["target_from"], tf), (g, v["target_to"], tt)]
            valid = {"target_from": tf, "target_to": tt}
            if v.get("on") == "today":
                valid["on"] = "today"
            else:
                sd = cols[s].get(_norm(v["source_date"]))
                need.append((s, v["source_date"], sd))
                valid["source_date"] = sd
            lost += [(t_, c_) for t_, c_, have in need if not have]
        where = []
        for w in r.get("where", []):                                       # the filter columns must be there too
            table = s if w["side"] == "source" else g
            have = cols[table].get(_norm(w["column"]))
            if have:
                where.append({**w, "column": have})
            else:
                lost.append((table, w["column"]))
        info = {k: r[k] for k in ("cardinality", "role", "condition", "sources", "module") if k in r}
        info["kind"] = kind
        if mirror is not None:
            info["decided_by"] = key_rules.get(g, RULE)
        if valid:
            info["valid_on"] = valid
        if where:
            info["where"] = where
        if lost:
            for table in dict.fromkeys(x for x, _ in lost):
                missing_cols.append({"table": table, "columns": [c for x, c in lost if x == table],
                                     "relationship": f"{r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}"})
            not_applied.append({"source": s, "target": g, "pack_source_cols": r["source_cols"],
                                "why": "columns missing: " + ", ".join(f"{x}.{c}" for x, c in lost), **info})
            continue
        rel = {"source": s, "source_cols": [a for a, _ in pairs], "target": g, "target_cols": [b for _, b in pairs], **info}
        if key_rules.get(g) == MIRROR_RULE and kind == "key" and r.get("apply") is not False and not r.get("where") \
                and sorted(_norm(b) for _, b in pairs) != sorted(_norm(c) for c in keys[g]):
            not_applied.append({**rel, "why": f"{MIRROR_RULE}: the mirror declares {g}'s key as {', '.join(keys[g])}, not the pack's "
                                              f"{', '.join(r['target_cols'])}; the mirror's metadata wins over the pack"})
            continue
        if r.get("apply") is False:
            not_applied.append({**rel, "why": "conditional: " + r.get("condition", "holds for some rows only") + " Listed, not applied; confirm it if your rows are of that kind."})
            continue
        applied.append(rel)
    hint, seen = "", variant
    present = set(found.values())
    for v in p["variants"]:
        only = [n for n, t in p["tables"].items() if t.get("variants") == [v] and n in present]
        if only:
            hint, seen = f"{v} (tables only that variant has: {', '.join(sorted(only))})", seen or v
    if seen:                                                              # BSEG is not missing from an S/4HANA schema
        missing_tables = {n for n in missing_tables if not p["tables"][n].get("variants") or seen in p["tables"][n]["variants"]}
    return Match(pack, found, keys, applied, not_applied, sorted(missing_tables), missing_cols, dropped, hint, keyless,
                 key_rules, {t: e for t, e in entries.items() if t in found}, mirror_problems, cols, by_alias,
                 reasons, by_key, ambiguous)


def match_any(schema, variant: str | None = None) -> Match | None:
    """The pack that recognises most of a schema's tables (sap, younium_salesforce, ...), or None when none recognises
    two. Ties go to the pack named first in alphabetical order. The engine (infer._pack) calls this since round n78.

    A pack counts only when at least one table it recognises has a name of the system's own: a pack table marked
    `common_name` (ACCOUNTS, PRODUCTS, INVOICES, PAYMENTS, Salesforce's Account, Contact, Opportunity) is an ordinary word
    another schema's table can carry with an `id` key, so tables of that kind alone never make a schema Younium or
    Salesforce. Every SAP table name is SAP's own (none is marked), so a schema the SAP pack recognises is read as before.
    match(schema, pack) asked for by name is not filtered."""
    best = None
    for name in available():
        m = match(schema, name, variant if name == "sap" else None)
        if m is None or not distinctive(m):
            continue
        if best is None or len(m.tables) > len(best.tables):
            best = m
    return best


def distinctive(m: Match) -> list[str]:
    """The pack tables of a match whose names are the system's own (not marked common_name), sorted. A table found by
    an alias marked `common_alias` (round n230: `Customer`, `Product` for the CDS views I_Customer, I_Product) is an
    ordinary word too and does not count; found as `I_Customer` it does."""
    tables = load(m.pack)["tables"]
    return sorted({n for t, n in m.tables.items()
                   if not tables[n].get("common_name") and not (t in m.by_alias and tables[n].get("common_alias"))})


def plan_with(schema, pack: str, **kwargs):
    """infer.plan over the schema with a pack's keys and plain key relationships given as the caller's keys and
    confirmed relationships, for a pack named by the caller (the engine itself reads the pack through match_any since
    round n78; this stays for comparing, and for a schema match_any would not take). The rules in the plan then read K1
    and confirmed, not the pack's rule; relationships of kind unique or valid_on and filtered ones are not passed (they
    would be plan.extended). Returns (plan, match)."""
    from .infer import plan
    m = match(schema, pack)
    if m is None:
        return plan(schema, **kwargs), None
    keys = {t: list(cols) for t, cols in m.keys.items()}
    confirmed = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"]}
                 for r in m.relationships if r.get("kind", "key") == "key" and not r.get("where")]
    return plan(schema, keys={**keys, **kwargs.pop("keys", {})}, confirmed=confirmed + list(kwargs.pop("confirmed", [])), **kwargs), m


def table_info(pack_table: str, pack: str = "sap") -> dict:
    return load(pack)["tables"][pack_table]


def amounts(m: Match) -> list[dict]:
    """Every amount the pack knows on a matched table, with its level and currency column. An amount on a table that
    others point at many-to-one (VBAK.NETWR for VBAP, VBAP.NETWR for VBEP) is repeated by a join with them."""
    p = load(m.pack)
    def spell(t: str, c: str) -> str:                               # n230: the schema's spelling where the names differ by more
        have = m.columns.get(t, {}).get(_norm(c), c)                # than case (NetAmount for NET_AMOUNT; NETWR stays NETWR)
        return c if have.lower() == c.lower() else have
    return [{"table": t, "column": spell(t, a["column"]), "level": a["level"], "currency": spell(t, a["currency"])}
            for t, name in m.tables.items() for a in p["tables"][name].get("amounts", [])]


EXPORTS = ("none", "krusgraph", "dab", "extraction", "dbt")


def draft(plan, source_name: str = "sap", export: str = "none", variant: str | None = None, mirror: dict | None = None) -> dict:
    """What the pack recognises in a plan's schema and what it lacks, read-only; optionally one export of the plan.
    The answer behind the sap_pack_draft tool. mirror (n129, library only; the tool does not take it): metadata a
    mirrored SAP source declares (sap_mirror.read); each table then says which rule gave its key and description, and
    each relationship which rule decided its target key. Build the plan with sap_mirror.plan to have the same keys."""
    from .infer import PlanInputError
    from . import pack_manifest
    if export not in EXPORTS:
        raise PlanInputError(f"export: {export!r} is not one of {', '.join(EXPORTS)}")
    p = load("sap")
    if variant is not None and variant not in p["variants"]:
        raise PlanInputError(f"variant: {variant!r} is not one of {', '.join(p['variants'])}")
    m = match(plan.schema, "sap", variant, mirror=mirror)
    if m is None:
        near = [t.name for t in plan.schema if pack_table(t.name)]
        return {"summary": "no SAP tables recognised (the pack needs two or more of its tables with their key columns); the plan "
                           "is the name rules' alone" + (f". Names the pack knows but without their key columns: {', '.join(near)}" if near else ""),
                "pack_tables": sorted(p["tables"]), "modules": p["modules"], "pack_manifest": pack_manifest.header("sap")}
    srcs = lambda ids: [{"title": p["sources"][i]["title"], "url": p["sources"][i]["url"], "fetched": p["sources"][i]["fetched"]} for i in ids]
    tables = [{"table": t, "pack_table": n, "level": p["tables"][n]["level"], "en": p["tables"][n]["en"],
               **({"de": p["tables"][n]["de"]} if "de" in p["tables"][n] else {}),
               **({"source_name": p["tables"][n]["source_name"]} if p["tables"][n].get("source_name") else {}),
               **({"corresponds_to": p["tables"][n]["corresponds_to"]["table"]} if p["tables"][n].get("corresponds_to") else {}),
               "key": m.keys[t], **({"note": p["tables"][n]["note"]} if p["tables"][n].get("note") else {}),
               "sources": srcs(p["tables"][n]["sources"])} for t, n in m.tables.items()]
    if mirror is not None:
        for row in tables:
            row.update(_mirror_fields(m, row["table"], p["tables"][row["pack_table"]]))
    rels = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"],
             "cardinality": r["cardinality"], "kind": r.get("kind", "key"), **({"valid_on": r["valid_on"]} if r.get("valid_on") else {}),
             **({"role": r["role"]} if r.get("role") else {}),
             **({"condition": r["condition"]} if r.get("condition") else {}),
             **({"decided_by": r["decided_by"]} if r.get("decided_by") else {}), "sources": srcs(r["sources"])} for r in m.relationships]
    in_plan = {(r.source, tuple(c.lower() for c in r.source_cols), r.target): r.rule for r in plan.relationships}
    in_plan.update({(r.source, tuple(c.lower() for c in r.source_cols), r.target): f"{r.rule} ({r.kind}, plan.extended)" for r in plan.extended})
    for r in rels:
        r["in_plan"] = in_plan.get((r["source"], tuple(c.lower() for c in r["source_cols"]), r["target"]), "no (confirmed or keys override it)")
    out = {"summary": f"{len(m.tables)} SAP table(s) recognised, {len(rels)} pack relationship(s) apply, {len(m.not_applied)} listed "
                      f"but not applied, {len(m.missing_tables)} pack table(s) missing that would complete them",
           "status": "documented in public sources, not verified against data; validate_plan with the same keys/confirmed verifies it",
           "variant_hint": m.variant_hint or "no table that only one variant has",
           "tables": tables, "relationships": rels, "not_applied": m.not_applied, "missing_tables": m.missing_tables,
           "missing_columns": m.missing_columns, "client_dropped": m.client_dropped,
           "amounts": amounts(m),
           "traps": [{"title": t["title"], "text": t["text"]} for t in p["traps"]],
           "next": "validate_plan checks keys and relationships against the rows; validate_plan's amount_levels names the header amounts a join repeats.",
           **({"mirror_problems": m.mirror_problems,
               "mirror_rule": f"{MIRROR_RULE}: keys and descriptions the mirrored source declares win over the pack and the name rules; "
                              "see each table's key_rule and description_rule and each relationship's decided_by"} if mirror is not None else {}),
           "pack_manifest": pack_manifest.header("sap")}          # n77: id, version and review status of packs/sap/manifest.yaml
    if export != "none":
        from . import exports
        if export == "krusgraph":
            out["export"] = exports.krusgraph_plan(plan)
        elif export == "dab":
            out["export"] = {"path": "dab-config.json", "config": exports.dab_config(plan)}
        elif export == "extraction":
            out["export"] = exports.extraction_list(plan, m)
        else:
            from . import dbt
            out["export"] = {"path": dbt.sources_path(source_name), "yaml": dbt.schema_yml(plan, source_name, plan.schema.schema)}
    return out


def _mirror_fields(m: Match, table: str, pack_table: dict) -> dict:
    """Which rule gave a matched table its key and its description, and the column descriptions the mirror declares."""
    e = m.mirror.get(table) or {}
    out = {"key_rule": m.key_rules.get(table, RULE)}
    if out["key_rule"] == MIRROR_RULE:
        out["key_from"] = e.get("key_from", "")
    if e.get("description"):
        out.update({"description": e["description"], "description_rule": MIRROR_RULE, "description_from": e.get("description_from", "")})
    else:
        out.update({"description": pack_table["en"], "description_rule": RULE})
    if e.get("columns"):
        out["column_descriptions"] = {c: {"description": d, "rule": MIRROR_RULE} for c, d in e["columns"].items()}
    return out


# ------------------------------------------------------------------ verification against real rows (round n31) ------

def _pack_relationship(entry: dict, pack: dict) -> tuple[int, dict] | None:
    """The pack relationship a validate_plan entry checked: same tables by pack name, same columns (the client may have
    been dropped by the extract)."""
    src, tgt = pack_table(entry["source"], pack["pack"]), pack_table(entry["target"], pack["pack"])
    cols = {_norm(c) for c in entry["columns"]}
    for i, r in enumerate(pack["relationships"]):
        if r["source"] != src or r["target"] != tgt:
            continue
        mine = {_norm(c) for c in r["source_cols"]}
        if cols <= mine and mine - cols <= set(CLIENT_COLUMNS):
            return i, r
    return None


def verification(validation: dict, where: str, when: str, pack: str = "sap") -> dict:
    """A proposal per pack relationship from a saved validate_plan answer: verified (it held for every row with a value,
    and no row matched twice), review (orphans or rows that matched more than one target row: read its condition first),
    no evidence (no row had a value), or not checked (a pack relationship between the tables checked that the answer
    does not contain: listed only, or past max_items). Proposals only; write_verified records the verified ones.
    `where` says what was checked, without names of a real company (for example "SAP S/4HANA sandbox, synthetic data");
    `when` is the date of the run."""
    p = load(pack)
    rows, seen = [], set()
    for e in validation.get("relationships", []):
        if e.get("rule") != RULE:
            continue
        found = _pack_relationship(e, p)
        if found is None:
            continue
        i, r = found
        seen.add(i)
        n, orphans, several = int(e.get("rows_with_value") or 0), int(e.get("orphans") or 0), int(e.get("several") or 0)
        if n == 0:
            proposal, why = "no evidence", "no row had a value in the reference columns"
        elif orphans or several:
            proposal = "review"
            why = "; ".join(x for x in (f"{orphans} of {n} rows point at nothing" if orphans else "",
                                        f"{several} rows match more than one target row" if several else "") if x)
            if r.get("condition"):
                why += f". The pack's condition: {r['condition']}"
        else:
            proposal, why = "verified", f"held for all {n} rows with a value"
        rows.append({"module": r["module"], "index": i, "source": r["source"], "source_cols": r["source_cols"], "target": r["target"],
                     "kind": r.get("kind", "key"), "proposal": proposal, "why": why,
                     "evidence": {"rows_with_value": n, "orphans": orphans, "several": several}})
    checked = {pack_table(k["table"], pack) for k in validation.get("keys", [])}
    for i, r in enumerate(p["relationships"]):
        if i not in seen and r["source"] in checked and r["target"] in checked:
            rows.append({"module": r["module"], "index": i, "source": r["source"], "source_cols": r["source_cols"], "target": r["target"],
                         "kind": r.get("kind", "key"), "proposal": "not checked",
                         "why": "listed only, not applied" if r.get("apply") is False else "not in the answer (raise max_items, or the columns were missing)"})
    counts = {k: sum(1 for x in rows if x["proposal"] == k) for k in ("verified", "review", "no evidence", "not checked")}
    return {"where": where, "when": when, "counts": counts, "relationships": rows,
            "summary": ", ".join(f"{v} {k}" for k, v in counts.items()),
            "note": "Proposals from counts, not proof of meaning: a relationship that held on one system can fail on another. "
                    "Record only runs on systems you may describe, and describe them without naming a company."}


def write_verified(report: dict, pack: str = "sap") -> list[str]:
    """Add {where, when, rows_with_value} to the `verified` list of every relationship the report proposes as verified,
    in the pack's own files (one line per relationship, as they are written). Returns what was changed."""
    from .sap_demo import DEMO_WHERE
    if DEMO_WHERE in report["where"].lower() or "synthetic" in report["where"].lower():
        raise ValueError("a run on synthetic rows proves nothing about the pack (the rows are written from it); "
                         "record only runs on a real SAP system you may describe")
    changed = []
    p = load(pack)
    by_module: dict[str, list[dict]] = {}
    for x in report["relationships"]:
        if x["proposal"] == "verified":
            by_module.setdefault(x["module"], []).append(x)
    for module, items in by_module.items():
        path = PACKS.parent / next(x["file"] for x in p["modules"] if x["module"] == module)   # PK1: an included module's own file
        lines = path.read_text(encoding="utf-8").split("\n")
        for x in items:
            r = {k: v for k, v in p["relationships"][x["index"]].items() if k != "module"}
            for n, line in enumerate(lines):
                st = line.strip()
                if not st.startswith("{") or '"source_cols"' not in st:
                    continue
                obj = json.loads(st.rstrip(","))
                if (obj["source"], obj["source_cols"], obj["target"], obj["target_cols"]) != (r["source"], r["source_cols"], r["target"], r["target_cols"]):
                    continue
                entry = {"where": report["where"], "when": report["when"], "rows_with_value": x["evidence"]["rows_with_value"]}
                if entry not in obj.get("verified", []):
                    obj["verified"] = obj.get("verified", []) + [entry]
                    srcs = obj.pop("sources")
                    obj["sources"] = srcs                                       # sources stay last on the line
                    indent = line[:len(line) - len(line.lstrip())]
                    lines[n] = indent + json.dumps(obj, ensure_ascii=False) + ("," if st.endswith(",") else "")
                    changed.append(f"{module}: {r['source']}.{'+'.join(r['source_cols'])} -> {r['target']}")
                break
        text = "\n".join(lines)
        json.loads(text)
        path.write_text(text, encoding="utf-8")
    _load.cache_clear()
    _names.cache_clear()
    return changed


def verification_markdown(report: dict) -> str:
    out = [f"# SAP pack verification: {report['where']}, {report['when']}", "", report["summary"], "", report["note"], "",
           "| Proposal | Relationship | Kind | Rows | Orphans | Several | Why |", "| --- | --- | --- | --- | --- | --- | --- |"]
    order = {"review": 0, "verified": 1, "no evidence": 2, "not checked": 3}
    for x in sorted(report["relationships"], key=lambda x: (order[x["proposal"]], x["module"], x["source"])):
        ev = x.get("evidence", {})
        out.append(f"| {x['proposal']} | {x['source']}.{'+'.join(x['source_cols'])} → {x['target']} | {x['kind']} | "
                   f"{ev.get('rows_with_value', '')} | {ev.get('orphans', '')} | {ev.get('several', '')} | {x['why'].replace('|', '/')} |")
    return "\n".join(out) + "\n"
