# Changing a data product: the change contract

Status: **the contract only** (round LFD2, 24 November 2026). `fabric_backend/changes.py` is a module of pure functions
with tests (`tests/test_lfd2_contract.py`). No tool uses it yet, nothing is applied by it, and nothing here has run
against a Fabric workspace. The rounds that follow apply a change to the drafts, count its numbers and add the tools
behind the switch `KRUSGRAPH_CHANGES`, which is off by default.

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

## What this round does not do

- No tool: the tool listing is unchanged.
- Nothing is applied, built or counted. `ok` means "allowed and unambiguous against this plan", nothing more.
- No renaming of a copied column, no filter across tables, no measure with a filter: each is a later decision.
- Relationships that are not key joins (`plan.extended`) are not used as paths.
