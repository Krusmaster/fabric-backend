# The data agent the Krusgraph Model makes: one layer, its examples, publishing

Round n185, the founder's additions 1 to 4 of 9 November 2026 (demo_lh_agent, after the pipeline had run). Everything
below was read on 9 November 2026. Nothing in this round ran against Fabric; it is covered by `tests/test_n185_agent.py`
with Fabric's data agent API as an in-memory test double.

## 1. One layer: silver, gold or the source, never two

**What the founder saw.** After the pipeline created the silver tables and the gold views, demo_lh_agent's data
source had the silver tables (and later the gold views) ticked as well as the seven shop tables Krusgraph selected, so
the agent saw two copies of every table.

**The cause.** `data_agent.apply` selected tables by name only. `silver.orders` and `shop.orders` are both called
`orders`, so once the silver schema existed, both were selected.

**Now.** The data source's schema tree is walked once (Staging_ListDatasourceElements, element types Schema, Tables,
Table, MaterializedViews, MaterializedView; microsoft/fabric-rest-api-specs 6f817cb `dataAgent/definitions.json`
ElementType). The agent reads exactly one layer:

| Layer | When | Tables |
| --- | --- | --- |
| Silver (the editor's default) | the plan's tables are all in the silver schema | `silver.<table>`: cleaned, keys and links held |
| Gold (an option) | the gold views are there | the materialized lake views, one wide view per fact table |
| Source | otherwise, or a lakehouse without schemas | the source schema, as before |

The plan's tables in the other layers' schemas are deselected (UpdateDataSourceElementRequest `isSelected: false`,
"the element configuration is preserved and restored when re-selected"). A table Krusgraph does not know is never
touched. The instructions and the examples are written for the chosen layer's schema, so the examples' T-SQL names
`[silver].[orders]` when the agent reads silver. The card and the dry run say which layer.

When Run once is ticked, Create starts the pipeline run without waiting for it. The agent is created on whatever is
there (the source, before the first run), and when the editor reads that the run succeeded, it sends the agent again
(`after_run: {status: "Succeeded"}`). The agent Krusgraph made is updated in place to the silver tables. An agent
Krusgraph did not make is never written.

## 2. The example questions: where Krusgraph writes them, where Fabric shows them

- Krusgraph writes 3 to 5 examples per agent as **few-shots** of the data source (Staging_CreateDatasourceFewshot).
  In the documented item definition these are `Files/Config/draft/{type}-{name}/fewshots.json`, `{id, question,
  query}` (Learn, "Data Agent item definition", ms.date 2026-01-21). Once the agent is published, a copy is under
  `published/`.
- Fabric shows them in the agent's **Example queries** pane and uses them to answer: "When a user asks a question
  against a data source, the Data Agent automatically retrieves the most relevant examples—typically the top four"
  (Learn, `data-agent-example-queries`, ms.date 2025-09-11).
- The questions the chat panel suggests are Fabric's own. Neither the item definition (its `stage_config.json` has only
  `aiInstructions`) nor the REST API (`DataAgentSettingsResponse` has only `aiInstructions`) documents a place for them.
  Krusgraph therefore cannot write them there, and does not try.
- "Every example query is validated against the schema of the selected data source—queries that don't pass validation
  aren't sent to the agent" (same page). With two layers selected, or with examples on `shop` while the agent reads
  `silver`, examples can fail that check. Create now reads each example's `validationStatus` (Valid, Invalid,
  Validating) back and shows it on the card, with Fabric's reason for each Invalid one.

## 3. Publishing: two separate ticks, both off

| Tick | What Create does | Source |
| --- | --- | --- |
| **Publish the agent in Fabric** | `POST /v1/workspaces/{ws}/dataAgents/{id}/staging/publish {publishedDescription}`: "Promotes the current staging state to the published environment, making it live." Delegated scope `Item.ReadWrite.All` or `DataAgent.ReadWrite.All`. These are the scopes creating the agent already needs, so no new permission is needed. Marked "Data Agent configuration management is currently in Preview". | fabric-rest-api-specs 6f817cb `dataAgent/swagger.json`, Items_PublishDataAgent |
| **Also make it available in Microsoft 365 Copilot** (only with the first) | Nothing in Fabric: the step is the portal's Publish dialog, **Publish to Agent Store**. Microsoft documents no API for it (the publish request has only `publishedDescription`). The card runs the preflight below and lists the portal step. | Learn `data-agent-microsoft-365-copilot`, ms.date 2026-10-26 |

Create publishes in Fabric only when all three hold. Otherwise the agent stays a draft and the card says which one did
not hold:

1. the person ticked it;
2. the agent reads one layer (section 1);
3. when Run once was ticked, that run succeeded. Until the editor has read the run's end the card says "waiting"; a run
   that failed leaves a draft.

The dry run says "Create publishes demo_lh_agent: people with access to the workspace can use it". `outputs.json`
records `published` on the agent's created entry. The published description tells Microsoft 365 Copilot to deliver
the agent's output as it is. Learn: "The description becomes the `description_for_model` in Microsoft Copilot", and
the MCP page says it becomes the MCP tool's description.

Nothing is retried in a loop: one publish call. A refusal is shown with its HTTP status, and the manual step stays in
the Next list.

### The Microsoft 365 Copilot preflight

On 9 November the founder got "Det gick inte att publicera dataagenten till Microsoft Copilot" ("Couldn't publish the
data agent to Microsoft Copilot") on a trial capacity; publishing in Fabric worked. The documented requirements, each
checked where Fabric's API can read it:

| Requirement (Learn) | How Krusgraph checks it | When it cannot |
| --- | --- | --- |
| "A paid F2 or higher Fabric capacity, or a Power BI Premium per capacity (P1 or higher) capacity with Microsoft Fabric enabled" (`data-agent-microsoft-365-copilot`) | Get Workspace (`capacityId`, `capacityRegion`; Workspace.Read.All), List Capacities (`sku`; Capacity.Read.All or Capacity.ReadWrite.All) | **Unverified** without Capacity.Read.All, which the workload app does not request |
| A trial capacity does not count as paid | a SKU starting with `FT` is taken as trial | **Unverified**: Learn shows no trial SKU name; the rule follows the founder's tenant |
| "Users can use Copilot and other features powered by Azure OpenAI", "Capacities can be designated as Fabric Copilot capacities"; outside the EU data boundary and the US also the two "Data sent to Azure OpenAI can be processed / stored outside ..." settings (`data-agent-tenant-settings`, ms.date 2026-04-20) | List Tenant Settings (`GET /v1/admin/tenantsettings`, Tenant.Read.All, a Fabric administrator only), matched by title | **Unverified** for anyone but a Fabric administrator |
| "Microsoft Copilot license or Office 365 commercial subscription" and a user licence per person; Copilot extensibility in the Microsoft 365 admin center | not readable through Fabric's API | always **Unverified**, with the link |

The card lists each line as ok, missing (with what is missing) or Unverified, with Microsoft's link.

## 4. The Model Context Protocol tab (input for a later round; no code now)

Learn, "Data agent as Model Context Protocol server" (`data-agent-mcp-server`, ms.date 2026-09-03):

- "When you publish a Fabric data agent, it becomes an MCP server that exposes a single MCP tool. That tool represents
  the data agent itself": a client sends a question and gets an answer grounded in the agent's data.
- The **Model Context Protocol** tab in the agent's Settings shows the server name, the **MCP server URL**, the tool
  name and the tool description, and offers an `mcp.json` download. The URL is
  `https://api.fabric.microsoft.com/v1/mcp/workspaces/{WorkspaceId}/dataagents/{DataAgentId}/agent` and "works only
  after you publish the data agent".
- Clients must speak MCP over streamable HTTP and attach a Fabric bearer token for
  `https://api.fabric.microsoft.com/.default`. "The data agent MCP server doesn't support dynamic client registration
  or client identity metadata." Long answers can use MCP tasks (`tasks/get`, `tasks/cancel`).
- The published description becomes the tool's description, which is what an orchestrator reads to decide when to
  call the agent.
- Prerequisites: the same paid F2+ (or P1+) capacity and cross-geo settings. Responses "might be sent outside of
  Fabric's compliance boundary".

For a later round: the Krusgraph card could show this URL for a published agent, and Krusgraph's own MCP server could
point to it (the agent answers questions; Krusgraph plans and builds). Whether the endpoint answers on a trial capacity
is **Unverified**.

## For the founder

- No new permission: publishing uses `Item.ReadWrite.All` or `DataAgent.ReadWrite.All`, which creating the agent already needs. `Capacity.Read.All` would let
  the preflight read the SKU instead of saying Unverified. It is optional and not requested now.
- On the trial tenant, tick only **Publish the agent in Fabric**. The Copilot tick's card should name the trial
  capacity as the missing requirement when the SKU can be read.
