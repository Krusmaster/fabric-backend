---
description: Plan and validate the keys and relationships of a Fabric source with Krusgraph (nothing is created)
argument-hint: "[workspace] [source] [schema]"
---

Plan the source the user names in `$ARGUMENTS` (workspace, source, optional schema; default schema `dbo`) with the
Krusgraph connector, without creating anything:

1. If a part is missing, find it with `list_workspaces` and `list_sources` and ask which one.
2. `plan_backend` with those values. Report the summary line, every relationship with its rule, the keyless tables
   and the ambiguous columns.
3. `validate_plan` with the same values. Report each key's uniqueness and each relationship's orphan count as
   counts at this moment.
4. If the plan has tables in no relationship, run `suggest_relationships` and show the ranked candidates with their
   inclusion share. Ask which to accept; do not add any on your own.
5. End with what a `create_backend` would create and what the user has to decide first.
