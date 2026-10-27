# Lovable on Fabric, end to end: every step, who does it, what blocks

Goal: someone with a Microsoft Fabric lakehouse builds an app in Lovable (or a similar builder) on that data,
with sign-in and real data, without getting stuck. This document walks the whole chain as it is on 26 October
2026, names the owner of each step (Krusgraph, Lovable, the Fabric or Entra admin, the builder), says whether it is
automated or manual, and marks what blocks. Facts come from Microsoft's documentation (MicrosoftDocs/fabric-docs at
commit 6b1f955, read offline on 26 October 2026) and Lovable's documentation (docs.lovable.dev, read through search
excerpts on the same day because the pages could not be fetched from this environment). Anything we could not read
in full is marked **unconfirmed**.

## The chain in one table

| # | Step | Who | Automated? | Blocks? | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Lovable connects to the Krusgraph MCP server (so the builder's chat can plan and create) | builder, Lovable, Krusgraph | manual add, then automatic | **yes, today**: Entra has no dynamic client registration, Lovable's OAuth path cannot register (see `docs/AUTH-DCR.md`) | Fix: `KRUSGRAPH_DCR=1` (this change, unit-tested). Alternatives: do the planning in Claude (works today), or Lovable's bearer-token option with a token minted by the user (unconfirmed) |
| 2 | Find the source and plan: `list_workspaces`, `list_sources`, `plan_backend`, `sample_rows`, `validate_plan`, `suggest_relationships` | Krusgraph | automatic | no | Run live on 25 and 26 October against `demo` / `demo_lh` / `shop` |
| 3 | Create the API for GraphQL item: `create_backend` (`plan_drift` first on an existing one) | Krusgraph | automatic | no | Updating an existing API in place is tested end to end (27 October 2026, `shop_api` with `confirmed`); creating a new one has not run live (Experimental); querying an existing API with `describe_backend` and `query_graphql` is tested end to end; it keeps an existing API's field names and refuses to drop relationships it has (`allow_removals`) |
| 4 | Turn on introspection on the item | Fabric workspace admin | **manual** | blocks only tools that read the schema | "By default, introspection is disabled ... This setting can only be toggled by workspace admins" (api-graphql-introspection-schema-export.md). No REST route for it in microsoft/fabric-rest-api-specs (read 26 October). `app_readiness` probes it and gives the click path |
| 5 | Create the app's own Entra app registration with a client secret | Entra admin or the builder with rights | manual | yes, once | api-graphql-service-principal.md step 1: skip redirect URIs and API permissions, create a client secret, note tenant id, client id, secret |
| 6 | Tenant setting *Service principals can use Fabric APIs* | Fabric tenant admin | manual, once per tenant | yes, for any service-principal app | OneLake catalog -> Govern -> Configurations -> Tenant settings -> Developer settings (same page, step 2) |
| 7 | Grant the app *Run Queries and Mutations* on the API (or Contributor on the workspace) and read access to the data source | Fabric workspace admin | **manual** | yes | Same page, step 3. No REST route to read or set item permissions in the spec (read 26 October); `app_readiness` reports "unknown" with the click path |
| 8 | Keep the secret out of the browser | Lovable or the app's backend | automatic with Lovable's Fabric connector; one paste with the edge function | no | Lovable's connector: "Your credentials are stored securely in Lovable's gateway and are never exposed to the browser or your app's frontend code" (docs.lovable.dev/integrations/microsoft-fabric). Edge function: `app_starter` writes `supabase/functions/fabric-graphql/index.ts`; secrets are Supabase secrets read with `Deno.env.get` |
| 9 | CORS | n/a with a backend | automatic | no | With a gateway or an edge function the browser never calls Fabric. For a browser calling Fabric directly, Microsoft's SPA guide registers a single-page-application platform and says: "If the application encounters an error related to cross-origin requests, add the Mobile and desktop applications platform ... with the same redirect URI" (connect-apps-api-graphql.md). The endpoint's CORS policy itself is not documented: **unconfirmed** |
| 10 | Query the data from the app | Lovable | automatic | no | Through the connector or `supabase.functions.invoke("fabric-graphql", ...)`; field names from `describe_backend` / `app_starter` |
| 11 | User sign-in in the app | Lovable / Supabase Auth | automatic once configured | no, but a design choice | Service principal: every user queries as one identity ("every app and builder on the connection queries Fabric as the same principal", Lovable docs). Per user: Lovable's "Microsoft Fabric app user connector" (**unconfirmed** details) or Supabase Auth with the Azure provider and the delegated scope `https://analysis.windows.net/powerbi/api/GraphQLApi.Execute.All` (the scope Microsoft's SPA guide names); each user then needs Run Queries and Mutations |

What remains manual because Fabric has no API for it: steps 4, 6 and 7. Krusgraph cannot remove them; it can only
say exactly what to click (`app_starter` checklist, `app_readiness` per item).

## Step by step

### 1. Connecting Lovable to Krusgraph (the builder's chat)

Lovable: "Open Connectors, scroll to the bottom of the All view, and select the Custom card labeled MCP"; "Enter the
Server URL where Lovable can reach your MCP server"; "OAuth (default) ... After you click Add & authorize, you're
prompted to authorize"; bearer token or API key "is for servers without OAuth"; "Like all chat connections, they are
personal to you, and they are never part of your published app" (docs.lovable.dev/integrations/custom-mcp, search
excerpt). Whether Lovable's OAuth client registers dynamically or accepts a typed client id is not in the excerpt:
unconfirmed. With Entra as the authorization server there is no registration endpoint, so an automatic registration
fails. `KRUSGRAPH_DCR=1` adds one (`docs/AUTH-DCR.md`); the callback URI Lovable shows must be registered on the
Entra app by the maintainer first.

Until that is deployed and verified, the builder plans and creates in Claude (works today) and switches to Lovable
at step 10, or uses the bearer-token option with a token minted by the user for the Krusgraph app (unconfirmed).

### 2 and 3. Plan and create

In Claude today: "Plan the tables in schema shop of demo_lh in workspace demo", "Check the plan against the data",
"Which columns could still be relationships?", "Create the API shop_api from that plan" (and before a re-run,
"What would change in shop_api?"). The answers of 25 and 26 October are in the README's status section.

### 4. Introspection

Click path (api-graphql-introspection-schema-export.md): the API's **Settings** gear -> **Introspection** page ->
toggle -> **Confirm**. "Enabling introspection exposes schema information to all users with access to the API
endpoint." Needed by builders that read the schema; not needed by an app that sends the queries `app_starter`
wrote. Is Lovable's Fabric connector such a builder? The README has said so since the first live run, but the
connector's page excerpt does not say it: **unconfirmed**; `app_readiness` reports the setting either way.

Can Krusgraph set it through the REST API? No. The API for GraphQL item definition in microsoft/fabric-rest-api-specs
(`graphQLApi/definitions.json`, read 26 October 2026) has no introspection or settings field; `updateDefinition`
carries only `graphql-definition.json`. So there is no flag on `create_backend` for it, and the answer tells the
admin what to click instead.

### 5 to 7. The app's identity in Entra and Fabric

From api-graphql-service-principal.md:

- Step 1, app registration: "Skip redirect URIs and authentication platforms", "Skip API permissions and scopes
  (service principals don't use delegated permissions)", "Do create a client secret"; capture tenant id, client id
  and the secret value.
- Step 2: "A Fabric tenant administrator must enable service principal usage: ... Under Developer settings,
  enable Service principals can use Fabric APIs".
- Step 3, option A: the API item -> **Manage permissions** -> **Add user** -> the app registration -> **Run Queries
  and Mutations** -> **Grant**; "Additionally, ensure the service principal has appropriate read/write permissions
  to the underlying data source". Option B: Contributor on the workspace.
- "Because a service principal requires either a certificate or a client secret, it isn't supported by the
  Microsoft Authentication Library (MSAL) in single-page applications (SPAs)" (api-graphql-service-principal.md,
  via the search excerpt of the same page): hence a backend.

The token the backend asks for: `client_credentials` with scope `https://api.fabric.microsoft.com/.default`
(the page's code samples). Neither of these three steps has a REST route in the spec; they stay manual.

### 8 to 10. The app side

Two ways:

- **Lovable's Microsoft Fabric connector** (docs.lovable.dev/integrations/microsoft-fabric): "puts one GraphQL
  endpoint in front of everything you have wired into a Fabric API for GraphQL item"; "Authentication uses a Microsoft
  Entra service principal"; "Your credentials are stored securely in Lovable's gateway and are never exposed to the
  browser or your app's frontend code"; "every app and builder on the connection queries Fabric as the same
  principal". Which fields it asks for (tenant id, client id, secret, endpoint) is unconfirmed from here; the README
  has said "endpoint, tenant id, client id and secret" since the first run.
- **The edge function from `app_starter`**: `supabase/functions/fabric-graphql/index.ts` gets the token with client
  credentials, caches it until shortly before expiry, refuses mutations, forwards the query to the endpoint, and
  answers with CORS headers for the app's origin. Secrets: `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`,
  `FABRIC_GRAPHQL_ENDPOINT`, set with `supabase secrets set ...` or the Secrets panel; read in the function with
  `Deno.env.get`, never in the frontend (the tests check that the frontend snippet names neither Entra nor Fabric).
  The pages call `supabase.functions.invoke("fabric-graphql", { body: { query, variables } })`.

### 11. User sign-in

- One identity for all users: the service principal (both ways above). Simple; row-level security is then the
  app's job.
- Per user: Supabase Auth with the Azure provider (`signInWithOAuth({ provider: "azure", options: { scopes:
  "https://analysis.windows.net/powerbi/api/GraphQLApi.Execute.All offline_access email" } })`), then
  `session.provider_token` is sent to the edge function in `x-fabric-token` and forwarded. The scope is the one
  connect-apps-api-graphql.md requires for a user ("This exact scope is required for accessing Fabric GraphQL
  APIs"); that Supabase returns a provider token with the Fabric audience for it is **unverified**. The app's Entra
  registration then needs the delegated permission Power BI Service -> GraphQLApi.Execute.All, and each user (or a
  group) needs Run Queries and Mutations. Lovable's "app user connector" is the equivalent inside Lovable:
  unconfirmed details.

## What Krusgraph adds in this change

- `app_readiness` (read-only): for an existing API, the definition's gaps (types without a key, types in no
  relationship, write access), one introspection query to see whether introspection is on, and "unknown" with the
  click path for what the API cannot read (permissions, tenant setting). Unit-tested.
- `app_starter`: the edge function, the frontend helper, the secrets list and command, the per-user alternative,
  a checklist that now starts with the app's own Entra registration and the tenant setting. Unit-tested; the parts
  that existed before ran live on 26 October.
- `KRUSGRAPH_DCR`: the registration facade for agents outside Claude (`docs/AUTH-DCR.md`). Unit-tested, off by
  default.

## Live test script (for the maintainer, against `demo` / `demo_lh` / `shop_api`)

Nothing below has been run yet. Expected answers come from the unit tests and the 25 and 26 October runs.

1. In Claude with the Krusgraph connector: "What does an app still need on shop_api in workspace demo?"
   Expected: `app_readiness` answers with `api` ok (7 types), `introspection` off or on with the probe's detail,
   `permissions` unknown with the Manage-permissions path, `keys` missing (`audit_log`), `relationships` ok if
   `ship_to_id` is in the API (it is since 26 October), `write_access` read-only.
2. "Give me the starter pack for an app on shop_api." Expected: the prompt, five queries, the checklist, and under
   `backend` the edge function with `Deno.env.get("ENTRA_CLIENT_SECRET")` and the endpoint of shop_api.
3. Entra (the app's own registration, not Krusgraph's): new app registration "shop-app", Certificates & secrets ->
   new secret; note tenant id, client id, secret. Fabric admin portal: Developer settings -> Service principals can
   use Fabric APIs = enabled (if not already). Workspace demo: shop_api -> Manage permissions -> Add user ->
   shop-app -> Run Queries and Mutations -> Grant; demo_lh -> Manage permissions -> shop-app -> Read all SQL
   endpoint data (or Contributor on the workspace for the test).
4. Lovable: new project, Cloud enabled. Paste the `lovable_prompt`. When Lovable asks for the four secrets, add them
   (tenant id, client id, secret, the endpoint). Expected: the function deploys; the app's first page lists
   `order_items` with product and customer names; no secret appears in the frontend bundle (search the project for
   `ENTRA_CLIENT_SECRET`: it must occur only in `supabase/functions/fabric-graphql/index.ts`).
5. Alternative check of step 4 with Lovable's own connector: Connectors -> Microsoft Fabric -> the same four values.
   Expected: the same queries work without the edge function. Note which fields the dialog asks for and whether it
   needs introspection on; that settles the two unconfirmed points above.
6. Per-user (optional): Supabase Auth -> Azure provider with shop-app's client id and secret; add the delegated
   permission Power BI Service -> GraphQLApi.Execute.All to shop-app; grant your own user Run Queries and Mutations
   on shop_api; sign in to the app with Microsoft; expected: `session.provider_token` is set and the query through
   `x-fabric-token` answers. If it answers 401, decode the token's `aud`: that settles the unverified scope point.
7. Agent sign-in (`docs/AUTH-DCR.md`, after deploying with `KRUSGRAPH_DCR=1`): Cursor and Lovable's custom MCP
   against `https://krusgraph.com/mcp`.

## Sources

- MicrosoftDocs/fabric-docs @ 6b1f955: `docs/data-engineering/api-graphql-service-principal.md`,
  `api-graphql-introspection-schema-export.md`, `connect-apps-api-graphql.md` (quotes above are from these files).
- microsoft/fabric-rest-api-specs, `graphQLApi/definitions.json` and `swagger.json`: no introspection or
  permission routes (read 26 October 2026).
- docs.lovable.dev/integrations/microsoft-fabric and /integrations/custom-mcp: quotes above come from search
  excerpts of 26 October 2026; the pages themselves could not be fetched from this environment.
- modelcontextprotocol/modelcontextprotocol, `docs/specification/2025-11-25/basic/authorization.mdx`: client
  registration order (pre-registered, CIMD, DCR, user-entered), resource indicators, PKCE.
- Supabase docs (search excerpts, 26 October 2026): `supabase secrets set`, `Deno.env.get`, `signInWithOAuth`
  with `provider: 'azure'` and `scopes`, `session.provider_token`.
