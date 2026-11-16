# Directory submission pack: Claude's Connectors Directory and ChatGPT

Round D2, 16 November 2026. This file holds the text to paste into each directory's form, one field at a time, with the
founder's steps in order. It builds on round C1's [CATALOG-READINESS.md](CATALOG-READINESS.md), which lists each
directory's requirements, the gaps and the description edits E1 to E4. Nothing here was submitted, published or sent.
The founder submits from his own accounts (CONTRIBUTING.md, "What an agent must not do").

No directory promises a listing, a placement or that an assistant will suggest a connector. Each one scans or reviews a
submission. After that, the model decides when to call a tool from what the user asks and what the tool's description
says. This pack therefore aims at accurate descriptions in the words people use for their problem, not at reach.

No password, client secret, token or workspace id belongs in this file or anywhere in the repository. Where a form asks
for credentials, this pack says how the founder gives them privately.

`tests/test_d2_directory_submission.py` checks this file on every change: each field's length against the form's limit,
C1's wording test (`tests/test_c1_tool_description_wording.py`) and the site's sales words on every field, no
credential-like value, the URLs against the site's own routes, and the registry description against the site.

## 1. Sources

| Directory | Source | Read |
| --- | --- | --- |
| Claude Connectors Directory | https://claude.com/docs/connectors/building/submission (the ten portal steps, the listing limits, the screenshot specification) | opened 16 Nov 2026 |
| | https://claude.com/docs/connectors/building/review-criteria, /authentication, /testing | opened 15 Nov 2026 by C1 |
| ChatGPT (apps submitted as plugins) | https://developers.openai.com/apps-sdk/app-submission-guidelines and the pages C1 lists | **Unverified**: developers.openai.com did not resolve from this session on 16 Nov 2026 either. The ChatGPT fields below are the ones C1 found in search excerpts. Read the form itself before pasting |
| Official MCP Registry | [MCP-REGISTRY.md](MCP-REGISTRY.md), [PUBLISHING.md](PUBLISHING.md); `https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph/krusgraph` | read 16 Nov 2026 |

## 2. Shared text (both directories)

The same words go to both forms, so a person who meets Krusgraph in either assistant reads the same thing.

Field: name

```text
Krusgraph for Microsoft Fabric
```

Field: one_liner

```text
See how your Microsoft Fabric tables connect, SAP tables included: keys and relationships with the rule behind each, checked against the rows, then a semantic model, report or API.
```

Field: description

```text
Krusgraph reads the tables in a Microsoft Fabric lakehouse, warehouse or SQL database and proposes their keys and relationships, each with the rule behind it. Declared keys come first, then rules on column names. validate_plan checks the plan against the data: duplicate keys, NULL keys and rows with no match, returned as counts, not row values.

For SAP tables in Fabric (VBAK, VBAP, KNA1, LIKP, VBRK and others, with or without a prefix), the keys include the client MANDT, and the order-to-cash relationships come from an SAP pack that cites SAP's public documentation. The pack has not been verified against an SAP system.

From the reviewed plan it drafts, without creating anything: a Power BI semantic model in TMDL (Direct Lake), silver and gold notebooks for data engineering in the lakehouse, a data dictionary, dbt tests, a Fabric IQ ontology, and data domains with a data contract each for data products. It flags an amount that a join would sum once per line, such as an order total that doubles.

When the user confirms, it creates items in the user's own workspace: an API for GraphQL, a semantic model, a Power BI report, notebooks, a pipeline, views, an ontology or a data agent. Each creating tool shows a dry run first, and none deletes anything.

Sign-in is with the user's own Microsoft Entra work account, and every call runs with that account's Fabric permissions. Metadata, sample rows and query results pass through and are not kept after the request. Open source under the MIT licence, made by Kruse Consulting AB. Not affiliated with Microsoft or SAP.
```

Field: website

```text
https://krusgraph.com/
```

Field: documentation_url

```text
https://krusgraph.com/docs
```

Field: privacy_url

```text
https://krusgraph.com/privacy
```

Field: terms_url

```text
https://krusgraph.com/terms
```

Field: support_url

```text
https://krusgraph.com/support
```

Field: support_email

```text
hello@krusgraph.com
```

Field: icon

```text
https://krusgraph.com/static/icon-512.png
```

The icon is the site's own mark, 512 × 512 PNG (`fabric_backend/static/icon-512.png`). A vector version is at
`https://krusgraph.com/static/favicon.svg`. Upload the PNG where a form asks for a file.

Field: company

```text
Kruse Consulting AB
```

### The words people use

There is no keyword field in Claude's portal (steps 1 to 10, section 3), and none was seen for ChatGPT. The words
below are those people use when they ask about the problem. They are in the one-liner and the description where they
are accurate, and in the two explainer articles (section 7), not in a hidden list.

| People ask about | Where it is said |
| --- | --- |
| SAP on Fabric, SAP tables (VBAK, VBAP, KNA1, LIKP, VBRK) | description, paragraph 2; article 1 |
| keys and relationships | one-liner; description, paragraph 1; both articles |
| lakehouse | description, paragraphs 1 and 3 |
| semantic model, Power BI report | one-liner; description, paragraphs 3 and 4; article 2 |
| data products | description, paragraph 3 (data domains with a data contract each) |
| data engineering | description, paragraph 3 (silver and gold notebooks) |
| Microsoft Fabric | name, one-liner, description |

## 3. Claude Connectors Directory

Portal: https://claude.ai/directory/manage, **Submit**, **MCP connector**. The portal has ten steps (source: the
submission page, opened 16 Nov 2026). Each row says what to enter. Text fields are the shared ones in section 2.

| Step | What the portal asks | What to enter |
| --- | --- | --- |
| 1 Connection | the server's `https://` URL, one for every user | `https://krusgraph.com/mcp` |
| 2 Tools | synced from the server, grouped read-only and write | nothing to type. 40 tools, each with a `title` and `readOnlyHint` or `destructiveHint` (`tests/test_submission.py`). Fix any flag on the server, not in the portal |
| 3 Listing | server name (up to 100 characters), one-liner (up to 200), description (up to 2,000), one to five categories, documentation URL, privacy policy URL, support contact, icon, URL slug (permanent once published) | name, one_liner, description, documentation_url, privacy_url, support_email, icon from section 2. Categories: the two closest to "Data & Analytics" and "Developer tools" in the portal's list (the names C1 and `deploy/SUBMISSION.md` recorded; the list itself is only in the portal). Slug: `krusgraph` |
| 4 Use cases | primary use cases, what users need before they connect, read or write | the three use cases below; prerequisites below; **read and write** |
| 5 Company | company name, website, a primary contact for review updates | Kruse Consulting AB, `https://krusgraph.com/`, the founder with hello@krusgraph.com |
| 6 Authentication | whether sign-in is required, how users sign in, the OAuth client Anthropic holds | **Required**. OAuth with **Anthropic-held client credentials**: the Entra app's client ID and a client secret, typed by the founder into the portal (section 3.1). No extra headers |
| 7 Data handling | own API, a partner's with permission, or a third party's; personal health data; sponsored content | "proxied from a partner's API with permission" (Microsoft Fabric's public APIs, on behalf of the signed-in user). Personal health data: "depends on configuration" (nothing is stored; a customer's own tables pass through under their permissions). Sponsored content: none |
| 8 Test & launch | confirmation that every tool was run as a custom connector; **no credentials in the portal** | confirm only after the runs in section 5 are done. Test access is given by email when a reviewer asks (section 5.1) |
| 9 Compliance | seven acknowledgements | the founder reads and ticks each one |
| 10 Review and submit | a final check; quality warnings are shared with the review team | read every warning before submitting |

**MCP App fields.** Krusgraph's tools answer with chat cards (MCP Apps, round n227), so the listing takes 3 to 5
carousel screenshots: PNG, at least 1000 px wide, cropped to the app response without the prompt, with the prompt text
given separately for each. No separate mobile images and no video. They are in section 6. Allowed link URIs: **none**.
The cards open Fabric portal addresses, which belong to Microsoft, and only origins the submitter owns may be listed
(C1, C-19). Users confirm each such link.

**Use cases (step 4).**

1. Understand an unfamiliar lakehouse or warehouse: list the tables, plan keys and relationships with the rule behind
   each, and check the plan against the rows.
2. SAP tables in Fabric: see how VBAK, VBAP, KNA1, LIKP, VBRK and the other order-to-cash tables connect, with the
   client MANDT in every key, and find an order value that a join would count once per item.
3. From a checked plan to Power BI and data engineering items: draft or create a semantic model, a report, silver and
   gold notebooks, a pipeline or an API for GraphQL, each with a dry run first.

Prerequisites: a Microsoft Fabric capacity and workspace; a Microsoft Entra work account with access to it (Viewer to
read, Contributor to create); an Entra administrator's one-time consent for the organisation.

### 3.1 OAuth details (Claude)

| Item | Value |
| --- | --- |
| Server URL | `https://krusgraph.com/mcp` |
| Protected resource metadata | `https://krusgraph.com/.well-known/oauth-protected-resource` (a `401` carries `WWW-Authenticate: Bearer resource_metadata=…`) |
| Authorization server | Microsoft Entra ID, multi-tenant app, tokens v2 |
| Application ID URI | `https://krusgraph.com/mcp`, scope `user_impersonation` |
| Redirect URI registered | `https://claude.ai/api/mcp/auth_callback` (Web) |
| Client credentials | Anthropic-held: client ID and secret entered in step 6 by the founder. Never in the repository or in a chat |
| Delegated permissions | listed in [SCOPES.md](SCOPES.md); `deploy/krusgraph.sh --check` verifies them |
| Admin consent | once per customer organisation, as `/start` describes |

## 4. ChatGPT (plugin with an MCP server) — fields Unverified

C1 could read only search excerpts of OpenAI's pages, and this round could not open them either. Check every field
against the form before pasting. The shared text of section 2 fits any length C1 saw.

| Field (as C1 found it) | What to enter |
| --- | --- |
| Developer organisation, verified (and the domain) | the founder's OpenAI organisation for Kruse Consulting AB and `krusgraph.com` (C1, G-1) |
| MCP server URL | `https://krusgraph.com/mcp/connect`, not `/mcp`: `/mcp` signs in only with the client Anthropic holds (C1, G-2) |
| Name, short and long description | name, one_liner, description from section 2 |
| Website, privacy policy, terms, support | website, privacy_url, terms_url, support_url (or support_email) from section 2. `/privacy` names OpenAI's policy beside Anthropic's for what the AI client does with the answers |
| Icon | icon from section 2 |
| Tool annotations | already on the server: every tool carries `readOnlyHint`, `destructiveHint` and `openWorldHint` (C1, G-4) |
| Test cases | the five positive and three negative cases in section 5, with the expected results the founder sees in developer mode |
| Review details: test credentials | entered by the founder in the form's "Review details" field only, never in the uploaded package (section 5.1) |
| Screenshots (possibly a video) | taken in ChatGPT's developer mode after the sign-in works (C1, G-12); the Claude screenshots of section 6 are not a substitute |

### 4.1 OAuth details (ChatGPT)

| Item | Value |
| --- | --- |
| Server URL | `https://krusgraph.com/mcp/connect` |
| Protected resource metadata | `https://krusgraph.com/.well-known/oauth-protected-resource/mcp/connect` |
| Authorization server | Krusgraph's own, at krusgraph.com, which then signs the user in with Microsoft Entra ([CLIENT-REGISTRATION.md](CLIENT-REGISTRATION.md)) |
| Client registration | client ID metadata documents (CIMD) or dynamic client registration; PKCE S256; a consent page per client |
| Redirect | ChatGPT's own, reported as `https://chatgpt.com/connector_platform_oauth_redirect` (**Unverified**). With CIMD the redirect must be on the client id's host |
| Tried | **not yet**: no ChatGPT sign-in has been recorded ([CLIENT-REGISTRATION.md](CLIENT-REGISTRATION.md), C1 G-3). The founder tries it in developer mode before submitting |

## 5. Test instructions (synthetic data only)

All tests run on synthetic data in the demo tenant: workspace `demo`, lakehouse `demo_lh`, schema `shop`
(`fabric_backend/seed.py`). The SAP case needs the SAP-shaped schemas in the same lakehouse
(`seed(spark, schema="shop", sap=True)`, `fabric_backend/sap_sample.py`: synthetic, not SAP data). The expected results
are the engine's on that data. The founder runs each one in each client before pasting it into a form and corrects
what differs.

| # | Scenario | Prompt | Expected tools | Expected result |
| --- | --- | --- | --- | --- |
| P1 | Find the data | "Which Fabric workspaces and lakehouses can I use?" | `list_workspaces`, `list_sources` | `demo` and `demo_lh` are listed; nothing changes |
| P2 | Plan keys and relationships | "Plan keys and relationships for schema shop in demo_lh." | `plan_backend` | keys and relationships, each with its rule, and a diagram; nothing is created |
| P3 | Check against the rows | "Check the shop plan against the data." | `validate_plan` | 6 of 6 keys unique and 7 of 7 relationships without orphans (live, 2 Nov 2026); counts only, no row values |
| P4 | Draft a semantic model | "Draft a Power BI semantic model for shop, but don't create anything." | `semantic_model_draft` | TMDL files and a README of decisions; nothing is created |
| P5 | Create with a dry run | "Create the GraphQL API shop_api for shop. Show me the dry run first." | `create_backend` with `dry_run=true`, then `dry_run=false` after the user confirms | the dry run says whether `shop_api` exists and what would change; the second call needs the confirmation and Contributor rights |
| P6 | SAP tables (optional; needs the SAP-shaped schemas) | "How do the SAP sales tables in schema sap_sd connect? Check them against the rows." | `plan_backend`, `validate_plan` | keys with MANDT from the SAP pack; "12 of 12 keys unique, 15 of 19 relationships hold without orphans" (the hosted tool on the same rows behind a fake Fabric, `tests/test_d2_explainers.py`; not yet run in Fabric) |
| N1 | Unrelated question | "What's the weather in Stockholm?" | none | no Krusgraph tool is called |
| N2 | Delete request | "Delete the table orders in demo_lh." | none that deletes | no Krusgraph tool deletes anything; the assistant says so |
| N3 | A mutation | "Run this mutation on shop_api: mutation { deleteOrders … }" | `query_graphql` | refused with `{error, kind, hint}`; nothing changes |

### 5.1 Credentials

- **Claude.** "Don't put credentials in the portal." A Community listing needs none. If the listing goes to Verified
  review, a reviewer asks for test access by email, and the founder answers that email privately.
- **ChatGPT.** The form's "Review details" field, typed by the founder, and nowhere else (Unverified, C1).
- **Both.** The reviewer account is a work account in the company's own tenant, with no admin role and no MFA prompt,
  on a review workspace with the synthetic data only. Its password does not expire during the review. Today it is a
  Viewer on `demo` only, so the creating tools cannot create anything for a reviewer: C1's gap C-17 and G-6, still
  open (section 9).

## 6. Screenshots of the chat cards

Folder: `docs/directory/screenshots/`, each image with its caption and prompt in `docs/directory/screenshots/README.md`.
They are taken from main after round n227 releases the chat cards, at 1280 px and 375 px wide, on the synthetic shop
and the SAP-shaped samples. The Claude carousel takes the 1280 px images (at least 1000 px wide). The 375 px images show
the same cards at phone width, for review only.

**Not taken yet.** Round n227 held the chat cards from 22:30 UTC on 15 November 2026 and had not released them by 05:24 UTC on 16 November (main polled every 10 minutes for two hours), so no screenshot is in the repository. The script is ready: `python docs/directory/shoot.py` (with `docs/directory/shoot_host.js`) renders five cards (start and plan on the shop, the check on the shop, the plan and the check on `sap_sd`) at 1280 and 375 px. Run it after n227 releases, add `README.md` with a caption and the prompt per image (the prompts are in `SHOTS` in the script), and `tests/test_d2_directory_submission.py` then checks the images against the carousel's specification.

## 7. Public pages that explain the problems

Two articles on krusgraph.com, written for people who search with a problem. Each one is built on the SAP-shaped sample,
and every number in it is checked against the engine by `tests/test_d2_explainers.py`. Both are in the sitemap and
`llms.txt` through `BLOG_POSTS` in `fabric_backend/pages.py`. They are live once the founder deploys.

| Article | URL |
| --- | --- |
| How SAP sales tables connect in Fabric (VBAK, VBAP, KNA1, LIKP, VBRK) | https://krusgraph.com/blog/sap-sales-tables-in-fabric |
| From SAP tables to a Power BI report in Fabric: keys, relationships and the doubled-total trap | https://krusgraph.com/blog/sap-tables-to-power-bi-report |

## 8. MCP Registry metadata

`server.json` already carries the site's one-line description: "See how your tables connect: the rule behind every
proposed link, and the counts from the check." (`fabric_backend/discovery.DESCRIPTION`, 96 characters, the same text in
the MCP Server Card at `/mcp/server-card`; `tests/test_site.py` keeps them equal). The registry still shows the text
published with 0.8.0 on 28 October 2026, "Turn Microsoft Fabric tables into an explainable graph and a GraphQL API."
(read 16 Nov 2026). A published version cannot be changed, so the new text goes out with the next version.

The publish step, prepared and not run. On the private laptop, from the repository root, after the next release raises
the version from 0.8.0 to 0.8.1 in `pyproject.toml`, `fabric_backend/__init__.py` and `server.json` (and tags it
`v0.8.1`, which the drift monitor's notebook installs, [PUBLISHING.md](PUBLISHING.md)):

```bash
python -m pytest -q tests/test_r1_mcp_registry.py tests/test_site.py
PRIVATE_KEY="$(openssl pkey -in key.pem -noout -text | grep -A3 "priv:" | tail -n +2 | tr -d ' :\n')"
mcp-publisher login dns --domain krusgraph.com --private-key "${PRIVATE_KEY}"
mcp-publisher validate
mcp-publisher publish
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph/krusgraph"
```

The last line should show 0.8.1 with `"isLatest":true` and the new description. One decision before it is still open
([MCP-REGISTRY.md](MCP-REGISTRY.md)): whether the entry's remote stays `https://krusgraph.com/mcp` or becomes
`https://krusgraph.com/mcp/connect`, the address that VS Code and other self-registering clients can sign in to.

## 9. Still open

| Item | Owner | State |
| --- | --- | --- |
| E1 `start`: drop "help" and "what can you do" from the description | the round holding the chat cards (n227 holds `start`) | open: not released to this round |
| E2 `plan_backend`: drop "(n169)" | — | done before this round: the description already ends "and nothing is planned." |
| E3 `domain_draft`: inputs and limits in the description | MCP tools and errors (open), but the tool listing's golden file `tests/golden/hosted_listing.json` is held by n227 | open: the text change moves that golden file |
| E4 `dbt_schema`: drop the sentence on dbt Labs' dbt-mcp (optional) | as E3 | open, for the same reason |
| Reviewer account as Contributor on a separate review workspace with the synthetic data (C-17, G-6) | founder | open |
| The remaining creating calls run once on the demo workspace before step 8 (C-20) | founder | open |
| ChatGPT sign-in tried in developer mode (G-3) | founder | open |
| `deploy/SUBMISSION.md` answer 3 and `plugin/krusgraph` still use the old one-liner ("an explainable graph and a GraphQL API") | Docs and submission; the plugin | open; this pack's section 2 replaces answer 3 |
| A tool text change needs a new registry version (R-4) | founder, at the next release | open |

## 10. The founder's steps, in order

1. Deploy main (`bash deploy/krusgraph.sh --update`), so krusgraph.com serves the two articles and the current tool
   texts. Read both articles first: they carry your byline as the blog does.
2. Make the reviewer account a Contributor on a separate review workspace with the synthetic `shop` data (and the
   SAP-shaped schemas for P6), with no MFA prompt and no password expiry during review.
3. Run P1 to P6 and N1 to N3 in Claude as a custom connector, and the remaining creating calls once (C-20).
4. Claude: open https://claude.ai/directory/manage, **Submit**, **MCP connector**, and work through the ten steps with
   section 3. Upload the 1280 px screenshots of section 6 with their prompts. Enter the client ID and secret in step 6
   yourself. Put no credentials anywhere else.
5. OpenAI: create or verify the developer organisation and the domain. In ChatGPT's developer mode, connect
   `https://krusgraph.com/mcp/connect`, sign in, run the same cases and take screenshots there.
6. ChatGPT: submit with section 4, checking each field against the form. Credentials only in "Review details".
7. Registry: at the next release, run the commands in section 8.
8. Record each submission's date and status in `deploy/SUBMISSION.md`. A listing is not described as accepted anywhere
   until the directory says so.
