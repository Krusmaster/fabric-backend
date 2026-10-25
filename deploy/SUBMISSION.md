# Claude Connectors Directory — submission pack (Krusgraph)

Publisher: **Kruse Consulting AB**. Portal: https://claude.ai/directory/manage → Submit new → MCP connector.

PRODUCT = **Krusgraph** · DOMAIN = **krusgraph.com** · CONTACT = **hello@krusgraph.com** · MCP URL = `https://krusgraph.com/mcp`

Open fields are marked `TODO(Gustav)`. Nothing in this file claims a listing, an approval or a partnership: the
connector is submitted, not accepted, until Anthropic says so.

## Before the portal — the order that works

| # | Step | Who | Status |
| --- | --- | --- | --- |
| 1 | Product name + domain registered | Gustav | done: Krusgraph, krusgraph.com (not "Fabric …", a Microsoft trademark) |
| 2 | Entra tenant for the AB, domain verified in it | Gustav | done (`MS=ms61673308` TXT record kept in DNS) |
| 3 | Azure subscription on the AB | Gustav | done; budget alert `TODO(Gustav)` |
| 4 | Fabric trial in the AB's tenant, workspace `demo`, lakehouse `demo_lh` | Gustav | `TODO(Gustav)`: run `fabric_backend.seed.seed(spark, "shop")` in a notebook attached to `demo_lh` |
| 5 | Entra app (multi-tenant, token v2, Application ID URI `https://krusgraph.com/mcp`, scope `user_impersonation`) | Gustav | done; `deploy/krusgraph.sh --check` verifies it and the six delegated permissions |
| 6 | Hosting + custom domain | `deploy/krusgraph.sh` then `--bind-domain` | done; see `deploy/KRUSGRAPH-START.md` |
| 7 | Privacy policy and docs live | automatic | https://krusgraph.com/privacy · https://krusgraph.com/docs (set `PRODUCT_NAME`, `CONTACT_EMAIL`, `COMPANY_ORGNR` in `deploy/krusgraph.json`) |
| 8 | Admin consent in the demo tenant | Gustav | `TODO(Gustav)`: https://login.microsoftonline.com/organizations/adminconsent?client_id=<client id> |
| 9 | Test as custom connector in Claude: every tool called once | Gustav | `TODO(Gustav)`: Settings → Connectors → Add custom connector → `https://krusgraph.com/mcp` |
| 10 | Email mcp-review@anthropic.com with the client id → Anthropic-held credentials | Gustav | `TODO(Gustav)`; secret only via the channel they give |
| 11 | Reviewer account: a user in the AB's tenant with access to `demo` only | Gustav | `TODO(Gustav)` |

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
1. Add the connector; sign in as `TODO(Gustav: reviewer UPN)` / password in the portal field.
2. Ask: *"List the data sources in workspace `TODO(Gustav: demo workspace id)`."* → `demo_lh`.
3. *"Plan a backend over demo_lh, schema shop."* → 7 tables, 6 relationships, `audit_log` keyless, `orders.ship_to_id` left unlinked.
4. *"Create it as shop_api_review."* → endpoint + the two remaining portal steps.
5. *"Using shop_api_review: which customers have orders with a Trail bike?"* → rows via `query_graphql`.

Tool annotations: `list_sources`, `list_tables`, `plan_backend`, `rayfin_connector`, `query_graphql` read-only; `create_backend` write, non-destructive, idempotent.

**9 Compliance** — seven acknowledgments; nothing in this server touches payments, media generation, or collects conversation data. `TODO(Gustav)`: tick them in the portal.
