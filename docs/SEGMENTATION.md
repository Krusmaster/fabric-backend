# Segmentation: candidate offers by where Krusgraph runs and what agent it needs (internal, not on the site)

Written 6 November 2026 (round n121). Not linked from the site. A working note for Gustav, not a decision.

**What is not known.** Prices, customers and demand are unknown. No segment below has a named customer, a
measured demand or a price; no figure in this note is a market figure. Every "exists today" line points at a file in
this repository as it stands on 6 November 2026; every "missing" line is a gap seen in the repository, not a promise.

## The input

A market observation from a Microsoft contact, 6 November 2026, given orally to Gustav and recorded here in his words:
customers choose agents along two lines.

1. **Where the agent runs**: a region, a country, in-house in their own environment, or on the laptop. This should
   match where their data access is.
2. **How capable and costly an agent each task needs.**

This is one person's observation, not a Microsoft statement or programme. Nothing here says anything about Microsoft
programmes beyond what Microsoft's public documentation says, and this note cites none.

## What the repository shows today

Krusgraph runs in four places (the Concepts page "Where it runs": `fabric_backend/concepts.py`, `WHERE_COLS`,
`WHERE_ROWS`, `where_cells()`, `where_md()`; the test `tests/test_n117_where_it_runs.py`):

| Place | Where the data access is | Source |
| --- | --- | --- |
| In the browser, `/check` | The visitor's files, read in the browser and not uploaded; nothing calls Fabric | `fabric_backend/browser_check.py`, `fabric_backend/static/check-worker.js`, `docs/TRUST.md` "Where it runs" |
| On the own computer: library, CLI `fabric-backend`, local MCP server `fabric-backend-mcp` | One ODBC connection from the machine (SQL Server, Azure SQL, a Fabric SQL endpoint) | `fabric_backend/mcp_server.py`, `fabric_backend/platforms/local.py`, `docs/LOCAL.md`, `tool_status.LOCAL_TOOLS` |
| In the customer's own Azure tenant | The customer's Fabric, through the customer's own Entra app, in the region they set | `deploy/krusgraph.sh`, `deploy/azure_containerapp.py`, `deploy/krusgraph.example.json` (`location`), `deploy/KRUSGRAPH-START.md` |
| Hosted, Azure Sweden Central | The person's Fabric, delegated through Entra; no table contents stored | `deploy/krusgraph.example.json` (`"location": "swedencentral"`), `docs/TRUST.md`, the `/it` page (`fabric_backend/page_templates/it.html`) |

These are not packaged as separate offers: there is one site, one pricing note (`docs/PRICING-NOTES.md`, a decision
not taken) and a dormant entitlement switch (`fabric_backend/entitlements.py`, off unless `KRUSGRAPH_ENTITLEMENTS=1`).

**On the second line (agent tier):** Krusgraph calls no language model itself (no `anthropic` or `openai` import in
`fabric_backend/`). The agent is the customer's own MCP client and model, under the customer's own agreement with that
vendor (`docs/TRUST.md`, Subprocessors). What Krusgraph decides is how much work is done by deterministic code (keys,
orphans, the total that doubles, drafts) and how much is left to the model. So "agent tier" below means the class of
model and client a task plausibly needs, which is the customer's choice and cost, not Krusgraph's. Which tier a task
really needs has not been measured.

Rough task classes, from the tools' own kind in `fabric_backend/tool_status.py` (`READS`, `DRAFT`, `CREATES`):

- **Light**: run a check and relay its counts (`validate_plan`, `list_tables`, `data_dictionary`). The engine does the
  work; a small, cheap model could plausibly drive it. Not tested with a small model.
- **Middle**: choose among drafts, read `review_plan` findings, assemble a semantic model or dbt hand-over.
- **Heavy**: multi-step creating sessions in Fabric (`create_backend`, `create_semantic_model`, the pipeline from
  n120), where a wrong step creates an item. Tested end to end with Claude and no other client so far (`tool_status.LIVE_RUN_DATE`).

## Candidate segments

Four candidates. Each is a hypothesis to test, not a finding.

### A. Try it with no account: the browser check

- **Who for**: a data engineer or analyst who wants to see what Krusgraph finds before anyone signs anything; a
  consultant before a first meeting.
- **Where it runs**: the visitor's browser; data never leaves it.
- **Tools and agent tier**: no agent at all; the engine runs in Pyodide. Checks (keys, orphans, totals a join repeats)
  and downloads (.pbip model, ontology RDF, app starter, evidence report).
- **Exists today**: `/check` live (`fabric_backend/browser_check.py`, `fabric_backend/browser_build.py`,
  `fabric_backend/static/check.js`).
- **Missing**: no dbt, notebooks or pipeline in the browser (`concepts.where_cells()`, Draft row); no path from a
  finished check to one of the other segments beyond links; no measure of how many people use it (the usage record in
  `fabric_backend/usage.py` covers tool calls on the server, not `/check`).
- **Questions for Gustav**: is this just a free entry point, or an offer of its own? Should anything be counted here,
  given the page's promise that files are not uploaded?

### B. On the laptop: local MCP server and CLI against a database the person can already reach

- **Who for**: a person whose data access is from their own machine (an on-prem SQL Server, Azure SQL, a Fabric SQL
  endpoint over ODBC) and who may not be allowed to send metadata to a hosted service.
- **Where it runs**: the person's computer; nothing but the queries to the database leaves it (`docs/LOCAL.md`).
- **Tools and agent tier**: the 17 tools in `tool_status.LOCAL_TOOLS`; drafts and checks, `create_views` and
  `create_backend` as dry runs by default. Light to middle tier; the model is whatever the person's client uses, which
  could be a local model, but that has not been tried.
- **Exists today**: `fabric-backend-mcp` (experimental), run on 28 October 2026 against SQL Server 2022 in a container
  (`docs/LOCAL.md`); `fabric-backend demo` (`docs/DEMO-20-MIN.md`).
- **Missing**: not run on Windows with Windows sign-in, nor started from Claude Desktop (`docs/LOCAL.md`, status);
  drafts that are hosted and not local (`gold_views_draft`, `drift_monitor_draft`, the pipeline) are not local; no packaged installer;
  no test with a small or local model.
- **Questions for Gustav**: stays free and open source (as `docs/PRICING-NOTES.md` proposes), or a paid support
  offer around it? Is a test with a small or on-device model worth a round?

### C. In the customer's own tenant and region

- **Who for**: an organisation whose rules say the service must run in their own Azure subscription, in a region or
  country they choose, next to their Fabric capacity.
- **Where it runs**: the customer's Azure tenant, the region set by `location` in their `deploy/krusgraph.json`;
  nothing passes through Kruse Consulting.
- **Tools and agent tier**: all hosted tools; the creating tools that need permissions the hosted app does not ask for
  (`create_semantic_model`, `create_data_agent`, `create_ontology`: `OPERATOR` in `tool_status.py`) are the customer's
  own decision in their own Entra app. Middle to heavy tier.
- **Exists today**: `deploy/krusgraph.sh`, `deploy/azure_containerapp.py`, `deploy/KRUSGRAPH-START.md`,
  `docs/OPERATIONS.md`; MIT licence.
- **Missing**: not yet run by a customer (Where it runs, Status row); no written support or update terms for a
  self-run copy; no guide that maps a region choice to where the customer's Fabric capacity is; the usage record
  (`fabric_backend/usage.py`) stays in their tenant, so Kruse Consulting sees nothing, which is the point but leaves
  no signal of use.
- **Questions for Gustav**: what would be sold here: setup, support, updates, nothing? Who answers when their deploy
  breaks?

### D. Hosted in Sweden Central, signed in with Entra

- **Who for**: a Fabric team that is fine with a service run by Kruse Consulting in an EU region and wants it working
  today without operating anything.
- **Where it runs**: Azure Container Apps, Sweden Central; every call as the signed-in person, delegated permissions,
  no table contents stored (`docs/TRUST.md`).
- **Tools and agent tier**: the full hosted set; tested end to end with Claude on 27 October 2026
  (`tool_status.LIVE_RUN`); later creating calls in `tool_status.LATER_LIVE`. Middle to heavy tier.
- **Exists today**: the live service, `/it`, `docs/TRUST.md`, `docs/DPA-DRAFT.md`, `docs/PILOT.md`, the dormant
  entitlement check.
- **Missing**: a single region; no pricing (`docs/PRICING-NOTES.md`: not decided); DPA is a draft; clients other
  than Claude are listed per client in `tool_status.py`, not all tested end to end; maintained by one person with no
  fixed response time (`SECURITY.md`).
- **Questions for Gustav**: a second region (or country-specific hosting) on a concrete request, or not at all,
  pointing such requests to C?

### Possible fifth: a light, non-creating server for small models

Not a place but a cut along the second line: a server with the creating tools and `sample_rows` switched off (idea 3
in `docs/LANDSCAPE.md`, "Server-wide switches"), meant for cheap, high-volume checking by a small model, run in B, C or
D. Nothing of it exists beyond the idea; listed so Gustav can say yes or no to it as a segment.

## Gaps across segments

1. No offer packaging: the four places share one site and no per-place terms (`docs/PRICING-NOTES.md`).
2. The agent-tier line is unmeasured: no tool has been run with a small or local model; Claude is the client tested end to
   end (`tool_status.py`).
3. No server switch that turns the creating tools off (`docs/LANDSCAPE.md`, idea 3), which a light-tier or a cautious in-house segment would
   want.
4. The local server is untried on Windows sign-in and from Claude Desktop (`docs/LOCAL.md`).
5. The own-tenant deploy has not been run by a customer, and has no support terms.
6. The hosted service has one region.
7. No demand data for any of this: `fabric_backend/usage.py` counts hosted tool calls and nothing else.

`docs/COMPARISON-MYRIADE.md` is relevant to C and D: there, self-hosting is described as on request and the images
as private (quoted from that project's own README); Krusgraph's own-tenant path is the open-source script. That is a
difference in packaging, not evidence of demand.

## Open questions for Gustav

1. Which of A–D (and the fifth) are offers, and which are just routes into another?
2. Is the Microsoft contact's two-line framing to be written on the site, and if so, in whose words?
3. Should a round test the light tools with a small model, so the second line has one observation behind it?
4. Who would pay for C, and for what?
5. A second hosted region: on request, or never?
6. Is there any way to learn demand without adding tracking to `/check` or the local server?
