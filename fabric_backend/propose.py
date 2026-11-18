"""Count before claiming, and let the data propose (round F2, SCOPE-REVIEW section 6, mechanism 4).

A key or link a name rule or a pack gives is a candidate until the rows are counted. With a connection (`execute`) and
`profile=True`, plan() does four things here, all read-only counting statements, none of which returns a row value:

1. Keys counted in the same call. Every key by name (K2, K4, K5) and every pack key is counted (rows, NULLs, distinct):
   its evidence state becomes "counted unique" or "counted, not unique" in this call, not in a later validate_plan.
   The keys that links point at are counted first. A key counted not unique stays in the plan (duplicate rows are a
   data fault to show) and is listed under plan.profile["not_unique"]. One exception: a key by a bare name (`id`,
   `no`, `nr`) or a composite guess (K4, K5) with a NULL or with no more than REFUTED_SHARE distinct values per row
   gives way when K6 finds a key in the same table (`No_` in a line table is the item's number).

2. K6, a key from the rows where the names give none. One aggregate statement per keyless table (rows, and per column
   NULLs and distinct values). A column that is unique and never NULL, in two or more rows, of a type a key can have
   (whole number, text, uniqueidentifier), is a key candidate. Names rank them: a column named like an identifier
   (`…id`, `…no`, `…nr`, `…code`, `…key`) before the others, the first in the table's column order on a tie. The key
   is applied when one column is named like an identifier or when the table has exactly one candidate; otherwise the
   candidates are listed under plan.profile["key_candidates"] and none is applied. When no single column is unique,
   the table's leading two, three and four columns are counted together (one statement each) and the shortest unique
   combination is the key: "the first columns of the table", as ERP tables are laid out. A combination of every
   column of the table is not taken (it says only that no row repeats), nor one that contains a column unique alone.

3. R6, a link from the rows. For a column the name rules left ambiguous, for an unlinked column named like a
   reference, for a table's own single key column that another table's key column has the same name as (a subtype:
   Employee.BusinessEntityID in Person), and then for other unlinked text columns: every non-NULL value (the first
   `sample` distinct values when a sample is set) is looked up in the single-column keys of the same type class, one
   statement per column for up to TARGETS_PER_STATEMENT keys. Names rank the keys the values fit: the same column
   name as the key, then a column that carries the table's whole name (the longer name first). Between keys of one
   name, and between the tables a name rule could not tell apart, the key with the fewest rows is the nearest
   (Employee's ids fit Person and BusinessEntity; Person is the nearest); that is decided over every value, never
   over a sample. A link is applied only with support from the name: the column was ambiguous by name, is named as
   the key or after the table, or is a text column named like a reference that fits exactly one key. A subtype link
   (a key in a key of the same name) needs fewer rows than its target. Whole numbers with no name support are never linked: 1..n fits
   any dense id. Everything else the rows fit goes to plan.proposed with its counts and is never applied.

4. Orphans re-counted once (recount): when a link's values are not all in the key, one more statement counts the
   matches as written (both sides cast to text), after trimming spaces, after folding case and after stripping leading
   zeros, and the answer says "297 of 300 rows with a value match after stripping leading zeros (0 as written)". SAP
   numbers (KUNNR, MATNR) and ERP exports that lose their zeros in a CSV are the common case. A link that holds only
   after such a conversion is proposed with that sentence, never applied: the join would need the same conversion.
   evidence.validate does the same for every relationship it counts with orphans.

The time: the profile stops when PROFILE_SHARE of the call's time budget (budget.py) is used or `max_queries`
statements have run; what was not reached says "not checked (time)" or "not counted", and nothing is applied from it.
Nothing here measures or promises a speed.

A pack table recognised by its key columns (signature): see signature_aliases.
"""
from __future__ import annotations

import os
from functools import lru_cache

from . import budget as _time
from .dialects import Dialect, TSQL
from .dialects import of as dialect_of

KEY_RULE = "K6"
LINK_RULE = "R6"
PROFILE_SHARE = 0.5                 # of the call's seconds; the rest is left for what the tool does with the plan
PROFILE_MAX_QUERIES = 60            # the hosted tools' cap on profile statements per call; KRUSGRAPH_PROFILE_QUERIES overrides, 0 turns it off
TARGETS_PER_STATEMENT = 8
MAX_PREFIX = 4                      # the longest leading-column combination counted as a composite key
MIN_ROWS = 2
REFUTED_SHARE = 0.9                 # a key by name with this share of distinct values or less (or a NULL) gives way to a K6 key
MIN_DISTINCT = 2
MAX_STATEMENTS_PER_COLUMN = 3       # a column with no name support is compared with at most this many groups of keys

_INTEGER = ("bigint", "smallint", "tinyint", "integer", "int", "long", "short", "byte")
_STRING = ("nvarchar", "varchar", "nchar", "char", "string", "sysname")
_NOT_STRING = ("text", "ntext")     # COUNT(DISTINCT …) cannot read them
_DATE = ("date", "datetime", "datetime2", "smalldatetime", "timestamp", "timestamp_ntz")


def max_queries() -> int:
    """The hosted cap on profile statements per call (0: the profile is off)."""
    try:
        v = int(os.environ.get("KRUSGRAPH_PROFILE_QUERIES", "") or PROFILE_MAX_QUERIES)
    except ValueError:
        v = PROFILE_MAX_QUERIES
    return max(0, v)


def type_class(data_type: str) -> str | None:
    """"integer", "string" or "guid" for a type a key can have and two columns can be compared in; None otherwise
    (decimals, floats, dates, bits, binary, long text)."""
    t = (data_type or "").lower().split("(")[0].strip()
    if t in _NOT_STRING:
        return None
    if t == "uniqueidentifier":
        return "guid"
    if t in _INTEGER:
        return "integer"
    if t in _STRING:
        return "string"
    return None


def _is_date(data_type: str) -> bool:
    return (data_type or "").lower().split("(")[0].strip() in _DATE


# ------------------------------------------------------------------ SQL ---------------------------------------------

def stats_sql(schema: str, table, dialect: Dialect = TSQL) -> tuple[str, dict[str, int]]:
    """One aggregate over a table: n, and per column c<i>_nulls and, for a type a key can have, c<i>_distinct."""
    q = dialect.quote
    parts, index = [f"{dialect.count}(*) AS n"], {}
    for i, c in enumerate(table.columns, 1):
        index[c.name] = i
        parts.append(f"SUM(CASE WHEN {q(c.name)} IS NULL THEN 1 ELSE 0 END) AS c{i}_nulls")
        if type_class(c.data_type):
            parts.append(f"COUNT(DISTINCT {q(c.name)}) AS c{i}_distinct")
    return f"SELECT {', '.join(parts)} FROM {dialect.table(schema, table.name)}", index


def inclusion_sql(schema: str, source: str, column: str, targets: list[tuple[str, str]], dialect: Dialect = TSQL,
                  sample: int | None = None, text: bool = False) -> str:
    """How many non-NULL values of source.column are in each of `targets` ([(table, key column)]): with_value,
    distinct_values and m0, m1, … in one statement. Each key is joined through SELECT DISTINCT, so a duplicated key
    cannot repeat a row. `sample`: the first so many distinct values stand for all. `text`: a blank is no value."""
    q, count = dialect.quote, dialect.count
    col = q(column)
    has = f"{col} IS NOT NULL" + (f" AND LTRIM(RTRIM({col})) <> ''" if text else "")
    src = dialect.table(schema, source)
    s = f"({dialect.select(col, f' FROM {src} WHERE {has}', int(sample), distinct=True)})" if sample else src
    joins = "".join(f" LEFT JOIN (SELECT DISTINCT {q(k)} FROM {dialect.table(schema, t)}) AS t{i} ON s.{col} = t{i}.{q(k)}"
                    for i, (t, k) in enumerate(targets))
    ms = "".join(f", {count}(t{i}.{q(k)}) AS m{i}" for i, (_t, k) in enumerate(targets))
    where = "" if sample else " WHERE " + has.replace(col, f"s.{col}")
    return f"SELECT {count}(*) AS with_value, {count}(DISTINCT s.{col}) AS distinct_values{ms} FROM {s} AS s{joins}{where}"


def normalized_inclusion_sql(schema: str, source: str, column: str, targets: list[tuple[str, str]], dialect: Dialect = TSQL) -> str:
    """As inclusion_sql over every row, with both sides cast to text, trimmed, case folded and without leading zeros:
    which key the values fit once the writing is made the same. A blank is no value."""
    q, count = dialect.quote, dialect.count
    form = lambda e: normal_forms(e, dialect)["zeros_stripped"]
    col = q(column)
    joins = "".join(f" LEFT JOIN (SELECT DISTINCT {form(q(k))} AS k FROM {dialect.table(schema, t)}) AS t{i} ON {form('s.' + col)} = t{i}.k"
                    for i, (t, k) in enumerate(targets))
    ms = "".join(f", {count}(t{i}.k) AS m{i}" for i in range(len(targets)))
    return (f"SELECT {count}(*) AS with_value, {count}(DISTINCT s.{col}) AS distinct_values{ms} FROM {dialect.table(schema, source)} AS s{joins} "
            f"WHERE s.{col} IS NOT NULL AND {normal_forms('s.' + col, dialect)['trimmed']} <> ''")


STEPS = ("as_written", "trimmed", "case_folded", "zeros_stripped")
_STEP_WORDS = {"as_written": "as written", "trimmed": "after trimming spaces",
               "case_folded": "after trimming spaces and folding case", "zeros_stripped": "after stripping leading zeros"}
RECOUNT_RULE = ("Orphans re-counted once: both sides cast to text, then spaces trimmed, then case folded, then leading "
                "zeros stripped; counts only, no value is read.")


def _text(expr: str, dialect: Dialect) -> str:
    return f"CAST({expr} AS STRING)" if dialect.name == "databricks" else f"CAST({expr} AS NVARCHAR(4000))"


def _strip_zeros(expr: str, dialect: Dialect) -> str:
    """Leading zeros off a text. T-SQL: PATINDEX finds the first character that is not a zero (works on every SQL
    Server version and on the Fabric SQL endpoint, unlike the two-argument LTRIM); a text of zeros only becomes ''."""
    if dialect.name == "databricks":
        return f"REGEXP_REPLACE({expr}, '^0+', '')"
    return f"CASE WHEN PATINDEX('%[^0]%', {expr}) = 0 THEN '' ELSE SUBSTRING({expr}, PATINDEX('%[^0]%', {expr}), 4000) END"


def normal_forms(expr: str, dialect: Dialect = TSQL) -> dict[str, str]:
    """The four expressions a value is compared under, each built on the one before (STEPS)."""
    a = _text(expr, dialect)
    b = f"LTRIM(RTRIM({a}))"
    c = f"UPPER({b})"
    return {"as_written": a, "trimmed": b, "case_folded": c, "zeros_stripped": _strip_zeros(c, dialect)}


def recount_sql(schema: str, source: str, source_cols: list[str], target: str, target_cols: list[str],
                dialect: Dialect = TSQL, blank_is_none: bool = False, initial: list[str] | None = None) -> str:
    """One statement: the rows of `source` with a value, and how many of them find a row of `target` under each of
    STEPS. Each step joins a SELECT DISTINCT of the target's converted key columns, so no row is counted twice."""
    q, count = dialect.quote, dialect.count
    src, tgt = dialect.table(schema, source), dialect.table(schema, target)
    joins, sums = "", ""
    for n, step in enumerate(STEPS):
        tforms = [normal_forms(q(c), dialect)[step] for c in target_cols]
        sforms = [normal_forms(f"s.{q(c)}", dialect)[step] for c in source_cols]
        sel = ", ".join(f"{e} AS k{j}" for j, e in enumerate(tforms))
        on = " AND ".join(f"{e} = n{n}.k{j}" for j, e in enumerate(sforms))
        joins += f" LEFT JOIN (SELECT DISTINCT {sel} FROM {tgt}) AS n{n} ON {on}"
        sums += f", {count}(n{n}.k0) AS {step}"
    has = " AND ".join(f"s.{q(c)} IS NOT NULL" for c in source_cols)
    if blank_is_none:
        has += "".join(f" AND LTRIM(RTRIM(s.{q(c)})) <> ''" for c in source_cols if c.upper() not in ("MANDT", "RCLNT", "CLIENT"))
    has += "".join(f" AND REPLACE(LTRIM(RTRIM(s.{q(c)})), '0', '') <> ''" for c in (initial or []))   # AP2: an optional SAP field's zeros
    return f"SELECT {count}(*) AS with_value{sums} FROM {src} AS s{joins} WHERE {has}"


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def recount_sentence(with_value: int, match: dict[str, int], what: str = "rows with a value") -> str:
    """"297 of 300 rows with a value match after stripping leading zeros (0 as written)", or that nothing more matches."""
    best = max(match.values()) if match else 0
    first = next((s for s in STEPS if match.get(s, 0) == best), "as_written")
    if first == "as_written":
        return (f"{match.get('as_written', 0)} of {with_value} {what} match as written; trimming spaces, folding case and "
                "stripping leading zeros match no more")
    return f"{best} of {with_value} {what} match {_STEP_WORDS[first]} ({match.get('as_written', 0)} as written)"


def recount(schema: str, source: str, source_cols: list[str], target: str, target_cols: list[str], execute,
            blank_is_none: bool = False, initial: list[str] | None = None) -> dict:
    """The re-count of a link with orphans: {"rows_with_value", "match": {step: rows}, "sentence"}, or
    {"not_counted": reason} when the statement could not run or the call's time is up. Never raises."""
    if _time.expired():
        return {"not_counted": _time.NOT_CHECKED}
    try:
        row = (list(execute(recount_sql(schema, source, source_cols, target, target_cols, dialect_of(execute), blank_is_none, initial))) or [{}])[0]
    except Exception as e:                                          # noqa: BLE001 - the class only: a message can quote a value
        if isinstance(e, _time.TimeUp) or _time.expired():
            return {"not_counted": _time.NOT_CHECKED}
        return {"not_counted": f"not counted: the re-count could not run ({type(e).__name__})"}
    m = _int(row.get("with_value"))
    match = {s: _int(row.get(s)) for s in STEPS}
    best = max(match.values())
    return {"rows_with_value": m, "match": match, "sentence": recount_sentence(m, match),
            "helps": best > match["as_written"], "all_match": bool(m) and best == m}


# ------------------------------------------------------------------ names -------------------------------------------

@lru_cache(maxsize=65536)
def _id_named(column: str, prefix: str) -> bool:
    """A column named like an identifier: customer_id, KundNr, ftgnr, No_, code."""
    from .coverage import _REF_WORDS, looks_like_reference
    from .infer import _strip_prefix, _words
    words = _words(_strip_prefix(column, prefix))
    return bool(words) and (looks_like_reference(column, prefix) or (len(words) == 1 and words[0] in _REF_WORDS))


@lru_cache(maxsize=65536)
def _column_words(column: str, prefix: str) -> tuple[str, frozenset]:
    """(the column's normalised name, its words without the reference suffix); once per column, not once per pair."""
    from .coverage import _REF_WORDS
    from .infer import _norm, _stem, _strip_prefix, _words
    bare = _strip_prefix(column, prefix)
    stem, _suf = _stem(bare)
    return _norm(bare), frozenset(w for w in (stem or _words(bare)) if w not in _REF_WORDS and len(w) > 1)


@lru_cache(maxsize=65536)
def _table_words(target: str) -> tuple[tuple[frozenset, ...], str]:
    """(the singular forms of each word of the table's name, its first word)."""
    from .infer import _content_words, _first_word, _singulars
    return tuple(frozenset(_singulars(w)) for w in _content_words(target)), _first_word(target)


@lru_cache(maxsize=65536)
def _abbreviation(word: str, target: str) -> bool:
    from .infer import _abbreviates
    return _abbreviates(word, target)


def affinity(column: str, prefix: str, target: str, key: str, target_prefix: str) -> float:
    """How much the names say that `column` points at `target`: 2 when the column is named as the target's key (and
    that name is not a bare id/no/code); 1 when the column is named like an identifier and carries every word of the
    target's name (ProductAssemblyID and Product, SalesPersonID and SalesPerson) or abbreviates it; 0 otherwise."""
    from .coverage import _REF_WORDS
    a, mine = _column_words(column, prefix)
    if a == _column_words(key, target_prefix)[0] and a not in _REF_WORDS:
        return 2
    if not mine or not _id_named(column, prefix):
        return 0                                                    # ErrorNumber, EmailPromotion, CreditRating: not references
    theirs, first = _table_words(target)
    if theirs and all(forms & mine for forms in theirs):
        return 1 + min(len(theirs), 9) / 10                         # the column names the table; the longer name wins (SalesPerson over Person)
    if first and any(w[0] == first[0] and _abbreviation(w, target) for w in mine):
        return 1
    return 0


# ------------------------------------------------------------------ the profile -------------------------------------

class Profile:
    """The row profile of one plan() call. `summary` becomes plan.profile."""

    def __init__(self, schema, execute, sample: int | None = None, max_queries: int | None = None,
                 pack_tables: set[str] | None = None):
        self.schema, self.execute = schema, execute
        self.dialect = dialect_of(execute)
        self.sample = int(sample) if sample else None
        self.left = int(max_queries) if max_queries is not None else None
        self.max_queries = self.left
        self.pack_tables = set(pack_tables or ())
        self.queries = 0
        self.failed = 0
        self.key_counts: dict[str, dict] = {}                      # table -> {columns, rows, nulls, distinct, unique}
        self.not_counted: dict[str, str] = {}                      # item -> reason ("time", "budget", "failed")
        self.key_candidates: dict[str, list[dict]] = {}            # keyless table -> candidates not applied
        self.keys_how: dict[str, str] = {}                         # table -> why K6 took that key
        self.stats: dict[str, dict] = {}                           # table -> {"rows": n, "columns": {name: (nulls, distinct|None)}}
        self.links_looked_at = 0

    # -- the two limits ------------------------------------------------------------------------------------------------
    def stop(self) -> str | None:
        """Why no further statement may start: "time", "budget" or None."""
        d = _time.current()
        if d is not None and (d.expired() or d.used() >= PROFILE_SHARE * d.seconds):
            return "time"
        if self.left is not None and self.left <= 0:
            return "budget"
        return None

    def run(self, sql: str) -> dict | None:
        """One counting statement's first row; None when it could not run (the item is then not counted)."""
        if self.left is not None:
            self.left -= 1
        self.queries += 1
        try:
            rows = list(self.execute(sql))
        except Exception:                                           # noqa: BLE001 - the item stays a candidate, the call goes on
            rows = None
        if not rows or not isinstance(rows[0], dict) or not rows[0]:   # no answer is not "an empty table": the item is not counted
            self.failed += 1
            return None
        return rows[0]

    # -- 1. keys counted in the same call ------------------------------------------------------------------------------
    def count_keys(self, keys: dict, rels: list, rules: tuple[str, ...]) -> None:
        """Count the keys whose rule is in `rules`, the ones most links point at first."""
        from . import evidence
        pointed: dict[str, int] = {}
        for r in rels:
            pointed[r.target] = pointed.get(r.target, 0) + 1
        order = sorted((t for t, (_c, rule) in keys.items() if rule in rules and t not in self.key_counts),
                       key=lambda t: -pointed.get(t, 0))
        for t in order:
            why = self.stop()
            if why:
                self.not_counted[f"key:{t}"] = why
                continue
            cols = keys[t][0]
            row = self.run(evidence.key_sql(self.schema.schema, t, cols, self.dialect))
            if row is None:
                self.not_counted[f"key:{t}"] = "failed"
                continue
            self.not_counted.pop(f"key:{t}", None)
            n, nulls, d = (_int(row.get(x)) for x in ("n", "nulls", "distinct_keys"))
            self.key_counts[t] = {"columns": list(cols), "rows": n, "nulls": nulls, "distinct": d,
                                  "unique": bool(n) and not nulls and d == n}

    # -- 2. K6 ---------------------------------------------------------------------------------------------------------
    @staticmethod
    def _weak(table, key: tuple[list[str], str]) -> bool:
        """A key by name that gives way when the rows refute it and offer another: a bare `id`, `no` or `nr` (every table
        of an ERP export has a `No_`; in a line table it is the item's number) and the composite guesses K4 and K5. A key
        named after its table (`customer_id` in customers) stays: duplicates in it are a data fault to show, not to hide."""
        from .infer import _norm, _strip_prefix, _table_prefix
        cols, rule = key
        if rule in ("K4", "K5"):
            return True
        return rule == "K2" and len(cols) == 1 and _norm(_strip_prefix(cols[0], _table_prefix(table))) in ("id", "no", "nr")

    def keys_from_rows(self, keys: dict) -> dict[str, tuple[list[str], str]]:
        """K6 for the tables without a key: {table: (columns, "K6")}."""
        from . import evidence
        from .infer import _table_prefix
        from .infer import _CLIENT
        out: dict[str, tuple[list[str], str]] = {}
        for t in self.schema:
            c0 = self.key_counts.get(t.name)
            refuted = (t.name in keys and self._weak(t, keys[t.name]) and c0 is not None and c0["rows"] >= MIN_ROWS
                       and (c0["nulls"] or c0["distinct"] <= REFUTED_SHARE * c0["rows"]))
            if (t.name in keys and not refuted) or t.name in self.stats:
                continue
            why = self.stop()
            if why:
                self.not_counted[f"table:{t.name}"] = why
                continue
            sql, index = stats_sql(self.schema.schema, t, self.dialect)
            row = self.run(sql)
            if row is None:
                self.not_counted[f"table:{t.name}"] = "failed"
                continue
            self.not_counted.pop(f"table:{t.name}", None)
            if any(f"c{i}_nulls" not in row for i in index.values()):   # not the answer to this statement: not counted
                self.failed += 1
                self.not_counted[f"table:{t.name}"] = "failed"
                continue
            n = _int(row.get("n"))
            cols = {c.name: (_int(row.get(f"c{index[c.name]}_nulls")),
                             _int(row.get(f"c{index[c.name]}_distinct")) if type_class(c.data_type) else None) for c in t.columns}
            self.stats[t.name] = {"rows": n, "columns": cols}
            if n < MIN_ROWS:
                self.key_candidates[t.name] = [{"reason": f"{n} row(s): too few to tell a key from the rows"}]
                continue
            prefix = _table_prefix(t)
            names = t.column_names
            client = names[0] if names and names[0].upper() in _CLIENT + ("CLIENT",) and cols[names[0]][0] == 0 else None
            first = names[1] if client and len(names) > 1 else names[0]
            cands = [c.name for c in t.columns if type_class(c.data_type) and cols[c.name] == (0, n) and c.name != client]
            named = [c for c in cands if _id_named(c, prefix)]
            pick = named[0] if named else (first if first in cands else None)
            was = f"; the key by name ({'+'.join(keys[t.name][0])}, {keys[t.name][1]}) is not unique in the rows and gives way" if refuted else ""
            if pick:
                key = ([client] if client else []) + [pick]            # a client column that leads the table is part of its key
                out[t.name] = (key, KEY_RULE)
                self.key_counts[t.name] = {"columns": key, "rows": n, "nulls": 0, "distinct": n, "unique": True}
                others = [c for c in cands if c != pick]
                self.keys_how[t.name] = (f"{pick} is unique and never NULL in all {n} rows"
                                         + (", and is named like an identifier" if named else ", and is the table's first column")
                                         + (f" after the client column {client}, which is part of the key" if client else "")
                                         + (f"; also unique: {', '.join(others)}" if others else "") + was)
                continue
            if cands and not refuted:                                # listed; the leading columns together are still tried
                self.key_candidates[t.name] = [{"columns": [c], "rows": n,
                                                "reason": "unique and never NULL, but neither named like an identifier nor the "
                                                          "table's first column: whether it is the key is for a person to say"} for c in cands]
            # no single column is taken: the leading columns together
            lead = []
            for c in t.columns:
                if not (type_class(c.data_type) or _is_date(c.data_type)) or cols[c.name][0]:
                    break
                lead.append(c.name)
            found = False
            for size in range(2, min(MAX_PREFIX, len(lead), len(names) - 1) + 1):   # never every column: that says only that no row repeats
                if lead[size - 1] in cands:
                    break                                           # a column that is unique alone makes no combination a key
                if refuted and [x.lower() for x in lead[:size]] == [x.lower() for x in keys[t.name][0]]:
                    continue                                        # counted already: not unique
                if self.stop():
                    self.not_counted[f"table:{t.name}"] = self.stop()
                    break
                r2 = self.run(evidence.key_sql(self.schema.schema, t.name, lead[:size], self.dialect))
                if r2 is None:
                    self.not_counted[f"table:{t.name}"] = "failed"
                    break
                n2, nulls, d = (_int(r2.get(x)) for x in ("n", "nulls", "distinct_keys"))
                if n2 and not nulls and d == n2:
                    out[t.name] = (lead[:size], KEY_RULE)
                    self.key_counts[t.name] = {"columns": lead[:size], "rows": n2, "nulls": 0, "distinct": d, "unique": True}
                    self.keys_how[t.name] = (f"no single column is taken; the first {size} columns together are unique and never "
                                             f"NULL in all {n2} rows" + was)
                    found = True
                    break
            if not found and f"table:{t.name}" not in self.not_counted and not refuted and t.name not in self.key_candidates:
                self.key_candidates[t.name] = [{"reason": f"no column and no combination of the first {min(MAX_PREFIX, max(len(lead), 1))} "
                                                          f"column(s) is unique and never NULL in the {n} rows"}]
        return out

    # -- 3. R6 ---------------------------------------------------------------------------------------------------------
    def links_from_rows(self, keys: dict, rels: list, ambiguous: list[dict], proposed_by_others: list[dict]):
        """R6: (relationships applied, proposals, the ambiguous entries the rows decided)."""
        from .infer import Relationship, _table_prefix
        schema = self.schema
        prefixes = {t.name: _table_prefix(t) for t in schema}
        types = {t.name: {c.name: c.data_type for c in t.columns} for t in schema}
        from .infer import _CLIENT
        clients = {t.name: next((c for c in t.column_names if c.upper() in _CLIENT + ("CLIENT",)), None) for t in schema}
        single: dict[str, str] = {}                                 # table -> the one key column values are compared with
        with_client: dict[str, str] = {}                            # table -> its client column, when the key is client + one column
        for t, (cols, _rule) in keys.items():
            c = self.key_counts.get(t)
            if c is not None and not c["unique"]:
                continue
            rest = [x for x in cols if x != clients.get(t)]
            if len(rest) == 1 and len(cols) - len(rest) <= 1:
                single[t] = rest[0]
                if len(cols) == 2:
                    with_client[t] = clients[t]
        linked = {(r.source, c.lower()) for r in rels for c in r.source_cols}
        taken = {(x["source"], c.lower()) for x in proposed_by_others for c in x.get("source_cols", [])}
        amb = {(a["table"], a["column"].lower()): a for a in ambiguous}

        def targets_for(table: str, column: str, only: list[str] | None = None, same_name: bool = False) -> list[tuple[int, str, str]]:
            cls = type_class(types[table][column])
            out = []
            for b, k in single.items():
                if only is not None and b not in only:
                    continue
                if b == table and k.lower() == column.lower():
                    continue
                if table in self.pack_tables and b in self.pack_tables:
                    continue                                        # between two pack tables the pack decides, not the rows
                if type_class(types[b][k]) != cls:
                    continue
                if b in with_client and not clients.get(table):
                    continue                                        # a key with a client column needs the client on both sides
                a = affinity(column, prefixes[table], b, k, prefixes[b])
                if b == table:
                    a = 0                                           # the table's own name says nothing about a self-reference
                if same_name and a < 2:
                    continue
                out.append((a, b, k))
            out.sort(key=lambda x: -x[0])
            return out

        def targets_any(table: str, column: str) -> list[tuple[str, str]]:
            """Every single-column key a text or whole-number column could be compared with once both are text."""
            return [(b, k) for b, k in single.items()
                    if not (b == table and k.lower() == column.lower()) and type_class(types[b][k]) in ("integer", "string")
                    and not (table in self.pack_tables and b in self.pack_tables) and not (b in with_client and not clients.get(table))]

        # the columns, in the order the names rank them
        work: list[tuple[str, str, str, list[tuple[int, str, str]]]] = []   # (kind, table, column, targets)
        for (table, col), a in amb.items():
            column = next(c for c in schema[table].column_names if c.lower() == col)
            if type_class(types[table][column]):
                ts = targets_for(table, column, only=list(a["candidates"]))
                if ts:
                    work.append(("ambiguous", table, column, ts))
        later: list[tuple[str, str, str, list[tuple[int, str, str]]]] = []
        for t in schema:
            own = [c.lower() for c in keys.get(t.name, ([], ""))[0] if c != clients.get(t.name) or len(keys[t.name][0]) == 1]
            for c in t.column_names:
                low = c.lower()
                if (t.name, low) in linked or (t.name, low) in amb or (t.name, low) in taken:
                    continue
                cls = type_class(types[t.name][c])
                if cls is None or c == clients.get(t.name):
                    continue
                if own == [low]:                                    # the table's own key: only a key of the same name (a subtype)
                    points_here = {r.source for r in rels if r.target == t.name}
                    ts = [x for x in targets_for(t.name, c, same_name=True) if x[1] not in points_here]
                    if ts:
                        work.append(("own key", t.name, c, ts))
                    continue
                ts = targets_for(t.name, c)
                if cls == "integer":
                    ts = [x for x in ts if x[0]]                    # whole numbers: only the keys the name supports
                named = _id_named(c, prefixes[t.name]) and not (len(own) > 1 and low in own and not any(x[0] for x in ts))
                support = any(x[0] for x in ts)
                if cls == "integer" and not support:
                    continue                                        # whole numbers with no name support: never compared
                if not ts:
                    continue
                (work if (named or support) else later).append(("reference" if named else "column", t.name, c, ts))
        work += later
        # a link by name whose column another key is also named as: the rows say which key is the nearest
        by_name = {}
        for r in rels:
            if r.rule in ("R1", "R2", "R4") and len(r.source_cols) == 1 and r.target in single and type_class(types[r.source][r.source_cols[0]]):
                others = [x for x in targets_for(r.source, r.source_cols[0], same_name=True) if x[1] != r.target]
                if others:
                    a = affinity(r.source_cols[0], prefixes[r.source], r.target, single[r.target], prefixes[r.target])
                    work.append(("by name", r.source, r.source_cols[0], [(a, r.target, single[r.target])] + others))
                    by_name[(r.source, r.source_cols[0])] = r

        new_rels, proposals, decided, replaced = [], [], [], set()
        not_reached = 0
        for kind, table, column, ts in work:
            if self.stop():
                not_reached += 1
                continue
            self.links_looked_at += 1
            text = type_class(types[table][column]) == "string"
            results: list[tuple[float, str, str, int, int, int]] = []     # affinity, table, key, with_value, matched, distinct
            groups = [ts[i:i + TARGETS_PER_STATEMENT] for i in range(0, len(ts), TARGETS_PER_STATEMENT)]
            if not any(x[0] for x in ts) and kind != "ambiguous":
                groups = groups[:MAX_STATEMENTS_PER_COLUMN]
            cut = False
            for g in groups:
                if self.stop():
                    cut = True
                    break
                row = self.run(inclusion_sql(schema.schema, table, column, [(b, k) for _a, b, k in g], self.dialect, self.sample, text))
                if row is None:
                    continue
                wv, dv = _int(row.get("with_value")), _int(row.get("distinct_values"))
                results += [(a, b, k, wv, _int(row.get(f"m{i}")), dv) for i, (a, b, k) in enumerate(g)]
            if cut and not results:
                not_reached += 1
                continue
            sampled = bool(self.sample) and any(r[5] >= self.sample for r in results)
            fit = [r for r in results if r[3] and r[4] == r[3] and r[5] >= MIN_DISTINCT]
            if sampled and len(fit) > 1:
                # several keys fit a sample: which is the nearest is decided over every value, never over a sample
                row = None if self.stop() else self.run(inclusion_sql(schema.schema, table, column, [(r[1], r[2]) for r in fit],
                                                                      self.dialect, None, text))
                if row is None:
                    if kind != "by name":
                        not_reached += 1
                    continue
                wv, dv = _int(row.get("with_value")), _int(row.get("distinct_values"))
                results = [(r[0], r[1], r[2], wv, _int(row.get(f"m{i}")), dv) for i, r in enumerate(fit)]
                fit = [r for r in results if r[3] and r[4] == r[3] and r[5] >= MIN_DISTINCT]
                sampled = False
            what = f"of the first {self.sample} distinct values" if sampled else "value(s)"
            best = self._nearest(fit, by_rows=kind in ("ambiguous", "own key", "by name"))
            if not fit and kind == "reference" and results and not self.stop():
                # a column named like a reference that fits no key as written: once more with the writing made the same
                # (text, trimmed, case folded, no leading zeros), also against the keys of the other type class
                entry = self._converted(table, column, targets_any(table, column), clients, with_client)
                if entry:
                    proposals.append(entry)
                    continue
            if kind == "by name":
                old = by_name[(table, column)]
                held = any(r[1] == old.target for r in fit)
                if best is None or best[1] == old.target or (not held and len(fit) != 1):
                    continue                                        # the link by name stands
                a, b, k, wv, _m, dv = best
                note = (f"R6 (by name it pointed at {old.target}), counted in the rows: {wv} of {wv} {what} of {table}.{column} are in {b}.{k}"
                        + (f"; they fit {old.target} too, and {b} has fewer rows: it is the nearest" if held
                           else f"; they are not all in {old.target}"))
                replaced.add(old.key)
                new_rels.append(Relationship(table, [column], b, [k], LINK_RULE, note=note))
                continue
            supported = bool(best) and (kind in ("ambiguous", "own key") or best[0] > 0 or (text and kind == "reference"))
            twin = False
            if supported and kind == "own key":                     # a subtype has fewer rows than what it is a subtype of
                mine, theirs = self.key_counts.get(table, {}).get("rows"), self.key_counts.get(best[1], {}).get("rows")
                twin = mine is None or theirs is None or mine >= theirs
                supported = not twin
            if best and supported:
                a, b, k, wv, _m, dv = best
                also = [r[1] for r in fit if r[1] != b]
                note = (f"R6 ({kind}), counted in the rows: {wv} of {wv} {what} of {table}.{column} are in {b}.{k}"
                        + (" (a sample: validate_plan counts every row)" if sampled else "")
                        + (f"; they also fit {', '.join(also)}: {b} is the nearest ("
                           + ("the names" if a > max(r[0] for r in fit if r[1] != b) else "the key with the fewest rows") + ")" if also else ""))
                if b in with_client:                                # client + number on both sides, as the key is
                    new_rels.append(Relationship(table, [clients[table], column], b, [with_client[b], k], LINK_RULE, note=note))
                else:
                    new_rels.append(Relationship(table, [column], b, [k], LINK_RULE, note=note))
                if kind == "ambiguous":
                    decided.append((table, column.lower()))
                continue
            for a, b, k, wv, m, dv in results:
                on_names = kind == "ambiguous" or (kind != "own key" and (a >= 2 or (a >= 1 and kind == "reference")))
                holds = wv and m == wv and dv >= MIN_DISTINCT
                if not holds and not on_names:
                    continue                                        # the rows do not fit and the names say nothing: no entry
                if holds and kind == "own key" and not twin:
                    continue
                if holds and twin:
                    reason = (f"{table}.{column} and {b}.{k} are both keys, named alike, and every value of the first is in the "
                              "second, which has no more rows: whether one table extends the other is for a person to say")
                elif holds and len(fit) > 1:
                    reason = (f"the rows fit {len(fit)} tables ({', '.join(r[1] for r in fit)}) and neither the names nor the "
                              "number of rows decide; which one is for a person to say")
                elif holds:
                    reason = (f"{wv} of {wv} {what} of {table}.{column} are in {b}.{k}, but the name gives no support: "
                              "confirm it to apply it")
                elif not wv:
                    reason = f"{table}.{column} has no values to compare"
                elif m == wv:
                    reason = f"{table}.{column} has {dv} distinct value: too few to tell"
                else:
                    reason = f"{wv - m} of {wv} {what} of {table}.{column} are not in {b}.{k}"
                    if on_names and not self.stop():
                        self.queries += 1
                        if self.left is not None:
                            self.left -= 1
                        rc = recount(schema.schema, table, [column], b, [k], self.execute, blank_is_none=text)
                        if rc.get("sentence"):
                            reason += "; re-counted over all rows: " + rc["sentence"]
                            if rc.get("all_match") and rc.get("helps"):
                                reason += ": the link holds only with that conversion, so it is proposed, not applied"
                sc, tc = ([clients[table], column], [with_client[b], k]) if b in with_client else ([column], [k])
                entry = {"source": table, "source_cols": sc, "target": b, "target_cols": tc, "rule": LINK_RULE, "kind": kind,
                         "reason": reason, "confirmed": {"source": table, "source_cols": sc, "target": b, "target_cols": tc}}
                proposals.append(entry)
        self.links_not_reached = not_reached
        return new_rels, proposals, decided, replaced

    def _converted(self, table: str, column: str, targets: list[tuple[str, str]], clients: dict, with_client: dict) -> dict | None:
        """The proposal for a reference column whose values fit exactly one key only after a conversion, or None."""
        schema = self.schema.schema
        targets = targets[:TARGETS_PER_STATEMENT * MAX_STATEMENTS_PER_COLUMN]
        fits = []
        for i in range(0, len(targets), TARGETS_PER_STATEMENT):
            if self.stop():
                return None
            g = targets[i:i + TARGETS_PER_STATEMENT]
            row = self.run(normalized_inclusion_sql(schema, table, column, g, self.dialect))
            if row is None:
                continue
            wv, dv = _int(row.get("with_value")), _int(row.get("distinct_values"))
            fits += [(b, k) for j, (b, k) in enumerate(g) if wv and _int(row.get(f"m{j}")) == wv and dv >= MIN_DISTINCT]
        if len(fits) != 1 or self.stop():
            return None
        b, k = fits[0]
        self.queries += 1
        if self.left is not None:
            self.left -= 1
        rc = recount(schema, table, [column], b, [k], self.execute, blank_is_none=True)
        if not rc.get("all_match") or not rc.get("helps"):
            return None
        sc, tc = ([clients[table], column], [with_client[b], k]) if b in with_client else ([column], [k])
        return {"source": table, "source_cols": sc, "target": b, "target_cols": tc, "rule": LINK_RULE, "kind": "conversion",
                "reason": f"{table}.{column} fits no key as written; {rc['sentence']} in {b}.{k}: the link holds only with that "
                          "conversion, so it is proposed, not applied (the join needs the same conversion on both sides)",
                "confirmed": {"source": table, "source_cols": sc, "target": b, "target_cols": tc}}

    def _nearest(self, fit: list[tuple], by_rows: bool = False):
        """The one key the names or the rows single out among those the values fit, or None. The number of rows decides
        only between keys of the column's own name, or between the tables a name rule itself could not tell apart."""
        if not fit:
            return None
        if len(fit) == 1:
            return fit[0]
        top = max(r[0] for r in fit)
        named = [r for r in fit if r[0] == top]
        if len(named) == 1 and top > 0:
            return named[0]
        if not (by_rows or top >= 2):
            return None
        sizes = [(self.key_counts.get(r[1], {}).get("rows"), r) for r in named]
        if any(s is None for s, _ in sizes):
            return None
        sizes.sort(key=lambda x: x[0])
        return sizes[0][1] if sizes[0][0] < sizes[1][0] else None

    # -- what the plan carries -----------------------------------------------------------------------------------------
    def summary(self, keys: dict) -> dict:
        out: dict = {
            "rule": "keys counted in this call; K6 and R6 from the rows where the names give nothing (fabric_backend/propose.py)",
            "queries": self.queries,
            "keys_counted": len(self.key_counts),
            "keys_unique": sum(1 for c in self.key_counts.values() if c["unique"]),
            "key_counts": self.key_counts,
            "tables_profiled": len(self.stats),
            "columns_compared": self.links_looked_at,
        }
        if self.max_queries is not None:
            out["max_queries"] = self.max_queries
        if self.sample:
            out["sample"] = self.sample
        nu = {t: c for t, c in self.key_counts.items() if not c["unique"] and c["rows"]}
        if nu:
            out["not_unique"] = {t: f"{'+'.join(c['columns'])}: {c['rows']} rows, {c['distinct']} distinct, {c['nulls']} NULL" for t, c in nu.items()}
        if self.keys_how:
            out["keys_from_rows"] = self.keys_how
        if self.key_candidates:
            out["key_candidates"] = self.key_candidates
        by: dict[str, list[str]] = {}
        for item, why in self.not_counted.items():
            by.setdefault(why, []).append(item)
        left = getattr(self, "links_not_reached", 0)
        if by or left:
            out["not_checked"] = {**{{"time": _time.NOT_CHECKED, "budget": "not counted: the statements allowed in this call were used up",
                                      "failed": "not counted: the statement could not run"}[w]: sorted(v) for w, v in by.items()},
                                  **({"columns_not_compared": left} if left else {})}
        if self.failed:
            out["failed"] = self.failed
        return out


# ------------------------------------------------------------------ a pack table by its key columns ----------------

SIGNATURE_MIN_COLUMNS = 2           # documented columns of the pack table, beyond its key, that the table must have


def _documented(pt: dict, pack: dict) -> set[str]:
    """The columns a pack documents for one of its tables, beyond the key: numbers, amounts, quantities, currencies,
    units, delta columns and the columns its relationships leave from."""
    out: set[str] = set()
    for f in ("number_columns", "delta", "currency_columns", "unit_columns"):
        out |= set(pt.get(f) or [])
    for a in pt.get("amounts") or []:
        out |= {a.get("column"), a.get("currency")}
    for a in pt.get("quantities") or []:
        out |= {a.get("column"), a.get("unit")}
    for r in pack["relationships"]:
        if r["source"] == pt["name"]:
            out |= set(r["source_cols"])
    return {c for c in out if c}


def signature_aliases(schema, pack_name: str = "sap") -> tuple[dict[str, str], dict[str, str]]:
    """Tables the pack does not know by name but whose columns are a pack table's: ({schema table: pack table},
    {schema table: why not, when several pack tables fit}).

    A table is read as pack table P when, after an optional client column, its first columns are exactly P's key
    columns, it has at least SIGNATURE_MIN_COLUMNS more columns the pack documents for P, and no other pack table with
    the same key columns has as many. The longest key wins (VBELN+POSNR is an item table, not a header). Two tables
    that fit the same pack table, and a pack table already present by name, are left alone. The key is still only a
    candidate: with a connection it is counted in the same call (Profile.count_keys)."""
    from . import sap_pack
    pack = sap_pack.load(pack_name)
    by_name = {sap_pack.table_name(t.name) for t in schema}
    client = {sap_pack._norm(c) for c in sap_pack.CLIENT_COLUMNS}
    found: dict[str, str] = {}
    unresolved: dict[str, str] = {}
    for t in schema:
        if sap_pack.table_name(t.name) in pack["tables"]:
            continue
        cols = [sap_pack._norm(c) for c in t.column_names]
        lead = cols[1:] if cols and cols[0] in client else cols
        have = set(cols)
        fits: list[tuple[int, int, str]] = []
        for name, pt in pack["tables"].items():
            key = [sap_pack._norm(c) for c in pt["key"] if sap_pack._norm(c) not in client]
            if not key or len(lead) < len(key) or set(lead[:len(key)]) != set(key):
                continue
            doc = {sap_pack._norm(c) for c in _documented(pt, pack)} - set(key) - client
            fits.append((len(key), len(doc & have), name))
        if not fits:
            continue
        longest = max(f[0] for f in fits)
        fits = sorted((f for f in fits if f[0] == longest), key=lambda f: -f[1])
        if fits[0][1] < SIGNATURE_MIN_COLUMNS or (len(fits) > 1 and fits[1][1] == fits[0][1]):
            unresolved[t.name] = ("its first columns are the key of " + ", ".join(f[2] for f in fits)
                                  + "; too few of the other documented columns are there to say which")
            continue
        if fits[0][2] in by_name:
            unresolved[t.name] = f"its columns are those of {fits[0][2]}, which is already in the schema by name"
            continue
        found[t.name] = fits[0][2]
    twice = {p for p in found.values() if list(found.values()).count(p) > 1}
    for t in [t for t, p in found.items() if p in twice]:
        unresolved[t] = f"two tables have the columns of {found[t]}"
        del found[t]
    return found, unresolved


def with_aliases(schema, aliases: dict[str, str]):
    """The schema with the aliased tables carrying their pack names, for the pack's own matching (sap_pack.match)."""
    from .schema import Schema, Table
    s = Schema(schema=schema.schema)
    for t in schema:
        name = aliases.get(t.name, t.name)
        s.tables[name] = Table(name, list(t.columns), schema=t.schema, keys=list(getattr(t, "keys", []) or []))
    return s


def unalias_match(m, back: dict[str, str]):
    """A pack match made over with_aliases(), with the schema's own table names again. The pack names stay where they
    are pack names (the values of `tables`, the sentences)."""
    from dataclasses import replace
    b = lambda name: back.get(name, name)

    def entry(d: dict) -> dict:
        return {k: (b(v) if k in ("source", "target", "table") and isinstance(v, str) else v) for k, v in d.items()}
    return replace(
        m, tables={b(t): p for t, p in m.tables.items()}, keys={b(t): k for t, k in m.keys.items()},
        relationships=[entry(r) for r in m.relationships], not_applied=[entry(r) for r in m.not_applied],
        missing_columns=[entry(r) for r in m.missing_columns], client_dropped=[b(t) for t in m.client_dropped],
        unmatched_keyless=[b(t) for t in m.unmatched_keyless], key_rules={b(t): r for t, r in m.key_rules.items()},
        mirror={b(t): e for t, e in m.mirror.items()})
