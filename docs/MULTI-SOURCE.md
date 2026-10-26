# A graph over several sources in one workspace: design note

Status: design only, nothing implemented. Today a plan covers one schema of one source item; `lineage` (added with
this note) reads which objects build on that source. This note is about the next step: relationships *between*
lakehouses, warehouses and SQL databases in the same workspace, how they would be derived, labelled and validated.

## Why it comes up

A workspace often holds a bronze lakehouse, a warehouse built from it and a SQL database for an app. The same
customer id appears in all three. A question like "which app tables depend on this lakehouse column" or "join the
warehouse's orders to the lakehouse's customers" crosses item boundaries, and a semantic model may already do so.

## What a cross-source relationship would be

`source_item.schema.table.column -> target_item.schema.table.column`, with the same shape as today's relationships
plus the item on both ends. Rules, in the order they would be tried:

| Rule | Evidence | Certainty (as in `graphs.WEIGHTS`) |
| --- | --- | --- |
| X0 declared | a semantic model in the workspace already relates the two tables across items (its TMDL names both partitions), or a GraphQL API's definition has both items as datasources with a relationship between them | 1.0, like R0 and `confirmed` |
| X1 lineage | the target table is a copy or a view of the source table (`lineage`: a view in the warehouse over a lakehouse table via a shortcut, a mirrored table), so a key in the source is the same key in the target | 0.9 |
| X2 name and key | the target has a single key column whose name matches the source column the way R1 matches inside a source (`<table>_id`, singular forms, suffixes), and the two columns have the same type | 0.6, like R2: the name alone is weaker across items than inside one, because naming conventions differ between a bronze layer and an app database |
| X3 verified | X2 plus an inclusion check: the share of the source column's values that exist in the target key, run as one query when both items share a SQL analytics endpoint host, or as two distinct-value lists compared on the server when they do not | raises X2 to 0.9 when the share is 1.0 with many distinct values |

Weaker name matches (R3, R4 equivalents) would not be used across items: the false-positive rate inside one source
is already the reason they carry 0.5, and across items there is no shared convention to lean on.

## Labelling

Every cross relationship carries the item on both ends, the rule, and for X3 the counts. In `analyze_schema` the
graph gets one node per table with a `source` attribute; roles and centrality run over the union; a subject area that
spans two items is reported as such. In `join_path` a hop across items is marked and its T-SQL uses three-part names
when the items share a SQL endpoint host (`[lakehouse].[schema].[table]`) and is refused with an explanation when
they do not (no cross-host join in T-SQL).

## Validation

- X2 candidates are listed as suggestions first, the way `suggest_relationships` works today, and become X3 only
  after the inclusion check. Nothing is applied without the user's `confirmed`.
- A cross relationship is never written into a GraphQL API that has one datasource; `create_backend` with several
  sources is a separate decision (the API item supports several datasources, each object belongs to one).
- The semantic model draft would keep one active path per table pair over the union; cross edges compete by the
  same certainty.

## What it needs that does not exist today

- A plan with several schemas and items: `Plan` is one schema; the engine's name index would need the item as part
  of the table key. This is the largest change and the reason to decide first whether the use case is real.
- Reading several sources per call: one SQL connection per item (each has its own endpoint host for a lakehouse and
  warehouse in the same workspace they usually share one host, a SQL database does not).
- A cost model: inclusion checks across items multiply the counting queries; a cap like today's `max_items`.

## Recommendation

Do not build the general case now. Two narrow steps give most of the value: (1) `lineage` across the workspace
(done with this change, read-only), (2) X0 from semantic models and APIs that already relate tables across items,
surfaced in `analyze_schema` as "related in model M" without any inference. X2/X3 only if a user asks for a join
across items that neither a model nor an API already has.
