"""A starter pack for building an app on a created API for GraphQL item: a Lovable prompt that describes the data
model, a connection description, five GraphQL queries that walk the relationships, the manual portal steps, and the
backend piece an app needs so that no secret reaches the browser: a Supabase edge function that gets an Entra token
with a service principal (client credentials) and forwards GraphQL queries to Fabric, with the secrets kept as
Supabase secrets; plus the per-user alternative (the app's users sign in with Entra and their own token is forwarded).
Everything comes from describe_backend's output, so field and type names are the API's own.

Sources followed (MicrosoftDocs/fabric-docs [6b1f955], read 26 October 2026): api-graphql-service-principal.md (client
credentials, scope https://api.fabric.microsoft.com/.default, "Run Queries and Mutations", tenant setting, and
"a service principal ... isn't supported by MSAL in single-page applications"); connect-apps-api-graphql.md (the
delegated scope https://analysis.windows.net/powerbi/api/GraphQLApi.Execute.All for a signed-in user).
"""
from __future__ import annotations

FUNCTION_NAME = "fabric-graphql"
SECRETS = ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "FABRIC_GRAPHQL_ENDPOINT")
DELEGATED_SCOPE = "https://analysis.windows.net/powerbi/api/GraphQLApi.Execute.All"


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


def edge_function(endpoint: str) -> str:
    """supabase/functions/fabric-graphql/index.ts: client credentials against Entra, the query forwarded to Fabric.
    Secrets come from Deno.env (Supabase secrets); the file itself holds none. Per-user mode: when the browser sends
    the signed-in user's own Fabric token in `x-fabric-token`, that token is forwarded instead."""
    return f'''// supabase/functions/{FUNCTION_NAME}/index.ts
// Forwards GraphQL queries from the app to Microsoft Fabric. The browser never sees an Entra secret:
// ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET and FABRIC_GRAPHQL_ENDPOINT are Supabase secrets.
// Service principal mode (default): one identity for the whole app (client credentials, scope .default).
// Per-user mode: the browser sends the signed-in user's own Fabric token in the x-fabric-token header
// (Supabase Auth with the Azure provider and the scope {DELEGATED_SCOPE}); it is forwarded as is.
const TENANT = Deno.env.get("ENTRA_TENANT_ID") ?? "";
const CLIENT_ID = Deno.env.get("ENTRA_CLIENT_ID") ?? "";
const CLIENT_SECRET = Deno.env.get("ENTRA_CLIENT_SECRET") ?? "";
const ENDPOINT = Deno.env.get("FABRIC_GRAPHQL_ENDPOINT") ?? "{endpoint}";
const SCOPE = "https://api.fabric.microsoft.com/.default";
const ALLOWED_ORIGIN = Deno.env.get("APP_ORIGIN") ?? "*";
const CORS = {{
  "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-fabric-token",
}};

let cached: {{ token: string; expires: number }} | null = null;

async function appToken(): Promise<string> {{
  if (cached && cached.expires > Date.now() + 60_000) return cached.token;
  if (!TENANT || !CLIENT_ID || !CLIENT_SECRET) throw new Error("ENTRA_TENANT_ID, ENTRA_CLIENT_ID and ENTRA_CLIENT_SECRET must be set as secrets");
  const r = await fetch(`https://login.microsoftonline.com/${{TENANT}}/oauth2/v2.0/token`, {{
    method: "POST",
    headers: {{ "Content-Type": "application/x-www-form-urlencoded" }},
    body: new URLSearchParams({{ grant_type: "client_credentials", client_id: CLIENT_ID, client_secret: CLIENT_SECRET, scope: SCOPE }}),
  }});
  if (!r.ok) throw new Error(`token request failed: HTTP ${{r.status}}`);
  const j = await r.json();
  cached = {{ token: j.access_token, expires: Date.now() + Number(j.expires_in) * 1000 }};
  return cached.token;
}}

Deno.serve(async (req) => {{
  if (req.method === "OPTIONS") return new Response("ok", {{ headers: CORS }});
  if (req.method !== "POST") return new Response("POST only", {{ status: 405, headers: CORS }});
  let body: {{ query?: unknown; variables?: unknown }};
  try {{ body = await req.json(); }} catch {{ return new Response(JSON.stringify({{ error: "JSON body expected" }}), {{ status: 400, headers: {{ ...CORS, "Content-Type": "application/json" }} }}); }}
  const query = body.query;
  if (typeof query !== "string" || /^\\s*(mutation|subscription)\\b/i.test(query)) {{
    return new Response(JSON.stringify({{ error: "queries only" }}), {{ status: 400, headers: {{ ...CORS, "Content-Type": "application/json" }} }});
  }}
  const userToken = req.headers.get("x-fabric-token");
  const bearer = userToken && userToken.length > 20 ? userToken : await appToken();
  const r = await fetch(ENDPOINT, {{
    method: "POST",
    headers: {{ Authorization: `Bearer ${{bearer}}`, "Content-Type": "application/json" }},
    body: JSON.stringify({{ query, variables: body.variables ?? {{}} }}),
  }});
  return new Response(await r.text(), {{ status: r.status, headers: {{ ...CORS, "Content-Type": "application/json" }} }});
}});
'''


def frontend_snippet() -> str:
    """What the app's pages call: the edge function, never Fabric or Entra directly."""
    return f'''// src/lib/fabric.ts — the browser talks to the edge function only
import {{ supabase }} from "@/integrations/supabase/client";

export async function fabricQuery<T>(query: string, variables: Record<string, unknown> = {{}}): Promise<T> {{
  const {{ data, error }} = await supabase.functions.invoke("{FUNCTION_NAME}", {{ body: {{ query, variables }} }});
  if (error) throw error;
  if (data?.errors?.length) throw new Error(data.errors[0].message);
  return data.data as T;
}}
'''


def per_user_snippet() -> str:
    """Per-user data: the app's users sign in with their Entra account and their own token is forwarded."""
    return f'''// Per-user alternative: each user signs in with Microsoft and queries as themselves.
// Entra app: delegated permission Power BI Service -> GraphQLApi.Execute.All; each user (or a group) needs
// "Run Queries and Mutations" on the API. Supabase Auth: Azure provider configured with the same app.
await supabase.auth.signInWithOAuth({{
  provider: "azure",
  options: {{ scopes: "{DELEGATED_SCOPE} offline_access email", redirectTo: window.location.origin }},
}});
// after the redirect: session.provider_token is the user's token for Fabric; send it with every query
const {{ data: {{ session }} }} = await supabase.auth.getSession();
await supabase.functions.invoke("{FUNCTION_NAME}", {{
  body: {{ query, variables }},
  headers: {{ "x-fabric-token": session?.provider_token ?? "" }},
}});
'''


def backend(endpoint: str) -> dict:
    return {
        "edge_function": {"path": f"supabase/functions/{FUNCTION_NAME}/index.ts", "source": edge_function(endpoint)},
        "secrets": list(SECRETS),
        "set_secrets": ("supabase secrets set ENTRA_TENANT_ID=<tenant id> ENTRA_CLIENT_ID=<client id> ENTRA_CLIENT_SECRET=<client secret> "
                        f"FABRIC_GRAPHQL_ENDPOINT={endpoint}   # or the Secrets panel of Lovable Cloud / the Supabase dashboard"),
        "frontend": {"path": "src/lib/fabric.ts", "source": frontend_snippet()},
        "per_user_alternative": {
            "when": "the app must show each user only what they may see in Fabric",
            "source": per_user_snippet(),
            "entra": f"delegated permission Power BI Service -> GraphQLApi.Execute.All on the app registration (scope {DELEGATED_SCOPE}); "
                     "Supabase Auth -> Azure provider with the app's client id and secret",
            "unverified": "that Supabase returns a provider_token with the Fabric audience for this scope has not been tried live; "
                          "the scope itself is the one Microsoft's SPA guide names (connect-apps-api-graphql.md).",
        },
        "lovable_connector": ("Lovable's own Microsoft Fabric connector does the service-principal part without this function: the "
                              "credentials stay in Lovable's gateway and every user of the app queries as that one identity "
                              "(docs.lovable.dev/integrations/microsoft-fabric). Use the edge function when the app lives outside "
                              "Lovable's connector model or needs the per-user mode."),
        "rules": ["The browser calls the edge function only; it never holds ENTRA_CLIENT_SECRET and never calls login.microsoftonline.com or the Fabric endpoint with the app's identity.",
                  "The function refuses mutations; the API is read-only unless a type says writable.",
                  "Set APP_ORIGIN to the app's origin before publishing so the function answers only that origin."],
    }


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
    back = backend(endpoint)
    prompt = "\n".join([
        f"Build a small internal web app on top of the GraphQL API \"{api_name}\" (Microsoft Fabric API for GraphQL).",
        "", "Data model (types, fields and relationships, exactly as the API names them):", *model_lines, "",
        "Most important views:", *[f"- {v}" for v in views],
        "- a search box that filters the list pages; pagination with `first` and `after` on every list query", "",
        "Access: the API needs a Microsoft Entra bearer token for the scope https://api.fabric.microsoft.com/.default; keep "
        "the token exchange server-side and never put a client secret in the browser. Endpoint and example queries below.", "",
        f"Endpoint: {endpoint}", "", "Example queries that show the relationships:", *[f"```graphql\n{q['query']}\n```" for q in qs],
        "", "Read-only: the API exposes no create/update/delete operations unless the type above says writable.", "",
        f"Backend: create the Supabase edge function `{FUNCTION_NAME}` with exactly this source and call it from the pages through "
        f"`src/lib/fabric.ts` below. The secrets {', '.join(SECRETS)} are Supabase secrets; ask me to add them, do not put values in code.",
        "", f"```ts\n{back['edge_function']['source']}```", "", f"```ts\n{back['frontend']['source']}```"])
    connection = {
        "endpoint": endpoint, "workspace_id": workspace_id, "api": api_name,
        "auth": "Authorization: Bearer <Entra access token for scope https://api.fabric.microsoft.com/.default>; the token's identity "
                "(a user, or a service principal) must have been granted access to the API item in the Fabric portal",
        "headers": {"Content-Type": "application/json"}, "method": "POST", "body": '{"query": "...", "variables": {}}',
        "query_shape": description.get("how_to_query", ""),
        "introspection": "off until a workspace admin turns it on under the item's settings; the queries below do not need it",
    }
    checklist = [
        f"Entra: register an app for the app itself (not the Krusgraph app): Certificates & secrets -> new client secret; note tenant id, client id, secret",
        "Fabric admin, once per tenant: Admin portal -> Tenant settings -> Developer settings -> 'Service principals can use Fabric APIs' = enabled",
        f"{api_name} -> ... -> Manage permissions -> Add user -> the app registration -> 'Run Queries and Mutations' -> Grant "
        "(a user who signs in to the app needs the same, when the per-user mode is used)",
        f"{api_name} -> Settings (gear) -> Introspection -> on -> Confirm (workspace admin; needed by schema-aware builders, not by the queries above)",
        f"Secrets: {back['set_secrets']}",
        "Deploy the edge function, then try the five queries through it; the field names come from describe_backend, so they match the API",
        "app_readiness lists what is still missing on the API side",
    ]
    return {"lovable_prompt": prompt, "connection": connection, "queries": qs, "checklist": checklist, "backend": back,
            "note": "Generated from the API's definition; unit-tested and run against a live API for GraphQL item on 26 October 2026 "
                    "(the backend part added after that run is unit-tested only)."}
