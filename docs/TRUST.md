# Trust: what Krusgraph does, with the source for each statement

The material for a public `/trust` page. Every statement below has a source in this repository (a file, a function
or a test), and says so; a statement that is Microsoft's, not ours, is marked as Microsoft's and pointed at Microsoft's
own material. No statement here says that Krusgraph follows or resembles a standard it is not certified against. Where the repository cannot show that something is true of the
live service, the row says that too. Written 2 November 2026 (round n76); the sources are read as they stand on that
day.

## Where it runs

| Statement | Source |
| --- | --- |
| The hosted service runs in Microsoft Azure, region Sweden Central, as an Azure Container App. | `deploy/krusgraph.example.json` (`"location": "swedencentral"`), `deploy/azure_containerapp.py`, the page for IT departments `fabric_backend/page_templates/it.html` ("Hosted in Azure, Sweden Central"), checked by `tests/test_site.py` (`test_it_page_lists_the_app_permissions_the_deploy_check_requires`). |
| The same code can be run in a customer's own Azure subscription and region with the same script. | `deploy/krusgraph.sh`, `deploy/KRUSGRAPH-START.md`, `docs/OPERATIONS.md`; `LICENSE` (MIT). |
| `/check` runs in the visitor's browser; the files dropped there are not uploaded. | `fabric_backend/browser_check.py`, `fabric_backend/static/check-worker.js`, the page's content security policy; the privacy page and /it describe it; `tests/test_check.py`, `tests/test_browser.py`. |
| Microsoft's attestations for the platform (ISO 27001, SOC 2 and the rest) cover Azure, not Krusgraph. | They are Microsoft's: Microsoft Trust Center, https://www.microsoft.com/trust-center (the address answered HTTP 200 from the session that wrote this file on 2 November 2026; its content was not read, and what it says is Microsoft's to say). Krusgraph has none of its own, see "Certifications" below. |

## What is stored, and what is not

| Statement | Source |
| --- | --- |
| No table contents are stored. Metadata (workspace, item, table and column names and types), the counts from checks, sample rows and query results pass through the server to the person's MCP client while the call runs and are not kept. | `SECURITY.md` ("What the service stores"), `fabric_backend/page_templates/it.html` and `PRIVACY.md`; the server has no database and writes nothing to disk (`fabric_backend/server.py`). |
| Tokens from Claude's sign-in are held in memory only, keyed by a hash, until shortly before they expire, and are never written to disk or logs. | `fabric_backend/entra.py` (the on-behalf-of cache), `docs/SECURITY.md`, tests `test_on_behalf_of_cache_never_shares_tokens_between_users`, `test_tokens_and_secrets_never_reach_logs_or_stdout` in `tests/test_security.py`. |
| For MCP clients other than Claude (VS Code, Cursor, Glama and others, signing in at `/mcp/connect`), a sign-in in progress is kept 10 minutes, Microsoft's tokens encrypted for at most 60 seconds until the client collects them, and Microsoft's refresh token encrypted for at most 90 days, in Azure Table Storage under a key of Krusgraph's own; the refresh token is never given to the client. Since 2 November 2026 (n83), after every renewal the answer the client got (an access token and the next refresh token) is also kept encrypted in that row and used for at most 60 seconds, so a client that lost the answer and asks again gets the same one; this happens at every renewal, not only at the first sign-in, and the copy stays encrypted and unused until the next renewal overwrites it or the line ends. | `fabric_backend/registration_store.py`, `fabric_backend/registration_flow.py` (`Layer._refresh`), `docs/CLIENT-REGISTRATION.md`, `docs/REFRESH-ROTATION.md`, `PRIVACY.md` (the table of records), `tests/test_client_registration.py`, `tests/test_refresh_rotation.py`. |
| Each tool call leaves one usage record: the tool's name, the outcome kind, the duration, whether it was a dry run and, when a salt is set, a salted hash of the organisation's tenant id. No user id, no IP address, no names of workspaces, tables or columns, no queries or results. | `fabric_backend/usage.py` (`FIELDS`), `PRIVACY.md`; `test_no_content_reaches_the_usage_line_or_metrics` and `test_privacy_page_lists_exactly_what_is_counted_and_follows_the_settings` in `tests/test_operations.py`. |

## Logs

| Statement | Source |
| --- | --- |
| The technical logs carry no content: no table contents, query text, tokens or headers. The HTTP access line with IP addresses is turned off when console logs go to Log Analytics. | `fabric_backend/usage.py`, `docs/SECURITY.md` ("What holds by design", "Usage statistics"), `deploy/azure_containerapp.py`. |
| Retention is a setting, `log_retention_days`, from 30 to 730 days; 30 is the documented proposal. The /it and /privacy pages render the live value ("deleted after N days") or say that console logs are not stored when the setting is off. | `deploy/azure_containerapp.py` (`log_retention_days`, the Log Analytics workspace's `--retention-time`), `deploy/krusgraph.example.json`, `fabric_backend/pages.py` (`LOGS_KEPT_DAYS`), `test_it_page_says_how_long_logs_are_kept_as_the_privacy_page_does` in `tests/test_site.py`. **Not shown by the repository:** whether the live service has Log Analytics switched on and at 30 days; `deploy/krusgraph.json` is git-ignored, and `docs/SECURITY.md` (open question 11) records that the alerts and Log Analytics were not yet set up when it was written. The public page should state the live value, read from /it, with its date. |
| Microsoft Entra ID records sign-ins in the customer's own tenant, as for any app. | `fabric_backend/page_templates/it.html`. |

## Identity and permissions

| Statement | Source |
| --- | --- |
| Sign-in is with the person's Microsoft work account (Microsoft Entra ID). Every call runs as that person, with that person's own Fabric permissions; all the app's permissions are delegated, and it asks for no application permissions. | `docs/SCOPES.md` (every permission with the Fabric REST operation behind it), `deploy/azure_containerapp.py` (`REQUIRED_SCOPES`), `fabric_backend/entra.py`; `/it` lists them, and `tests/test_site.py` keeps that list equal to `REQUIRED_SCOPES`. |
| An administrator approves the app once (admin consent) and can revoke it at any time under Enterprise applications; a person can disconnect the connector in their client. | `fabric_backend/page_templates/it.html` ("How to revoke access"), `docs/SCOPES.md` (the consent link and its return address). |
| The Entra app's publisher is verified: Kruse Consulting AB, publisher domain krusgraph.com (Microsoft Entra publisher verification). Verification says who publishes the app; it says nothing about its security. | `fabric_backend/page_templates/it.html` (`#verified-publisher`), checked by `test_who_stands_behind_it` in `tests/test_site.py`. The verification itself is a record in Entra that the maintainer completed; the repository carries the statement, not the record. |
| Tokens are validated before the MCP transport sees a request: RS256 signature against Microsoft's published keys, expiry, audience, issuer for the token's own tenant, and the delegated scope. Only RS256 is accepted. | `fabric_backend/entra.py`, `docs/SECURITY.md` ("Verified by tests", 20 cases), `tests/test_security.py`, `tests/test_entra.py`. |
| Refresh tokens for MCP clients other than Claude rotate at every use, and an old one coming back ends the whole sign-in, with one exception since 2 November 2026: the token just replaced, from the same client id, within 60 seconds, gets the same answer again (a retry after a lost answer). The consequence: a stolen old refresh token used within those 60 seconds is not detected; it gets the same access token (valid about an hour) and the current refresh token. Client ids are public, so the client-id check does not stop a thief. Outside the window detection is as before. | `fabric_backend/registration_flow.py` (`Layer._refresh`), `docs/REFRESH-ROTATION.md`, `docs/RISK-REGISTER.md` (R9), `tests/test_refresh_rotation.py`; tested against a mocked Entra and store only. |
| Signed-in tool calls are rate-limited per user and per organisation; the ids are kept as salted hashes in memory. | `fabric_backend/limits.py`, `docs/OPERATIONS.md` §1, `tests/test_operations.py`. |

## What the tools may change

| Statement | Source |
| --- | --- |
| Planning, checking and the drafts only read. | The tools' annotations (`read_only_hint`) in `fabric_backend/server.py`; `tests/test_submission.py` (`test_every_tool_has_a_title_and_a_hint`). |
| Eight of the nine creating tools are dry run by default: they answer with what they would create until called with `dry_run=false`. `create_backend` has no dry run and creates or updates the one API for GraphQL named in the call. | `fabric_backend/server.py` (the `create_*` tools, `tool_params.DryRun`), `fabric_backend/tool_status.py` (`NO_DRY_RUN`); the sentences on /it, /terms and /docs render from `NO_DRY_RUN`, and `tests/test_site.py` checks them against the tools' signatures. |
| No tool deletes anything in Fabric. A creating tool creates or updates under a name; `create_backend` writes nothing when an update would drop relationships the API has; `create_report` leaves a report of the same name alone. | `fabric_backend/deploy.py` (`create_or_update_api`: "Never deletes"), the docstrings of the creating tools in `fabric_backend/server.py`, `deploy/SUBMISSION.md` ("destructive, idempotent, never delete"), `tests/test_create_refusals.py`, `tests/test_creating_tools.py`. |
| Creating needs the person's own Contributor role on the workspace; the hosted app cannot run or schedule pipelines (it does not ask for `DataPipeline.Execute.All`). | `docs/SCOPES.md`, `fabric_backend/page_templates/it.html`. |

## Security practices

| Statement | Source |
| --- | --- |
| A security policy with a reporting address, and the same address in `security.txt` (RFC 9116) with a fixed expiry that a test reminds the maintainer to renew. | `SECURITY.md`; `fabric_backend/discovery.py` (`security_txt`, `SECURITY_EXPIRES`), served at `/.well-known/security.txt` by `fabric_backend/server.py`; `tests/test_site_extras.py`. |
| A security review of sign-in and the MCP endpoint, with each case tied to a test, what was found and fixed, and what stays open. | `docs/SECURITY.md`; `tests/test_security.py`, `tests/test_entra.py`, `tests/test_site_extras.py`, `tests/test_operations.py`. |
| Dependencies are pinned to exact versions for the image; a weekly `pip-audit` checks them against known vulnerabilities; Dependabot watches the Python packages and the GitHub Actions. | `deploy/constraints.txt`, `.github/workflows/audit.yml`, `.github/dependabot.yml`. |
| A CycloneDX SBOM of the image's exact versions is built on every push to `main` and every version tag, kept as a workflow artifact for 90 days. | `.github/workflows/sbom.yml`. |
| The licences of every dependency are listed, generated from the pins, and checked for staleness. | `THIRD_PARTY_NOTICES.md`, `tools/third_party_notices.py` (`--check`). |
| Request bodies are capped at 4 MiB whatever the headers say; oversized authorization headers are refused fast and never echoed; every tool error is scrubbed of token-shaped strings and secret-like header pairs. | `fabric_backend/server.py` (the security wrapper), `fabric_backend/errors.py` (`scrub`), `docs/SECURITY.md`, `tests/test_security.py`. |
| The client secret can live in Azure Key Vault, read with the container app's managed identity; rotation is documented. | `fabric_backend/keyvault.py`, `docs/OPERATIONS.md` §2. **Not shown by the repository:** whether the live service uses Key Vault. |
| Operations are code: `--doctor` shows the state of the service (including the secret's and the certificate's dates), `--backup` exports the registration table, `--budget` sets a cost budget; a continuity section says what someone else needs if the maintainer is unavailable. | `deploy/krusgraph.sh`, `deploy/azure_containerapp.py`, `docs/OPERATIONS.md` §8 and §9, `tests/test_deploy_doctor.py`. §8 says these have not yet been run against the live subscription. |
| Maintained by one person. No fixed response time, no bug bounty. | `SECURITY.md`. |

## Open source

| Statement | Source |
| --- | --- |
| The whole thing is open source under the MIT licence: engine, MCP server, website and deployment. | `LICENSE`, `pyproject.toml`, `README.md`. |
| Third-party licences are listed per package. | `THIRD_PARTY_NOTICES.md`. |
| Rules for people and agents who change the repository, including that no customer data and no unbacked claim goes in. | `CONTRIBUTING.md`, enforced in part by `tests/test_site.py` and `tests/test_architecture.py`. |

## Subprocessors

Who handles data on Krusgraph's behalf when the hosted service is used. The AI client is not on this list: it is the
customer's own vendor, under the customer's agreement with that vendor (Anthropic for Claude, Microsoft for VS Code,
Anysphere for Cursor, and so on); Krusgraph's tools answer the client the person connected.

| Subprocessor | What | Where | Source |
| --- | --- | --- | --- |
| Microsoft Azure (Microsoft Ireland Operations Ltd. for EU customers, per Microsoft's own terms) | Azure Container Apps runs the server; Azure Log Analytics holds the usage records and console log when switched on; Azure Table Storage holds the encrypted sign-in records for MCP clients other than Claude; Azure Key Vault holds the client secret when switched on; Azure Container Registry holds the image. | Sweden Central | `deploy/azure_containerapp.py`, `deploy/krusgraph.example.json`, `docs/OPERATIONS.md`. The contracting entity for Azure is Microsoft's statement, not verified from this repository. |

Microsoft Fabric itself is not a subprocessor of Krusgraph: the customer's Fabric tenant is the customer's own
Microsoft service, and Krusgraph reads it on the signed-in person's behalf (`docs/SCOPES.md`).

Anthropic holds the OAuth client credentials for the Claude connector directory listing (`deploy/SUBMISSION.md`,
"Authentication"); that is a credential for signing in, not a flow of customer data to Anthropic from Krusgraph.

## Data processing agreement

A draft template is in `docs/DPA-DRAFT.md`. It is a draft and not legal advice: it names the records above with their
purposes and retention from `PRIVACY.md`, and leaves the legal review to the customer's and Kruse Consulting AB's own
advisers. The pricing page says a data processing agreement is available on request (`fabric_backend/page_templates/pricing.html`).

## Certifications

**Krusgraph is not ISO 27001 or SOC 2 certified; here is what we do instead.** The practices above, each with its
source; a self-assessment against the 93 controls of ISO/IEC 27001:2022 Annex A, control by control, with what is in
place, partly in place, missing or not applicable, and no score (`docs/ISO27001-SELF-ASSESSMENT.md`); an internal
risk register whose probabilities stay "not assessed" until something in the repository can carry a value
(`docs/RISK-REGISTER.md`); and `SECURITY.md`, which says the same in one line ("Krusgraph holds no security
certification").

## What this page does not say

- Nothing about any Microsoft certification as if it were Krusgraph's.
- No "partner", "certified" or "endorsed by Microsoft" (`CONTRIBUTING.md`). Krusgraph is an independent open-source
  project of Kruse Consulting AB and is not affiliated with Microsoft.
- No uptime figure, no response time, no customer count: none exists in the repository (`docs/MISSING-EVIDENCE.md`).
- No statement about the live configuration that `deploy/krusgraph.json` holds and the repository does not: log
  retention, Key Vault, the tenant allow-list. The /it page renders those from the running service.

## Keeping it true

A statement on the public page is a statement from a table here, with the file next to it. When the file changes, the
row changes in the same commit. The tests named above are what stops the pages from drifting away from the code; the
date at the top is when the sources were last read for this file.
