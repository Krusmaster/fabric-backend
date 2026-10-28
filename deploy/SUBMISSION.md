# Claude Connectors Directory — submission pack (Krusgraph)

Publisher: **Kruse Consulting AB**. Portal: https://claude.ai/directory/manage → Submit → **MCP connector** (not a
plugin bundle: Krusgraph is one remote server; a bundle with skills can be linked to it later).

PRODUCT = **Krusgraph** · DOMAIN = **krusgraph.com** · CONTACT = **hello@krusgraph.com** · MCP URL = `https://krusgraph.com/mcp`

Nothing in this file claims a listing, an approval or a partnership: the connector is submitted, not accepted, until
Anthropic says so. No password, secret or workspace id belongs here.

## Before the portal

| # | Step | Status |
| --- | --- | --- |
| 1 | Product name + domain, Entra tenant for the AB with the domain verified, Azure subscription | done |
| 2 | F2 capacity, workspace `demo`, lakehouse `demo_lh`, schema `shop` seeded from `fabric_backend.seed` | done; the capacity runs for the whole review window |
| 3 | Entra app (multi-tenant, token v2, Application ID URI `https://krusgraph.com/mcp`, scope `user_impersonation`), admin consent in the demo tenant | done; `deploy/krusgraph.sh --check` verifies it |
| 4 | Hosting, custom domain, `min_replicas: 1` | done; `--update` after every change the portal should see |
| 5 | Run as a custom connector in Claude against `demo` / `demo_lh` / `shop` | first run 26 Oct 2026 (14 steps, 16 tools, no creating call). The run that counts is 27 Oct 2026: 30 tools read-only, as drafts or as dry runs, then one creating call, `create_backend` updating `shop_api` in place (`fabric_backend/tool_status.py` `LIVE_RUN`, `docs/LIVE-TEST.md`). Not run live: `sap_pack_draft` (Draft only), and the operator-only `create_ontology`, `create_silver_notebook`, `create_gold_views`, `create_drift_monitor`; `compare_semantic_model` only as far as the model lookup |
| 6 | Reviewer account in the AB's tenant: no admin role, Viewer on `demo` only, no MFA prompt | done 26 Oct 2026; see "Reviewer sign-in" |
| 7 | Every tool has `annotations.title`, read-only/destructive hints, descriptions that describe and do not direct; every parameter has a description (n18, n26) | done (the portal's Tools step showed no suggestions for the earlier tool set; `tests/test_submission.py` checks titles and hints for every tool) |
| 8 | Site icon at `/favicon.ico` (the directory shows the server's favicon) | done |

## Reviewer sign-in (Entra free tier)

Security defaults force every account to register MFA, which would stop a reviewer. What works without a paid
licence: security defaults **off**, per-user MFA **on** for the maintainer's own accounts, the registration campaign
**disabled**, self-service password reset **none**, and the reviewer created with a strong password that was already
changed once (so the first sign-in asks nothing). Azure portal and Entra admin sign-in keep Microsoft's mandatory MFA
regardless. After the listing: turn security defaults back on or disable the reviewer account.

## Registered redirect URIs

| Redirect URI | Type | Registered |
| --- | --- | --- |
| `https://claude.ai/api/mcp/auth_callback` | Web | yes |
| `http://localhost`, `http://127.0.0.1` (Claude Code loopback) | Public client / native | not on the Entra app; clients other than Claude sign in at `/mcp/connect` instead (below) |

## Two ways to sign in

- `/mcp` — the URL in the portal. Claude signs in with Microsoft Entra ID using the client credentials Anthropic holds.
- `/mcp/connect` — for VS Code, Cursor, Glama and other clients: Krusgraph's own authorization server with client
  registration and a consent page, then Entra (`docs/CLIENT-REGISTRATION.md`; on at krusgraph.com since 27 October 2026).
  Not part of the directory submission.

## Other catalogs

| Catalog | Entry | Status |
| --- | --- | --- |
| Official MCP Registry | `com.krusgraph/krusgraph` | published; verified 26 October 2026 (`docs/PUBLISHING.md`) |
| Glama | https://glama.ai/mcp/connectors/com.krusgraph/krusgraph | listed (seen 27 October 2026); ownership is confirmed with `/.well-known/glama.json`, served only on krusgraph.com, after the next `--update` |

## Portal answers (as submitted)

**1 Connection** — `https://krusgraph.com/mcp`, one URL for every user.

**2 Tools** — read live from the server: 36 tools, 28 read-only, 8 write (`create_backend`, `create_views`,
`create_semantic_model`, `create_data_agent`, `create_ontology`, `create_silver_notebook`, `create_gold_views`,
`create_drift_monitor`: destructive, idempotent, never delete; all but `create_backend` dry-run by default). New since
the earlier submission (22 tools, 18 read-only, 4 write) include `sap_pack_draft`. `tests/test_submission.py` keeps
these numbers and names equal to `server.mcp.list_tools()`.

**3 Listing** — Name *Krusgraph for Microsoft Fabric* · slug `krusgraph` (permanent) · categories Data & Analytics,
Development tools · author Kruse Consulting AB · docs https://krusgraph.com/docs · support hello@krusgraph.com ·
privacy https://krusgraph.com/privacy · icon: the site favicon.
- One-liner: Turn Microsoft Fabric tables into an explainable graph and a GraphQL API — keys and relationships inferred, with the rule behind every link shown.
- Description: what it reads, the rule behind every link, validate_plan and suggest_relationships against the data;
  the GraphQL API and read-only queries; the drafts (TMDL, data dictionary, dbt, Fabric IQ, Rayfin) and the graph
  analysis; dry runs for the other create tools; sign-in with the user's own account, nothing stored, MIT, not
  affiliated with Microsoft.

**4 Use cases** — (1) understand an unfamiliar lakehouse: plan, check against the data; (2) create a GraphQL API and
answer questions through nested relationships; (3) draft a semantic model, data dictionary and dbt tests.
Prerequisites: a Fabric capacity and workspace, a work account with access (Viewer to read, Contributor to create),
an administrator's one-time consent. Read and write.

**5 Company** — Kruse Consulting AB, https://krusgraph.com.

**6 Authentication** — always required; OAuth with **Anthropic-held client credentials** (the portal detects "installers
bring their own client" because Entra has no DCR — that would make every customer register an app). Client secret
required, pasted in the portal by the maintainer. No extra request headers.

**7 Data handling** — "we proxy a partner's API with permission" (Microsoft Fabric public APIs, delegated, on behalf
of the user); personal health data "depends on configuration" (nothing collected or stored; a customer's own tables
pass through transiently under their permissions); no sponsored content.

**8 Test & launch** — reviewer instructions in the portal (account, password, ten questions against `demo` with the
expected answers, what the write tools do for a Viewer). Self-tested: yes.

**9 Compliance** — seven acknowledgements, ticked by the maintainer; additional notes on the operator, OAuth/OBO, no
storage, write tools never delete, synthetic review data.

## Against Anthropic's requirements (read 28 October 2026)

Source: https://claude.com/docs/connectors/building/submission ("Submit a connector to the directory").

| Requirement as stated there | Krusgraph |
| --- | --- |
| Remote, reachable over HTTPS | `https://krusgraph.com/mcp` |
| "OAuth 2.0 for authenticated services"; Anthropic can hold the OAuth client | Entra ID, Anthropic-held client credentials (answer 6) |
| "every tool includes a `title` and the applicable `readOnlyHint` or `destructiveHint`" | all 36; `tests/test_submission.py` |
| Tested in Claude as a custom connector; "run every tool yourself" (Test & launch) | 30 tools on 27 Oct 2026; not yet `sap_pack_draft` and the operator-only tools (step 5) — run them, or say so in the portal, before ticking it |
| Documentation, privacy policy URL, support contact, icon | /docs, /privacy, hello@krusgraph.com, /favicon.ico |
| Test account for reviewers, entered in the portal | step 6 |
| Seven compliance acknowledgements | answer 9 |
| Not an MCP App, no `ui/open-link` | no screenshots or link allowlist needed |

After submitting, a listing is by default a Community connector; escalations go to `mcp-review@anthropic.com` (same page).
