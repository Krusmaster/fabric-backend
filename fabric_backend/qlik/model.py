"""Qlik's associations as keys and relationships of a Krusgraph plan (Q1). See the package docstring.

The trap this is written around. Qlik associates two tables on *every* field name they share. With one shared field
that is one link. With two or more, Qlik builds a synthetic key over the fields together, so two rows associate only
where all of them are equal (Unverified, as every Qlik fact here). A Power BI relationship has one column per side
and needs a one side where the value is unique. Turning each shared field into a relationship of its own gives two
paths between the same tables, or links on a field that is unique nowhere; picking one field silently changes which
rows relate. So nothing is picked silently: each synthetic key is put in one case, with the counts that decided it.

| Case | The counts show | What goes into the plan |
|---|---|---|
| `one_field_links` | exactly one shared field is unique in one of the two tables | a relationship on that field; for every other shared field the number of rows that matched on the link but not on that field (in Qlik they did not associate) |
| `composite_key` | no single field is unique, the fields together are unique in one table | one relationship on all the fields, which combined_keys.py carries as one combined key column |
| `two_facts_sharing_dimensions` | the fields together are unique in neither table | no relationship between the two; each field is a dimension both relate to (an existing table where the field is unique, or a new one). When the pairs themselves are the information it is a many-to-many, and a person decides |
| `a_person_decides` | more than one field could carry the link, or both tables are unique on the fields | nothing; the candidates are listed |
| `not_decided` | nothing was counted and the names do not say | nothing; what to count is listed |

A shared field with no unique side is not a relationship either (`no_key_side`): it is an attribute two tables
happen to name alike, which is also how most Qlik circular references arise.

Where the one side comes from: the rows, when `execute` is given (evidence.key_sql: unique means every row has a
value and no value twice); otherwise Krusgraph's name rules (infer.plan's keys), marked "by name, not counted".
"""
from __future__ import annotations

from .. import evidence, infer
from ..dialects import TSQL
from ..schema import Column, Schema, Table

DIFFERENCES = [
    "Direction: a Qlik selection reaches every associated table; a Power BI relationship filters from the one side "
    "to the many side by default. A measure on the one side that a selection on the many side filtered in Qlik needs "
    "a measure written for it.",
    "Rows without a match: in Qlik they do not associate; in a Power BI model they land on the blank row of the one "
    "side and stay in the total. Same total, different groups.",
    "Case: Qlik field values are case-sensitive; the Power BI engine is not. Distinct counts can differ.",
]


def _ints(rows, names: list[str]) -> list[int]:
    r = rows[0]
    if isinstance(r, dict):
        low = {str(k).lower(): v for k, v in r.items()}
        return [int(low.get(n) or 0) for n in names]
    return [int(v or 0) for v in list(r)[:len(names)]]


class _Rows:
    """What is known about the rows: counted through `execute`, each count once, or read from the names."""

    def __init__(self, read: dict, execute, schema: str, dialect, tables: dict | None, max_queries: int):
        self.cols = {t["name"]: {c["field"]: c["column"] for c in t["columns"]} for t in read["tables"]}
        self.landed = {t["name"]: (tables or {}).get(t["name"], t["table"]) for t in read["tables"]}
        self.execute, self.schema, self.dialect, self.max = execute, schema, dialect, max_queries
        self.queries, self.not_counted, self.failed, self.cache = 0, 0, [], {}
        by_name = infer.plan(to_schema(read), packs=False).keys
        self.names = {t: ({c.lower() for c in cols}, rule) for t, (cols, rule) in by_name.items()}

    def c(self, table: str, fields) -> list[str]:
        return [self.cols[table][f] for f in fields]

    def _run(self, key: tuple, sql: str, names: list[str]):
        if key in self.cache:
            return self.cache[key]
        if self.execute is None:
            return None
        if self.queries >= self.max:
            self.not_counted += 1
            return None
        self.queries += 1
        try:
            out = _ints(self.execute(sql), names)
        except Exception as e:                                          # the answer says so; the mapping goes on
            self.failed.append({"query": " ".join(str(k) for k in key), "why": type(e).__name__})
            out = None
        self.cache[key] = out
        return out

    def unique(self, table: str, fields) -> dict:
        """{"unique": True | False | None, "how": ...} for the fields together; None means not known."""
        cols = self.c(table, fields)
        if self.execute is None:
            key, rule = self.names.get(table, (set(), ""))
            if key == {x.lower() for x in cols}:
                return {"unique": True, "how": f"by name (rule {rule}), not counted"}
            return {"unique": None, "how": "not counted, and the names do not say"}
        got = self._run(("key", table, tuple(cols)), evidence.key_sql(self.schema, self.landed[table], cols, self.dialect),
                        ["n", "nulls", "distinct_keys"])
        if got is None:
            return {"unique": None, "how": "not counted (the query failed or the limit of queries was reached)"}
        n, nulls, distinct = got
        return {"unique": None if n == 0 else (nulls == 0 and distinct == n), "how": "counted in the rows",
                "rows": n, "nulls": nulls, "distinct": distinct, "verdict": evidence.key_verdict(n, nulls, distinct)}

    def link(self, source: str, fields, target: str) -> dict | None:
        """Rows of the source with a value, and how many of them match no row of the target."""
        got = self._run(("link", source, tuple(fields), target),
                        evidence.relationship_sql(self.schema, self.landed[source], self.c(source, fields), self.landed[target],
                                                  self.c(target, fields), self.dialect), ["with_value", "orphans"])
        if got is None:
            return None
        return {"with_value": got[0], "without_a_match": got[1], "verdict": evidence.relationship_verdict(*got)}

    def differs(self, source: str, target: str, link: str, other: str) -> int | None:
        """Rows of the source (both fields with a value) that match the target on `link` but on no row of the target
        with the same `other`: the rows a synthetic key over both fields kept apart."""
        q, d = self.dialect.quote, self.dialect
        s, t = d.table(self.schema, self.landed[source]), d.table(self.schema, self.landed[target])
        (sl, so), (tl, to) = self.c(source, [link, other]), self.c(target, [link, other])
        sql = (f"SELECT {d.count}(*) AS n FROM {s} AS s WHERE s.{q(sl)} IS NOT NULL AND s.{q(so)} IS NOT NULL "
               f"AND EXISTS (SELECT 1 FROM {t} AS t WHERE t.{q(tl)} = s.{q(sl)}) "
               f"AND NOT EXISTS (SELECT 1 FROM {t} AS t WHERE t.{q(tl)} = s.{q(sl)} AND t.{q(to)} = s.{q(so)})")
        got = self._run(("differs", source, target, link, other), sql, ["n"])
        return None if got is None else got[0]


def to_schema(read: dict, tables: dict | None = None) -> Schema:
    """The script's tables as a Schema, with the lakehouse names. The script says nothing about types, so every column
    is `string` here; pass the landed tables' own Schema to `to_plan` once they exist."""
    s = Schema(schema="qlik")
    for t in read["tables"]:
        name = (tables or {}).get(t["name"], t["table"])
        s.tables[name] = Table(name, [Column(c["column"]) for c in t["columns"]], schema="qlik")
    return s


def _two_paths(rels: list[dict]) -> list[dict]:
    """Relationships that close a loop: the second way between two tables, with the first way."""
    near: dict[str, list[tuple[str, dict]]] = {}
    out = []
    for r in rels:
        a, b = r["source"], r["target"]
        prev, queue = {a: None}, [a]
        while queue and b not in prev:
            x = queue.pop(0)
            for y, via in near.get(x, []):
                if y not in prev:
                    prev[y] = (x, via)
                    queue.append(y)
        if b in prev:
            path, x = [], b
            while prev[x] is not None:
                x, via = prev[x]
                path.append(via["id"])
            out.append({"between": [a, b], "one_way": r["id"], "other_way": path[::-1],
                        "in_the_model": "a tabular model keeps one active path between two tables: the semantic model draft "
                                        "keeps the more certain one active and makes the other inactive, and says which"})
        else:
            near.setdefault(a, []).append((b, r))
            near.setdefault(b, []).append((a, r))
    return out


def map_associations(read: dict, execute=None, schema: str = "dbo", dialect=TSQL, tables: dict | None = None,
                     max_queries: int = 300) -> dict:
    """`read` is `read_script`'s answer. `execute` runs a read-only query over the landed tables (the callable the
    engine's own checks take) in `schema`; `tables` maps a Qlik table to its landed name when that differs from the
    proposed one. Without `execute` nothing is counted and the one sides come from the names."""
    rows = _Rows(read, execute, schema, dialect, tables, max_queries)
    shared = {a["field"]: list(a["tables"]) for a in read["associations"]}
    order = {t["name"]: {f: i for i, f in enumerate(t["fields"])} for t in read["tables"]}
    pairs = {tuple(s["tables"]): list(s["fields"]) for s in read["synthetic_keys"]}
    links: dict[tuple, dict] = {}                 # (source, target, fields) -> how it was decided
    one_side: dict[str, str] = {}                 # field -> the table the others point at
    no_key, undecided, facts = [], [], {}

    for f, ts in shared.items():                  # 1. a one side per shared field
        facts[f] = {t: rows.unique(t, [f]) for t in ts}
        uniq = [t for t in ts if facts[f][t]["unique"] is True]
        parent = uniq[0] if len(uniq) == 1 else None
        if len(uniq) > 1:
            named = [t for t in uniq if rows.names.get(t, (set(), ""))[0] == {rows.cols[t][f].lower()}]
            if len(named) == 1:
                parent = named[0]
            else:
                undecided.append({"field": f, "tables": uniq, "counts": {t: facts[f][t] for t in uniq},
                                  "why": "each value occurs once in more than one of these tables (one-to-one), and the names "
                                         "do not say which table the others point at: a person decides"})
                continue
        if parent is None and len(uniq) == 0:
            if any(facts[f][t]["unique"] is None for t in ts):
                undecided.append({"field": f, "tables": ts, "counts": facts[f],
                                  "why": "no table is known to hold each value once: count the field in these tables "
                                         "(ask again once the tables are landed, so that the rows are counted)"})
            else:
                no_key.append(f)
            continue
        one_side[f] = parent
        for s in ts:
            if s != parent:
                links[(s, parent, (f,))] = {"one_side": facts[f][parent], "one_to_one": facts[f][s]["unique"] is True}

    synthetic, covered = [], set()                # 2. each synthetic key in one case
    for (a, b), fs in pairs.items():
        entry = {"tables": [a, b], "fields": fs,
                 "in_qlik": "a synthetic key over these fields together: two rows associated only where all of them were equal"}
        between = [(f, s, t) for f in fs for s, t in ((a, b), (b, a)) if (s, t, (f,)) in links]
        covered |= {(f, a, b) for f in fs}
        if len(between) == 1:
            f, s, t = between[0]
            others = []
            for g in fs:
                if g == f:
                    continue
                n = rows.differs(s, t, f, g) if execute is not None else None
                third = one_side.get(g)
                o = {"field": g, "rows_that_match_on_the_link_but_differ_here": n if n is not None else "not counted"}
                if third and third not in (a, b):
                    o["proposal"] = (f"keep it: both tables point at {third} through it. That gives two ways from {third} to {s} "
                                     "(see two_paths)")
                elif n == 0:
                    o["proposal"] = f"in every matching row it repeats {t}'s value: keep it in {t} and drop it from {s}, or rename it in {s}"
                else:
                    o["proposal"] = f"another field that shares the name: rename it per table ({s}_{rows.cols[s][g]}, {t}_{rows.cols[t][g]})"
                if n:
                    o["moves_numbers"] = (f"{n} row(s) of {s} did not associate with their {t} row in Qlik because {g} differed; "
                                          f"related on {f} alone they do. A number grouped across the two tables differs by these rows")
                others.append(o)
            entry.update({"case": "one_field_links", "link": {"source": s, "target": t, "field": f}, "other_fields": others})
        elif len(between) > 1:
            for f, s, t in between:
                held = links.pop((s, t, (f,)))
                entry.setdefault("candidates", []).append({"source": s, "target": t, "field": f, "one_side": held["one_side"]})
            entry.update({"case": "a_person_decides",
                          "why": "more than one of the shared fields could carry the link; a model allows one active "
                                 "relationship between two tables, and which one is a decision about what the tables mean"})
        else:
            ua, ub = rows.unique(a, fs), rows.unique(b, fs)
            entry["counts"] = {a: ua, b: ub}
            if (ua["unique"] is True) != (ub["unique"] is True):
                s, t = (b, a) if ua["unique"] is True else (a, b)
                fs = sorted(fs, key=lambda f: order[t][f])               # in the order of the one side's columns
                links[(s, t, tuple(fs))] = {"one_side": entry["counts"][t], "one_to_one": False}
                entry.update({"case": "composite_key", "link": {"source": s, "target": t, "fields": fs},
                              "in_the_model": "a relationship has one column per side: the plan carries the fields as one "
                                              "combined key column on both sides (combined_keys.py), written in the silver step"})
            elif ua["unique"] is True:
                entry.update({"case": "a_person_decides",
                              "why": "the fields together are unique in both tables (one-to-one); which table points at the "
                                     "other, or whether they are one table, is a decision"})
            elif ua["unique"] is False and ub["unique"] is False:
                dims = [{"field": f, "dimension": one_side[f]} if one_side.get(f) not in (None, a, b)
                        else {"field": f, "dimension": None, "proposal": f"a new dimension table of the distinct values of {f}, "
                                                                           "which both tables then relate to"} for f in fs]
                entry.update({"case": "two_facts_sharing_dimensions", "dimensions": dims,
                              "in_the_model": "no relationship between the two tables; each shared field is a dimension both "
                                              "relate to. If the pairs of values are themselves the information it is a "
                                              "many-to-many and needs a bridge table: a person decides"})
            else:
                entry.update({"case": "not_decided",
                              "why": "count the shared fields, one by one and together, in both tables (give `execute` once the "
                                     "tables are landed); until then nothing between these two tables is in the plan"})
        entry["decided_by"] = "counts in the rows" if execute is not None else "names only: nothing was counted"
        synthetic.append(entry)

    def loose(f):                                 # the pairs of tables sharing f that no synthetic key explains
        ts = shared[f]
        return [[a, b] for i, a in enumerate(ts) for b in ts[i + 1:] if (f, a, b) not in covered and (f, b, a) not in covered]
    undecided = [u for u in undecided if loose(u["field"])]

    attributes = []                               # 3. shared fields that are unique nowhere and no synthetic key explains
    for f in no_key:
        if loose(f):
            attributes.append({"field": f, "tables": shared[f], "counts": facts[f],
                               "in_qlik": "an association: a selection in one table filtered the others through this field",
                               "in_the_model": "not a relationship: no table holds each value once. Either rename it per table "
                                               "(two attributes), or make a dimension table of its distinct values that the "
                                               "tables relate to (one shared attribute): a person decides"})

    key_of: dict[str, list[str]] = {}             # 4. one key per table; the relationships
    wanted: dict[str, dict[tuple, int]] = {}
    for (s, t, fs) in links:
        wanted.setdefault(t, {})[fs] = wanted.get(t, {}).get(fs, 0) + 1
    for t, sets in wanted.items():
        named = [fs for fs in sets if rows.names.get(t, (set(), ""))[0] == {x.lower() for x in rows.c(t, fs)}]
        key_of[t] = list(named[0] if named else sorted(sets, key=lambda fs: (-sets[fs], fs))[0])
    rels = []
    for (s, t, fs), how in sorted(links.items()):
        r = {"id": f"{rows.landed[s]}.{'+'.join(rows.c(s, fs))} -> {rows.landed[t]}", "source": rows.landed[s],
             "source_cols": rows.c(s, fs), "target": rows.landed[t], "target_cols": rows.c(t, fs), "qlik_fields": list(fs),
             "one_side": how["one_side"]["how"], "in_plan": "relationship" if list(fs) == key_of[t] else "extended"}
        if r["in_plan"] == "extended":
            r["why_extended"] = (f"{t} is also the one side on {'+'.join(key_of[t])}, which is its key in the plan; this link is "
                                 "on a second unique column and is kept beside the key joins")
        if how["one_to_one"]:
            r["one_to_one"] = True
        counted = rows.link(s, fs, t) if execute is not None else None
        if counted:
            r["counts"] = counted
            if counted["without_a_match"]:
                r["moves_numbers"] = (f"{counted['without_a_match']} row(s) of {s} have a value that is not in {t}: in Qlik they "
                                      "associated with nothing; in the model they land on the blank row and stay in the total")
        rels.append(r)

    plan_rels = [r for r in rels if r["in_plan"] == "relationship"]
    sources, targets = {r["source"] for r in plan_rels}, {r["target"] for r in plan_rels}
    out_tables = []
    for t in read["tables"]:
        n = rows.landed[t["name"]]
        role = ("dimension that points on (a snowflake step or a header)" if n in sources and n in targets else
                "fact" if n in sources else "dimension" if n in targets else "not linked")
        row = {"qlik": t["name"], "table": n, "columns": [c["column"] for c in t["columns"]], "role": role, "as_loaded": t["as_loaded"]}
        if t["name"] in key_of:
            row["key"] = rows.c(t["name"], key_of[t["name"]])
        out_tables.append(row)

    circular = []
    for c in read["circular_references"]:
        inside = {rows.landed[t] for t in c["tables"]}
        kept = [f for f in c["fields"] if any(f in r["qlik_fields"] for r in rels if {r["source"], r["target"]} <= inside)]
        gone = [f for f in c["fields"] if f not in kept]
        circular.append({**c, "in_the_plan": (f"the link on {', '.join(gone)} is not a relationship here (no unique side, or not "
                                              "decided), so these tables do not form a loop in the plan" if gone else
                                              "every link of the loop is a relationship: see two_paths for the path that is "
                                              "made inactive")})
    return {
        "kind": "qlik_associations_as_a_plan",
        "decided_by": ("counts in the rows" if execute is not None else "names only: nothing was counted"),
        "tables": out_tables,
        "relationships": rels,
        "synthetic_keys": synthetic,
        "shared_fields_with_no_key_side": attributes,
        "circular_references": circular,
        "two_paths": _two_paths(plan_rels),
        "link_table_candidates": [{**x, "in_the_model": "a table whose every field links to another table: a bridge or a "
                                                         "factless fact. It stays a table; whether dimensions replace it is "
                                                         "a person's decision"} for x in read["link_table_candidates"]],
        "undecided": undecided,
        "differences_that_move_numbers": DIFFERENCES,
        "counting": {"queries": rows.queries, "not_counted_limit": rows.not_counted, "failed": rows.failed},
        "not_read": read["not_read"],
    }


def to_plan(mapping: dict, schema: Schema | str | None = None):
    """The mapping as Krusgraph's plan: (infer.Plan, also_found). The keys go in as the caller's keys (K1) and the
    relationships as `confirmed`, so the plan holds exactly what the mapping decided. `also_found` lists what
    Krusgraph's name rules would add between these tables: not associations in Qlik, so not in the plan, and shown.
    `schema` is the landed tables' own Schema (with their types), or the name of the schema they are in; without a
    Schema every column is a string."""
    if not isinstance(schema, Schema):
        name = schema or "qlik"
        schema = Schema(schema=name)
        for t in mapping["tables"]:
            schema.tables[t["table"]] = Table(t["table"], [Column(c) for c in t["columns"]], schema=name)
    keys = {t["table"]: t["key"] for t in mapping["tables"] if "key" in t}
    plain = [r for r in mapping["relationships"] if r["in_plan"] == "relationship"]
    confirmed = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"]}
                 for r in plain]
    p = infer.plan(schema, keys=keys, confirmed=confirmed, packs=False)
    note = {(r["source"].lower(), tuple(c.lower() for c in r["source_cols"]), r["target"].lower()):
            f"a Qlik association on {'+'.join(r['qlik_fields'])}; the one side {r['one_side']}" for r in plain}
    also = [{"source": r.source, "source_cols": r.source_cols, "target": r.target, "target_cols": r.target_cols, "rule": r.rule}
            for r in p.relationships if r.rule != "confirmed"]
    p.relationships = [r for r in p.relationships if r.rule == "confirmed"]
    for r in p.relationships:
        r.note = note.get((r.source.lower(), tuple(c.lower() for c in r.source_cols), r.target.lower()), "")
    for r in mapping["relationships"]:
        if r["in_plan"] == "extended":
            p.extended.append(infer.ExtendedRelationship(r["source"], list(r["source_cols"]), r["target"], list(r["target_cols"]),
                                                         "confirmed", note=f"a Qlik association on {'+'.join(r['qlik_fields'])}",
                                                         kind="unique"))
    return p, also
