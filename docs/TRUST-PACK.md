# Krusgraph trust pack

For a buyer's security, privacy and procurement team. Round n199, 10 November 2026. Written from the repository as it
stands at commit `7c2a2b3` (main). Every statement names the file that shows it. Where the repository cannot show
something, the row says **To confirm by the founder**. Nothing here claims a certification, an audit, compliance with a
standard, or a partnership with or endorsement by Microsoft, Anthropic or anyone else.

Krusgraph is published by Kruse Consulting AB, Sweden. It is open source under the MIT licence (`LICENSE`). It is run
by one person (`SECURITY.md`).

Related files, read for this pack: `docs/TRUST.md` (every statement with its source), `docs/SECURITY.md` (sign-in
review), `docs/SCOPES.md` (permissions per tool), `docs/DPA-DRAFT.md`, `docs/ISO27001-SELF-ASSESSMENT.md`,
`docs/WORKLOAD-PUBLISH.md`, the draft attestation `fabric_backend/page_templates/WORKLOAD-ATTESTATION.md`,
`docs/LIFECYCLE-DESIGN.md`, `docs/CONNECT-DESIGN.md`. How a pilot starts and ends: `docs/PILOT-ONBOARDING.md`.

## 1. The two ways a customer uses Krusgraph

| | Krusgraph for Fabric (the workload) | Krusgraph for Claude (the MCP server) |
| --- | --- | --- |
| What it is | The item **Krusgraph Model** inside Microsoft Fabric | An MCP server the person adds to Claude or another MCP client |
| Code | `workload/` (editor), `fabric_backend/workload_api.py`, `fabric_backend/workload_host.py` (engine routes) | `fabric_backend/server.py`, `fabric_backend/mcp_server.py` |
| Address | `https://workload.krusgraph.com` | `https://krusgraph.com/mcp` |
| Entra app | `Krusgraph workload (dev)`, client id `853a0cf0-7d35-42b7-b384-26178755a72a` (`docs/WORKLOAD-PUBLISH.md`) | the Krusgraph app; its client id is set at deploy time and shown on `https://krusgraph.com/it` (`deploy/azure_containerapp.py`) |
| AI model | None (`fabric_backend/offering.py`, `NO_AI`) | The person's own AI client (for example Claude) receives the tools' answers |
| Status | Runs as `Org.Krusgraph` in Kruse Consulting's own tenant only. `Krusgraph.Modeler` for other tenants waits for Microsoft to register the name (`docs/WORKLOAD-PUBLISH.md`, step 1) | Live at krusgraph.com |

Both run on the same engine (`fabric_backend/`) and the same hosted service.

## 2. What Krusgraph reads, and what it never stores

**Krusgraph for Fabric** reads:

- workspace, lakehouse, schema, table and column names and data types (`workload_api.py`, `run_schemas`, `run_review`);
- counts from the check against the rows: rows, empty values, duplicates, orphans. The check "returns counts, never a
  value" (`workload_api.py`, `run_check`, `check_totals`);
- the item's own state and the items it built, in the customer's workspace.

It never reads row values for the review or the check, and stores none
(`fabric_backend/page_templates/WORKLOAD-ATTESTATION.md`, "OneLake" and "Data Residency").

**Krusgraph for Claude** reads the same metadata and counts. In addition, when the person asks, it reads up to 20 sample
rows (`sample_rows`) and the results of read-only GraphQL queries (`query_graphql`). These pass through the server's
memory to the person's MCP client and are not kept (`SECURITY.md`, `docs/SCOPES.md`). Columns that look like personal
data by name are masked unless the person asks (`fabric_backend/privacy.py`).

**What is stored, and where:**

| What | Where | Holds | Kept | Source |
| --- | --- | --- | --- | --- |
| `review.json`, `source.json`, `outputs.json`, `item.json` | The Krusgraph Model item's own definition, in the customer's Fabric workspace | The accepted keys and relationships, the chosen lakehouse and schema, the choices and ids of items built, the last Create's summary. No token, no row value | Until the customer deletes the item | `WORKLOAD-ATTESTATION.md` ("OneLake", "Item Definition Portability"), `workload/Workload/app/items/ModelItem/` |
| The items Krusgraph builds (notebooks, views, pipeline, semantic model, report, API for GraphQL, ontology, data agent, App) | The customer's workspace | Ordinary Fabric items | Until the customer deletes them | `docs/LIFECYCLE-DESIGN.md` §0 |
| Tokens | Server memory only, keyed by a hash | On-behalf-of tokens for Fabric and SQL | Until shortly before they expire; never written to disk or logs | `fabric_backend/entra.py`, `docs/SECURITY.md` |
| Workload console log | Azure Log Analytics, Sweden Central, when switched on | One JSON line per route: route, output, kind, duration. "No token, no body, no table contents, no item names" | `log_retention_days`, 30 to 730 days; 0 means not stored | `workload_api.py` (`log`), `deploy/azure_containerapp.py`, `deploy/krusgraph.example.json` |
| MCP usage record | Same | Tool name, outcome kind, duration, dry run, optionally a salted hash of the tenant id. No user id, no IP address | Same | `fabric_backend/usage.py`, `fabric_backend/page_templates/PRIVACY.md` |
| Rate-limit counters | Server memory, per replica | Salted hashes of user id and tenant id | Rolling minutes and hours | `fabric_backend/limits.py` |
| Sign-in records for MCP clients other than Claude | Azure Table Storage, Sweden Central, encrypted with Krusgraph's own key | The sign-in in progress, Microsoft's tokens, Microsoft's refresh token | 10 minutes; 60 seconds; at most 90 days | `fabric_backend/registration_store.py`, `docs/CLIENT-REGISTRATION.md` |
| The pilot's tenant id | `deploy/krusgraph.json` (`workload_allowed_tenants`), git-ignored, never in the repository | The tenant id only | Until the pilot ends | `docs/WORKLOAD-PUBLISH.md`, A2 |

The live log retention is not in the repository. `https://krusgraph.com/it` renders the live value. **To confirm by the
founder** before a pilot: the value is 30 days or more and Log Analytics is switched on (`docs/WORKLOAD-PUBLISH.md`,
TODO 8).

## 3. Where it runs

- Microsoft Azure, region **Sweden Central** (EU), one Azure Container App. The region is the `location` key that
  `deploy/krusgraph.sh` passes to `deploy/azure_containerapp.py` (`deploy/krusgraph.example.json`:
  `"location": "swedencentral"`).
- Fabric public cloud only. Customers in every Fabric region reach the same service in Sweden Central. For a tenant
  outside the EU, its names and counts are processed in Sweden in transit (`WORKLOAD-ATTESTATION.md`, "Data Residency").
- Everything Krusgraph builds stays in the customer's workspace, in the customer's region.
- A customer can run the same code in its own Azure subscription and region with the same script (`deploy/krusgraph.sh`,
  `deploy/KRUSGRAPH-START.md`). Krusgraph for Fabric is not part of that self-hosted option today (`offering.py`).

## 4. How it signs in

- Microsoft Entra ID only. The person signs in with their own work account. The Fabric editor gets every token from the
  Fabric host (`acquireFrontendAccessToken`); it has no sign-in library and no password (`WORKLOAD-ATTESTATION.md`).
- **Delegated permissions only.** Every call runs as the signed-in person, with that person's own Fabric rights. The
  engine exchanges the person's token on their behalf (on-behalf-of) for a Fabric or SQL token (`entra.OnBehalfOf` in
  `fabric_backend/entra.py`). Krusgraph can reach nothing the person cannot reach. Neither app has application
  permissions.
- **No long-lived tokens.** "Krusgraph holds no long-lived tokens. Every call runs as the signed-in user, on behalf of
  that user, while the item is open" (`docs/LIFECYCLE-DESIGN.md`, §0). Anything that runs while nobody is looking runs
  inside the customer's Fabric, under the customer's own identity, in the pipeline Krusgraph made.
  The one exception is on the MCP path: for MCP clients other than Claude, Microsoft's refresh token is kept encrypted
  for at most 90 days (section 2). Krusgraph for Fabric keeps no refresh token.
- Tokens are checked before anything runs: RS256 signature against Microsoft's keys, expiry, audience, issuer, the
  delegated scope, and the tenant allow-list. 20 cases are tested (`docs/SECURITY.md`, `tests/test_security.py`,
  `tests/test_entra.py`).
- Only allowed tenants are served. The workload engine answers only tenants on `KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS`
  (`fabric_backend/entra.py`). Any other tenant sees "Krusgraph is not turned on for your organisation yet." and nothing
  is read (`docs/WORKLOAD-PUBLISH.md`, A2).
- Creating is never automatic. Every creating action is a dry run first. Nothing is created until the person chooses
  Create (Fabric) or calls a tool with `dry_run=false` (MCP). No tool deletes anything in Fabric (`docs/TRUST.md`, "What
  the tools may change").

## 5. Delegated permissions, and why

### Krusgraph for Fabric: the workload app `853a0cf0-…`

From the draft attestation (`WORKLOAD-ATTESTATION.md`, "Microsoft Entra Access") and `docs/WORKLOAD-DEV.md` (§7).
Which of the narrow or broad scopes are granted on the app today is **To confirm by the founder** (Entra → App
registrations → API permissions); the customer's admin sees the exact list on the consent screen.

| Permission (API) | Why | Needed? |
| --- | --- | --- |
| `Fabric.Extend` (Power BI Service) | The workload runs inside Fabric | Yes |
| `Workspace.Read.All` (Power BI Service) | List the workspace and its lakehouses | Yes |
| `Lakehouse.Read.All` (Power BI Service) | Read the lakehouse and its SQL endpoint | Yes |
| `Item.ReadWrite.All`, or the narrower `Notebook.ReadWrite.All`, `DataPipeline.ReadWrite.All`, `SemanticModel.ReadWrite.All`, `Report.ReadWrite.All`, `GraphQLApi.ReadWrite.All`, `DataAgent.ReadWrite.All` (Power BI Service) | Create or update only the items the person chooses, after the dry run | Yes, for Create |
| `user_impersonation` (Azure SQL Database) | Read column metadata and run the counting queries of the check on the SQL analytics endpoint | Yes |
| `Dataset.ReadWrite.All` (Power BI Service) | One refresh of the new semantic model after Create | Optional |
| `DataPipeline.Execute.All` (Power BI Service) | Run once or Schedule the new pipeline, only when the person ticks it | Optional |
| `Tenant.Read.All` (Power BI Service) | One read-only preflight: List Tenant Settings, to say whether a setting an output needs is on. Answers only for a Fabric administrator | Optional |
| `Capacity.Read.All` (Power BI Service) | Read the capacity's SKU before publishing a data agent | Optional |

### Krusgraph for Claude: the Krusgraph app

Generated from `fabric_backend/access.py`, equal to `REQUIRED_SCOPES` in `deploy/azure_containerapp.py` (kept equal by
`tests/test_n146_one_source.py`). Detail per tool: `docs/SCOPES.md`.

| Permission (API) | Why |
| --- | --- |
| `User.Read` (Microsoft Graph) | Sign-in only |
| `Workspace.Read.All` (Fabric) | List workspaces, find a workspace by name |
| `Item.Read.All` (Fabric) | List items; read a pipeline's latest runs for lineage |
| `GraphQLApi.ReadWrite.All` (Fabric) | Create or update the one API for GraphQL named in the call; read an API's definition (Fabric has no read-only scope for it) |
| `GraphQLApi.Execute.All` (Fabric) | Run the read-only GraphQL queries the person asks for; mutations are refused |
| `Notebook.ReadWrite.All` (Fabric) | Create or update notebooks, only with `dry_run=false` |
| `DataPipeline.ReadWrite.All` (Fabric) | Create or update a pipeline definition, only with `dry_run=false` |
| `Item.ReadWrite.All` (Fabric) | Create or update a semantic model, report, ontology or data agent, only with `dry_run=false`; read semantic model definitions |
| `user_impersonation` (Azure SQL Database) | Column names, counting queries, up to 20 sample rows on request, and `create_views` with `dry_run=false` |

Not requested on this app: `DataPipeline.Execute.All`, `Item.Execute.All`, `Workspace.ReadWrite.All`. The hosted MCP
app cannot run or schedule pipelines (`docs/SCOPES.md`).

## 6. "No AI" by default, and the opt-in paths

| Path | AI model? | Who receives data | Source |
| --- | --- | --- | --- |
| Krusgraph for Fabric (default) | **None.** The keys and relationships come from the engine's named rules; the check counts rows | Krusgraph's service (Sweden Central) and the customer's Fabric. Nothing goes to an AI provider | `offering.py` (`NO_AI`), `fabric_backend/infer.py`, `docs/INFERENCE.md` |
| A data agent Krusgraph creates | Fabric's own AI, when someone asks the agent | Microsoft, under the customer's Fabric terms. Krusgraph is not involved after Create | `offering.py` (`NO_AI`) |
| Krusgraph for Claude (opt-in: the person adds the connector) | The person's own AI client | The tools' answers (names, counts, and the sample rows and query results the person asks for) go to the person's client and its AI provider: **Anthropic** when the client is Claude. Krusgraph does not send data to Anthropic itself; the customer's own agreement with the client vendor covers it | `fabric_backend/access.py` (`flows_md`), `offering.py` (`WAYS`) |
| The Claude agent in the customer's own Azure | **Design only, not built.** Off by default, opt-in per tenant, runs on Claude in Microsoft Foundry in the customer's own Azure subscription. Anthropic's page says prompts and completions stay within Azure for "Hosted on Azure", and only usage metadata and content flagged by Anthropic's safety systems go to Anthropic | `docs/LIFECYCLE-DESIGN.md` §7 |

Anthropic holds the OAuth client credentials of the Claude connector directory listing. That is a sign-in credential,
not a flow of customer data from Krusgraph to Anthropic (`docs/TRUST.md`, "Subprocessors").

## 7. Sub-processors

| Sub-processor | What | Where | When |
| --- | --- | --- | --- |
| Microsoft (Azure) | Container Apps (the service), Log Analytics (logs, when switched on), Table Storage (MCP sign-in records), Key Vault (client secret, when switched on), Container Registry (the image) | Sweden Central | Always, for the hosted service (`deploy/azure_containerapp.py`, `docs/DPA-DRAFT.md` §6) |
| Anthropic | None for Krusgraph for Fabric. For Krusgraph for Claude, Anthropic is the customer's own AI vendor, not Krusgraph's sub-processor. For the designed Claude agent, Anthropic would be reached through the customer's own Foundry deployment | — | Only when the customer opts in to a Claude path (section 6) |

Microsoft Fabric is the customer's own Microsoft service, not a sub-processor of Krusgraph. Whether the DPA should
list Anthropic at all for the Claude paths is a question for the lawyers (section 9).

## 8. How to revoke access

| Step | Who | Where | Effect |
| --- | --- | --- | --- |
| Remove admin consent, or delete the app | The customer's Entra admin | Entra admin centre → **Enterprise applications** → the Krusgraph app (or Krusgraph workload app) → **Permissions** or **Properties → Delete** | No new tokens. A token already issued stays valid until it expires (60 to 90 minutes; `docs/SECURITY.md`, open question 1) |
| Delete the Krusgraph Model items | A user or workspace admin | The Fabric workspace | Removes `review.json`, `outputs.json` and the rest |
| Delete the items Krusgraph built, if not wanted | A user or workspace admin | The Fabric workspace | Krusgraph never deletes them itself |
| Turn off the tenant setting | The customer's Fabric admin | Admin portal → Tenant settings → Additional workloads | The workload is hidden |
| Remove the tenant from Krusgraph's lists | Krusgraph | `workload_allowed_tenants`, Fabric's Publish tab (`docs/WORKLOAD-PUBLISH.md`, "Withdrawing a pilot") | The engine stops answering at once |
| Disconnect the connector | The person | Their MCP client | Their client stops calling |

## 9. Status: what is and is not in place

| Item | Status | Source |
| --- | --- | --- |
| Microsoft Entra publisher verification, Krusgraph app (MCP) | The /it page states it is verified (Kruse Consulting AB, domain krusgraph.com). The record is in Entra, not in the repository. **To confirm by the founder** with a screenshot of the consent screen | `fabric_backend/page_templates/it.html` (`#verified-publisher`), `docs/TRUST.md` |
| Microsoft Entra publisher verification, workload app `853a0cf0-…` | **Not yet.** Also to rename the app from "Krusgraph workload (dev)" | `docs/WORKLOAD-PUBLISH.md`, step 2; `WORKLOAD-ATTESTATION.md` |
| Fabric workload vendor attestation (`Krusgraph.Modeler`) | **Draft.** Written, not signed, not sent to Microsoft, not accepted. Open points marked Not yet | `fabric_backend/page_templates/WORKLOAD-ATTESTATION.md`, `docs/WORKLOAD-PUBLISH.md`, step 6 |
| Fabric workload name `Krusgraph.Modeler` | **Not registered.** Upload refused; support ticket with Microsoft | `docs/WORKLOAD-PUBLISH.md`, step 1 |
| ISO/IEC 27001 | **Not held.** A self-assessment against the 93 Annex A controls exists; it is not a certification | `docs/ISO27001-SELF-ASSESSMENT.md`, `SECURITY.md` |
| SOC 2 | **Not held** | `SECURITY.md` |
| Penetration test, independent security assessment | **Not done.** Who and when: **To confirm by the founder** | `WORKLOAD-ATTESTATION.md`, "Security general"; `docs/WORKLOAD-PUBLISH.md`, TODO 5 |
| Privacy review | **Not done** | `docs/WORKLOAD-PUBLISH.md`, TODO 6 |
| Conditional Access | **Not tested** | `WORKLOAD-ATTESTATION.md` |
| GDPR roles | Working position: the customer is the **controller**; Kruse Consulting AB is the **processor** for the hosted service. `docs/DPA-DRAFT.md` notes this should be confirmed by each side's lawyer, since Krusgraph holds no table contents | `docs/DPA-DRAFT.md` |
| Data processing agreement | **Template to be drafted with a lawyer.** `docs/DPA-DRAFT.md` is a project draft, not legal text and not reviewed | `docs/DPA-DRAFT.md` |
| Business continuity and disaster recovery plan | **Not written.** No RTO or RPO | `WORKLOAD-ATTESTATION.md` |
| Service level agreement | **None.** Support by email, best effort, one person | `SECURITY.md`, `WORKLOAD-ATTESTATION.md` |

**When ISO 27001 or SOC 2 would make sense.** A certification is a cost in money and time for a one-person company.
It makes sense when buyers make it a hard gate in procurement, more than once; when there is revenue to pay for the
audit and the yearly surveillance; and when there is more than one person, so roles can be separated. For Nordic and EU
buyers ISO 27001 is the more common ask; SOC 2 is more common in the United States. The self-assessment
(`docs/ISO27001-SELF-ASSESSMENT.md`) lists the gaps to close first. The decision is **To confirm by the founder**.

**What the DPA needs (clauses to list, not legal text).** For the lawyer to draft:

1. Parties and roles (controller, processor), and the case where Krusgraph holds no personal data.
2. Subject matter, duration, nature and purpose (per path: Fabric workload, MCP server).
3. Types of personal data and data subjects (users' identity claims; personal data in names or sample rows on the MCP
   path).
4. Documented instructions: the person's own actions in the item or tool calls.
5. Confidentiality of the people who process the data.
6. Technical and organisational measures (annex; from this pack and `docs/TRUST.md`).
7. Sub-processors: the list, notice of changes, the right to object.
8. International transfers (none planned beyond Sweden Central; Microsoft's own terms).
9. Help with data subjects' requests.
10. Breach notification: channel and time limit.
11. Help with impact assessments and prior consultation.
12. Deletion or return at the end.
13. Audit and information rights, sized for a one-person processor.
14. Liability, term, governing law (Sweden), venue.
15. What happens on the opt-in AI paths (who is whose vendor).

## 10. Answers to a standard vendor security questionnaire

Today = in place, with the file that shows it. Planned = written down as a step, not done. Not applicable = does not
apply to how Krusgraph works. **To confirm by the founder** = the repository cannot show it.

| # | Question | Status | Answer | File |
| --- | --- | --- | --- | --- |
| 1 | How do users authenticate? | Today | Microsoft Entra ID only, the person's own work account. No local accounts, no passwords | `fabric_backend/entra.py`, `WORKLOAD-ATTESTATION.md` |
| 2 | Is MFA supported or enforced? | Today | Enforced by the customer's own Entra policies at sign-in; Krusgraph does not weaken them | `docs/SECURITY.md` |
| 3 | Conditional Access? | Planned | Not tested yet | `docs/WORKLOAD-PUBLISH.md`, TODO 7 |
| 4 | Least privilege, role-based access? | Today | Delegated permissions only; every call runs with the person's own Fabric rights; no application permissions; creating needs the person's own Contributor role | `docs/SCOPES.md`, `docs/TRUST.md` |
| 5 | Can access be revoked? | Today | Remove admin consent or delete the app in Entra; existing tokens expire within 60 to 90 minutes | `fabric_backend/page_templates/it.html`, `docs/SECURITY.md` |
| 6 | Tenant isolation? | Today | Tokens are validated per tenant; the workload engine serves only allow-listed tenants; on-behalf-of tokens are cached per user, never shared | `fabric_backend/entra.py`, `tests/test_security.py` |
| 7 | Encryption in transit? | Today | HTTPS only; the ingress refuses plain HTTP (`allowInsecure: False`); HSTS; storage account TLS 1.2 minimum | `deploy/azure_containerapp.py`, `docs/SECURITY.md` |
| 8 | Encryption at rest? | Today, partly | No customer data is stored by Krusgraph. MCP sign-in records are encrypted by the application with its own key. Azure's own encryption at rest for Storage and Log Analytics is Microsoft's platform default, **to confirm by the founder** against Microsoft's documentation | `fabric_backend/registration_store.py` |
| 9 | Key and secret management? | Today, partly | Client secret can live in Azure Key Vault, read by managed identity; never logged. Whether the live service uses Key Vault: **To confirm by the founder** (`--doctor`) | `fabric_backend/keyvault.py`, `docs/OPERATIONS.md` §2 |
| 10 | What customer data do you store? | Today | None from tables. Metadata and counts pass through memory during a call. The item's state stays in the customer's workspace | `SECURITY.md`, section 2 above |
| 11 | Do you use customer data to train AI models? | Not applicable | Krusgraph for Fabric uses no AI model. Krusgraph trains no model | `offering.py` (`NO_AI`) |
| 12 | Data location? | Today | Azure Sweden Central (EU) only | `deploy/krusgraph.example.json`, `deploy/azure_containerapp.py` |
| 13 | Data deletion on request or at contract end? | Today, partly | The customer deletes its items itself. Krusgraph removes the tenant id from its lists. Logs age out at the retention setting; deleting log lines earlier on request: **To confirm by the founder** | `docs/WORKLOAD-PUBLISH.md`, `docs/DPA-DRAFT.md` §5 |
| 14 | Logging and monitoring? | Today, partly | Content-free usage and route logs; `/health`; alert commands written but not yet run. Fabric activity id not yet in logs | `fabric_backend/usage.py`, `workload_api.py` (`log`), `docs/OPERATIONS.md` §4, `docs/SECURITY.md` open question 11 |
| 15 | Log retention? | To confirm by the founder | A setting from 30 to 730 days; the live value is on `/it` | `deploy/azure_containerapp.py`, `docs/TRUST.md` "Logs" |
| 16 | Backups? | Today, partly | Customer state lives in the customer's Fabric, not with Krusgraph. `--backup` exports the MCP sign-in table; not yet run against the live subscription. The service is rebuilt from the public repository with one script | `docs/OPERATIONS.md` §8.3, `WORKLOAD-ATTESTATION.md` |
| 17 | Business continuity and disaster recovery? | Planned | No written plan, RTO or RPO. A continuity section says what someone else needs if the maintainer is unavailable | `docs/OPERATIONS.md` §9, `docs/WORKLOAD-PUBLISH.md` TODO 11 |
| 18 | Incident response? | Planned | A reporting address and `security.txt` exist. No incident response plan with roles and notification duties | `SECURITY.md`, `docs/ISO27001-SELF-ASSESSMENT.md` 5.24 to 5.28 |
| 19 | Breach notification to customers? | To confirm by the founder | To be set in the DPA (channel and time limit) | `docs/DPA-DRAFT.md` §5 |
| 20 | Vulnerability management? | Today | Pinned Python dependencies, weekly `pip-audit`, Dependabot for Python and GitHub Actions, an SBOM on every push. The editor's npm dependencies are not watched by Dependabot: **To confirm by the founder** | `deploy/constraints.txt`, `.github/workflows/audit.yml`, `.github/dependabot.yml`, `.github/workflows/sbom.yml` |
| 21 | Penetration testing? | Planned | Not done. Who and when: **To confirm by the founder** | `docs/WORKLOAD-PUBLISH.md` TODO 5 |
| 22 | Secure development? | Today | Open source; automated tests on every push, including token validation; security review of sign-in with each case tied to a test; error text scrubbed of tokens | `.github/workflows/ci.yml`, `docs/SECURITY.md`, `fabric_backend/errors.py` |
| 23 | Who has access to production? Staff access? | To confirm by the founder | One person maintains the service. The roles needed are named; who holds them is outside the repository. Azure and Entra admin sign-in use Microsoft's mandatory MFA | `SECURITY.md`, `docs/ISO27001-SELF-ASSESSMENT.md` 5.17, 8.2 |
| 24 | Background checks, security training? | Not applicable / To confirm by the founder | One-person company | `SECURITY.md` |
| 25 | Container and host hardening? | Today | The server runs as an unprivileged user (`USER 10001`); request bodies capped at 4 MiB; CSP `frame-ancestors` only Fabric and Power BI; CORS only for those origins; no cookies | `Dockerfile`, `fabric_backend/server.py`, `WORKLOAD-ATTESTATION.md` |
| 26 | Rate limiting, abuse protection? | Today, partly | Per user and per tenant on MCP tool calls; unauthenticated requests are not limited by the app | `fabric_backend/limits.py`, `docs/SECURITY.md` open question 3 |
| 27 | Sub-processors? | Today | Microsoft Azure only for the hosted service; see section 7 | `docs/TRUST.md`, `docs/DPA-DRAFT.md` |
| 28 | Certifications? | Not held | No ISO 27001, no SOC 2, no other | `SECURITY.md` |
| 29 | Private Link, private networking? | Not applicable today | The editor and engine are on the public internet. Customers whose data may not leave their Azure can self-host the MCP server | `WORKLOAD-ATTESTATION.md` "Private Links", `offering.py` |
| 30 | Change management? | Today | Every change is a commit on GitHub with tests in CI; versions in `CHANGELOG.md`; only the latest version is supported | `SECURITY.md`, `CHANGELOG.md` |

## 11. Keeping this pack true

When a file named here changes, the row changes in the same commit. Any row marked **To confirm by the founder** is
answered by the founder, with the date, before this pack is sent to a buyer.
