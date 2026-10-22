# Claude Connectors Directory — submission pack

Publisher: **Kruse Consulting AB**. Portal: https://claude.ai/directory/manage → Submit new → MCP connector.
Placeholders: `{{PRODUCT}}`, `{{DOMAIN}}`, `{{CONTACT}}`.

## Before the portal — the order that works

| # | Step | Who | How |
| --- | --- | --- | --- |
| 1 | Product name + domain registered | Gustav | not "Fabric …" (Microsoft trademark) |
| 2 | Entra tenant for the AB, domain verified in it | Gustav | Entra admin center → Custom domain names |
| 3 | Azure subscription on the AB | Gustav | pay-as-you-go; budget alert at €20/month |
| 4 | Fabric trial in the AB's tenant, workspace `demo`, lakehouse `demo_lh` | Gustav | `fabric_backend.seed.seed(spark, "shop")` in a notebook |
| 5 | Entra app | script | `MCP_PUBLIC_URL=https://{{DOMAIN}}/mcp ./deploy/entra-app.sh` |
| 6 | Hosting + custom domain | script | `MCP_DOMAIN={{DOMAIN}} … ./deploy/containerapp.sh` |
| 7 | Privacy policy and docs live | automatic | the server serves `/privacy` and `/docs`; set `PRODUCT_NAME`, `CONTACT_EMAIL`, `COMPANY_ORGNR` on the container |
| 8 | Admin consent in the demo tenant | Gustav | consent URL printed by step 5 |
| 9 | Test as custom connector in Claude: every tool called once | Gustav | Settings → Connectors → Add custom connector → `https://{{DOMAIN}}/mcp` |
| 10 | Email mcp-review@anthropic.com with the client id → Anthropic-held credentials | Gustav | secret only via the channel they give |
| 11 | Reviewer account: a user in the AB's tenant with access to `demo` only | Gustav | no access to anything else |

## Portal answers (draft)

**1 Connection** — Universal URL: `https://{{DOMAIN}}/mcp`

**3 Listing**
- *Name (≤100):* {{PRODUCT}} for Microsoft Fabric
- *One-liner (≤200):* Turn Microsoft Fabric tables into a GraphQL API and app backend — keys and relationships inferred, with the rule behind every link shown.
- *Description (≤2000):*
  > {{PRODUCT}} reads the tables in a Fabric lakehouse, warehouse or SQL database and works out how they relate:
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
  > github.com/Krusmaster/fabric-backend.
- *Categories:* Data & Analytics; Developer Tools
- *Documentation:* https://{{DOMAIN}}/docs · *Privacy:* https://{{DOMAIN}}/privacy · *Support:* {{CONTACT}}

**4 Use cases** — Needs: a Microsoft Fabric capacity (trial is fine) and an Entra admin's one-time consent. Reads and writes: reads metadata and data; writes only by creating/updating API for GraphQL items (`create_backend`); never deletes.

**5 Company** — Kruse Consulting AB, {{WEBSITE}}, {{CONTACT}}

**6 Authentication** — OAuth, Anthropic-held client credentials (Entra ID has no DCR/CIMD). Authorization server: `https://login.microsoftonline.com/organizations/v2.0`. Claude Code: loopback redirects `http://localhost` and `http://127.0.0.1` registered as public-client redirects (Entra ignores the port).

**7 Data handling** — Underlying API: Microsoft Fabric / Azure SQL, called on the user's behalf with their consent. No health data, no sponsored content.

**8 Test & launch — reviewer instructions**
1. Add the connector; sign in as `{{REVIEWER_UPN}}` / password in the portal field.
2. Ask: *"List the data sources in workspace {{DEMO_WS_ID}}."* → `demo_lh`.
3. *"Plan a backend over demo_lh, schema shop."* → 7 tables, 6 relationships, `audit_log` keyless.
4. *"Create it as shop_api_review."* → endpoint + the two remaining portal steps.
5. *"Using shop_api_review: which customers have orders with a Trail bike?"* → rows via `query_graphql`.

Tool annotations: `list_sources`, `list_tables`, `plan_backend`, `rayfin_connector`, `query_graphql` read-only; `create_backend` write, non-destructive, idempotent.

**9 Compliance** — seven acknowledgments; nothing in this server touches payments, media generation, or collects conversation data.
