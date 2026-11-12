# Selling migrations into Microsoft Fabric with Krusgraph (draft, W10)

Round W10. A sales draft, docs only. Nothing here is on the site, in `llms.txt` or published anywhere. Written
12 November 2026 by a scheduled Claude session with no live user, from the founder's line of the same day: "we need to
be able to sell how to migrate from Databricks and Snowflake by using Krusgraph; the same with migrating from Qlik to
Power BI by using Krusgraph."

The design behind every sentence is [`../MIGRATION-PLATFORMS-DESIGN.md`](../MIGRATION-PLATFORMS-DESIGN.md) (W10): the
paths, what Krusgraph does at each step, what it reads, what stays manual, and the builds B1 to B9 this text refers to.
W7's `docs/MIGRATION-DESIGN.md` covers existing platforms, ERP to S/4HANA, and the Qlik and Tableau design.

Rules for this text (`CONTRIBUTING.md`, "What never goes into the repository"):

- **Nothing here says Fabric is cheaper or faster** than Databricks, Snowflake or Qlik. We do not know that for any
  customer, and it is not our claim to make. The buyer has already decided to move, or is deciding for their own
  reasons; we sell that the move can be checked.
- **No competitor bashing.** Databricks, Snowflake and Qlik are named as the place the data and the reports are today.
- **No "partner", "certified" or "endorsed"**, for Microsoft or anyone else. Krusgraph is independent. "Works with
  Microsoft Fabric" describes compatibility only.
- **No customer names, no invented numbers, quotes or logos.** Every example is the synthetic shop schema
  (`fabric_backend/seed.py`).
- **No AI in Krusgraph for Fabric** (`offering.py`). Every check is a rule or a count; the pitch says so.
- **A draft sentence is not a public sentence.** Section 6 lists, per sentence, the proof that must be in the
  repository before it may go out. Today most of it is missing, and section 6 says which.
- Prices are not in this text. `docs/PILOT.md` has proposals to test; P1's `docs/PRICING-DESIGN.md` was claimed but not
  on `main` when this was written.

---

## 1. The one idea

> **A migration is finished when the numbers agree, not when the tables are copied.**

Copying tables is the part Microsoft Fabric already does (mirroring, shortcuts, Copy job). What goes wrong is after
the copy: a KPI that was 4 812 300 in the old report is 4 811 950 in the new one, nobody can say why, and trust in the
new platform is gone in the first week. The causes are small and well known: a type that was widened, a time zone, a
NULL that became an empty string, a decimal that lost precision, a customer number that lost its leading zeros, a
comparison that was case-sensitive on one side and not on the other.

Krusgraph is the method for that part:

1. **Count before.** Read the old platform read-only: what there is, which keys are unique, which links hold. Counts,
   never rows.
2. **Count after.** The same counts on the tables once they are in OneLake.
3. **The same KPI, the same number, or the reason.** A short list of KPIs the business signs. Each is computed on both
   sides. Where they differ, Krusgraph points at the column and the rule that explains the difference, or says plainly
   that it cannot explain it.
4. **Build from the checked plan.** Silver and gold, the semantic model, the report, the ontology, the data product
   with its owner.
5. **Retire the old on evidence.** When the list is green for the agreed period, and not before.

Kruse Consulting does the migration. Krusgraph is how it is done and how it is shown to be done.

---

## 2. The offer, in three steps (the same for every source)

| Step | What the buyer gets | Who does what | Ends with |
|---|---|---|---|
| **1. Assessment** | A read-only inventory with counts (what exists, what is used, what is not), the keys and links checked against the rows, a first list of KPIs to hold constant, the risks found (section 5 of the design), and a migration path per object: mirror, shortcut, copy, rewrite, or leave | Kruse Consulting runs it with Krusgraph. The buyer gives a read-only identity and names an owner per subject area | A written assessment the buyer can act on with anyone, with or without us |
| **2. Pilot** | One subject area (or one Qlik app) moved end to end: landed in OneLake, silver and gold, a semantic model, one report, and a reconciliation per KPI with every difference explained or listed as open | Kruse Consulting builds. The buyer's KPI owners sign the list | The pilot's reconciliation sheet, and a plan and estimate for the rest based on what the pilot measured |
| **3. Migration** | The remaining subject areas in waves, each with its own reconciliation, a parallel run, a cutover date and a retire step | Kruse Consulting, with Krusgraph as the method. The buyer owns the decisions: which KPI definition is right when two disagree, when to cut over, when to switch the old off | Old platform or app retired, per wave, on the buyer's sign-off |

Three things we say in every first meeting:

- The assessment is read-only. Nothing is created, changed or copied on the old platform.
- The assessment is useful even if the buyer does not migrate, or migrates with someone else.
- We do not promise that every number will match. We promise that every number is compared and every difference is
  shown.

---

## 3. Per source

### 3.1 Databricks to Fabric

| | |
|---|---|
| **Buyer** | Head of data platform or data and analytics lead, in an organisation that runs Microsoft 365 and Power BI and has Azure Databricks beside it. The CFO or CIO is the economic buyer when the trigger is consolidation |
| **Trigger** | A decision, already taken or on the table, to consolidate on Microsoft: one capacity, one security model, Power BI as the only report tool. A contract or commitment up for renewal. A platform team too small for two platforms. *The buyer brings the cost question; we do not answer it for them* |
| **What they fear** | Notebooks and jobs nobody has an inventory of. Reports that change their numbers. A long freeze. Finding out halfway that half the tables are unused |
| **The first honest answer** | Not everything has to move at once, or at all. Fabric can read Unity Catalog tables in place (mirroring of the catalog's metadata, shortcuts to the Delta files), so the first step can be to *read* from Fabric and check, before anything is rewritten (design, section 2) |
| **Offer** | Assessment of one catalog. Pilot on one schema with its silver, gold and one report. Migration in waves |

**One-page pitch: Databricks**

> **Moving from Databricks to Microsoft Fabric, with every number checked**
>
> You have decided to bring your data platform closer to Power BI and Microsoft 365, or you are weighing it. The
> tables are the easy part: Microsoft Fabric can read your Unity Catalog tables where they are. The hard part is
> everything built on them: notebooks, jobs, views and dashboards that nobody has counted, and KPIs that must show the
> same number the day after as the day before.
>
> **What we do.** Kruse Consulting migrates with Krusgraph, an open-source method that counts instead of guessing.
>
> - **Inventory, read-only.** Catalogs, schemas, tables, views, notebooks and jobs, counted, with what reads what.
> - **Keys and links checked against the rows**, on the Databricks side and again in OneLake.
> - **Your KPIs held constant.** Each one computed on both sides. The same number, or the column and the rule that
>   explains the difference.
> - **Rebuilt from the checked plan**: silver and gold, a Power BI semantic model, a report, an ontology, and a data
>   product with a named owner.
> - **Cutover when the list is green.** The old jobs are switched off on evidence, one wave at a time.
>
> **What you decide.** Which definition of a KPI is right when two disagree. What is not worth moving. When to cut
> over.
>
> **What we do not promise.** That Fabric will cost less or run faster for you; that is your own measurement. That
> notebooks translate by themselves; they are rewritten by people, and Krusgraph checks the result.
>
> **Start.** A read-only assessment of one catalog. You keep the result whatever you decide.
>
> *Krusgraph is independent and open source (MIT). It is not affiliated with Microsoft or Databricks.*

### 3.2 Snowflake to Fabric

| | |
|---|---|
| **Buyer** | Head of BI or data platform owner, often with the finance function close by, in an organisation where Snowflake holds the warehouse and Power BI is the report tool. The CFO or CIO is the economic buyer |
| **Trigger** | Consolidation on Microsoft. A contract renewal that makes someone ask what the warehouse is for. A wish to have the warehouse, the semantic model and the reports under one security model. *The buyer brings the cost question* |
| **What they fear** | SQL that behaves differently: upper-case names, time zones, semi-structured columns, numbers with 38 digits. A semantic layer that lives in views and in people's heads. Finance closing on two sets of numbers |
| **The first honest answer** | Fabric can mirror Snowflake tables into OneLake and keep them up to date, so both sides can run in parallel while the numbers are compared. Mirroring copies tables; it does not move views, procedures, tasks or the meaning of a KPI (design, section 3) |
| **Offer** | Assessment of one database. Pilot on one schema (finance or sales) with a reconciliation per KPI. Migration in waves |

**One-page pitch: Snowflake**

> **Moving from Snowflake to Microsoft Fabric, with every number checked**
>
> Your warehouse is in Snowflake and your reports are in Power BI. If you bring them together in Microsoft Fabric,
> the tables can be mirrored and kept current while you work. What does not move by itself is the SQL: views, tasks
> and procedures written for another dialect, and the definitions of your KPIs.
>
> **What we do.** Kruse Consulting migrates with Krusgraph, an open-source method that counts instead of guessing.
>
> - **Inventory, read-only.** Databases, schemas, tables, views, tasks and what is queried at all, counted.
> - **Keys and links checked against the rows.** Snowflake does not enforce primary and foreign keys, so we count
>   them, in Snowflake and again in OneLake.
> - **Your KPIs held constant.** Each one computed on both sides. The same number, or the reason: a type, a time
>   zone, a NULL, a decimal, upper and lower case, a leading zero.
> - **Rebuilt from the checked plan**: silver and gold, a Power BI semantic model, a report, an ontology, and a data
>   product with a named owner.
> - **Parallel run, then cutover.** Snowflake is switched off when the list has been green for the period you set.
>
> **What you decide.** Which definition wins. What stays behind. The date.
>
> **What we do not promise.** That Fabric will cost less or run faster for you. That SQL translates by itself; views
> are rewritten by people, and Krusgraph checks the result against the rows.
>
> **Start.** A read-only assessment of one database. You keep the result whatever you decide.
>
> *Krusgraph is independent and open source (MIT). It is not affiliated with Microsoft or Snowflake.*

### 3.3 Qlik Sense to Power BI

| | |
|---|---|
| **Buyer** | BI manager or head of controlling, in an organisation with Microsoft 365 where Qlik Sense apps and Power BI reports live side by side. The CFO or CIO is the economic buyer |
| **Trigger** | A licence renewal. A decision that Power BI is the standard. The one person who understands the load scripts is leaving, or has left. A move from client-managed Qlik that forces a project anyway |
| **What they fear** | That the logic is in the load script and in set analysis nobody can read. That users will say "the numbers were right in Qlik". That a hundred apps become a hundred projects |
| **The first honest answer** | A Qlik app is not converted, it is re-modelled. Qlik links tables by field name and makes synthetic keys where two tables share several fields; Power BI wants one column per relationship and a star. That is a design step with decisions in it, and it is where the numbers are won or lost (design, part B) |
| **Offer** | Assessment of the app portfolio (which apps, which are used, which share logic). Pilot on one app: data model, measures, one report, a reconciliation per KPI. Migration app by app, shared logic first |

**One-page pitch: Qlik**

> **From Qlik Sense to Power BI, with every measure reconciled**
>
> You are standardising on Power BI. Your Qlik apps hold years of logic: load scripts, set analysis, master measures.
> There is no button that converts them, and a tool that says otherwise leaves you to find the differences in
> production.
>
> **What we do.** Kruse Consulting migrates with Krusgraph, an open-source method that counts instead of guessing.
>
> - **The load script read into a plan.** Tables, fields and how they associate, with every synthetic key and link
>   table listed and resolved into a proper key, checked against the rows.
> - **Measures translated where the translation is certain**, suggested where it is not, and left to a person where
>   Qlik and DAX think differently. Each one says which of the three it is.
> - **A reconciliation per KPI.** The Qlik value and the Power BI value side by side, per month or per unit, with the
>   differences explained or listed as open.
> - **Apps to reports**: a semantic model that several reports share, instead of one model per app.
> - **Section access to row-level security as a written design**, decided and tested by your people, never applied
>   by a tool.
>
> **What you decide.** Which measure is right when two apps disagree. Which apps are not worth moving. Who sees
> what.
>
> **What we do not promise.** That Power BI is better than Qlik. That every expression has a twin in DAX; some do
> not, and we say which.
>
> **Start.** A read-only assessment of your apps. You keep the result whatever you decide.
>
> *Krusgraph is independent and open source (MIT). It is not affiliated with Microsoft or Qlik.*

---

## 4. Three LinkedIn post drafts (Wednesdays 08:30, Stockholm time)

Drafts for the founder's own profile. Nothing is scheduled or sent by this round. M1 also drafts LinkedIn posts under
`docs/marketing/`; the founder decides which draft takes which Wednesday. Each post is on the method and on synthetic
data, because that is what exists today (section 6). None may go out before the proof named under it is in the
repository.

**Post 1. Wednesday 18 November 2026, 08:30: the idea**

> A migration is not finished when the tables are copied.
> It is finished when the numbers agree.
>
> Moving a data platform into Microsoft Fabric, the copy is the easy part. Fabric has mirroring, shortcuts and Copy
> job for that.
>
> The hard part starts the day after: the same KPI, two numbers, and nobody who can say why.
>
> The reasons are almost always small:
> – a customer number that lost its leading zeros
> – a timestamp that changed time zone
> – a NULL that became an empty string
> – a decimal that lost its last digits
> – "ABC" and "abc" being the same on one side and different on the other
>
> We are building this into Krusgraph: count on the old side, count again in OneLake, and for every KPI either the
> same number or the column and the rule that explains the difference.
>
> No AI in that step. Rules and counts, so the answer is the same every time.
>
> Design note, open source: [link to docs/MIGRATION-PLATFORMS-DESIGN.md]

*Proof needed before it goes out:* the design text is on `main` (this round). The post says "we are building", which
is true once B1 is claimed; if B1 has not started on the 18th, change the sentence to "we have designed". No picture is
needed. Rows 1 and 2 of section 6.

**Post 2. Wednesday 25 November 2026, 08:30: Databricks and Snowflake**

> "We are moving from Snowflake to Fabric." "We are moving from Databricks to Fabric."
> I hear both more often now. I have no opinion on whether you should. That is your decision and your numbers.
>
> If you do, here is the order I would do it in:
>
> 1. Inventory, read-only. What exists, and what is actually used. Counted.
> 2. Check the keys and the links against the rows, before the move. Neither platform enforces them for you.
> 3. Write down the ten KPIs that must not change. Get a name next to each.
> 4. Land the tables in OneLake. Check the keys and the links again.
> 5. Compute the ten KPIs on both sides. Same number, or find out why.
> 6. Only then rebuild: silver, gold, semantic model, report.
> 7. Run both in parallel. Switch the old off when the list has been green for a month.
>
> Steps 2, 4 and 5 are where Krusgraph helps: the same counting on both sides, by rule.
>
> What do you check before you switch the old platform off?

*Proof needed before it goes out:* "Neither platform enforces them" is the vendors' own documentation, cited in the
design, sections 2 and 3: check the citations are still marked Verified. "Steps 2, 4 and 5 are where Krusgraph helps"
needs B1 (the two-sided check) built and unit-tested on the synthetic pair; until then write "where Krusgraph is meant
to help; step 2 works today on tables already in Fabric". Rows 2, 3 and 4 of section 6.

**Post 3. Wednesday 2 December 2026, 08:30: Qlik**

> Moving from Qlik Sense to Power BI is not a conversion. It is a re-modelling.
>
> Qlik links tables by field name. When two tables share two fields, it makes a synthetic key and carries on.
> Power BI wants one column per relationship and, ideally, a star.
>
> So the questions in a Qlik to Power BI move are not about charts:
>
> – Which synthetic keys are real composite keys, and which are accidents of naming?
> – Which link table is really a dimension?
> – What does this set analysis expression ignore, and does the DAX measure ignore the same thing?
> – Does the measure give the same number per month as it did in Qlik?
>
> We are building the first three as rules in Krusgraph: the load script read into a plan, every synthetic key
> listed with a proposal and a count. The fourth is a reconciliation sheet per KPI.
>
> What a person still decides: which number is right when two apps disagree. No tool should decide that.

*Proof needed before it goes out:* the Qlik sentences are Qlik's documentation, cited in the design, part B. "We are
building" needs W7's reader on `main` (it was claimed, not pushed, when this was written) and B6 claimed. Rows 5 and 6
of section 6.

---

## 5. The assessment checklist a buyer can run in the chat on day one

For the buyer's own data person, in Claude (or another MCP client) connected to Krusgraph. It is split by what works
**today** and what is **design only**, because a checklist that fails on day one sells nothing.

### 5.1 Today: on tables that are already in Fabric

This is the "after" half of the method, and it works on any source Fabric can already reach, including a mirrored
Snowflake database or a mirrored Azure Databricks catalog once the buyer has set one up (Fabric's own step, design
sections 2 and 3). Honest status: Krusgraph's tools are tested live on a lakehouse with synthetic data; on mirrored
Snowflake and Databricks items they are tested with Fabric mocked and **have not had a live run** (`README.md`,
"Snowflake and Databricks").

| # | Ask in the chat | Tool | What you get |
|---|---|---|---|
| 1 | "List my workspaces and the sources in *workspace*." | `list_workspaces`, `list_sources` | The items Krusgraph can read as you |
| 2 | "List the tables in *source*, schema *schema*." | `list_tables` | Tables and columns with types, as Fabric shows them |
| 3 | "Plan this schema and say what stands behind each key and link." | `plan_backend` | Keys and relationships with the rule for each, and the evidence state: counted or not |
| 4 | "Validate the plan against the rows, with the column profile." | `validate_plan(profile=true)` | Per key: rows, distinct, NULLs. Per link: rows without a match. Per column: NULL share and distinct count. Counts only, no values |
| 5 | "Where can a total double?" | `validate_plan` (`amount_levels`) | Header amounts that a join to lines would repeat |
| 6 | "Which tables belong together, and which stand alone?" | `analyze_schema` | Roles, groupings, tables nothing links to |
| 7 | "What is built on these tables?" | `lineage` | Semantic models, APIs and reports that read them |
| 8 | "Compare the existing semantic model *name* with the plan." | `compare_semantic_model` | Relationships in the model that the rows do not support, and the reverse |
| 9 | "Write the review file." | `review_plan(validate=true)` | One file to hand to the person who signs |

What the buyer has after an hour: the landed side counted. What they do not have yet: the same counts from the old
side, and the comparison.

### 5.2 Today, local and Draft only: on the old side

- **Databricks.** The local stdio server with `KRUSGRAPH_PLATFORM=databricks` reads one Unity Catalog schema and runs
  the same key and link counts on a SQL warehouse (`docs/DATABRICKS.md`). **Draft only: unit-tested with Databricks
  mocked, never run against a workspace.** Say so when offering it.
- **Snowflake.** The CLI and `plan_from(execute=...)` read `INFORMATION_SCHEMA` on Snowflake (`README.md`). There is
  no Snowflake adapter that runs the counts; that is B2.
- **Qlik.** W7 claimed a small reader for a synthetic `.qvs` load script; it was not on `main` when this was written.

### 5.3 Design only: the questions the assessment will answer (B1 to B9)

Written as the buyer would ask them, so the offer can be read aloud. None of these work today.

1. "Inventory catalog *X*: how many schemas, tables, views, notebooks and jobs, and which have not been read in 90
   days?"
2. "Which of these tables can Fabric read in place, which must be copied, and which cannot be moved as they are?
   Give the reason per table."
3. "Check every key and link on the source. Then check them again on the landed tables and show only what changed."
4. "Here are our ten KPIs. Compute each on both sides, per month."
5. "For KPI 4 the numbers differ. Which column, and which rule?"
6. "List the views whose SQL uses something the target does not have."
7. "For Qlik app *Y*: list the synthetic keys and what you propose for each."
8. "Which measures in app *Y* can be translated with certainty, which are suggestions, and which need a person?"
9. "Who still reads the old tables this week?"

---

## 6. The proof each sentence needs before it can go public

A sentence leaves "draft" when its row is true and the place that says so is in the repository. Status on
12 November 2026.

| # | Sentence (in any pitch or post) | Proof it needs | Status today |
|---|---|---|---|
| 1 | "Krusgraph checks keys and links against the rows" | `validate_plan` on a Fabric source, live | **Have**, on a lakehouse with synthetic data (`docs/LIVE-TEST.md`, 27 October 2026). Say "on tables in Fabric" |
| 2 | "Fabric can read Unity Catalog tables in place / can mirror Snowflake" | Microsoft Learn, cited with URL and date | In the design's Sources, each marked Verified or Unverified. Use only the Verified ones, and write "Microsoft Fabric can", never "we" |
| 3 | "...on the Databricks side and again in OneLake" / "...in Snowflake and again in OneLake" | B1 unit-tested on the synthetic pair; then one live run against a real Databricks workspace and a real Snowflake account, with synthetic data, written up in `docs/LIVE-TEST.md` | **Missing.** Databricks side: mocked only (`docs/DATABRICKS.md`). Snowflake side: no adapter. Needs trial accounts, which only the founder can open |
| 4 | "The same number, or the column and the rule that explains the difference" | B1 and B3 on the synthetic pair with planted differences: every planted difference found and named, no false reasons; the test in `tests/`; then the live run of row 3 | **Missing.** Nothing built |
| 5 | "The load script read into a plan, every synthetic key listed" | W7's reader on `main`, then B6 unit-tested on synthetic `.qvs` files; then one run on a real, non-customer Qlik app (a Qlik sample app or one the founder builds) | **Missing.** W7's reader claimed, not on `main` |
| 6 | "Measures translated where the translation is certain" / "a reconciliation per KPI" | B7 with a published list of exactly which set analysis forms are translated; B8 run once on a real Qlik app and the Power BI model built from it, synthetic data | **Missing.** Nothing built. Needs a Qlik Sense tenant or desktop, which only the founder can provide |
| 7 | "Rebuilt from the checked plan: silver and gold, a semantic model, a report, an ontology" | The existing tools, live | **Partly.** Items created live 28 to 30 October and 7 November 2026 on synthetic data; `docs/MISSING-EVIDENCE.md` rows 1, 2 and 6 (screenshots, the notebooks' run in Fabric) still open |
| 8 | "A data product with a named owner" | The Data product page with an owner field, live | **Partly.** `product_life.py` (n198) is the first slice; the owner field is design (`docs/DOMAINS-DESIGN.md`) |
| 9 | "Kruse Consulting migrates with Krusgraph" | One migration done, even a small one on a pilot's data, with the customer's written yes to be mentioned, or stated without a name | **Missing.** No pilot has run (`docs/MISSING-EVIDENCE.md` row 9). Until then: "Kruse Consulting offers", not "has done" |
| 10 | "Open source (MIT)", "independent" | `LICENSE`, `CONTRIBUTING.md` | **Have** |
| 11 | Any number: hours saved, share of measures translated, time to migrate | A measurement on a named, reproducible set | **Missing, and not to be estimated.** No number goes out before it is measured |

What we never say, whatever proof arrives: that Fabric is cheaper or faster; that a migration is automatic; that
Krusgraph converts notebooks, SQL or Qlik apps; "certified", "partner", "endorsed"; a customer's name without their
written yes.

---

## 7. What exists today, what to build, the estimate, the first three

**Exists today (sales side).** `docs/PILOT.md` (a pilot package for one Fabric workspace, prices as proposals to
test); `docs/FAQ-COMPETITION.md`; `docs/MISSING-EVIDENCE.md`; the site's `/check` page on synthetic files. Nothing on
migration: no page, no offer text, no demo, no assessment template. `docs/marketing/` did not exist on `main` before
this file (M1 holds the folder for its own new files).

**To build (sales side).** Estimates in rounds of the usual size; the engine builds they wait for are in the design.

| # | Build | Waits for | Rounds |
|---|---|---|---|
| S1 | **The synthetic "before and after" demo**: the shop schema as a Snowflake-shaped and a Databricks-shaped source and as landed tables, with the planted differences, and the reconciliation sheet as a page a prospect can read. The first thing to show in a meeting | B1 | 1 |
| S2 | **The assessment report template**: the document the assessment ends with (inventory counts, key and link table, KPI list, risk list, path per object), filled from Krusgraph's answers, with the synthetic demo as the sample | B2 or B4 for the inventory; can start with section 5.1's tools | 1 |
| S3 | **The offer page text** for assessment, pilot and migration (one page per source, from section 3), with prices from the founder's decision on P1 | The founder's decisions; rows 3 and 4 of section 6 for the public version | 0.5 |
| S4 | A `/migrations` page on the site | Rows 3, 4 and 9 of section 6. **Not before** | 1 |
| S5 | A Swedish version of the three pitches and posts | The founder's yes to the English wording | 0.5 |

**First three.** S1 (after B1), S2, S3. Roughly 2.5 rounds, and none of it public until section 6 allows.

**The founder's decisions this text waits for.**

1. Is the assessment sold at a fixed price, and is it credited against the pilot? (P1, `docs/PILOT.md`.)
2. Which source first? The engine order in the design is the two-sided check first, because all three sources need it.
3. Trial accounts for Databricks and Snowflake and a Qlik Sense environment for the live proof (rows 3, 5 and 6).
4. Posts in English, Swedish or both; and which Wednesday goes to these drafts and which to M1's.
