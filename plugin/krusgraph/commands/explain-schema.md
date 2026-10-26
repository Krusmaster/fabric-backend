---
description: "Explain an unknown Fabric source as a graph: table roles, central tables, subject areas, and how two tables connect"
argument-hint: "[workspace] [source] [schema] [table A] [table B]"
---

Explain the source the user names in `$ARGUMENTS` (workspace, source, optional schema, optionally two tables) with
the Krusgraph connector:

1. `analyze_schema`: report each table's role with the reason behind it, the most central tables, the subject
   areas, and any cycles or table pairs with more than one path (where a Power BI model becomes ambiguous).
2. If two tables are named, `join_path` between them: the chain, the rule and certainty per hop, the T-SQL, and the
   safest chain when it differs from the shortest. If no path exists, show the suggested missing relationship and ask
   whether to use it as `confirmed`.
3. If the user asks "what could still be connected", `suggest_relationships` with the evidence per candidate.

Keep it to what the metadata shows; say so when a role or a path rests on a weak rule (R3, R4).
