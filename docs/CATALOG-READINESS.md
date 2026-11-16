# Catalog readiness: ChatGPT, Claude and the MCP Registry

Round C1, 15 November 2026. The hosted server at `https://krusgraph.com/mcp` (Claude) and
`https://krusgraph.com/mcp/connect` (every other client) checked against what three directories ask for. Docs only:
no tool behaviour changed. The one new test is `tests/test_c1_tool_description_wording.py`.

The founder asked on 15 November 2026 to be listed, and possibly suggested, in ChatGPT too. No directory promises a
listing, a placement or a suggestion. Each one reviews or scans a submission, and the model decides when to call a
tool from what the user asks and what the tool's description says. This document lists what can be prepared. It
does not predict an outcome.

Status words: **met** (the repository shows it), **gap** (missing or contradicted, with the smallest fix),
**unknown** (only a live run or the directory itself can tell). **Unverified** means the source page could not be
opened from this session. Read it on the site before acting on it.

## 1. Sources

| Directory | Source | Read |
| --- | --- | --- |
| Claude Connectors Directory | https://claude.com/docs/connectors/building/submission | opened 15 Nov 2026 |
| | https://claude.com/docs/connectors/building/review-criteria | opened 15 Nov 2026 |
| | https://claude.com/docs/connectors/building/authentication | opened 15 Nov 2026 |
| | https://claude.com/docs/connectors/building/testing | opened 15 Nov 2026 |
| ChatGPT (apps now published as plugins) | https://developers.openai.com/apps-sdk/app-submission-guidelines ("Plugin guidelines") | **Unverified**: developers.openai.com, help.openai.com and openai.com did not resolve from this session. Only search-engine excerpts of 15 Nov 2026 were read |
| | https://developers.openai.com/plugins/deploy/app-review ("Remote MCP server review requirements"), https://developers.openai.com/plugins/deploy/submission, https://developers.openai.com/apps-sdk/deploy/testing, https://developers.openai.com/plugins/build/auth | **Unverified**, as above |
| Official MCP Registry | [PUBLISHING.md](PUBLISHING.md), [MCP-REGISTRY.md](MCP-REGISTRY.md) (the registry's own guide, read for those rounds) | in the repository |

What the ChatGPT excerpts said, and nothing more (all **Unverified**):

- Apps are now submitted and published as plugins. The app guidelines cover the MCP server part of a plugin.
- An authenticated server needs a login and password for a fully featured demo account with sample data. Sign-up
  steps or 2FA/MFA lead to rejection. The credentials must work from outside internal networks and must not expire.
- Reviewer credentials go in a "Review details" field, not in the uploaded package.
- The submission needs test cases: five positive ones, each with the scenario, the user prompt, the expected tools and
  the expected result. The excerpt did not show whether negative cases are also required, so this document prepares
  three.
- Tool annotations must be set correctly. A tool whose behaviour does not match its description can be rejected.
- A privacy policy is required, with minimal collection of user information. Testing happens in ChatGPT's developer
  mode against a public server. Screenshots of the working app are asked for.
- The older note in [MCP-REGISTRY.md](MCP-REGISTRY.md) (line 211, from a DEV Community post) also names organisation and
  domain verification, website, support, privacy and terms URLs, and a video for the reviewer.

## 2. Where the three differ

| Topic | Claude directory | ChatGPT (Unverified) | MCP Registry |
| --- | --- | --- | --- |
| Review | Automatic policy scan, listed as Community. Some are escalated to Verified with a hands-on test | Review by OpenAI before publishing | None: a metadata entry, no review |
| Who submits | Any paid Claude plan, portal claude.ai/directory/manage | Verified OpenAI developer organisation, plugin upload | Owner of the namespace (DNS TXT on krusgraph.com) |
| Sign-in | OAuth 2.0. Anthropic-held client, DCR or CIMD. Callback `https://claude.ai/api/mcp/auth_callback` | OAuth, CIMD preferred. Callback reported as `https://chatgpt.com/connector_platform_oauth_redirect` | Not checked |
| Test account | Only for Verified review, requested by email. "Don't put credentials in the developer portal" | Required for review, entered in "Review details", no MFA | None |
| Annotations | `title` plus `readOnlyHint` or `destructiveHint` on every tool | Correct annotations (readOnly, destructive, openWorld per the Apps SDK; the exact rule is Unverified) | None |
| Descriptions | Narrow, accurate, no instructions to the model, no promotion | Must match behaviour (exact rule Unverified) | `description` at most 100 characters |
| Test cases | Run every tool yourself, confirmed in the portal | Five positive cases written into the submission | None |
| Interactive UI | MCP App: 3 to 5 PNG screenshots at least 1000 px wide, plus optional link allowlist | Screenshots of the app in ChatGPT | None |

## 3. Claude Connectors Directory

| # | Requirement (source, read 15 Nov 2026) | Status | Evidence | Smallest fix |
| --- | --- | --- | --- | --- |
| C-1 | Remote server over HTTPS | met | `server.json:15` (`https://krusgraph.com/mcp`) | — |
| C-2 | OAuth 2.0; a `401` with `WWW-Authenticate: Bearer resource_metadata=…`; protected resource metadata whose `resource` equals the URL | met | `fabric_backend/entra.py:10-11`, `:78`, `:93-94` | — |
| C-3 | Callback `https://claude.ai/api/mcp/auth_callback` registered (Anthropic-held client) | met | `deploy/SUBMISSION.md:49` | — |
| C-4 | Entra: the MCP URL registered as Application ID URI | met | `deploy/SUBMISSION.md:17` (`https://krusgraph.com/mcp`) | — |
| C-5 | Claude Code: loopback redirect on any port for `localhost` and `127.0.0.1` | met at `/mcp/connect` | `fabric_backend/registration.py:262-288` (`redirect_problem`); `docs/CLIENT-REGISTRATION.md:73` | — |
| C-6 | PKCE S256 advertised; CIMD needs `client_id_metadata_document_supported` and `none` | met for `/mcp/connect` | `fabric_backend/registration.py:691-698` | — |
| C-7 | Refresh errors answer `invalid_grant`; refresh tokens rotated for public clients | met | `fabric_backend/registration_flow.py:567-599` | — |
| C-8 | Every tool has a `title` and `readOnlyHint` or `destructiveHint` | met | `fabric_backend/server.py:366-367`, `:429-458` (title copied into annotations); `tests/test_submission.py:31` | — |
| C-9 | Read and write in separate tools; no catch-all request tool | met | 31 read-only and 10 creating tools, each with one purpose (`fabric_backend/tool_status.py` `_RAW`) | — |
| C-10 | Custom query tools name the target API | met | `query_graphql` runs GraphQL against "an API for GraphQL item" the user names (`server.py:3089`) | — |
| C-11 | Tool names at most 64 characters | met | longest is `export_item_definitions` (23) | — |
| C-12 | Narrow, accurate descriptions; no promotion; nothing that steers the model or interferes with other tools | met with three edits suggested (section 6) | `tests/test_c1_tool_description_wording.py` passes on all 40 hosted tools | edits E1 to E3 for the owning round |
| C-13 | Actionable errors, no bare "Internal Server Error" | met | `fabric_backend/errors.py:98` (`{error, kind, hint}`), `:341` (`safe`) | — |
| C-14 | Responses reasonably sized | met | `server.py:3163` (bounded JSON), `MAX_RESULT_CHARS` | — |
| C-15 | Privacy policy URL | met | `/privacy` (`server.py:3327`) from `fabric_backend/page_templates/PRIVACY.md` | — |
| C-16 | Documentation URL, support contact, icon | met | `/docs`, `/support` (`fabric_backend/pages.py:51`), `/favicon.ico` (`deploy/SUBMISSION.md:22`) | — |
| C-17 | Test account: sandbox with sample data, not a customer account; write tools exercisable "on real resources"; credentials not in the portal | **gap** | `deploy/SUBMISSION.md:20` (reviewer is Viewer on `demo` only, so the creating tools cannot create); `:112` and `:129` (password typed into the portal, which the page now says not to do) | Give the reviewer Contributor on a separate review workspace with the synthetic `shop` schema. Change SUBMISSION.md answer 8 to "test access on request by email" |
| C-18 | MCP App: 3 to 5 PNG carousel screenshots, at least 1000 px wide, cropped to the app response, a prompt for each | **gap** | `deploy/SUBMISSION.md:131` says "Not an MCP App". Since n227 the server shows chat cards (`fabric_backend/mcp_apps*.py`; `server.py:675` `meta=_mcp_apps.tool_meta()`) | Take 3 to 5 screenshots on the synthetic demo once n227 releases. Correct line 131 |
| C-19 | Allowed link URIs (optional) for `ui/open-link` | unknown | `fabric_backend/mcp_apps_build.py:366`, `:399` open Fabric portal addresses, which belong to Microsoft | Declare none. Only origins Krusgraph owns may be listed, so users confirm each Fabric link |
| C-20 | Tested in Claude, every tool | partly met | `fabric_backend/tool_status.py` `LIVE_RUN`, `LATER_LIVE`; `create_views` and `create_data_agent` have no recorded creating run (`CREATE_RECORD`) | Run the remaining creating calls once on the demo workspace before ticking "Test & launch" |
| C-21 | Seven compliance acknowledgements | founder | `deploy/SUBMISSION.md` answer 9 | Founder ticks them in the portal |

## 4. ChatGPT (plugin with an MCP server) — all requirements Unverified

| # | Requirement (excerpts, see section 1) | Status | Evidence | Smallest fix |
| --- | --- | --- | --- | --- |
| G-1 | Verified developer organisation (and domain) at OpenAI | unknown | nothing in the repository | Founder creates or verifies the OpenAI organisation for the company and the domain |
| G-2 | Public HTTPS MCP server | met | `server.json:15`; `/mcp/connect` is the address for clients other than Claude (`deploy/SUBMISSION.md:52-56`) | Submit `https://krusgraph.com/mcp/connect`, not `/mcp`: `/mcp` signs in with Anthropic-held credentials only |
| G-3 | OAuth with CIMD or DCR; ChatGPT's redirect accepted | unknown | CIMD and DCR are on (`fabric_backend/registration.py:691-698`). A CIMD redirect must be on the client id's host (`:512`), and `chatgpt.com` matches `chatgpt.com`. `docs/CLIENT-REGISTRATION.md:12`: "ChatGPT ha[s] not been tried" | Founder connects ChatGPT in developer mode to `/mcp/connect` once and records the result in CLIENT-REGISTRATION.md |
| G-4 | Annotations set correctly (read-only, destructive, open world) | met as declared; one choice to review | All 41 tools carry all three hints (`server.py:366-367`, `:463`). Note for the MCP tools round: `create_report` only adds an item and never updates, but it is declared `destructiveHint: true` (`server.py:1671`), which is the cautious choice | None needed. Changing it is a behaviour decision for the owning round, not this one |
| G-5 | Descriptions match behaviour, no promotion | met with edits E1 to E3 | as C-12 | as C-12 |
| G-6 | Demo account, fully featured, sample data, no MFA, no sign-up, works from outside, does not expire | **gap** | Reviewer account exists without an MFA prompt (`deploy/SUBMISSION.md:37-43`), but as Viewer only (`:20`), so it is not fully featured. Microsoft's mandatory MFA applies to the admin portals only (`:42-43`) | Same fix as C-17. Check before submitting that the password does not expire inside the review window |
| G-7 | Five positive test cases (scenario, prompt, expected tools, expected result) | **gap** (now drafted) | none in the repository before this round | Use section 7. The founder runs each one in ChatGPT developer mode and corrects the expected results |
| G-8 | Negative test cases (prompts that must not call the tools) | **gap** (now drafted) | as G-7 | Section 7 |
| G-9 | Privacy policy: collection, use, retention, sharing, contact | met | `fabric_backend/page_templates/PRIVACY.md:70-85` (what is processed and for how long), `:159-161` (third parties; "Microsoft Azure in the EU (Sweden Central)"), `:172` (contact) | Check that the published `/privacy` names OpenAI beside Anthropic: line 163 names Anthropic's policy only (a text edit to PRIVACY.md, held by n234 for its visitor wording) |
| G-10 | Minimal data collection; no conversation data | met | `PRIVACY.md:26-39` (counts, not row values, except sample rows and queries the user asks for); usage record without user id (`:82`) | — |
| G-11 | Terms and support URLs | met | `/terms` and `/support` (`fabric_backend/pages.py:51`, `:71`); `/terms` is titled "Preview terms" | Founder decides whether preview terms are enough to submit |
| G-12 | Screenshots, and possibly a reviewer video | gap | none for ChatGPT | Take them in developer mode after G-3 works |
| G-13 | Content suitable for all audiences, usage policies | met | data modelling tools; no generated media | — |

## 5. Official MCP Registry

| # | Requirement | Status | Evidence | Smallest fix |
| --- | --- | --- | --- | --- |
| R-1 | `server.json` valid against the schema, a domain namespace verified by DNS | met | `server.json:2-3`; `docs/PUBLISHING.md` | — |
| R-2 | `description` at most 100 characters, `version` equal to `pyproject.toml` | met | `server.json:5-6`; checked by `python -m pytest` (`docs/PUBLISHING.md`, "Before you start") | — |
| R-3 | Remote publicly reachable | met | `server.json:12-16` | — |
| R-4 | A text change needs a new version | met as a rule | `docs/MCP-REGISTRY.md:190-192` | — |

The registry and Claude's directory read tool texts the same way. ChatGPT reads them through the plugin. None of the
three takes a "recommend this" field. What decides whether a model calls a tool is how well the description matches
the user's request, so the edits below aim at precision, not reach.

## 6. Description edits for the owning rounds

No tool was changed in this round. These are text edits only, for the round that holds **MCP tools and errors**
(`fabric_backend/server.py`; n227 holds `start` and the cards' words, so E1 goes to n227 or its successor). Each keeps
the tool's behaviour.

| # | Tool | Now | Suggested | Why |
| --- | --- | --- | --- | --- |
| E1 | `start` (`server.py:471`) | "A guided path for a first or vague message ('start', 'start Krusgraph', 'help', 'what can you do', 'check my data')" | "A guided path through Krusgraph's tools for a user who asks to start Krusgraph or to check their Fabric data ('start Krusgraph', 'check my data in Fabric')." | 'help' and 'what can you do' match messages meant for the assistant or for other connectors. Claude's review rejects descriptions that "interfere with Claude calling other tools" |
| E2 | `plan_backend` (`server.py:580`) | "… and nothing is planned (n169)." | "… and nothing is planned." | An internal round number means nothing to a reviewer or a model |
| E3 | `domain_draft` (`server.py:1343`) | "Proposes domains from the plan. Returns JSON with interfaces and an ODCS contract per domain. Changes nothing." | "Proposes data domains from the plan: groups of tables with their interfaces and an ODCS data contract per domain. Requires workspace and source. Returns JSON. A proposal only; the domains are not created in Fabric. Changes nothing." | It is the only description without its required inputs and limits |
| E4 (optional) | `dbt_schema` (`server.py:1284`) | "Can sit beside dbt Labs' dbt-mcp, which runs dbt." | delete the sentence | It names another product's server. This is not promotion, but a reviewer may read it as pointing to an external tool |

`tests/test_c1_tool_description_wording.py` checks titles and descriptions of the hosted and the local server for
promotional or steering words ("always", "best", "recommend Krusgraph", "prefer this tool", "instead of other tools",
"guaranteed", "certified by" and similar). "best" occurs twice in its ranking sense ("counts the best against the
data") and is listed as an exact exempt phrase in the test. A new exemption should be added the same way, so that it
is visible in review.

## 7. Test cases (draft, synthetic data only)

These run against the demo workspace `demo`, lakehouse `demo_lh`, schema `shop`, all synthetic
(`fabric_backend.seed`). Expected results are taken from `docs/LIVE-TEST.md` and `fabric_backend/tool_status.py`.
The founder must rerun them in each client before pasting them into a portal.

**Positive**

| # | Scenario | Prompt | Expected tools | Expected result |
| --- | --- | --- | --- | --- |
| P1 | Find the data | "Which Fabric workspaces and lakehouses can I use?" | `list_workspaces`, `list_sources` | `demo` and `demo_lh` are listed, read-only |
| P2 | Plan keys and links | "Plan keys and relationships for schema shop in demo_lh." | `plan_backend` | Keys and relationships, each with its rule (K0–K5, R0–R5), and a Mermaid diagram. Nothing is created |
| P3 | Check against the rows | "Check the shop plan against the data." | `validate_plan` | On `shop`, 6 of 6 keys unique and 7 of 7 relationships without orphans (LIVE-TEST, 2 Nov 2026). Counts only, no row values |
| P4 | Draft before building | "Draft a Power BI semantic model for shop, but don't create anything." | `semantic_model_draft` | TMDL files and a README of decisions. Nothing is created |
| P5 | Build with confirmation | "Create the GraphQL API shop_api for shop. Show me the dry run first." | `create_backend` with `dry_run=true`, then with `dry_run=false` after the user confirms | The dry run says whether `shop_api` exists and what would change. The second call needs the confirmation and Contributor rights |

**Negative** (the tools should not be called, or should refuse)

| # | Prompt | Expected |
| --- | --- | --- |
| N1 | "What's the weather in Stockholm?" | No Krusgraph tool is called |
| N2 | "Delete the table orders in demo_lh." | No Krusgraph tool deletes anything; the assistant should say so |
| N3 | "Run this mutation on shop_api: mutation { deleteOrders … }" | `query_graphql` refuses mutations with `{error, kind, hint}`; nothing changes |

## 8. Founder only

These need a person, an account or a decision. No agent may do them (CONTRIBUTING.md, "What an agent must not do").

1. **OpenAI**: create or verify the developer organisation for the company and the domain. Allow the domains
   developers.openai.com and help.openai.com in the agent environment's network settings so the next round can read
   the current rules. All of section 4 is Unverified until then.
2. **ChatGPT developer mode**: connect `https://krusgraph.com/mcp/connect`, sign in, and run P1 to P5 and N1 to N3.
   Record the result in `docs/CLIENT-REGISTRATION.md` (G-3).
3. **Review account**: a separate review workspace with the synthetic `shop` data, with the reviewer as Contributor
   there and nowhere else. Check there is no MFA prompt and no password expiry during review. Give the credentials
   only in OpenAI's "Review details" field and by email to Anthropic when asked, never in the repository or in
   Anthropic's portal (C-17, G-6).
4. **Policy text**: add OpenAI beside Anthropic in `/privacy` (G-9). Decide whether the "Preview terms" page is enough
   (G-11).
5. **Screenshots**: 3 to 5 PNGs of the chat cards for Claude (C-18) and the ones ChatGPT asks for (G-12), on synthetic
   data only.
6. **Submit**: Claude via claude.ai/directory/manage (seven acknowledgements). ChatGPT via OpenAI's plugin
   submission. The registry entry is already published. A text change to a tool needs a new registry version
   (R-4).
