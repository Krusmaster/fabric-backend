# Semantic views: the plan as YAML for Fabric

Round BL64, 23 November 2026. Status: a draft. Nothing is written to Fabric or OneLake, and the output has not been
published in a Fabric workspace yet.

Microsoft Fabric has semantic views (preview), part of Fabric IQ. In a lakehouse, YAML files under
`Context/Semantic Views/<view>/` define datasets, relationships, metrics and descriptions. Publish compiles them to TMDL
in `SystemContext/` and creates a read-only Direct Lake semantic model with the view folder's name. The format is open
YAML based on Apache Ossie (incubating), with requirements of Fabric's own.

## What the draft gives

`semantic_view_draft` (hosted tool) and `fabric_backend.semantic_view.draft` (library) turn the plan into one file,
`Context/Semantic Views/<name>/<name>_semantic_view.yaml`, the same name Fabric gives its starter file:

- `version: 0.2.0.dev0` and `name`, and one model `description`.
- One dataset per table of the plan: `name` (the table name), `source` (`schema.table`) and a `description` with the
  table's role in the plan's graph and its key with the rule (K0-K5, R0-R5 or SAP pack).
- The relationships of the semantic model draft's active set (`semantic_model.active_set`, the same call). With
  `validate_plan`'s counts (the tool's default, `validate=true`), the counts decide that set, as in BL51. A semantic view
  has no inactive relationships, so the inactive ones are listed in the answer under `not_in_view_inactive`, each with
  its reason. A relationship is written only when its `to` side is a one-column key that `validate_plan` counted
  unique; the others are listed under `to_side_not_checked`. Each relationship carries its rule and its counts (rows
  with a value, matched, orphans) as a YAML comment, since relationships have no `description` property. Counts only,
  never a row value.
- Metrics: the row count of each fact table, `COUNTROWS('<dataset>')` in DAX, as the semantic model draft suggests
  it. Nothing else: sums are left out, because an amount at the level of an order header repeats on its lines and the
  semantic model draft handles those level by level.

The answer also lists:

- `needs_key_column`: relationships that need more than one column on a side, or point at a table keyed on several
  columns (SAP's MANDT+VBELN). They do not fit a semantic view, which relates one column per side. A combined key
  column in silver or gold (one column holding the key's parts, on both tables) makes them fit.
- `not_unique`: relationships whose `to` side `validate_plan` counted as not unique, with the counts.
- `personal_data`: columns named like personal data. A semantic view reads every column of a dataset's table and cannot
  leave one out, so these columns are in the generated model. Krusgraph's relationships, metrics and descriptions do
  not use them unless `show_personal_data=true`. To keep them out, point the dataset at a gold view without them
  (`gold_views_draft` leaves them out) or restrict them with OneLake security.
- `gate`, when the source is not a lakehouse.

## What is left for a later round

- Writing the file to the lakehouse's `Context/Semantic Views/` folder (a create tool with `dry_run=false`).
- Publishing the view. The List and Publish APIs are in beta and do not accept a third-party token, which is what the
  hosted connector holds.
- Reading the silver layer's combined key columns, so the `needs_key_column` relationships can be written, as the
  semantic model draft does when a silver step exists.

Today a person uploads the file (Upload files on the view folder in the lakehouse) and publishes the view there.

## Limits from Microsoft's pages

From [Semantic view YAML syntax reference](https://learn.microsoft.com/fabric/fundamentals/semantic-views-yaml-reference),
[Create a semantic view](https://learn.microsoft.com/fabric/fundamentals/semantic-views-create) and
[Considerations and limitations](https://learn.microsoft.com/fabric/fundamentals/semantic-views-overview#considerations-and-limitations):

- Lakehouses only.
- A published metric needs a DAX expression. Other dialects are kept in the file but not published.
- A relationship has a single column on each side, its `to` column must hold unique values, and every relationship is
  active, so only one filter path may join two tables. Datasets are inferred by Publish; relationships are not.
- Only `.yaml` files are published (`.yml` is ignored without a warning), at most 20 files and 16 MB per view.
- The folder name becomes the view name and the semantic model's name; the YAML `name` is required but not used.
- No CI/CD: no Git integration or deployment pipelines, for the view or its model.
- The List and Publish APIs are in beta and do not accept a third-party token.
- Creating an ontology from the generated semantic model is not supported (and neither is XMLA access).
- `fields`, `primary_key`, `unique_keys`, `ai_context` and `custom_extensions` are omitted by Publish with a warning, so
  the draft writes none of them.

Sources read on 23 November 2026 in MicrosoftDocs/fabric-docs at commit `0374a4d`:
`docs/fundamentals/semantic-views-yaml-reference.md` (ms.date 2026-10-20), `semantic-views-create.md` (ms.date
2026-11-18) and `semantic-views-overview.md` (ms.date 2026-11-18). The learn.microsoft.com pages themselves could not
be reached from the session; the repository is their source.

## Verified, and how

Unit tests on the synthetic samples shop, sap_demo, sap_sd and shop_faults, with `validate_plan` counted on SQLite
(`tests/test_bl64_semantic_view.py`): the YAML parses, has the reference's required properties and only properties it
supports, relationships have one column per side onto a counted unique key, composite keys are listed and never
written, with counts the relationships equal the semantic model draft's active set, no row value appears, and no HTTP
call is made. Not run against Fabric: the file has not been uploaded to a lakehouse or published.
