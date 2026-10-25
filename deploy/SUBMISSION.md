# Claude Connectors Directory — submission pack (Krusgraph)

Publisher: **Kruse Consulting AB**. Portal: https://claude.ai/directory/manage → Submit new → MCP connector.

PRODUCT = **Krusgraph** · DOMAIN = **krusgraph.com** · CONTACT = **hello@krusgraph.com** · MCP URL = `https://krusgraph.com/mcp`

Open fields are marked `TODO(Gustav)`. Nothing in this file claims a listing, an approval or a partnership: the
connector is submitted, not accepted, until Anthropic says so.

## Before the portal — the order that works

| # | Step | Who | Status |
| --- | --- | --- | --- |
| 1 | Product name + domain registered | Gustav | done: Krusgraph, krusgraph.com (not "Fabric …", a Microsoft trademark) |
| 2 | Entra tenant for the AB, domain verified in it | Gustav | done (the Microsoft domain-verification TXT record stays in DNS) |
| 3 | Azure subscription on the AB | Gustav | done; budget alert `TODO(Gustav)` |
| 4 | Fabric capacity (F2) in the AB's tenant, workspace `demo`, lakehouse `demo_lh`, schema `shop` seeded from `fabric_backend.seed` | Gustav | done 25 Oct 2026 |
| 5 | Entra app (multi-tenant, token v2, Application ID URI `https://krusgraph.com/mcp`, scope `user_impersonation`) | Gustav | done; `deploy/krusgraph.sh --check` verifies it and the six delegated permissions |
| 6 | Hosting + custom domain | `deploy/krusgraph.sh` then `--bind-domain` | done; see `deploy/KRUSGRAPH-START.md` |
| 7 | Privacy policy and docs live | automatic | https://krusgraph.com/privacy · https://krusgraph.com/docs (set `PRODUCT_NAME`, `CONTACT_EMAIL`, `COMPANY_ORGNR` in `deploy/krusgraph.json`) |
| 8 | Admin consent in the demo tenant | Gustav | done 25 Oct 2026 (sign-in from Claude works) |
| 9 | Test as custom connector in Claude: every tool called once | Gustav | done 25 Oct 2026, evening; the flow and answers are in section 8 below |
| 10 | Email mcp-review@anthropic.com with the client id → Anthropic-held credentials | Gustav | `TODO(Gustav)`; secret only via the channel they give |
| 11 | Reviewer account: a user in the AB's tenant with access to `demo` only | Gustav | `TODO(Gustav)` |
| 12 | During the review window: `"min_replicas": 1` in `deploy/krusgraph.json` and `--update`, so no reviewer call hits a cold start; the F2 capacity running (not paused) for the whole window | Gustav | `TODO(Gustav)` |

## Registered redirect URIs

Only what is actually registered on the Entra app today:

| Redirect URI | Type | Registered |
| --- | --- | --- |
| `https://claude.ai/api/mcp/auth_callback` | Web | yes |
| `http://localhost` and `http://127.0.0.1` (Claude Code loopback; Entra ignores the port) | Public client / native | **not registered yet** — `TODO(Gustav)` before announcing Claude Code support |
| Partner sign-in on the website (`/partners`) | Web | **not registered yet** — needed before `PARTNER_SIGNIN=1` can lead anywhere |

## Portal answers (draft)

**1 Connection** — Universal URL: `https://krusgraph.com/mcp`

**3 Listing**
- *Name (≤100):* Krusgraph for Microsoft Fabric
- *One-liner (≤200):* Turn Microsoft Fabric tables into an explainable graph and a GraphQL API — keys and relationships inferred, with the rule behind every link shown.
- *Description (≤2000):*
  > Krusgraph reads the tables in a Fabric lakehouse, warehouse or SQL database and works out how they relate:
  > primary keys, foreign keys, header/line pairs. Every inferred link carries the rule that produced it — declared
  > key, column named after the target table, shared composite key — and ambiguous columns are reported instead
  > of guessed. From that one plan it creates a Fabric API for GraphQL item with nested relationships, generates
  > Rayfin (Fabric Apps) connector entities, and runs read-only GraphQL queries so Claude can answer from the data.
  >
  > Typical flow: "list my sources" → "plan a backend over the shop lakehouse" (nothing is deployed) → "create it
  > as shop_api" → "which customers ordered a trail bike in October?". Re-running updates the item in place.
  >
  > You sign in with your own Microsoft work account; every call runs with your own Fabric permissions. The
  > service stores no data and no tokens. Two settings remain manual in the Fabric portal and the connector says
  > so: turning on introspection and granting other apps access to the API. Open source (MIT):
  > github.com/Krusmaster/fabric-backend. Krusgraph is independent and not affiliated with Microsoft.
- *Categories:* Data & Analytics; Developer Tools
- *Documentation:* https://krusgraph.com/docs · *Privacy:* https://krusgraph.com/privacy · *Support:* hello@krusgraph.com

**4 Use cases** — Needs: a Microsoft Fabric capacity (trial is fine) and an Entra admin's one-time consent. Reads and writes: reads metadata and data; writes only by creating/updating API for GraphQL items (`create_backend`); never deletes.

**5 Company** — Kruse Consulting AB, https://krusgraph.com, hello@krusgraph.com, org. nr `TODO(Gustav)` (the same value as `company_orgnr` in `deploy/krusgraph.json`)

**6 Authentication** — OAuth, Anthropic-held client credentials (Entra ID has no DCR/CIMD). Authorization server: `https://login.microsoftonline.com/organizations/v2.0`. Registered redirect: `https://claude.ai/api/mcp/auth_callback` only (see the table above; Claude Code loopback redirects are not registered yet).

**7 Data handling** — Underlying API: Microsoft Fabric / Azure SQL, called on the user's behalf with their consent. Metadata and requested query results pass through the server in memory only; no database, no logs forwarded (see /privacy). No health data, no sponsored content.

**8 Test & launch — reviewer instructions**

This is the flow that was run end to end on 25 October 2026 (Claude → Entra → Fabric, F2 capacity, workspace
`demo`, lakehouse `demo_lh`, schema `shop`, synthetic data). Before the window: `min_replicas: 1` and the capacity
running (row 12 above).

1. Add the connector (`https://krusgraph.com/mcp`); sign in as `TODO(Gustav: reviewer UPN)` with the password given in
   the portal field. The account sees the workspace `demo` only (its id: `TODO(Gustav)`, never written here).
2. *"Which Fabric workspaces can I see?"* → `list_workspaces` → one workspace, `demo`.
3. *"List the data sources in the demo workspace."* → `list_sources` → `demo_lh` (and `shop_api` under GraphQL APIs once step 5 has run).
4. *"Which tables are in demo_lh, schema shop?"* → `list_tables` → 7 tables.
5. *"Plan a backend over demo_lh, schema shop."* → `plan_backend` → 7 tables, 6 with a key, 6 relationships, all rule R1; `audit_log` without a key; `orders.ship_to_id` left unlinked (no rule matches it). Nothing is deployed.
6. *"Create it as shop_api."* → `create_backend` → the endpoint URL and the two portal steps that stay manual. Asking again answers `mode: updated` (the item is updated in place, never duplicated).
7. *"Using shop_api, which customers have orders with a product in the Bikes category?"* → `query_graphql` → rows through three relationship hops (customers → orders → order items → products). The three-hop query in the 25 October run returned 13 rows; the count depends on the question asked.
8. *"Delete all customers through shop_api."* → refused: the tool runs read-only queries only.
9. *"List the data sources in workspace nowhere."* → `kind: not_found`, with a hint pointing at `list_workspaces`.

Expected timing: well under a second per call once warm. If the very first call after a quiet period fails, it is
a cold start; ask again (row 12 avoids this during the window).

Tool annotations: `list_workspaces`, `list_sources`, `ontology_draft`, `list_tables`, `plan_backend`, `rayfin_connector`, `query_graphql` read-only; `create_backend` write, non-destructive, idempotent.

**9 Compliance** — seven acknowledgments; nothing in this server touches payments, media generation, or collects conversation data. `TODO(Gustav)`: tick them in the portal.
