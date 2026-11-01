# FAQ: "Why not …?" (internal, for Gustav; not for the site)

Short answers to the questions a buyer asks, with what the other product's own documentation says, where it says it, and
when it was read. Rules: a statement about a Microsoft product comes from Microsoft Learn; about another vendor, from
that vendor's own page; nothing from blogs, press or partners. Where a page could not be opened, the answer says
**overifierat** and stops. No claim of being the single or sole option, in any wording: the angle is the same in every
answer and it is a fact about this repository, not a comparison. Krusgraph's own statements rest on `fabric_backend/tool_status.py` and
`docs/LIVE-TEST.md` as of 1 November 2026.

**How the Microsoft pages were read.** learn.microsoft.com cannot be opened from the agent sessions (network policy;
the same was true for `examples/benchmark/README.md`). The pages below were read on 1 November 2026 from the
documentation's source repository, MicrosoftDocs/fabric-docs, commit c694e9d (1 November 2026), which is what Learn
publishes; each row gives the Learn address, the source file and the page's own `ms.date`. Before any of this is
quoted outside, open the Learn page itself and check that the sentence is still there. Pages that are not in that
repository (Power BI's own docs, Purview's own docs) are marked overifierat.

## Krusgraph's angle, the same in every answer

1. **The evidence step before the build.** `plan_backend` names the rule behind every key and relationship (K0–K5,
   R0–R5, or a pack's source); `validate_plan` counts against the rows (duplicate key values, references with no matching
   row, the total that doubles); `suggest_relationships` checks candidates against the data; the person decides with
   `keys=` and `confirmed=`. `/check` does the plan and the counting in the browser, with no account and no capacity.
2. **It creates Fabric's own objects from that reviewed plan**, through the user's own permissions: an API for
   GraphQL (`create_backend`: an update in place of `shop_api` on 27 October 2026), a Power BI semantic model
   (`create_semantic_model`: `shop_model_live`, 29 October 2026), a Fabric IQ ontology item (`create_ontology`:
   `shop_ontology`, 28 October 2026), a report (`create_report`, 30 October 2026), notebooks and a pipeline (28 October
   2026, not yet run in Fabric), views and a data agent (dry runs on 27 October 2026). The status per tool, in the site's
   words, is https://krusgraph.com/docs#test-status.

So Fabric IQ, Copilot and Purview are where the result lands or what sits next to it, not what Krusgraph replaces.

## "Why not just Fabric IQ / the Fabric ontology?"

**What Microsoft Learn says** (read 1 November 2026 from fabric-docs c694e9d):

- *What is Fabric IQ?* — https://learn.microsoft.com/en-us/fabric/iq/overview (`docs/iq/overview.md`, ms.date
  07/08/2026): the ontology (preview) item "defines entity types, properties, relationships, rules, and metrics, and
  binds them to live enterprise data". "You can create ontology items from scratch or generate them from existing Power
  BI semantic models to bootstrap from trusted logic already in production." "You can also generate ontology details
  with the ontology agent or import them from open standards like RDF or OWL."
- *What is ontology (preview)?* — https://learn.microsoft.com/en-us/fabric/iq/ontology/overview
  (`docs/iq/ontology/overview.md`, ms.date 10/16/2026): "You can build an ontology from scratch, or you can generate it
  directly from semantic models." Generating from a semantic model keeps "relevant tables, columns, relationships,
  calculated columns, and source-owned DAX measures". The item "stores and serves ontology definitions and bindings (it
  isn't itself a general-purpose data-query engine)". It is a preview item.
- *Use the ontology agent (preview)* — https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-ontology-agent
  (ms.date 10/20/2026): the agent works in three steps, "Discover: explores the workspace items you point it to … and
  samples a few rows per table", "Draft: proposes an ontology definition (entity types, relationships, data bindings,
  and contextualizations) grounded in the discovered evidence", "Validate: runs structural and grounding checks on the
  draft". Under preparation: "Clear table, column, key, and relationship names help the agent infer entity types,
  properties, data bindings, and contextualizations." Changes follow "a proposal-first model".
- *Create relationship types (preview)* — https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-relationship-types
  (ms.date 09/04/2026): by hand in the portal, the author selects the property on the origin entity type and the target,
  or a mapping table.

**The honest answer.** Fabric IQ is where Krusgraph's plan can land: `ontology_draft` writes the plan in the ontology
item's own shape and `create_ontology` created `shop_ontology` live on 28 October 2026 (7 entity types, 7 relationship
types), reviewed in the portal by Gustav on 29 October. Microsoft's own ways to fill an ontology are, per the pages
above, by hand, from an existing semantic model (which must already carry the relationships), by import, or with the
ontology agent, which infers from names and sampled rows and runs checks the page does not spell out. What Krusgraph
adds is the evidence step with named rules and counts (which rule, which count, what was left to the person), it runs
before any Fabric item or capacity exists (`/check`), and the same plan also becomes the API, the model and the
notebooks. What it does not do: it does not replace the ontology item, its agent, rules or metrics, and the ontology
agent's checks have not been compared with `validate_plan` on the same data (no such measurement exists).

## "Why not Copilot in Power BI?"

**What Microsoft Learn says** (read 1 November 2026 from fabric-docs c694e9d):

- *Overview of Copilot in Fabric* — https://learn.microsoft.com/en-us/fabric/fundamentals/copilot-fabric-overview
  (`docs/fundamentals/copilot-fabric-overview.md`, ms.date 06/19/2026): in the Power BI workload, Copilot can "create
  reports automatically", "generate a summary for the report page that you created, and generate synonyms for better
  Q&A capabilities". It consumes Fabric capacity; "Copilot is enabled by default for tenants with paid Fabric
  capacities (F2 or higher)"; "In Power BI Desktop, Copilot experiences are available to users with access to a workspace
  that uses Fabric capacity or those assigned to a Fabric Copilot capacity." It is powered by Azure OpenAI in US and EU
  datacenters, with a tenant setting for capacities elsewhere.
- *Privacy, security, and responsible use for Copilot in Power BI* —
  https://learn.microsoft.com/en-us/fabric/fundamentals/copilot-power-bi-privacy-security (ms.date 05/26/2026):
  "Copilot uses the data in a semantic model that you provide, combined with the prompts you enter, to create visuals";
  "To create DAX queries, explain DAX queries, or explain DAX topics, Copilot uses the semantic model metadata, such as
  table and column names"; and the advice "Review Copilot-generated DAX queries before you apply them to your model."
- *Overview of Copilot for Power BI* — https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-introduction:
  **overifierat.** The page is in Power BI's own documentation, which is not in fabric-docs and could not be opened.
  Whether Copilot proposes relationships or keys in a model is therefore not stated here.
- Power BI Desktop's relationship *autodetect* is not Copilot. `examples/benchmark/README.md` approximates its
  documented rules and says the Learn page should be re-read before the approximation is quoted: **overifierat** in the
  same sense.

**The honest answer.** Per the pages read, Copilot in Power BI works on a semantic model that exists: reports, summaries,
synonyms, DAX, with the user asked to review the DAX. Krusgraph's work is before that model exists: which tables relate,
on what rule, checked against the rows, and then the model itself in TMDL (`semantic_model_draft`;
`create_semantic_model` created `shop_model_live` on 29 October 2026, refreshed and reviewed in the portal the same
day). A model Krusgraph creates is an ordinary semantic model, so Copilot can be used on it afterwards. Krusgraph needs
no Fabric capacity for the check (`/check`); creating the model needs the user's own permissions and a workspace.

## "Why not Purview?"

**What Microsoft Learn says** (read 1 November 2026 from fabric-docs c694e9d):

- *Use Microsoft Purview to protect Microsoft Fabric* —
  https://learn.microsoft.com/en-us/fabric/governance/microsoft-purview-fabric (`docs/governance/microsoft-purview-fabric.md`,
  ms.date 08/26/2026): "Microsoft Fabric provides built-in governance capabilities for discovering, governing, and
  managing data. Microsoft Purview works with Fabric to protect sensitive data and support audit, risk, and compliance
  scenarios." Fabric's own OneLake catalog does discovery, governance insights, recommended actions and "Lineage — trace
  how data flows across Fabric items, from source to report". Purview adds: "Discover and classify sensitive data, and
  apply protection with information protection and sensitivity labels", data loss prevention for lakehouses, warehouses,
  databases and semantic models, audit, and "governance and risk controls for Fabric Copilots and agents". The page
  does not mention keys or relationships between tables, nor creating APIs, models or ontology items.
- *What is Microsoft Purview?* — https://learn.microsoft.com/en-us/purview/purview: **overifierat.** Purview's own
  documentation is not in fabric-docs and could not be opened.

**The honest answer.** Purview, as the Fabric page describes it, classifies, protects and audits data and sits next to
the OneLake catalog's discovery and lineage. Krusgraph does something else: it works out how the tables in one source
relate, with the rule and the counts, and builds from that. The two meet at one point: Fabric returns an item's Purview
sensitivity label (`sensitivityLabel.id`, read-only; `docs/SCOPES.md`), and Krusgraph's own privacy rules (P1: masking
by column name, left out of examples) do not read Purview labels. Nothing is said here about Purview's catalog or its
data map beyond what the Fabric page states.

## "What about Solid AI?"

**overifierat.** The vendor's own page could not be opened from this session (the host does not resolve under the
network policy), and no other vendor page was reachable. A web search on 1 November 2026 returned press coverage of a
company called Solid describing semantic models and a "context graph" over Snowflake, Databricks and BigQuery; that is
press, not the vendor's page, so it is not used here and should not be quoted. To fill this in: open the vendor's site,
note the address and the date, and write what it says it does, in its words. Until then the answer to a buyer is: "I
have not read their material; here is what Krusgraph does and where that is documented", then the two points above.

## What is not claimed anywhere in this file

- That any of these products cannot do what Krusgraph does: the pages read say what they do, not what they do not.
- Any number from a comparison on the same data: none exists (the benchmark compares with an approximation of Power
  BI's documented autodetect rules and with dbt-style tests, on synthetic sets, with its limitations stated).
- Anything about pricing or licensing beyond the capacity sentences quoted above.
