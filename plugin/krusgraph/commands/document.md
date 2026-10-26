---
description: Data dictionary and dbt sources file for a Fabric source, from the Krusgraph plan (nothing is created)
argument-hint: "[workspace] [source] [schema]"
---

Document the source the user names in `$ARGUMENTS` (workspace, source, optional schema) with the Krusgraph connector:

1. `data_dictionary` with `validate=true`: hand-over Markdown with tables, columns, keys and relationships with their
   rules, roles and subject areas, and the counts from the data. Save it under the `path` the answer suggests, or
   show it when the user has no repository open.
2. `dbt_schema` with the source name the user's dbt project uses (ask if unknown; `arguments_block=false` for dbt
   before 1.10.5). Save it under `models/sources/<name>.yml`, or show it.
3. Point out the keyless tables and the composite keys both files mention: dbt has no built-in test for a
   composite key, and the dictionary's Description column is left for the user to fill in.
