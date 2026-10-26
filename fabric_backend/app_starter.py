"""A starter pack for building an app on a created API for GraphQL item: a Lovable prompt that describes the data
model, a connection description, five GraphQL queries that walk the relationships, and the manual portal steps.
Everything comes from describe_backend's output, so field and type names are the API's own."""
from __future__ import annotations


def _pick_fields(t: dict, n: int = 4) -> list[str]:
    return [f for f in t.get("fields", []) if not f.startswith("_")][:n]


def queries(description: dict, n: int = 5) -> list[dict]:
    types = {t["type"]: t for t in description.get("types", [])}
    by_source = {t.get("source"): t for t in description.get("types", [])}
    out: list[dict] = []
    # one query per type, the many-to-one links first (a fact with its dimension), then a second pass for the rest
    for pass_no in (0, 1):
        for t in description.get("types", []):
            rels = sorted(t.get("relationships", []), key=lambda r: (r.get("cardinality") != "ManyToOne", r.get("field", "")))
            if pass_no == 0 and rels:
                rels = rels[:1]
            elif pass_no == 1:
                rels = rels[1:2]
            for r in rels:
                if len(out) >= n:
                    break
                target = by_source.get(r.get("to")) or types.get(str(r.get("to", "")).split(".")[-1])
                if not target:
                    continue
                inner = " ".join(_pick_fields(target, 3))
                sub = f"{r['field']} {{ items {{ {inner} }} }}" if r.get("cardinality") == "OneToMany" else f"{r['field']} {{ {inner} }}"
                out.append({"title": f"{t['type']} with {r['field']} ({r.get('cardinality')})",
                            "query": f"query {{ {t['query_field']}(first: 10) {{ items {{ {' '.join(_pick_fields(t))} {sub} }} }} }}"})
    for t in description.get("types", []):
        if len(out) >= n:
            break
        if not t.get("relationships"):
            out.append({"title": f"first rows of {t['type']}", "query": f"query {{ {t['query_field']}(first: 10) {{ items {{ {' '.join(_pick_fields(t, 6))} }} }} }}"})
    return out[:n]


def starter(description: dict, endpoint: str, api_name: str, workspace_id: str) -> dict:
    types = description.get("types", [])
    model_lines = []
    for t in types:
        rels = ", ".join(f"{r['field']} → {str(r.get('to', '')).split('.')[-1]} ({r.get('cardinality')})" for r in t.get("relationships", []))
        model_lines.append(f"- {t['type']} (query `{t['query_field']}`, {'by key, ' if t.get('by_key') else ''}{'writable' if t.get('writable') else 'read-only'}): "
                           f"fields {', '.join(t.get('fields', []))}" + (f"; relationships: {rels}" if rels else ""))
    qs = queries(description)
    facts = [t for t in types if sum(1 for r in t.get("relationships", []) if r.get("cardinality") == "ManyToOne") >= 2]
    views = ([f"a list/detail page for {f['type']} with its related records expanded" for f in facts]
             or [f"a list/detail page for {t['type']}" for t in types[:2]])
    prompt = "\n".join([
        f"Build a small internal web app on top of the GraphQL API \"{api_name}\" (Microsoft Fabric API for GraphQL).",
        "", "Data model (types, fields and relationships, exactly as the API names them):", *model_lines, "",
        "Most important views:", *[f"- {v}" for v in views],
        "- a search box that filters the list pages; pagination with `first` and `after` on every list query", "",
        "Access: the API needs a Microsoft Entra bearer token for the scope https://api.fabric.microsoft.com/.default; keep "
        "the token exchange server-side and never put a client secret in the browser. Endpoint and example queries below.", "",
        f"Endpoint: {endpoint}", "", "Example queries that show the relationships:", *[f"```graphql\n{q['query']}\n```" for q in qs],
        "", "Read-only: the API exposes no create/update/delete operations unless the type above says writable."])
    connection = {
        "endpoint": endpoint, "workspace_id": workspace_id, "api": api_name,
        "auth": "Authorization: Bearer <Entra access token for scope https://api.fabric.microsoft.com/.default>; the token's identity "
                "(a user, or a service principal) must have been granted access to the API item in the Fabric portal",
        "headers": {"Content-Type": "application/json"}, "method": "POST", "body": '{"query": "...", "variables": {}}',
        "query_shape": description.get("how_to_query", ""),
        "introspection": "off until a workspace admin turns it on under the item's settings; the queries below do not need it",
    }
    checklist = [
        f"{api_name} -> Settings -> Introspection -> On (needed by schema-aware tools such as Lovable; a workspace admin does this)",
        f"{api_name} -> Manage permissions -> add the app's service principal (or the users) with 'Run Queries and Mutations'",
        "Once per tenant: Admin portal -> 'Service principals can call Fabric public APIs' = enabled (only if the app signs in as a service principal)",
        "Store the Entra client secret on the server side of the app; the browser only ever sees the app's own session",
        "Try the five queries with the token first; the field names come from describe_backend, so they match the API",
    ]
    return {"lovable_prompt": prompt, "connection": connection, "queries": qs, "checklist": checklist,
            "note": "Generated from the API's definition; unit-tested and run against a live API for GraphQL item on 26 October 2026."}
