# Changing a data product: the change contract

Status: **the contract, its drafts and its numbers** (round LFD2, 24 November 2026; rounds LFD3 and LFD4, 25 November
2026). `fabric_backend/changes.py` is a module of pure functions with tests (`tests/test_lfd2_contract.py`); LFD3 applies a
list of changes to the silver, gold and semantic model drafts (below, *Applying a list*; `tests/test_lfd3_apply.py`, and
the silver notebook on a local PySpark 4.0.1 in `tests/test_spark_notebooks.py`); LFD4 counts the numbers before and
after each change on the rows (below, *The numbers*; `fabric_backend/change_numbers.py`, `tests/test_lfd4_numbers.py`,
on SQLite over the synthetic samples). No tool uses it yet, and nothing here has run against a Fabric workspace. The
round that follows adds the tools behind the switch `KRUSGRAPH_CHANGES`, which is off by default.

## What it is for

A person who has built a data product writes a sentence in their own MCP client: *remove test customers*, *add region
from addresses*, *add a measure: order value per customer*. The client's model turns the sentence into one small JSON
request. Krusgraph runs no model: it checks the request by fixed rules against the plan and answers one of three things.

| Answer | Meaning |
| --- | --- |
| `ok` | the request is unambiguous and allowed; the answer carries the normalised change and its id |
| `question` | something is ambiguous; the answer says what, with candidates, and chooses nothing |
| `denied` | the request is not allowed; the answer says why |

The contract is the whole surface between the client's model and Krusgraph. A request is data, never text to run: there
is no field for SQL, DAX or any other expression, and a field that would carry one is denied.

## The five change types

Every request has `type`. `contract` (`krusgraph.change/1`) and `base` are optional: `base` names the plan the change
was written against, as `{"plan_id": "plan-…", "schema_fingerprint": "sha256:…"}` (either or both; the same two values
the review file and the pipeline carry).

### `filter_rows`

```json
{"type": "filter_rows", "table": "customers",
 "drop_where": {"column": "is_test", "op": "is_true"},
 "cascade": ["orders", "order_items"]}
```

`drop_where` is a predicate over named columns of `table`: the rows it holds for go. The operations are `equals`,
`is_true` and `is_not_empty`, and nothing else. A predicate is one of

- `{"column": c, "op": "equals", "value": v}`: `v` is one string, number or true/false of the column's kind;
- `{"column": c, "op": "is_true"}`: a true/false column or a whole-number flag;
- `{"column": c, "op": "is_not_empty"}`;
- `{"any": [predicates]}` or `{"all": [predicates]}`, at most 4 levels deep and 20 predicates in all.

`cascade` lists the tables whose rows go with them: rows that point, by the plan's relationships, at a row that goes.
An empty list means that no other table's rows go. A cascade table must point at the filtered table directly or through
another cascade table.

### `add_column`

```json
{"type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"],
 "via": [{"from": {"table": "orders", "columns": ["ship_to_id"]},
          "to": {"table": "addresses", "columns": ["address_id"]}}]}
```

`table` gets the columns, `from` has them. `via` is the join path as a list of links, each a relationship of the plan,
in order from `table` to `from`. Without `via` the plan gives the path when one path that repeats no row is shorter
than every other (the shortest path, as `join_path` takes it); longer ones are named in the answer's notes.

### `add_link`

```json
{"type": "add_link", "from": {"table": "orders", "columns": ["ship_to_id"]},
 "to": {"table": "addresses", "columns": ["address_id"]}}
```

From the rows that point to the key they point at. An accepted link becomes a *confirmed* relationship: the answer's
`resolved.confirmed` is the entry `plan_backend` takes in `confirmed`. Confirmed means stated by a person, not counted;
`validate_plan` counts it against the rows. The plan that includes the link is a new plan with a new id, so the changes
after it carry the new `base`.

### `add_measure`

```json
{"type": "add_measure", "name": "Order value per customer",
 "measure": {"form": "ratio",
             "numerator": {"measure": "Order amount"},
             "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}
```

Four forms: `count` (the rows of `table`), `distinct_count` and `sum` (of `column` in `table`), and `ratio` of a
`numerator` and a `denominator`, each of which is a `count`, a `distinct_count`, a `sum` or an existing measure by name
(`{"measure": "Order amount"}`). A ratio of ratios is not a form.

### `revert`

```json
{"type": "revert", "change": "chg-680f0a7414dc3b1e"}
```

The id of an applied change. The caller hands in the ids applied so far; without them only the id's shape is checked,
and the answer says so.

## The canonical form and the id

`canonical(change)` needs no plan. It checks the request's shape and returns one form for every spelling of the same
request:

- keys sorted; every name trimmed and in Unicode NFC; a measure's name with single spaces;
- lists that are sets sorted and without repeats: the columns of `add_column`, the tables of `cascade`, the predicates
  of an `any` or `all`, the column pairs of a link;
- an `any` inside an `any` (or `all` inside `all`) is one group, and a group of one predicate is that predicate;
- a whole number written as `7.0` is `7`;
- `contract` is always present.

`canonical_json` is that form as JSON with sorted keys and no spaces. The id is `chg-` and the first sixteen
hexadecimal digits of the SHA-256 of that text. No clock, no counter, no random part: the same change gives the same id
on any machine, and the canonical form of a canonical form is itself.

`canonical` does not change the case of a name, because only the plan knows how a table is spelled. `validate` does:
its `ok` answer carries the *normalised* change, which is canonical, has every table and column in the plan's own
spelling, names the current plan in `base`, and has the path of an `add_column` and the cascade of a `filter_rows`
filled in. The id in the answer is the id of the normalised change, so `CUSTOMERS` and `customers` are one change after
validation. Validating a normalised change against the same plan gives it back unchanged.

## Questions

| Kind | When | Candidates |
| --- | --- | --- |
| `filter_column` | `filter_rows` without `drop_where` | the table's flag columns, by type (true/false) or by name (`is_…`, `has_…`, test, demo, deleted, …), each with the predicate to send and, when the caller has counts, how many rows are true |
| `cascade` | `filter_rows` without `cascade`, and other tables point at the table | every table that points at it, directly or through others, with the links and, when the caller has counts, its rows |
| `path` | `add_column` without `via`, and several equally short paths repeat no row | each path as the `via` to send |
| `link` | `add_column` without `via`, and no path repeats no row, but a column could be a link | each as an `add_link` change: what the plan proposed and did not apply, and reference-like columns with the type of the other table's key |
| `link_direction` | `add_link` from a table's key to a column that is no key | the same link the other way |

A question chooses nothing. A candidate is listed because a rule matched its name or type; the answer says which. The
counts in a candidate are the caller's: this module reads no rows (`counts` in `validate`; a later round computes them).

## Denials

| Kind | Reason |
| --- | --- |
| `bad_request`, `unknown_contract`, `unknown_field`, `too_complex` | the request is not shaped as above |
| `unknown_type` | not one of the five types |
| `free_text` | SQL or another expression as text: a string where a predicate, a measure or a link belongs, a field such as `sql`, `where`, `expression` or `dax`, an `op` or `form` that is not one of the listed words, or a value with a line break or one of `;` `--` `/*` `*/` and the backtick |
| `instruction_like` | a name reads like an instruction to a model (below) |
| `stale_base` | `base` names another plan than the current one |
| `unknown_table`, `unknown_column` | the name is not in the plan |
| `personal_data` | the column looks like personal data by the rules of `privacy.py` (P1–P6, by name, catalog tag or knowledge pack). A change neither filters on such a column, copies it nor measures it. `show_personal_data` does not apply here |
| `wrong_type` | `is_true` on a column that is no flag, or a value of another kind than its column |
| `not_dependent`, `cascade_gap` | a cascade table does not point at the filtered table, or only through a table that is not in the cascade |
| `fan_out` | the join path has a step against a relationship's direction (one-to-many), so rows would be repeated: orders → customers → addresses repeats every order once per address of its customer |
| `repeated_amount` | the column is an amount with one value per row of its table, and would stand on every row that points at it (the total that doubles) |
| `unknown_link`, `bad_via`, `no_path` | a link in `via` is not in the plan, the links do not lead from the one table to the other, or nothing connects the two |
| `type_mismatch`, `not_a_key` | a link between columns of different kinds, or to a column that is not the target's key |
| `not_additive` | a `sum` of a column that is no number, or is a key or a reference |
| `unknown_measure` | a ratio names a measure that does not exist |
| `already_exists`, `no_change` | the column, link or measure is already there, or the change changes nothing |
| `unknown_change` | `revert` names a change that was not applied |

The rules that deny are the engine's own, not new ones:

- **Fan-out** is the direction of the plan's relationships, as `join_path` reports it per step (many-to-one or
  one-to-many). A step against the direction repeats rows unless the reference is its table's own key (one-to-one), the
  exception `amounts.py` makes. The reason quotes `amounts.RULE`.
- **Repeated amounts** are `amounts.py`'s header amounts: the columns the semantic model does not sum by default and the
  gold views leave out at line level.
- **Personal data** is `privacy.personal_columns`.
- **A stale base** is compared with `review.plan_id` and `review.schema_fingerprint` over `drift.plan_snapshot`.

### Names that read like instructions

A column name comes from the data owner's source and travels back to the client's model in an answer. A name that
reads like an instruction is therefore denied, is never repeated in the denial, and is never listed as a candidate.
Three fixed rules, by the name only, as `privacy.py` judges:

- `N1`: the name is shaped like text: a control character, a line break, markup (`<`, `>`, `{`, `}`, backtick), more
  than eight words or more than 128 characters.
- `N2`: the name pairs an order (ignore, disregard, forget, bypass, override, reveal, …) with what a model is told
  (instructions, prompt, previous, system, …).
- `N3`: the name addresses the reader (you are, you must, system prompt, as an AI, …).

`delivery_instructions`, `system_id` and `override_price` pass. The rules are a list of words, so they miss what the
list does not hold; they are one layer, and the contract having no free text is the other.

## Applying a list (LFD3)

`changes.apply(changes, plan)` takes the list of changes of a data product, in order (each a change, or an `ok` answer
of `validate`), validates every one against the current plan and answers one of:

| Answer | Meaning |
| --- | --- |
| `ok` | `changes`: one entry per change, in the list's order, with its `id`, the normalised `change`, `resolved` and `notes`; a repeated change counts once and a `revert` takes out the change it names. `confirmed`: the confirmed relationships the list's links stand on |
| `replan` | an `add_link` is not in the plan yet: `confirmed` holds the entries for `plan_backend`. Plan again with them and apply the same list to the new plan, where the link is a relationship and the changes that need it are accepted |
| `denied`, `question` | `validate`'s answer for the entry at `at`; nothing applies |

A change written against an earlier plan of the same tables (another `plan_id`, the same `schema_fingerprint`: the plan
was made again, with a confirmed link, say) is checked again against the current plan by every rule. One written
against other tables is denied as `stale_base`. Same list, same plan: the same answer and the same ids.

The `ok` answer is what the drafts take, each as `changes=`; **an empty list gives every draft byte for byte as without
one** (the golden files do not change):

| Change | Draft | What it does |
| --- | --- | --- |
| `filter_rows` | silver notebook (`silver.spec(..., changes=)`, `silver.apply_changes`, `silver.simulate`) | after the table is read, `exclude_rows` leaves the rows `drop_where` holds for out of silver (a NULL never matches, so such a row stays); each table of the cascade then leaves out, with `follow_excluded`, the rows that point at them over the links `validate` resolved, in the order the notebook writes the tables. The rows go to `krusgraph_quarantine` with the change's id as the rule; the source tables are only read. A table outside the cascade checks its references against the parent's silver rows and the rows the change left out (`with_excluded`), so its rows stay, as the contract says |
| `add_column` | gold views (`gold.spec(..., changes=)`, `gold.apply_changes`) | the view of the table (its fact view, or its dimension view with `dimensions=true`) joins the change's `via` path step by step and selects each column as `<from>_<column>`. A step the view already joins (the same link from the same table) is reused, so a column the view already carries is marked, not repeated; a new step is a `LEFT JOIN` with no rule in the WHERE, so no row is left out, and every step is many-to-one or one-to-one, so none is repeated. A name another column has gets `_via_<the first link's columns>` |
| `add_measure` | semantic model (`semantic_model.draft(..., changes=)`, `draft_on_gold`) | one measure, after the suggested ones, on the first table its form names (or that of the measure it reads). The DAX is built from the form: `COUNTROWS('t')`, `DISTINCTCOUNT('t'[c])`, `SUM('t'[c])`, `[measure]` and `DIVIDE(numerator, denominator)`. A measure the model cannot hold (a table or measure not in it, a name taken) is not added, and the summary says why |
| `add_link` | the plan | a confirmed relationship of the plan (`replan` above), which every draft follows like any other |

The semantic model's summary and README have a section `changes` that says, per change, where it is drafted; a model
on the source tables says that a `filter_rows` does not reach it, and one on gold that it does. On shop_lfd, scenario A
(remove the test customers with their addresses, audit rows, orders and lines; region from addresses over
`orders.ship_to_id`; order value per customer) gives 10 customers, 60 orders and 134 lines in silver, 60 rows in the
gold view of orders with `addresses_region`, and the measure `DIVIDE([Order amount], DISTINCTCOUNT('orders'[customer_id]))`,
which over those rows is 51 296.70 / 10 = 5 129.67 (LFD1's numbers).

## The numbers (LFD4)

`change_numbers.count(applied, plan, execute)` takes `apply`'s `ok` answer and counts, for every change of the list, the
numbers before it (the changes before it in the list applied) and after it (it applied too). Krusgraph runs no model:
every number is the answer of a SELECT statement over the source, and the answer carries that statement next to the
number (`before_sql`, `after_sql`, or `sql` for a measure) and once more as a receipt row (`receipt`, the format of
`receipt.build`; `change_numbers.markdown` writes it as `krusgraph-receipt.md`). `statements(applied, plan)` gives the
statements without running them.

| Change | What is counted |
| --- | --- |
| `filter_rows` | the rows of the filtered table and of each table in the cascade, before and after, with the distinct values of each single-column reference; the sum of every amount that reads those tables (the quantity × price measures and line amounts of `amounts.order_amount_measures`, and the header amounts, each summed once over its own table; a price is not summed), before and after, with the difference and its share. The other amounts, and the tables that point in from outside the cascade, are counted once and said to be untouched |
| `add_column` | the rows of the table's view before and after the join path (`LEFT JOIN`s to rows in the same state): they must be equal. Per new column, the rows without a value and the number of distinct values. **The doubling check**: every amount on the table, or on a line table that points at it, is summed before and after the join; the sums must be equal, and `doubled` says whether one differs |
| `add_measure` | the measure's value in the list's state (a ratio is its numerator and its denominator, each counted, divided as DAX's `DIVIDE`: blank on 0), its value on the source as it is when a filter comes before it, and the plan's other measures, unchanged |
| `add_link` | nothing: it changes no row, and `validate_plan` counts the link |

A filter's "after" is counted on the source as the silver notebook does it: a row goes when `drop_where` holds for it (a
NULL never matches), a row of a cascade table when it points, over the links `validate` resolved, at a row that goes.
With several filters a row stays when none of them leaves it out. `tests/test_lfd4_numbers.py` checks that the counts are
the row counts `silver.simulate` leaves.

`count_path(change, plan, execute, applied=...)` counts an `add_column`'s path as it was written, also one that
`validate` denied as `fan_out`, so the denial can show its numbers.

On the samples (`tests/test_lfd4_numbers.py`; the numbers are LFD1's, `docs/SAMPLE-LFD.md`):

| Scenario | Numbers |
| --- | --- |
| A, shop_lfd: remove the test customers (cascade to addresses, audit rows, orders and lines) | customers 12 → 10, orders 66 → 60, lines 146 → 134, order amount 56 834.70 → 51 296.70 (−5 538.00, 9.7 %) |
| A: region from addresses over `orders.ship_to_id` | the orders view 60 → 60 rows, region missing on 0 of 60, 2 distinct values; order amount over the view 51 296.70 before and after the join |
| A: order value per customer | 5 129.67 (4 736.23 on the source with the test customers); the order amount unchanged |
| A, denied: region over orders → customers → addresses | 60 → 103 rows and 51 296.70 → 93 842.80: the join repeats every order once per address of its customer |
| B, sap_lfd: billing documents without the cancelled one and its cancellation (cascade to the items) | documents 3 → 1, items 4 → 2, billed (`VBRK.NETWR`) 600.00 → 400.00; the orders untouched, 4 rows and 950.00 |

Rules that hold for every answer:

- Only SELECT statements, written through `dialects.py` (T-SQL for Fabric, SQLite for the tests, Databricks); names come
  from the plan, a value only from the change's own `drop_where`.
- Counts and sums, never a row value: a distinct count is a number, not the values. With `KRUSGRAPH_NO_ROW_VALUES=1` a
  sum over fewer than three rows is hidden and only its count is shown.
- One time budget per call (`budget.py`): a statement not reached in time is "not counted (time)", with no number; one
  that fails is "not counted: <reason>". Nothing is guessed.

`verify_build.measure_sql` translates the ratio form too, `DIVIDE(a, b)` with each part one of the other forms or a
`[measure]` in one of them, so `verify_build` counts a measure an `add_measure` drafted.

## What these rounds do not do

- No tool: the tool listing is unchanged.
- Nothing is built in Fabric: the changes reach the drafts, and their numbers are counted on the source. `ok` means
  "allowed and unambiguous against this plan", nothing more.
- No renaming of a copied column, no filter across tables, no measure with a filter: each is a later decision.
- Relationships that are not key joins (`plan.extended`) are not used as paths.
