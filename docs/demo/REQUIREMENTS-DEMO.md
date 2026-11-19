# Demo: from requirements to a checked data agent (SAP order to cash)

Written 19 November 2026 by round RQ1. A click script for a phone. It uses Krusgraph together with Copilot Workspaces
and the synthetic SAP demo (`fabric_backend/sap_demo.py`). The flow and the Microsoft Learn sources are in
`docs/REQUIREMENTS-TO-FABRIC.md`. Each step says what you should see and whether that has been tested.

**Before you start**

- Use it in Claude: the Krusgraph connector is added in claude.ai.
- The SAP demo tables are in the lakehouse `demo_lh` of the workspace `demo` (`docs/LIVE-TEST-SAP.md`, steps 1–2).
  Write the schema they are in where this script says `sap_silver`.
- No Fabric data? Step 3 has an offline variant (`sample=true`).
- Steps 1 and 7 need the Microsoft 365 Copilot app and a licence that includes Copilot Workspaces (Copilot Notebooks)
  and data agents in Copilot. Learn's pages do not agree on which licence that is; see the doc.

## 1. Collect the requirements in a Copilot Workspace (not tested)

1. Open the Microsoft 365 Copilot app → **Workspaces** (on some tenants still called **Notebooks**). Create
   `SAP order-to-cash requirements`.
2. Paste the meeting notes as a page or a note, then ask Copilot:

   > Summarise the business requirements in these notes as a short list, one requirement per line, no numbers or amounts.

**Expected:** Copilot answers with a list. Its wording varies. To get the same result as below every time, use the
list in step 2 as it is.

## 2. Copy the list

Copy this text exactly. It is the demo list; the tests and the golden use the same text.

```
Requirements from the sales meeting (summarised by Copilot):
- Revenue per customer and month
- Order value per material and month
- Late deliveries per customer
- Unpaid invoices per customer
- Show our best customers
```

## 3. Paste it into Krusgraph (in Claude)

In claude.ai, type:

> Match these requirements to my SAP data in workspace demo, lakehouse demo_lh, schema sap_silver:

Then paste the list.

**Offline variant:** *"Run requirements_draft with sample=true on this list:"* and paste the list. This runs on the
synthetic SAP demo in memory; no Fabric is needed.

**Expected** (the card titled *Requirements*): *"5 requirements: 1 answerable now, 1 with a trap, 2 missing data, 1
unclear."* Then one line per requirement:

| Id | State on the card | What it says |
| --- | --- | --- |
| R1 | Answerable now | key and joins counted |
| R2 | Answerable, with a trap | VBAK.NETWR is the whole document's value and repeats on every VBAP row |
| R3 | Missing data | needs LIKP.WADAT_IST |
| R4 | Missing data | needs BSID |
| R5 | Unclear | Best or top by which measure: revenue, order value, number of orders or quantity? And over which period? |

Tap **Show** next to R2 to see the evidence: the columns, the join `sap_vbap → sap_vbak` marked failed (1 row points at
nothing), and the trap.

**Tested:** the offline variant and the card's layout at 390 px, light and dark, with unit tests and a browser test
(`tests/test_rq1_requirements_draft.py`). Not yet run against the live lakehouse.

## 4. Answer the open question (optional)

Change the last line to `Revenue per customer and year` and paste the list again. R5 becomes answerable.

**Tested:** unit tests.

## 5. Draft the gold views and the semantic model

Tap **Draft the gold views for R1, R2**, then **Draft the semantic model for R1, R2**. Both are drafts over the three
tables R1 and R2 use (`sap_vbak`, `sap_vbap`, `sap_vbrk`). Nothing is created.

**Expected:** the gold views' Spark SQL and the TMDL model. The model sums line amounts, not header amounts.

**Tested:** the two tools are unit-tested on their own. The buttons with these arguments are unit-tested. The run
from this card on the live lakehouse is not.

## 6. The data agent, with R1 and R2 as example queries (dry run)

Tap **Data agent with R1, R2 as examples (dry run)**. The card sends a sentence to the chat, and Claude runs
`create_data_agent` with `requirements=` and `dry_run=true`.

**Expected:** the dry run's `agent.fewshots` include two example queries. Their questions are "Revenue per customer and
month" and "Order value per material and month", and each query starts with `-- R1: ...` or `-- R2: ...`. Under
`requirements`, `added` is R1 and R2, and R3, R4 and R5 are listed with their states. Nothing is created.

To create it, say **"Create it"** (`dry_run=false`). This writes to the demo tenant, so Gustav decides.

**Tested:** the dry run, with unit tests on the SAP demo (the REST calls are not made in a dry run). The create with
requirement example queries is not tested.

## 7. Ask the data agent in Copilot Chat (not tested)

1. In the Fabric portal, open the data agent → **Publish** → **Publish to Agent Store** (Learn: "Consume a data agent
   from Microsoft Copilot").
2. In the Microsoft 365 Copilot app → Copilot Chat, `@`-mention the agent and ask:

   > What was the revenue per customer in October 2026?

**Expected:** an answer from the billing documents, one row per customer and currency. Try it from inside the
Workspace too. Whether that works is not documented on Learn, so note what you see.

## What is honest to say, and what is not yet

- **Honest:** "used together with Copilot Workspaces". "Use it in Claude". "By rules, no AI inside Krusgraph". "Each
  requirement is traced to its evidence, and a person approves". "Tested on synthetic SAP data".
- **Not yet:** "integrated with Copilot Workspaces", "works with Copilot Workspaces", agents inside a Workspace, any
  claim about speed, and any run on customer data.
