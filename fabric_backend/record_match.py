"""GR1: the same customer in several systems (a CRM, an ERP, an MDM hub), matched on a key and counted on the rows.

    match(sides, execute, dialect, show_personal_data=False, entity="customer") -> dict

Two or three **sides**, each a table in a source with its key column(s) and, optionally, compare columns (name, country)
that should agree when the key matches. Nothing is guessed and nothing is merged:

**The key is normalised by fixed, named rules**, one per key column, chosen by the person or proposed from the column's
name (`propose_rule`), and always shown with the reason:

    N1  trimmed and upper case                      every key the other rules do not name
    N2  N1, then spaces, dashes, dots and slashes   organisation numbers, VAT ids, DUNS, GLN (combine.identifier_of,
        removed                                     the names SM7's rule M1 reads)
    N3  trimmed and lower case                      e-mail addresses (privacy.py's rule P2)
    N4  spaces, dashes, brackets, dots, slashes     telephone numbers (privacy.py's rule P3). A leading 00 and a leading
        and plus signs removed, a leading 00 removed + become the same number; a national number that starts with one
                                                    0 stays as it is: the country code cannot be known by rule.

A composite key's parts are normalised one by one and joined with `|`; a row whose key has an empty or NULL part has
no key and is counted as such. Compare columns are normalised with N1.

**The buckets** are counted over the distinct normalised keys of each pair of sides, and of all sides together, by SQL
on the rows (`pair_sql`, `all_sql`; `side_sql` per side). Every key lands in exactly one bucket, so they add up:

    matched      the key is on both sides, once on each
    only_in_a    once on side A, not on side B (and only_in_b the other way)
    duplicated   on more than one row of a side: it cannot be matched safely, whatever the other side holds
    conflicts    a part of matched: the key matches but a compare column differs after N1 (both sides hold a value)

Up to EXAMPLES keys per bucket are shown (`examples_sql`), masked by privacy.py's rules when a key column looks like
personal data by name (an e-mail address, a telephone number), unless show_personal_data. No other row value is
returned: conflicts name the column that differs, never the values.

**Candidates for a person** (`candidates_sql`): when both sides of a pair compare a field named `name`, the keys found
on one side only whose N1 name equals the name of a key found on the other side only. Exact equality after N1, never
similarity; listed for a person to look at, never matched.

Nothing here writes. The statements are SELECTs over the sides' tables; the server runs them over one SQL connection.
"""
from __future__ import annotations

import re

from .dialects import TSQL, Dialect

RULES = {
    "N1": "trimmed and upper case",
    "N2": "trimmed, upper case, spaces, dashes, dots and slashes removed",
    "N3": "trimmed and lower case (e-mail addresses)",
    "N4": "spaces, dashes, brackets, dots, slashes and plus signs removed, a leading 00 removed (telephone numbers)",
}
COMPARE_RULE = "N1"
MAX_SIDES, MIN_SIDES = 3, 2
MAX_KEY_COLS, MAX_COMPARE = 3, 4
EXAMPLES = 3
MAX_CANDIDATES = 20
BUCKETS = ("matched", "only_in_a", "only_in_b", "duplicated", "conflicts")
NEXT_STEP = "Decide per field which source wins; a golden record view comes next"
_FIELD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,40}$")


FLAG = "KRUSGRAPH_MATCH_RECORDS"          # the tool is registered only when the operator sets it (off by default)
_ON = {"1", "true", "yes", "on"}


def on(environ=None) -> bool:
    """KRUSGRAPH_MATCH_RECORDS: register match_records. Read at import."""
    import os
    return (environ if environ is not None else os.environ).get(FLAG, "").strip().lower() in _ON


class MatchInputError(ValueError):
    """A side the call described wrongly: (kind, error, hint), answered as the tools answer an error."""

    def __init__(self, kind: str, error: str, hint: str):
        super().__init__(error)
        self.kind, self.error, self.hint = kind, error, hint

    def answer(self) -> dict:
        return {"error": self.error, "kind": self.kind, "hint": self.hint}


# ------------------------------------------------------------------------------------------------ the rules
def propose_rule(table: str, column: str) -> tuple[str, str]:
    """(rule, why) for a key column, by its name: N2 for an official identifier, N3 for an e-mail address, N4 for a
    telephone number, else N1."""
    from . import combine, privacy
    kind = combine.identifier_of(column)
    if kind:
        return "N2", f"{column} is named as {'an' if kind[0] in 'aeiou' else 'a'} {kind}"
    found = privacy.classify(table, column) or {}
    if found.get("rule") == "P2":
        return "N3", f"{column} is named as an e-mail address"
    if found.get("rule") == "P3":
        return "N4", f"{column} is named as a telephone number"
    return "N1", f"{column} is not named as an identifier, e-mail address or telephone number"


def _text(expr: str, d: Dialect) -> str:
    return f"CAST({expr} AS STRING)" if d.name == "databricks" else f"CAST({expr} AS NVARCHAR(4000))"


def _strip(x: str, chars: str) -> str:
    for ch in chars:
        x = f"REPLACE({x}, '{ch}', '')"
    return x


def normal(expr: str, rule: str, d: Dialect = TSQL) -> str:
    """The SQL of one rule applied to a column expression."""
    t = _text(expr, d)
    if rule == "N1":
        return f"UPPER(LTRIM(RTRIM({t})))"
    if rule == "N2":
        return _strip(f"UPPER(LTRIM(RTRIM({t})))", " -./")
    if rule == "N3":
        return f"LOWER(LTRIM(RTRIM({t})))"
    if rule == "N4":
        x = _strip(t, " -()./+")
        return f"CASE WHEN SUBSTRING({x}, 1, 2) = '00' THEN SUBSTRING({x}, 3, 4000) ELSE {x} END"
    raise MatchInputError("bad_input", f"unknown rule {rule!r}", "Use one of " + ", ".join(f"{k} ({v})" for k, v in RULES.items()) + ".")


def key_expr(side: dict, d: Dialect = TSQL, alias: str = "t") -> str:
    """The normalised key of one row: one column as its rule gives it; several joined with '|', NULL when a part is empty."""
    q = d.quote
    parts = [normal(f"{alias}.{q(c)}", r, d) for c, r in zip(side["key"], side["rules"])]
    if len(parts) == 1:
        return parts[0]
    empty = " OR ".join(f"{p} IS NULL OR {p} = ''" for p in parts)
    joined = ", '|', ".join(parts)
    return f"CASE WHEN {empty} THEN NULL ELSE CONCAT({joined}) END"


# ------------------------------------------------------------------------------------------------ the statements
def _ctes(side: dict, tag: str, fields: list[str], d: Dialect) -> str:
    """s<tag>: every row's normalised key and compare values; g<tag>: one row per key with how many rows hold it (and,
    for a key held once, that row's compare values)."""
    q = d.quote
    cols = "".join(f", {normal('t.' + q(side['compare'][f]), COMPARE_RULE, d)} AS {q('f_' + f)}" for f in fields
                   if f in side["compare"])
    mins = "".join(f", MIN({q('f_' + f)}) AS {q('f_' + f)}" for f in fields if f in side["compare"])
    return (f"s{tag} AS (SELECT {key_expr(side, d)} AS k{cols} FROM {side['ref']} AS t),\n"
            f"g{tag} AS (SELECT k, {d.count}(*) AS n{mins} FROM s{tag} WHERE k IS NOT NULL AND k <> '' GROUP BY k)")


def shared_fields(*sides: dict) -> list[str]:
    """The compare fields every given side has, in the first side's order."""
    return [f for f in sides[0]["compare"] if all(f in s["compare"] for s in sides[1:])]


def _differs(f: str, a: str, b: str, d: Dialect) -> str:
    c = d.quote("f_" + f)
    return f"({a}.{c} IS NOT NULL AND {b}.{c} IS NOT NULL AND {a}.{c} <> {b}.{c})"


def side_sql(side: dict, d: Dialect = TSQL) -> str:
    """One side alone: its rows, the rows without a key, its distinct keys, the keys held by more than one row and
    those rows."""
    n = d.count
    return (f"WITH {_ctes(side, 'a', [], d)}\n"
            f"SELECT (SELECT {n}(*) FROM sa) AS rows_total, "
            f"(SELECT {n}(*) FROM sa WHERE k IS NULL OR k = '') AS rows_without_key, "
            f"(SELECT {n}(*) FROM ga) AS keys_total, "
            f"(SELECT {n}(*) FROM ga WHERE n > 1) AS keys_duplicated, "
            f"(SELECT COALESCE(SUM(n), 0) FROM ga WHERE n > 1) AS rows_in_duplicated_keys")


def _pair_from(a: dict, b: dict, fields: list[str], d: Dialect) -> str:
    return (f"WITH {_ctes(a, 'a', fields, d)},\n{_ctes(b, 'b', fields, d)},\n"
            f"u AS (SELECT k FROM ga UNION SELECT k FROM gb)\n")


def pair_sql(a: dict, b: dict, d: Dialect = TSQL) -> str:
    """Two sides: every distinct key of either side in exactly one bucket, and the conflicts per compare field."""
    fields = shared_fields(a, b)
    both = "ga.n = 1 AND gb.n = 1"
    per = "".join(f", SUM(CASE WHEN {both} AND {_differs(f, 'ga', 'gb', d)} THEN 1 ELSE 0 END) AS {d.quote('conflict_' + f)}"
                  for f in fields)
    anyf = " OR ".join(_differs(f, "ga", "gb", d) for f in fields) or "1 = 0"
    return (_pair_from(a, b, fields, d)
            + f"SELECT {d.count}(*) AS keys_total, "
              f"SUM(CASE WHEN {both} THEN 1 ELSE 0 END) AS matched, "
              f"SUM(CASE WHEN ga.n = 1 AND gb.k IS NULL THEN 1 ELSE 0 END) AS only_in_a, "
              f"SUM(CASE WHEN gb.n = 1 AND ga.k IS NULL THEN 1 ELSE 0 END) AS only_in_b, "
              f"SUM(CASE WHEN ga.n > 1 OR gb.n > 1 THEN 1 ELSE 0 END) AS duplicated, "
              f"SUM(CASE WHEN {both} AND ({anyf}) THEN 1 ELSE 0 END) AS conflicts{per}\n"
              f"FROM u LEFT JOIN ga ON ga.k = u.k LEFT JOIN gb ON gb.k = u.k")


def examples_sql(a: dict, b: dict, d: Dialect = TSQL, n: int = EXAMPLES) -> str:
    """The first `n` keys (in key order) of each bucket of a pair; `matched` here is the matched keys without a conflict."""
    fields = shared_fields(a, b)
    anyf = " OR ".join(_differs(f, "ga", "gb", d) for f in fields) or "1 = 0"
    return (_pair_from(a, b, fields, d)
            + ", x AS (SELECT CASE WHEN ga.n > 1 OR gb.n > 1 THEN 'duplicated' "
              f"WHEN ga.n = 1 AND gb.n = 1 AND ({anyf}) THEN 'conflicts' "
              "WHEN ga.n = 1 AND gb.n = 1 THEN 'matched' WHEN gb.k IS NULL THEN 'only_in_a' ELSE 'only_in_b' END AS bucket, "
              "u.k AS k FROM u LEFT JOIN ga ON ga.k = u.k LEFT JOIN gb ON gb.k = u.k)\n"
              "SELECT bucket, k FROM (SELECT bucket, k, ROW_NUMBER() OVER (PARTITION BY bucket ORDER BY k) AS rn FROM x) AS y "
              f"WHERE rn <= {int(n)} ORDER BY bucket, k")


def candidates_sql(a: dict, b: dict, d: Dialect = TSQL, n: int = MAX_CANDIDATES) -> str | None:
    """Keys on one side only whose N1 name equals that of a key on the other side only; None without a `name` field
    on both sides."""
    if "name" not in shared_fields(a, b):
        return None
    f = d.quote("f_name")
    return (_pair_from(a, b, ["name"], d)
            + ", na AS (SELECT ga.k, ga." + f + " AS nm FROM ga WHERE ga.n = 1 AND NOT EXISTS (SELECT 1 FROM gb WHERE gb.k = ga.k)),\n"
              "nb AS (SELECT gb.k, gb." + f + " AS nm FROM gb WHERE gb.n = 1 AND NOT EXISTS (SELECT 1 FROM ga WHERE ga.k = gb.k))\n"
            + d.select("na.k AS key_a, nb.k AS key_b",
                       " FROM na JOIN nb ON na.nm = nb.nm WHERE na.nm IS NOT NULL AND na.nm <> '' ORDER BY na.k, nb.k", n + 1))


def all_sql(sides: list[dict], d: Dialect = TSQL) -> str:
    """Every side together (three sides): each distinct key in exactly one of: in all once, in some (more than one side,
    not all, once each), in one only, duplicated (on more than one row of any side); conflicts are a part of in all."""
    tags = [chr(ord("a") + i) for i in range(len(sides))]
    fields = list(dict.fromkeys(f for s in sides for f in s["compare"]))
    ctes = ",\n".join(_ctes(s, t, fields, d) for s, t in zip(sides, tags))
    union = " UNION ".join(f"SELECT k FROM g{t}" for t in tags)
    joins = " ".join(f"LEFT JOIN g{t} ON g{t}.k = u.k" for t in tags)
    present = " + ".join(f"CASE WHEN g{t}.k IS NULL THEN 0 ELSE 1 END" for t in tags)
    dup = " OR ".join(f"g{t}.n > 1" for t in tags)
    once = " AND ".join(f"g{t}.n = 1" for t in tags)
    diffs = [_differs(f, f"g{x}", f"g{y}", d) for f in fields for i, x in enumerate(tags) for y in tags[i + 1:]
             if f in sides[i]["compare"] and f in sides[tags.index(y)]["compare"]]
    anyf = " OR ".join(diffs) or "1 = 0"
    return (f"WITH {ctes},\nu AS ({union}),\n"
            f"p AS (SELECT u.k, {present} AS present, CASE WHEN {dup} THEN 1 ELSE 0 END AS dup, "
            f"CASE WHEN {once} THEN 1 ELSE 0 END AS everywhere, CASE WHEN ({once}) AND ({anyf}) THEN 1 ELSE 0 END AS differs "
            f"FROM u {joins})\n"
            f"SELECT {d.count}(*) AS keys_total, SUM(everywhere) AS in_all, "
            f"SUM(CASE WHEN dup = 0 AND present > 1 AND everywhere = 0 THEN 1 ELSE 0 END) AS in_some, "
            f"SUM(CASE WHEN dup = 0 AND present = 1 THEN 1 ELSE 0 END) AS in_one_only, SUM(dup) AS duplicated, "
            f"SUM(differs) AS conflicts FROM p")


# ------------------------------------------------------------------------------------------------ the sides
def _cols(raw, what: str) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw or not all(isinstance(c, str) and c.strip() for c in raw):
        raise MatchInputError("bad_input", f"{what}: one column name or a list of them",
                              'Example: {"source": "crm_lh", "schema": "crm", "table": "accounts", "key": "org_no"}.')
    return [c.strip() for c in raw]


def parse_sides(raw, sample: bool = False) -> list[dict]:
    """The sides as given, checked for shape (not yet against the tables): label, workspace, source, schema, table,
    key, rules (as given, or None per column), compare {field: column}."""
    if not isinstance(raw, list) or not MIN_SIDES <= len(raw) <= MAX_SIDES:
        raise MatchInputError("bad_input", f"sides: {MIN_SIDES} or {MAX_SIDES} tables to match, each a source, a table and its key",
                              'Example: [{"source": "crm_lh", "schema": "crm", "table": "accounts", "key": "org_no"}, '
                              '{"source": "erp_lh", "schema": "sap", "table": "KNA1", "key": "STCD1"}].')
    out = []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict) or not str(s.get("table") or "").strip():
            raise MatchInputError("bad_input", f"side {i}: needs a table and its key column(s)",
                                  'Each side is {"source", "schema", "table", "key"}; "compare" and "rules" are optional.')
        if not sample and not str(s.get("source") or "").strip():
            raise MatchInputError("bad_input", f"side {i}: needs a source (a lakehouse, warehouse or SQL database)",
                                  "list_sources shows the sources of a workspace; sample=true matches the synthetic set.")
        key = _cols(s.get("key") or s.get("keys"), f"side {i} key")
        if len(key) > MAX_KEY_COLS:
            raise MatchInputError("bad_input", f"side {i}: at most {MAX_KEY_COLS} key columns", "Name the columns of one key.")
        rules = s.get("rules", s.get("rule"))
        if rules is None:
            rules = [None] * len(key)
        elif isinstance(rules, str):
            rules = [rules] * len(key)
        elif isinstance(rules, dict):
            low = {str(k).lower(): v for k, v in rules.items()}
            rules = [low.get(c.lower()) for c in key]
        if not isinstance(rules, list) or len(rules) != len(key):
            raise MatchInputError("bad_input", f"side {i}: rules must be one rule, one per key column, or {{column: rule}}",
                                  "Rules: " + ", ".join(f"{k} ({v})" for k, v in RULES.items()) + ".")
        rules = [str(r).strip().upper() if r else None for r in rules]
        bad = [r for r in rules if r and r not in RULES]
        if bad:
            raise MatchInputError("bad_input", f"side {i}: unknown rule {bad[0]!r}",
                                  "Rules: " + ", ".join(f"{k} ({v})" for k, v in RULES.items()) + ".")
        compare = s.get("compare") or {}
        if not isinstance(compare, dict) or len(compare) > MAX_COMPARE or not all(
                isinstance(k, str) and _FIELD.match(k) and isinstance(v, str) and v.strip() for k, v in compare.items()):
            raise MatchInputError("bad_input", f"side {i}: compare is {{field: column}}, at most {MAX_COMPARE} fields",
                                  'Example: {"name": "account_name", "country": "country"}; the same field names on each side.')
        schema = str(s.get("schema") or "dbo").strip()
        table = str(s["table"]).strip()
        out.append({"label": str(s.get("label") or f"{schema}.{table}").strip(), "workspace": s.get("workspace"),
                    "source": str(s.get("source") or "").strip(), "schema": schema, "table": table, "key": key,
                    "rules": rules, "compare": {k.lower(): v.strip() for k, v in compare.items()}})
    labels = [s["label"].lower() for s in out]
    if len(set(labels)) != len(labels):
        raise MatchInputError("bad_input", "two sides have the same label", "Give each side its own label, such as CRM, ERP, MDM.")
    return out


def bind(side: dict, table, ref: str) -> dict:
    """The side against the table as read (`table`: a schema.Table): its exact column names, each key column's rule
    (given, or proposed by name, and why), and `ref`, how the SQL names the table."""
    have = {c.name.lower(): c.name for c in table.columns}

    def col(name: str, what: str) -> str:
        if name.lower() not in have:
            raise MatchInputError("column_not_found", f"{side['label']}: no column {name!r} ({what}) in {side['schema']}.{table.name}",
                                  f"Columns of {table.name}: " + ", ".join(c.name for c in table.columns[:40]) + ".")
        return have[name.lower()]
    key = [col(c, "key") for c in side["key"]]
    rules, why = [], []
    for c, r in zip(key, side["rules"]):
        if r:
            rules.append(r)
            why.append("chosen in the call")
        else:
            rule, reason = propose_rule(table.name, c)
            rules.append(rule)
            why.append("proposed: " + reason)
    compare = {f: col(c, f"compare {f}") for f, c in side["compare"].items()}
    return {**side, "table": table.name, "key": key, "rules": rules, "rule_why": why, "compare": compare, "ref": ref}


def align_rules(sides: list[dict]) -> list[dict]:
    """A key part whose rule was proposed N1 on one side takes the rule proposed for the same part on another side
    (N2, N3 or N4, by that column's name), so the same key is compared the same way: `STCD1` beside `org_no`. A rule
    chosen in the call is never changed; two different proposals other than N1 are left as they are (check_rules says so)."""
    width = max(len(s["key"]) for s in sides)
    for i in range(width):
        named = {s["rules"][i] for s in sides if i < len(s["rules"]) and s["rules"][i] != "N1" and s["rule_why"][i].startswith("proposed")}
        if len(named) != 1:
            continue
        rule = named.pop()
        other = next(s for s in sides if i < len(s["rules"]) and s["rules"][i] == rule)
        for s in sides:
            if i < len(s["rules"]) and s["rules"][i] == "N1" and s["rule_why"][i].startswith("proposed"):
                s["rules"][i] = rule
                s["rule_why"][i] = (f"proposed: {rule}, as for {other['label']}'s {other['key'][i]} (the same key, compared "
                                    f"the same way); {s['key'][i]}'s own name names no identifier")
    return sides


def check_rules(sides: list[dict]) -> list[str]:
    """Warnings when the sides normalise the same key position by different rules (allowed, said)."""
    out = []
    for i in range(max(len(s["key"]) for s in sides)):
        used = {s["rules"][i] for s in sides if i < len(s["rules"])}
        if len(used) > 1:
            out.append(f"Key part {i + 1} is normalised by different rules on different sides ({', '.join(sorted(used))}); "
                       "keys only meet when the rules give the same text. Pass rules to use one rule everywhere.")
    if len({len(s["key"]) for s in sides}) > 1:
        out.append("The sides have keys of different lengths; a composite key only meets a key with as many parts.")
    return out


# ------------------------------------------------------------------------------------------------ the counts
def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _personal_keys(side: dict) -> list[dict]:
    from . import privacy
    out = []
    for c in side["key"]:
        f = privacy.classify(side["table"], c)
        if f:
            out.append({"side": side["label"], "column": c, "rule": f["rule"], "what": f["what"]})
    return out


def match(sides: list[dict], execute, d: Dialect = TSQL, show_personal_data: bool = False,
          entity: str = "customer") -> dict:
    """The counts, examples and candidates for bound sides (bind), over `execute`. Read-only: SELECTs only."""
    from . import privacy
    queries: list[dict] = []

    def run(label: str, sql: str) -> list[dict]:
        queries.append({"counts": label, "sql": sql})
        return list(execute(sql))

    flagged = [f for s in sides for f in _personal_keys(s)]
    mask = bool(flagged) and not show_personal_data
    shown = lambda k: privacy.MASK if mask and k is not None else k

    per_side = []
    for s in sides:
        r = run(f"side {s['label']}", side_sql(s, d))[0]
        per_side.append({"side": s["label"], "rows": _int(r.get("rows_total")), "rows_without_key": _int(r.get("rows_without_key")),
                         "keys": _int(r.get("keys_total")), "keys_duplicated": _int(r.get("keys_duplicated")),
                         "rows_in_duplicated_keys": _int(r.get("rows_in_duplicated_keys"))})
    pairs = []
    for i, a in enumerate(sides):
        for b in sides[i + 1:]:
            name = f"{a['label']} + {b['label']}"
            fields = shared_fields(a, b)
            r = run(f"pair {name}", pair_sql(a, b, d))[0]
            counts = {k: _int(r.get(k)) for k in ("keys_total",) + BUCKETS}
            counts["conflicts_by_field"] = {f: _int(r.get("conflict_" + f)) for f in fields}
            ex: dict[str, list] = {k: [] for k in BUCKETS}
            for row in run(f"examples {name}", examples_sql(a, b, d)):
                ex.setdefault(str(row.get("bucket")), []).append(shown(row.get("k")))
            entry = {"a": a["label"], "b": b["label"], "compared": fields, "counts": counts, "examples": ex,
                     "sentence": _pair_sentence(a["label"], b["label"], counts, fields)}
            sql = candidates_sql(a, b, d)
            if sql is None:
                entry["candidates_for_a_person"] = {"not_listed": "no compare field named name on both sides"}
            else:
                got = run(f"candidates {name}", sql)
                entry["candidates_for_a_person"] = {
                    "rule": "the name after N1 is exactly the same, the keys differ; listed for a person, never matched",
                    "count": min(len(got), MAX_CANDIDATES), "more": len(got) > MAX_CANDIDATES,
                    "pairs": [{a["label"]: shown(g.get("key_a")), b["label"]: shown(g.get("key_b"))} for g in got[:MAX_CANDIDATES]]}
            pairs.append(entry)
    together = None
    if len(sides) > 2:
        r = run("all sides", all_sql(sides, d))[0]
        together = {k: _int(r.get(k)) for k in ("keys_total", "in_all", "in_some", "in_one_only", "duplicated", "conflicts")}
    out = {"entity": entity,
           "sides": [{"label": s["label"], "source": s["source"], "schema": s["schema"], "table": s["table"],
                      "key": [{"column": c, "rule": r, "rule_says": RULES[r], "why": w}
                              for c, r, w in zip(s["key"], s["rules"], s["rule_why"])],
                      "compare": [{"field": f, "column": c, "rule": COMPARE_RULE} for f, c in s["compare"].items()]}
                     for s in sides],
           "rules": RULES,
           "counts": {"summary": summary(entity, sides, per_side, pairs, together), "per_side": per_side, "pairs": pairs,
                      **({"all_sides": together} if together else {})},
           "queries": queries,
           "personal_data": {"key_columns": flagged, "masked": mask,
                             "notice": (privacy.notice([{"table": f["side"], **f} for f in flagged], show_personal_data)
                                        if flagged else "No key column looks like personal data by name; example keys are shown.")},
           "warnings": check_rules(sides),
           "never": "nothing is merged, written or fuzzy-matched: keys meet only when their normalised text is equal",
           "next_steps": [{"label": NEXT_STEP,
                           "ask": "For each field (name, country, ...), which system's value should win when they differ?"}]}
    return out


def _n(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _pair_sentence(a: str, b: str, c: dict, fields: list[str]) -> str:
    s = (f"{a} + {b}: {c['matched']} matched, {c['only_in_a']} only in {a}, {c['only_in_b']} only in {b}, "
         f"{c['duplicated']} duplicated within a side")
    if fields:
        s += f"; {c['conflicts']} of the matched differ on {' or '.join(fields)}"
    return s + "."


def summary(entity: str, sides: list[dict], per_side: list[dict], pairs: list[dict], together: dict | None) -> str:
    """The counts in plain words: all sides together when there are three, else the pair."""
    names = [s["label"] for s in sides]
    rules = sorted({r for s in sides for r in s["rules"]})
    head = f"{entity.capitalize()} keys in {', '.join(names[:-1])} and {names[-1]}, normalised by {', '.join(rules)}: "
    nokey = sum(p["rows_without_key"] for p in per_side)
    tail = (f" {_n(nokey, 'row has', 'rows have')} no key." if nokey else "") + " Counted on the rows; nothing merged."
    if together:
        t = together
        conf = f"; {t['conflicts']} of those {t['in_all']} differ on a compared field" if any(s["compare"] for s in sides) else ""
        return (head + f"{t['in_all']} in all {len(sides)} once each, {t['in_some']} in some but not all, "
                       f"{t['in_one_only']} in one only, {t['duplicated']} duplicated within a source (cannot match safely)"
                + conf + "." + tail)
    return head + pairs[0]["sentence"].split(": ", 1)[1] + tail


# ------------------------------------------------------------------------------------------------ the sample
SAMPLE_SIDES = [
    {"label": "CRM", "source": "sample", "schema": "crm", "table": "accounts", "key": "org_no",
     "compare": {"name": "account_name", "country": "country"}},
    {"label": "ERP", "source": "sample", "schema": "erp", "table": "KNA1", "key": "STCD1",
     "compare": {"name": "NAME1", "country": "LAND1"}},
    {"label": "MDM", "source": "sample", "schema": "mdm", "table": "customer", "key": "org_number",
     "compare": {"name": "customer_name", "country": "country_code"}},
]


def sample_db():
    """seed.RECORDS in an in-memory SQLite database, one attached database per schema (crm, erp, mdm), and an execute()
    that reads the engine's T-SQL (dialects.sqlite_sql). Built on every call: nothing is kept between calls."""
    import sqlite3
    from .dialects import sqlite_sql
    from .seed import RECORDS
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for schema, tables in RECORDS.items():
        con.execute(f"ATTACH DATABASE ':memory:' AS [{schema}]")
        for name, (ddl, data) in tables.items():
            con.execute(f"CREATE TABLE [{schema}].[{name}] ({ddl})")
            con.executemany(f"INSERT INTO [{schema}].[{name}] VALUES ({','.join('?' * len(data[0]))})", data)

    def execute(sql: str):
        cur = con.execute(sqlite_sql(sql))
        cols = [c[0] for c in cur.description or []]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    execute.close = con.close
    return execute


def sample_table(schema: str, table: str):
    """A table of seed.RECORDS as read (a schema.Table), or None."""
    from .seed import RECORDS, records_schema
    hit = next((s for s in RECORDS if s.lower() == str(schema).lower()), None)
    if hit is None:
        return None
    s = records_schema(hit)
    return next((t for t in s if t.name.lower() == str(table).lower()), None)
