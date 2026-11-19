# From business requirements to checked items in Microsoft Fabric

Written 19 November 2026 by round RQ1. This is a flow for the SAP order-to-cash demo (`fabric_backend/sap_demo.py`),
used together with Copilot Workspaces. It has not been tested end to end in a Copilot Workspace, so it does not say
"integrated with" or "works with". The click script is in `docs/demo/REQUIREMENTS-DEMO.md`.

## The flow

1. **Collect requirements (Microsoft 365).** The business collects its requirements in a Copilot Workspace, for example
   revenue per customer and month, late deliveries and unpaid invoices. Copilot summarises them as a list. Krusgraph is
   not part of this step.
2. **Paste the list into Krusgraph.** Someone copies the list and pastes it into `requirements_draft` (in Claude:
   "Match these requirements to my SAP data" and the list). It is plain text, one requirement per line. Bullets,
   numbers, checkboxes and headings are dropped. Nothing is read from the Workspace.
3. **Krusgraph matches each requirement to checked data.** The matching uses rules only, with no AI. Each line gets
   an id (R1, R2 ...) and one of four states:

   | State | When | What the answer gives |
   | --- | --- | --- |
   | answerable now | Every table, column and join is in the plan. Every join was counted and held (no orphans), or none is needed. | A T-SQL query starting with `-- R1: ...`, the key check and the joins with their counts. |
   | answerable with a trap | It can be answered only by following a rule, which the answer states. Examples: a header amount that repeats on every line (`VBAK.NETWR` over `VBAP` rows), a join with rows that point at nothing, quantities in several units. | The query that follows the rule, and the trap in one sentence with its counts. |
   | missing data | A table or field the requirement needs is not in the plan. | The table or field named, with what it means and an alternative. Examples: `LIKP.WADAT_IST`, `BSID`, `VBAP.WAVWR`. |
   | unclear | The words do not decide. Examples: no measure, "sales" (invoiced or ordered?), "best" without a measure. | One question to answer before pasting the list again. |

   The answer then feeds the existing next steps. Each item carries its requirement ids:
   - `gold_views_draft` and `semantic_model_draft` get the tables the answerable requirements use (`tables=`);
   - `create_data_agent` gets the same list as `requirements=`. Each answerable requirement becomes an example query
     whose question is the requirement and whose query starts with its id. This sits next to the topics and
     templates of round DA2 (`docs/DATA-AGENT-TOPICS-TEMPLATES.md`).

   Every create is a dry run first. A person approves by reading the dry run and calling it again with
   `dry_run=false`.
4. **Ask the data agent (Microsoft 365).** The business asks the Fabric data agent in Microsoft 365 Copilot. Learn
   documents this through **Publish to Agent Store**, then chatting with the agent or `@`-mentioning it in Copilot
   Chat. Whether the agent can be used from inside the same Copilot Workspace is not documented (see below).

## What the rules are

The rules live in `fabric_backend/requirements_draft.py`, rule version `RQ1-1`. They use:

- **Word lists** (`SYNONYMS`), in English and Swedish. They map words to a measure: revenue, order value, number of
  orders, quantity, late deliveries, unpaid invoices or margin. They also map words to dimensions: customer (sold-to
  by default, or payer if the requirement says "payer"), material, country and sales organisation. Time grains are
  day, month or year; a week or quarter gets a question.
- **The SAP pack's table names** (`sap_pack.pack_table`, with or without a prefix such as `sap_vbrk`), plus a small
  field glossary (`FIELDS`).
- **validate_plan's counts**: key uniqueness, orphans per join, and lines per header for the amounts. These are the
  evidence. Without counts (`validate=false`) nothing is called checked.

The same list and the same plan give the same answer, byte for byte (`tests/golden/rq1_sap_demo.json`). Personal-data
columns are never used, so a customer is its number. The queries name columns only. No row value is read by the rules
or returned: the leak test compares every answer with the demo's rows.

On the synthetic SAP demo, the list in the click script gives one of each state:

| Id | Requirement | State | Why |
| --- | --- | --- | --- |
| R1 | Revenue per customer and month | answerable | `VBRK.NETWR` once per billing document, by sold-to party (`KUNAG`), billing month (`FKDAT`), client and currency. The `VBRK` key was counted unique. |
| R2 | Order value per material and month | trap | `VBAK.NETWR` repeats on every `VBAP` row (1.67 lines per order on average, up to 3), so the query sums `VBAP.NETWR`. One `VBAP` row points at no order and is left out. |
| R3 | Late deliveries per customer | missing | `LIKP.WADAT_IST` (actual goods issue date). `LIKP.ERDAT` is when the delivery was created, not when it left. |
| R4 | Unpaid invoices per customer | missing | `BSID` (open customer items), or `BSAD`/`BSEG.AUGDT`, or `ACDOCA`. Billing documents say what was invoiced, not what was paid. |
| R5 | Show our best customers | unclear | "Best or top by which measure ...? And over which period?" |

## What Microsoft Learn says (read 19 November 2026)

Only learn.microsoft.com and microsoft.com were read. No undocumented or private endpoint was called.

**(a) What Copilot Workspaces is**

- The name "Copilot Workspaces" does not appear on Learn. Learn's admin pages still say **Copilot Notebooks**.
- The rename appears in two blog posts on microsoft.com:
  - "Copilot at Microsoft Ignite" (17 November 2026,
    https://www.microsoft.com/en-us/copilot/blog/2026/11/17/copilot-at-microsoft-ignite-expanding-whats-possible-with-intelligence-built-for-work/):
    "As the evolution of Copilot Notebooks, it's where people and agents build on each other's work" and "Workspaces
    is now available in Frontier".
  - Tech Community, "What's New in Microsoft Copilot – October 2026" (date not shown): "Existing notebooks will
    become workspaces".
- A support article titled "Copilot Notebooks Is Now Copilot Workspaces" was seen only as a search result. It could
  not be opened here, so it is not cited as read.
- No Microsoft page found gives a GA date.
- **Licensing.** Learn's pages disagree:
  - "Copilot Notebooks requirements" (cpcn-requirements, ms.date 2026-05-14,
    https://learn.microsoft.com/en-us/microsoft-365/loop/cpcn-requirements) says both "Microsoft Copilot license" and
    "Users need the Microsoft Copilot or Copilot Chat license".
  - The Graph configuration page for Copilot resources (preview, ms.date 2026-11-05,
    https://learn.microsoft.com/en-us/graph/utcm-copilot-resources) says "Copilot Notebooks also require a Microsoft 365
    Copilot license".
  - Nothing on Learn covers Workspaces licensing.
- **Storage.** "Copilot Pages and Notebooks storage" (cpcn-storage, ms.date 2026-05-14, updated 2026-11-14,
  https://learn.microsoft.com/en-us/microsoft-365/loop/cpcn-storage) says "Pages and Notebooks are stored in OneDrive
  for Business". cpcn-requirements still names a SharePoint Embedded container.

**(b) Agents and MCP in a Workspace**

- Not documented on Learn: no page says a Notebook or a Workspace can attach a Fabric data agent, a declarative or
  Copilot Studio agent, or an MCP connector.
- The Ignite post says "people and agents" work together but names no agent type and no setup.
- The Microsoft 365 Copilot release notes (https://learn.microsoft.com/en-us/microsoft-365/copilot/release-notes,
  entry of 27 October 2026) mention custom MCP connectors deployed from the Microsoft 365 admin center. That is not
  tied to Notebooks or Workspaces.
- **Fabric data agents in Microsoft 365 Copilot.** "Consume a data agent from Microsoft Copilot" (ms.date
  2026-10-26, https://learn.microsoft.com/en-us/fabric/data-science/data-agent-microsoft-365-copilot):
  - It describes **Publish to Agent Store**, then chatting with the agent or using `@` to mention it from Copilot Chat.
  - Its prerequisites include an F2 or P1 capacity or higher, cross-geo AI settings, and a Microsoft Copilot licence
    or an Office 365 commercial subscription.
  - The page has no preview label. The concept page (ms.date 2026-05-11,
    https://learn.microsoft.com/en-us/fabric/data-science/concept-data-agent) says the data agent "is a generally
    available feature".
  - The Copilot Studio route is preview (https://learn.microsoft.com/en-us/fabric/data-science/data-agent-microsoft-copilot-studio,
    ms.date 2026-05-12).
- So step 4 is documented for Copilot Chat. Inside a Workspace it is not.

**(c) Reading a Workspace's content programmatically**

- Not documented on Learn: there is no Graph endpoint, SDK or export for a Notebook's or a Workspace's content as such.
- Learn documents file-level access to the storage ("Copilot Pages and Copilot Notebooks compliance summary",
  cpcn-compliance-summary, ms.date 2026-07-06,
  https://learn.microsoft.com/en-us/microsoft-365/loop/cpcn-compliance-summary):
  - Graph's `driveItem` content and format conversion, for third-party tools;
  - Purview eDiscovery export;
  - "Copilot Notebooks create and update `.pod` files". The `.pod` format itself is not documented.
- Krusgraph therefore reads nothing from the Workspace: the list is pasted. That is enough for the demo.

## What is not tested or not documented

- Not tested: the paste from a real Copilot Workspace, the data agent in Copilot Chat with the requirement example
  queries, and `requirements_draft` against a live Fabric workspace. Unit tests and the golden run on the synthetic
  SAP demo in SQLite.
- Not documented on Learn (19 November 2026): the name Copilot Workspaces, its licensing and GA date, agents or MCP
  inside a Workspace, and an API for a Workspace's content.
- Not built:
  - `semantic_model_draft` does not take the requirement measures as input. They are listed in `feeds` to review.
  - `gold_views_draft` drafts the plan's views over the requirement tables, not one view per requirement.
  - Requirements outside SAP order to cash get "missing" with rule `RQ-X0`.
  - The local stdio server does not have the tool.
