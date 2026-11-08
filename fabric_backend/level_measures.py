"""Suggested measures that sum at the right level (round n133), added to semantic_model_draft's TMDL. Nothing is created.

Three kinds, each with a description that says why and that it is a suggestion (`/// Suggested by Krusgraph: ...`):

1. An amount column at its own level. Every numeric column whose name reads as an amount (amounts.looks_like_amount:
   order_amount, freight, belopp) and that summarizeBy sums gets `SUM('table'[column])` on its own table, also on a
   table that is not a fact (the fact tables' sums come from semantic_model.suggested_measures already). A price per
   unit (list_price, StandardCost, UnitPrice) or a percentage is not an amount to add up and gets none.

2. A header amount that a join repeats over lines (amounts.header_amounts, validate_plan's amount_levels): the header
   already gets `SUM('orders'[order_amount])` on its own table (semantic_model.draft), the amount from the header table,
   one value per order. That sum does not follow a filter on the lines (a product), because the relationship filters
   from orders to order_lines and not back. The measure added here does, and still counts each order once:

       CALCULATE(SUM('orders'[order_amount]), TREATAS(VALUES('order_lines'[order_id]), 'orders'[order_id]))

   the orders that have lines in the current filter, each order's amount once. Written for a single-column link from
   the line to a single-column header key, when the plan's graph calls the line table a fact table (order lines, not a
   product's document list), and not for a price per unit or a percentage (a sum of list prices per product is no
   amount); it does not need the relationship to be active.

3. A header amount in a flat table (round n106): one table where every line carries its order's amount. Names cannot
   tell order_amount from line_amount there, so this kind needs the counts: only an entry of amount_levels'
   `flat_tables` with `pattern` true (one value per header value, header values repeated) gets

       SUMX(VALUES('order_lines'[order_id]), CALCULATE(MAX('order_lines'[order_amount])))

   one value per order (CALCULATE turns the row of VALUES into a filter on that order; MAX of a value that is the same
   on every row of the order is that value), summed over the orders in the current filter. The column itself is then
   not summed by default (summarizeBy: none), and a plain SUM of it is not suggested. A line amount in the same table
   (line_amount, which differs within an order) keeps its SUM. Without counts (semantic_model_draft without
   validate=true) the flat table gets plain sums only, as before.

Syntax. The TMDL is written the way semantic_model.py already writes measures (`measure 'Name' = <DAX>`, an indented
`formatString` and `lineageTag`, a `///` description line above; quoting by semantic_model.tmdl_name), from the
Microsoft samples semantic_model.py cites. The DAX uses SUM, SUMX and RELATED as the repo already generates them
(semantic_model.py, amounts.py), and VALUES, CALCULATE, MAX and TREATAS in their usual forms `VALUES(<column>)`,
`CALCULATE(<expression>, <filter>)`, `MAX(<column>)` and `TREATAS(<table expression>, <column>)`. These forms were NOT
re-read against the Microsoft DAX reference (learn.microsoft.com/dax: sumx-function-dax, values-function-dax,
calculate-function-dax, max-function-dax, treatas-function-dax) or the TMDL overview
(learn.microsoft.com/analysis-services/tmdl/tmdl-overview) in this round: those pages could not be reached from where
it was written (6 November 2026). What was checked instead, in tests/test_n133_level_measures.py: the generated
documents read with the TMDL reader the repo uses (model_compare.from_tmdl, the same one dax_refs builds on) and every
measure's references resolved by the n126 scanner (dax_refs.Model) with nothing left unread. Neither runs DAX: whether
Power BI evaluates these expressions as described is not tested here.
"""
from __future__ import annotations

from . import amounts as _amounts


def _dax_table(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _dax_col(table: str, column: str) -> str:
    return f"{_dax_table(table)}[{column.replace(']', ']]')}]"


def _fmt(data_type: str) -> str:
    from .semantic_model import number_format          # n151: "#,0" for whole numbers
    return number_format(data_type)


def flat_amounts(validation: dict | None, names: set[str]) -> dict[tuple[str, str], str]:
    """(table, amount column) -> header column, for the flat-table entries amount_levels counted as header amounts."""
    out: dict[tuple[str, str], str] = {}
    for e in ((validation or {}).get("amount_levels") or {}).get("flat_tables") or []:
        if e.get("pattern") is True and e["table"] in names:
            out.setdefault((e["table"], e["amount_column"]), e["header_column"])
    return out


def _not_additive(column: str, sql_type: str) -> bool:
    """A price or cost per unit or a percentage: a number on the row, not an amount to add up (UnitPrice, StandardCost,
    RecommendedRetailPrice, StandardDiscountPercentage)."""
    words = _amounts._words(column)
    return (_amounts.is_price(column, sql_type) or bool(words) and words[-1] in ("percentage", "percent", "pct", "rate", "procent")
            or any(w in ("unit", "standard", "list", "retail", "recommended") for w in words))


def suggest(plan, chosen, measures: list[dict], header_level: dict, consumed: set, ref_cols: set, taken: set[str],
            validation: dict | None, summarize_by, data_type, role_of: dict[str, str]) -> tuple[list[dict], dict[tuple[str, str], str]]:
    """The measures to add to `measures` (which already holds semantic_model's) and the flat-table amounts found.
    `taken`: model names in use (lower case), extended in place. `summarize_by` and `data_type` are semantic_model's,
    passed in so the rule stays in one place. Deterministic: tables and columns in plan order."""
    names = {t.name for t in chosen}
    flat = flat_amounts(validation, names)
    have = {(m["table"], m.get("column")) for m in measures}
    out: list[dict] = []

    def name(base: str, table: str) -> str:
        n = base if base.lower() not in taken else f"{base} ({table})"
        taken.add(n.lower())
        return n

    # 1. amount columns at their own level, on any table
    for t in chosen:
        key = plan.keys.get(t.name, ([], ""))[0]
        for c in t.columns:
            k = (t.name, c.name)
            if k in have or k in header_level or k in consumed or k in flat or c.name not in t.column_names:
                continue
            if not _amounts.looks_like_amount(c.name, c.data_type) or _not_additive(c.name, c.data_type):
                continue
            if summarize_by(c.name, c.data_type, (t.name, c.name.lower()) in ref_cols or c.name in key) != "sum":
                continue
            out.append({"table": t.name, "column": c.name, "name": name(f"Total {c.name}", t.name),
                        "expression": f"SUM({_dax_col(t.name, c.name)})", "format": _fmt(data_type(c.data_type)),
                        "why": f"{t.name}.{c.name} reads as an amount and is summed at its own level, one value per {t.name} row "
                               f"(no relationship of the plan repeats it on the rows of another table)"})

    # 2. header amounts a join repeats: the sum that follows a filter on the lines, once per header
    for f in _amounts.header_amounts(plan):
        h, line = f["header"], f["line"]
        hkey = plan.keys.get(h, ([], ""))[0]
        if h not in names or line not in names or role_of.get(line) != "fact" or len(f["line_columns"]) != 1 or len(hkey) != 1 \
                or [c.lower() for c in f["header_columns"]] != [hkey[0].lower()]:
            continue
        fk = f["line_columns"][0]
        for c in f["amount_columns"]:
            col = next(x for x in plan.schema[h].columns if x.name == c)
            if (h, c) not in header_level or (h, c) in consumed or _not_additive(c, col.data_type):
                continue
            dt = data_type(col.data_type)
            out.append({"table": h, "column": c, "name": name(f"Total {c} by {line}", h),
                        "expression": f"CALCULATE(SUM({_dax_col(h, c)}), TREATAS(VALUES({_dax_col(line, fk)}), {_dax_col(h, hkey[0])}))",
                        "format": _fmt(dt),
                        "why": f"sums {h}.{c} at the level of {h}, once per {h} row that has {line} rows in the current filter: "
                               f"{line} has several rows per {h} row, so a sum over the joined rows would count each {h} once per "
                               f"line, and the plain sum on {h} does not follow a filter on {line} (the relationship filters from "
                               f"{h} to {line}); TREATAS passes the {line}.{fk} values in the filter on to {h}.{hkey[0]}"})

    # 3. header amounts in a flat table, from amount_levels' counts
    for (t, c), hcol in flat.items():
        dt = data_type(next(col.data_type for col in plan.schema[t].columns if col.name == c))
        out.append({"table": t, "column": c, "name": name(f"Total {c} once per {hcol}", t),
                    "expression": f"SUMX(VALUES({_dax_col(t, hcol)}), CALCULATE(MAX({_dax_col(t, c)})))",
                    "format": _fmt(dt),
                    "why": f"{t}.{c} has one value per {hcol} and {hcol} values repeat across {t} rows (counted by validate_plan's "
                           f"amount_levels): it is the {hcol} level's amount copied onto each row, so a sum over {t} rows counts "
                           f"each {hcol} once per row; the measure takes the value once per {hcol} (VALUES, then CALCULATE and MAX) "
                           f"and sums those, and the column is not summed by default (summarizeBy: none)"})
    return out, flat
