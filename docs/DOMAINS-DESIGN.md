# Krusgraph for an organisation with several domains (design, W8)

Round W8. A design text, docs only, nothing implemented here. Written 12 November 2026 by a scheduled Claude session
with no live user, from the founder's notes of 11 and 12 November 2026: an organisation that uses Krusgraph across
several domains needs a structured way to work with its data products; Krusgraph supports the processes and a data
mesh way of working; it may get smarter from use; when a customer needs something, Krusgraph suggests it and Kruse
Consulting can help set it up; tips on which Fabric capacity suits the customer and how to save resources; and keeping
data quality up over time, connected to the OneLake catalog or Microsoft Purview (the founder mentioned Osmos).

It builds on, and does not repeat:

- `docs/FABRIC-IQ-AT-SCALE.md` sections 6 and 8 (n186): what one data product is, one Krusgraph Model item per data
  product, shared entities as bound copies, "align, do not duplicate".
- `docs/LIFECYCLE-DESIGN.md` (n191): detect, diagnose, propose, autonomy levels, approvals, the audit log.
- `docs/PROMOTE-DESIGN.md` (n198): dev, test and prod with Fabric's own Git integration and deployment pipelines.
- `docs/SCOPE-REVIEW.md` (S1): evidence state and coverage on every answer; count before claiming; suggestions narrow,
  each with rule and counts. Everything below that proposes something follows S1 section 6.
- `docs/WORKLOAD-UX-DESIGN.md` (D1): the six-step flow and the Data product page with its life strip and tabs.

**The W0, W2 and W3 design texts were not on `main`** when this was written (checked at claim time and again before
the last commit, 12 November 2026); only W7's claim was. Where this text touches what they are expected to cover (the
suggestion engine, the onboarding guide), it rests on S1 sections 6 and 7 instead and says so.

Rules for this text:

- **No AI in Krusgraph for Fabric** (`offering.py`). Every suggestion here is a rule, a count or a table.
- **No claim on the site** of data mesh, Purview, Osmos or capacity-advice support until the part is built and tested.
  Nothing in this text is site copy.
- Krusgraph is independent. "Works with Microsoft Fabric" describes compatibility only; there is no partnership with
  Microsoft.
- **Verified** means a public page was opened on 12 November 2026 and says it; the page and its date are in Sources.
  **Unverified** means no public page was found that says it, or the page could not be opened.
- **Today** names the file that does it now. **New** is work for a later round. Effort is **S** (a day or less),
  **M** (a few days), **L** (a week or more); "rounds" are build rounds of the usual size (one claim, one release).

Two words that collide, kept apart from here on:

| Word | Means |
|---|---|
| **Fabric domain** | Microsoft's: a group of workspaces by business area, with domain admins and contributors (part 1) |
| **Grouping** | Krusgraph's: tables that belong together, proposed by `domains.py` from the plan's links (S1 section 7 asks for this word). A grouping can become a data product; it is not a Fabric domain |

---

## 1. The portfolio: every Krusgraph data product, per Fabric domain

One page that answers, for a domain owner or the platform team: which data products do we have, who owns each, is
each healthy, which version, who uses it, and at which of the eight steps (part 2) it stands.

### What Fabric offers, and who may do what (Learn, opened 12 November 2026)

| Thing | What Learn says | Who | Source |
|---|---|---|---|
| Create a Fabric domain | "To create domain, you must be a Fabric admin." Subdomains: a Fabric admin or a domain admin; subdomains have no admins of their own | **Fabric admin** | F1 |
| Domain admin | Updates the description, names contributors, associates workspaces. Cannot delete or rename the domain or change its admins | Named by a Fabric admin | F1 |
| Domain contributor | A workspace admin allowed to assign their own workspaces to the domain (everyone by default, or named users and groups, or admins only) | Set per domain | F1 |
| See domains | "All users within a tenant can see all the domains defined in the tenant." Assignment does not change who can see or open an item | Everyone | F1 |
| List and get domains, no admin | `GET /v1/domains`, `GET /v1/domains/{id}`: id, displayName, description, parentDomainId. Scope `Domain.Read.All`. No roles returned | Any user | F3 |
| A workspace's domain | `GET /v1/workspaces/{id}` returns `domainId`, `capacityId` and `tags`. Viewer or higher; `Workspace.Read.All` | Workspace viewer | F5 |
| Assign a workspace to a domain | `POST /v1/workspaces/{id}/assignToDomain`. Workspace admin, and domain contributor or domain admin; `Workspace.ReadWrite.All` | Workspace admin | F4 |
| Admin domains API | `/v1/admin/domains…` (create, update, delete, assign workspaces by id, capacity or principal, role assignments): "The caller must be a Fabric administrator"; `Tenant.Read.All` or `Tenant.ReadWrite.All` | **Fabric admin** | F2 |
| Assign one item to a domain | Not documented; domains group workspaces | Unverified | F1 |
| Endorsement: Promoted | "Any user with write permissions on an item can promote it" | Item writer | E1 |
| Endorsement: Certified, Master data | Only reviewers a Fabric admin authorised (security groups only; a domain admin may override when delegated); each must be switched on by a Fabric admin | **Fabric admin** enables | E1, E2 |
| Set endorsement by API | No operation in the Core Items list sets it; the endorsement pages describe the portal only. Power BI REST not checked | Unverified (none found) | E3 |
| Read endorsement without admin | The OneLake catalog API overview says Get Item returns it; the Get Item reference has no such field. The admin scanner returns `endorsementDetails` | Unverified until tried live | C3, E3, L3 |
| Tags | Fabric admins create tenant tags, Fabric or domain admins domain tags; "Users with Write or Contributor permissions can apply up to 10 tags per item" | **Admin** creates; contributor applies | T1 |
| Tag calls | Create: `POST /v1/admin/tags/bulkCreateTags`, `Tenant.ReadWrite.All`. List: `GET /v1/tags`, `Tag.Read.All`. Apply: `POST …/items/{id}/applyTags` with tag ids, contributor, `ItemMetadata.ReadWrite.All` or `Item.ReadWrite.All` | As above | T2 |
| Item description | `PATCH /v1/workspaces/{ws}/items/{id}`, 256 characters, read and write on the item, `Item.ReadWrite.All` or the item type's scope | Item writer | T3 |
| OneLake catalog | Explore (name, type, owner, refreshed, workspace, endorsement, sensitivity; filters by domain, tags, endorsed), Govern, Secure | Everyone, for what they can open | C1, C2 |
| Catalog search API (preview) | `POST /v1/catalog/search`, `Catalog.Read.All`, results limited to what the caller may open. Searches name, workspace name and description; filters by type and workspace only. Returns no owner, endorsement, tags or domain | Any user | C4 |
| Govern tab limits | "Subitems such as tables aren't supported"; "Items of third-party workloads aren't included in the charts" | n/a | C5 |
| A data product object in Fabric | None found in the Fabric pages opened | Unverified (absence) | C1 |
| Who reads an item: relations | `GET …/items/{id}/relations/downstream?beta=true`: item read permission, `Item.Read.All`; "not recommended for production use" | Item reader (beta) | L1 |
| Who has access to an item | `GET /v1/admin/workspaces/{ws}/items/{id}/users` (preview): who may, not who does | **Fabric admin** | L2 |
| Tenant-wide lineage | Scanner API (`admin/workspaces/getInfo`, lineage and data sources): Fabric admin or a permitted service principal, `Tenant.Read.All` | **Fabric admin** | L3 |
| Who actually queried an item | No API found | Unverified | n/a |

### What the portfolio shows, and from where

| Column | From | Today | New |
|---|---|---|---|
| Fabric domain | The workspace's `domainId` (F5), the name from List Domains (F3) | `_product()` proposes groupings and says a domain "needs a Fabric administrator" | Read the real domain. One new delegated scope, `Domain.Read.All`; without it the page groups by workspace and says why |
| Data product | Each Krusgraph Model item the user can open (one item per product, `FABRIC-IQ-AT-SCALE.md` 8.1) | `outputs.json` per item | A read across workspaces, inside n226's time budget, with "12 of 30 workspaces read" when time runs out |
| Owner | `outputs.json` | `owner: null` | P1 of 8.1 |
| Step | Part 2, derived | none | Part 2, first round |
| Health | `krusgraph.health` through the SQL endpoint (`POST /workload/v1/health`, n200) | One word per product | The contract line of part 3: "31 of 34 clauses kept" with the run's date; "no run for 6 days" is its own state, never green |
| Version | The contract's version (part 3) | `0.1.0` | Part 3 |
| Consumers | Declared (part 3); observed from `lineage.py` in the workspace | `lineage` tool | The relations call (L1) when it leaves beta; until then the column says "in this workspace only" |
| Endorsement | Read only | none | Only after a live test shows a non-admin can read it; else "not read" with the reason |
| Capacity | `capacityId` (F5); SKU when the user may read it (part 8) | none | Part 8 |

Three honest limits, shown on the page:

1. **It lists what the signed-in person can open.** "Showing 14 data products in 6 workspaces you can open. Other
   workspaces may hold more." A tenant-wide list needs a Fabric admin's token (`Tenant.Read.All`); it is not proposed
   first, and Krusgraph's apps do not ask for that scope.
2. **A product in a workspace without a domain** is listed under "No Fabric domain", with the step an admin or
   contributor takes. Krusgraph does not assign workspaces.
3. **Krusgraph Model items do not appear in the Govern tab's charts** (C5). The portfolio is therefore not a duplicate
   of Govern; and descriptions and tags (part 9) go on the lakehouse, model and report, which Govern does count.

**Needs a Fabric admin:** creating domains and subdomains, naming domain admins, creating tags, switching on
certification and master data and naming who may certify, anything tenant-wide (scanner, admin lists). **Needs a
domain admin or contributor who is workspace admin:** putting a workspace in a domain. **Needs nobody but the user:**
reading domains, reading their own products, writing descriptions, applying existing tags, promoting an item.

**Where it shows.** In the Model editor, a Portfolio page reached from the Data product page ("All data products"):
the first layer of the overview in `FABRIC-IQ-AT-SCALE.md` 8.2, as a table first (D1: the same content as a list,
colour never the only signal). In the chat, one tool, `portfolio`, with the same rows and the coverage line.

**Estimate and first build.** Two rounds. First (M): the read across workspaces with domain, owner, step, health and
version, as a table, with the three limits said. Second (M): consumers and endorsement, each only after a live test
in the publisher's tenant. First to build: the table, because every other part needs a place to be seen.

---

## 2. The operating model: eight fixed steps

One data product moves through eight steps, always in this order. The steps are data (a closed list, like the issue
classes in `LIFECYCLE-DESIGN.md` section 2), not prose in a UI. Each step has one person who decides and one next
button. A step is never skipped silently: a product built before it had an owner shows "Approved: nobody yet".

### Roles

| Role | Who, in Fabric terms | Decides |
|---|---|---|
| **Domain owner** | A Fabric domain admin of the domain (part 1), or a person the organisation names when it does not use Fabric domains | Which needs become data products in the domain; who owns each; retire |
| **Data product owner** | A person in Entra, kept in `outputs.json` (`FABRIC-IQ-AT-SCALE.md` 8.1); needs write rights on the product's items | The contract; approves changes (`LIFECYCLE-DESIGN.md` 5.1); asks for endorsement |
| **Steward** | A person with write rights on the organisation's rule book (part 5) | Key and link decisions that become organisation rules; shared entity definitions (part 4); quality thresholds |
| **Platform team** | Fabric administrators and capacity administrators | Fabric domains, tenant settings, tags, capacity, Purview; everything in this text marked "needs a Fabric admin" |

Krusgraph grants no right and creates no role. A role is who Fabric lets do the thing, plus a name written in the
product's record. One person may hold several roles; in a small organisation all four can be the same person, and the
steps still show in order.

### The steps

| # | Step | Who decides | What Krusgraph shows | Next button | Stays a human decision |
|---|---|---|---|---|---|
| 1 | **Need** | Anyone states it; the domain owner takes it up | A need is a short record: the question to answer, the source, who asks. In the portfolio (part 1) as "Needs: 3 open" | **Look at the source** (plan and check, read only) | Whether the need is worth a product |
| 2 | **Suggestion** | Nobody yet | Groupings from counted links only, entities for tables with a counted key, measures for additive amounts (S1 section 7, "build, narrow"); each with rule, counts and evidence state; and the organisation rule behind it when there is one (part 5) | **Accept, split or merge** | Which tables belong together; the product's name |
| 3 | **Approval** | Domain owner (that it should exist and who owns it); data product owner (the contract, part 3) | The dry run: every item that would be made, every tenant setting it needs, the contract draft, the capacity the workspace is on (part 8) | **Approve** (with a reason, written to the audit log) | All of it. Krusgraph never approves |
| 4 | **Build** | Data product owner clicks; Fabric checks their rights | Create, as today (silver, gold, pipeline, model, report, API, ontology, agent), per item with its state | **Create** | Which outputs; the workspace |
| 5 | **Publish** | Data product owner asks; whoever holds the endorsement right decides | Catalog description and tags as a draft with the exact calls (`catalog.py`); the endorsement the items have now, read only; "Ready to ask for Promoted: all 14 checks passed in the last 7 runs" as a fact, not a request sent | **Write description and tags** (dry run first); **Open in Fabric** for endorsement | Endorsement, always (part 1: no documented call sets it, and it is a judgement). Sensitivity labels |
| 6 | **Monitor** | Nobody; the pipeline runs | The health word per product from `krusgraph.health` (`docs/HEALTH.md`), the contract's clauses with pass, fail or not checked (part 3), capacity facts (part 8) | **See health** | Thresholds (the owner's `ROW_COUNT_DROP`, freshness intervals) |
| 7 | **Change** | Data product owner; consumers are told for a breaking change | The proposal with its dry run (`LIFECYCLE-DESIGN.md` section 3); which contract clauses change and which consumers that reaches; the version bump | **Approve change** | Whether to break a consumer; the notice period |
| 8 | **Retire** | Domain owner and data product owner | Consumers that still read it; the soft retire (schedules off) before any delete (`product_life.py`) | **Retire** (never the primary button, as in D1) | When; whether to delete data |

### Where the step shows

**In the Model editor (Krusgraph for Fabric).** D1's six screens stay as they are; steps 1 to 4 are D1's Source, Map,
Check, Dry run and Create. Steps 5 to 8 live on the Data product page, whose life strip (D1 section 4.6: Suggested,
Checked, Built, Keep up to date, Versions, Retire) becomes the eight steps with the current one marked. The foot bar's
one primary button is the step's next button from the table. A step waiting for someone else says who: "Waiting for
the domain owner (their name) to approve". The portfolio (part 1) shows the same step word per product, so a domain
owner sees "3 at Approval, 1 at Change" without opening any.

**In the chat (Krusgraph for Claude and other MCP clients).** Every plan-derived answer carries one field,
`step: {now, next, who}`, and the card's next button (`mcp_apps_next.py`, n218) is that step's button. Without cards
the answer's last line is the same sentence: "Step 3 of 8, Approval. Next: the owner approves the dry run." The chat
never moves a product past step 3 by itself: approval is recorded with the signed-in person's identity, and an agent
passing `dry_run=false` without it gets `kind: needs_approval` with the name of who can give it. (Today
`create_backend` asks the agent to get the user's go-ahead; this makes the go-ahead a record instead of a sentence in
the skill.)

**What data mesh means here, and no more.** Four things, each of which is a step or a record above: products owned in
the domain (the owner field); a product has a contract others can rely on (part 3); the platform is self-service (the
dry run names what an admin must do first); shared rules are applied by a computer where they can be (the row checks,
the rule book). Krusgraph does not make an organisation a data mesh, and the site must not say so.

### Estimate and first build

Two rounds. First (M): the step as data on every product record and answer, derived from what already exists (has a
plan, has a check, has an owner, has outputs, has a description, has health rows): no new state to keep, so it cannot
disagree with the product. Second (M): Need and Approval as records in the item's definition with the audit row, and
`needs_approval` in the chat. Publish, Change and Retire reuse n116, the Lifecycle rounds and n198.

---

## 3. The data product contract

**Today.** `domains.py` (`contract()`, `draft()`) writes one ODCS v3.2.0 YAML per grouping from the plan: tables,
columns with logical types, keys, and the interfaces to other groupings; status `draft`, version `0.1.0`
(`docs/DOMAINS.md`). It is not kept in the item, has no owner, and nothing compares it with the rows after Create.

**The design: the contract holds only what Krusgraph can state, and every clause names the check that tests it.** A
promise nothing checks is written as "stated by the owner, not checked", never as a pass.

| Clause | Holds | From | Checked by (`krusgraph.health`, `docs/HEALTH.md`) | When it fails |
|---|---|---|---|---|
| **Contents** | The tables and views the product offers (gold views, the model's tables), columns and types; for an amount column its level (header or line) and, when the plan knows it, the currency or unit column | The plan, `gold.py`, `level_measures.py` | `drift` (a column or table gone or retyped), `row_count` | Red; a removed or retyped column is a breaking change |
| **Keys** | Per table the key, with its rule and evidence state (S1: declared, counted and holds, by name only) | The plan after the check | `key` (NULL keys plus duplicates) | Red. A key "by name only" cannot be promised: the clause says "candidate, not counted" |
| **Links** | The links inside the product and the interfaces it offers or uses | The plan, `domains.py` `interfaces` | `orphans`; `join_rows` and `join_sums` for a gold view that joins (the doubled-total check) | Red for the product; for an interface also amber on the consumer |
| **Refresh** | The schedule the pipeline has, and the promise: "data no older than 2 schedule intervals" | The pipeline's schedule (`health.interval_minutes`) | `freshness`, from Delta history, never from rows | Amber at 2 intervals, red at 3, as today |
| **Owner** | A person in Entra and, optionally, the Fabric domain | `outputs.json` | That the person still has write rights on the items (a read at open); a missing owner is amber | "Choose an owner" is the next button |
| **Consumers** | Two lists, kept apart: **declared** (a product or person who asked to rely on an interface, with the date and the contract version they read) and **observed** (items that read the product's tables: the `lineage` tool, same workspace; other workspaces only as far as the signed-in user can see, part 1) | The need record of the consuming product; `lineage.py` | An observed consumer that is not declared is shown: "reads orders, has not declared it" | Nothing fails; it is the list a breaking change notifies |
| **Version** | `major.minor.patch` | Bumped on an approved change (`LIFECYCLE-DESIGN.md` 5.2) | n/a | Major: a column, table, key or interface removed or retyped, or a slower refresh. Minor: something added. Patch: descriptions |

What the contract does not hold: prices, an uptime figure, a response time, anything about the meaning of a value
that no rule can test. The owner may add free text under "Stated by the owner"; it is shown under that heading and
never contributes to green.

**Checked like everything else.** The check notebook already writes one row per check and run. The contract page is a
join of the contract's clauses with the latest run's rows by `object`: each clause shows pass, fail, warn, or "not
checked" with the reason (the evidence state from n226's `coverage.py`). "Contract kept: 31 of 34 clauses passed, 1
failed, 2 not checked" is the product's line in the portfolio. No new check type is needed for the first version; the
clause-to-check mapping is the table above.

**Where it is kept.** A `contract.yaml` part in the Krusgraph Model item's definition (as 8.1 proposed), status
`draft` until the owner approves at step 3, then `active`; each approved change keeps the previous file as a version.
The definition travels with Git integration only if a workload item does (Unverified, `PROMOTE-DESIGN.md`); until
then each stage's item holds its own copy and the Data product page says when they differ.

**Estimate and first build.** Two rounds. First (M): the contract kept in the item with owner, refresh and version,
and the clause-to-check join on the Data product page: this turns the health table into "is the contract kept". Second
(M): declared consumers and the notice on a major change. ODCS's own quality and SLA blocks are filled only from the
table above; whether to follow a later ODCS version is a small decision for the round.

---

## 4. Shared entities across domains

The case: Sales, Service and Finance each have data products, and each has customers. Without a rule each builds its
own `Customer`, with its own key, and totals by customer never agree across reports.

**One shared vocabulary, owned in parts.** Not one big ontology item that everyone edits, and not one per domain that
nobody compares. Each entity has exactly one owning data product; the set of entities marked shared is the
organisation's vocabulary.

| Question | Rule |
|---|---|
| Who owns an entity | The data product that holds the table the key is counted on (the provider side of the interface, `domains.py`). For Customer, the product over the customer master |
| What the owner decides | The entity's name, its key, its shared properties and their descriptions |
| What a consumer may do | **Reference** it: a link from its own table to the owner's key, checked as an interface (`orphans` across products). **Extend** it: add its own properties and links in its own namespace (`service#Customer.sla_tier`), from its own tables that carry the owner's key |
| What a consumer may not do | Change the key, rename the entity, redefine a shared property, or hold a second entity with the same name and another key |
| When an extension should be shared | The consumer proposes it to the owner (a change at step 7 on the owner's product). The owner decides |
| Two domains both claim the entity | Krusgraph counts and shows: rows and distinct keys on each side, how many key values are in both, how many only in one, and the same after trim, case fold and leading-zero strip (S1 mechanism 4). "CRM has 41 200 customers, ERP 38 950; 37 800 match on customer_no after stripping leading zeros." Which is the master is the stewards' decision, recorded with its reason |
| The owner changes the key | A major change of the owner's contract; every referencing product is listed and told before approval |

**How it is written in Fabric.** As `FABRIC-IQ-AT-SCALE.md` 8.1: one namespace per data product inside an ontology
item is Verified (preview) there; a reference from one ontology item to another is **Unverified** (no Learn page
found). So a shared entity is written into the consumer's ontology as a bound copy with the description "Defined in
`customers`. Edit it there.", and on each Create and each health run Krusgraph compares the copy with the owner's
definition and says when they differ. In the semantic model the same idea is the conformed dimension: the consumer's
model reads the owner's gold view of the customer, it does not build its own. If Microsoft documents cross-item
references, the bound copy becomes a reference and nothing else changes.

**The register.** The list of shared entities is not a new item to keep in step. It is read: every Krusgraph Model
item the user can open has its contract, and an entity with `shared: true` in its owner's contract is in the register.
The portfolio (part 1) shows it: entity, owning product and domain, key, the products that reference it, the products
that extend it, and "copy differs" where it does.

**Estimate and first build.** Two rounds, after part 3's first round. First (M): `shared: true` on an entity, the
register as a read, and the cross-product `orphans` check for an interface (the consumer's pipeline counts its
reference column against the owner's gold view: one more row in its health table). Second (M): bound copies checked
equal (P6 in 8.1) and the two-claimants count. The first is worth building alone: "your Service product has 312
customer numbers that the Customer product does not know" is the sentence a multi-domain organisation lacks.

---

## 5. Smarter from use, without AI

"Smarter" here means one thing: **a decision a person has made once is not asked again, and shapes the next
suggestion, and the suggestion says so.** No model is trained; nothing is statistical beyond counting.

**Today.** `review.py` keeps, per plan, each key and link with `review` (proposed, accepted, rejected, open), a reason,
and `check` (what the rows said). `carried_arguments()` turns the file back into `keys` and `confirmed` for the next
call on the same schema. Decisions do not travel to another schema, product or person.

### Decisions become rules, in a closed list of shapes

| Shape | Example decision | The rule it becomes | Effect on the next suggestion |
|---|---|---|---|
| **Link by column name** | Accepted `orders.kund_nr → customers.customer_no` | "A column named `kund_nr` refers to `customers.customer_no`" | Proposed for `invoices.kund_nr` with rule **O1** and the decision it rests on; still counted before it is shown as holding |
| **Rejected link** | Rejected `orders.status_id → statuses.id` ("status is a code list per module") | "Do not propose `status_id → statuses.id`" | Not proposed; listed under "Not proposed because of a decision", with the decision |
| **Key by table pattern** | Accepted key `(id, valid_from)` on `price_hist` | "Tables named `*_hist` have key `(id, valid_from)`" | Proposed as a candidate key with rule **O2**; counted before it is called a key |
| **Rejected key** | Rejected `id` as key of `stg_orders` (reloads duplicate it) | "`stg_*`: `id` is not a key" | Not proposed; listed |
| **Shared entity** | Stewards chose ERP as master for Customer | "Customer is owned by product `customers`" | A second Customer is proposed as a reference, not a new entity (part 4) |
| **Name of a thing** | Renamed entity `Kna1` to `Customer` | "`KNA1` is called Customer" | The name is proposed; the description says where it came from |

Rules of the rules:

1. **Rows outrank rules.** An organisation rule proposes; the count decides. A rule whose link has orphans is shown as
   "proposed by rule O1 (decision of 3 November 2026), counted: 412 orphans", never as passed.
2. **Every suggestion names what it rests on:** the rule id, and behind it the decision: who (or "a steward", see
   privacy), when, on which product, with which reason. "Why this?" on any proposed row opens exactly that.
3. **A decision stays local until a person promotes it.** One accepted link is a decision on one product. When the
   same decision has been made on three products (a count, shown), Krusgraph offers the steward "Make this an
   organisation rule?". A steward can also promote at once. Nothing becomes a rule by itself.
4. **Deterministic.** The same plan, rules and rows give the same suggestions, in the same order. A rule can be
   switched off and the suggestion list is recomputed; the diff is shown before the switch is kept.
5. **Conflicts are shown, not resolved.** Two rules that disagree both appear with their decisions; the steward
   decides which stays.
6. **Rules age.** A rule whose proposals were rejected twice since it was made is marked "questioned" and shown to the
   steward; it keeps working until a person changes it.

### Where it is stored, who can change it, privacy

| Question | Answer |
|---|---|
| Where | In the customer's tenant only. For Krusgraph for Fabric: a `rules.json` part in one Krusgraph Model item the platform team names as the organisation's rule book (its id is a workload setting), read by every other item at plan time. For the chat: the same file, read from the rule book item or passed as a `rules` argument beside `previous` (`review_plan`); for Krusgraph Open Source, a file in the user's repository |
| Not where | Not on Krusgraph's hosted service, which keeps no customer content (the trial row holds a tenant id and salted hashes only, `docs/BILLING-MODEL.md`). Not shared between organisations. Kruse Consulting does not see a customer's rules unless the customer hands the file over |
| Who can change it | Whoever Fabric lets write the rule book item: the stewards. Everyone who can read it sees every rule and its history. Each change is an audit row (who, when, before, after, reason) |
| What it holds | Table and column names and name patterns, rule shapes, decision ids, product names, dates, reasons typed by people, counts. Never a row value, a sample, a token |
| Personal data | A decision names a member of staff. Stored as the Entra object id; the display name is resolved when shown, to people in the same tenant. A tenant setting shows the role instead of the name ("a steward"). A person's id can be removed from past decisions on request; the decision and its reason stay. Reasons are free text: the field says "do not write personal data here" |
| Sensitive names | Column names can themselves be sensitive (`diagnosis_code`). They never leave the tenant by this design, and `privacy.py`'s masked columns are not written into rules by name |
| Size limit of an item definition | Unverified (`LIFECYCLE-DESIGN.md` section 4). If too small, the rules go to a lakehouse file the rule book item points at |

"Smarter across customers" (rules learned at one customer helping another) is **not proposed**. It would need each
customer's opt-in and would send their names out. What does travel is what Kruse Consulting curates and publishes
itself: the packs (`docs/PACKS.md`), which name public sources.

**Estimate and first build.** Three rounds. First (M): shapes 1 and 2 (link by column name, rejected link) from one
`rules.json`, in `infer.py` as rule O1 with the decision id in the plan's rule text, and "Not proposed because of a
decision". This alone answers "it asked me the same thing in every schema". Second (M): the rule book item, promote
and switch off with the diff, the audit rows. Third (M): the key shapes, the questioned mark, the role-instead-of-name
setting. Depends on S1 mechanism 4 (count before claiming, n226 and after) so that a rule-proposed item is counted in
the same call.

---

## 6. Guidance for agents

Agents (Claude, Copilot, others) increasingly do the building in Fabric. Krusgraph can tell them when it is useful.
It must do so the way it would tell a person: truthfully, once, and leaving the choice with the user.

### Three places, one text

| Place | Today | New |
|---|---|---|
| **Server instructions** (`server.py`, `MCPServer(instructions=…)`) | A long paragraph of paths and tool names, grown round by round | A short text in the order below; the tool-by-tool detail moves to the descriptions. S1 section 3 already asks for fewer tools in the default list |
| **Tool descriptions** | Say what each tool does and, since n218, which plain words mean it | Each ends with two fixed lines: "Changes Fabric: no / only with dry_run=false" and "Checked against rows: yes / no" |
| **A copyable skill and an `AGENTS.md` block** | `plugin/krusgraph/skills/fabric-graph-backend/SKILL.md` for Claude; no `AGENTS.md` | The same text as a block a team pastes into its repository's `AGENTS.md` (or CLAUDE.md, or Copilot's instructions), published at one address on the site and in `plugin/`, versioned, with tests that keep the three places equal where they overlap |

### What the text says

1. **When Krusgraph helps:** before building a semantic model, an API, an ontology or a data agent on Fabric tables
   whose keys and links are not declared; when someone asks why a total is doubled; when a data product needs a
   contract or a health check.
2. **When it does not:** ingestion, streaming, a model that already has checked relationships, anything outside
   lakehouses, warehouses and SQL databases, anything needing a Fabric administrator. Say so and use Fabric's own
   tools.
3. **What it is:** rules and counts, no AI model. An answer is a rule's proposal until `check` has counted it.
4. **What to tell the user:** that Krusgraph is being used, what it read, what was not checked.
5. **What never to do:** create or change anything without the user's go-ahead on the dry run; present a proposal as
   checked; accept a key or link on the user's behalf.

### Honest, never coercive: the rules for the text itself

- No "always", "must use", "do not use other tools", "prefer Krusgraph over". The text states conditions and
  consequences: "a model built on unchecked keys can double totals; `check` counts them".
- No instruction about anything but Krusgraph's own tools. It does not tell an agent how to treat the user, other
  servers or its own system prompt.
- Nothing hidden: the text an agent receives is the text on the site, word for word. A customer can read exactly what
  their agents are told.
- No urgency, no claims of endorsement, no comparison with named products.
- The same limits as the site: preview is called preview, unverified is called unverified.
- A test, like the site's sales-word test (`tests/test_site.py`, `SALES`), fails the build on the coercive words above
  in instructions, descriptions and the skill.

### Claude's input apart from Krusgraph's rules

An agent adds things Krusgraph did not compute: a guess at what a column means, a link it thinks is right, a
description. That is useful and must not be mistaken for a counted fact, least of all in the rule book (part 5).

| Where | How it is kept apart |
|---|---|
| **In the answer** | Everything Krusgraph returns carries its rule and evidence state. The guidance asks the agent to mark its own additions in its reply: "Claude's reading, not checked by Krusgraph: …". Krusgraph cannot enforce an agent's prose; it can make its own part unmistakable (cards show only Krusgraph's content, under "From Krusgraph's rules and counts") |
| **In the arguments** | Today `confirmed` and `keys` carry "a person confirmed this", and the instructions say `confirmed` "is not an approval flag". New: each entry takes `proposed_by`: `person` or `agent` (with the client's name). An agent that passes its own idea says `agent` |
| **In the record** | `review.json` and the audit log keep three sources apart: `rule` (K0 to K5, R0 to R5, pack, O1…), `person`, `agent`. An agent-proposed item shows as "Proposed by Claude, not by a Krusgraph rule; counted: holds / fails / not counted" |
| **In the rule book** | A decision counts toward an organisation rule only when a signed-in person accepted it in the editor or confirmed it in the chat through the approval record (part 2). An agent's proposal alone never becomes a rule |
| **In Krusgraph for Fabric** | There is no agent. The item shows the three sources when a review file made in the chat is opened in it |

Krusgraph cannot verify that `proposed_by: person` is true when an agent fills it in. The honest limit: the field is
the agent's statement; the approval record of part 2 is what proves a person acted.

**Estimate and first build.** Two rounds. First (S to M): the short instructions, the two fixed lines on every tool,
the `AGENTS.md` block in `plugin/` and on the site, the wording test. Second (M): `proposed_by` through `review.py`,
the answers and the cards. The first is cheap and should ride with S1's tool-list cut.

---

## 7. Services: where a paid set-up by Kruse Consulting fits

Internal. An idea for the founder, not an offer, not for the site in this form. Krusgraph's subscription stays what
`docs/BILLING-MODEL.md` says; services are separate and optional, and nothing in the product works worse without them.

### Where help is needed, and what Krusgraph can say there

The founder's line: when a customer needs something, Krusgraph suggests it, and Kruse Consulting helps set it up. The
honest form is that the product names the **need** from a fixed condition, says what the customer can do themselves,
and mentions help once.

| Condition (counted, deterministic) | What Krusgraph says | Self-service path | Where a set-up fits |
|---|---|---|---|
| A domain has no data product with an owner | "No product in Sales has an owner" | Steps 1 to 3 of part 2 | **Domain start**: the first product of a domain, with owner, contract and health, built together |
| The same entity name with different keys in two domains | The two-claimants count (part 4) | The stewards decide | **Shared entity agreement**: a facilitated decision on Customer, Product, Supplier, with the counts as the agenda |
| More than N tables without a key by any rule (S1's coverage line) | "106 tables have no key by name or count" | `keys` by hand; the review file | **Source mapping**: an ERP-specific pass; the result is rules in the customer's rule book and, where public sources allow, a pack |
| A step needs a Fabric admin (domain, tag, tenant setting, capacity) | The dry run's list | The admin's own steps, linked to Learn | **Platform set-up** with the platform team: domains, tags, workspaces per stage (`PROMOTE-DESIGN.md`) |
| A check has failed for 14 days with no decision | "orphans on orders.customer_id: failing since 29 October" | The Lifecycle proposal | **Quality review**: root cause in the source system, which no tool does |
| Capacity facts of part 8 show a pattern | The fact, with the customer's own numbers | Fabric's own settings | **Capacity review**, from the customer's measured numbers only |
| The customer wants results in Purview (part 9) | What can be written and what needs a licence | Their Purview admin | **Governance hook-up**, once that part exists and is tested |

How it is shown: one line under the condition, "Kruse Consulting offers help with this", with a link to a page; shown
once per condition, dismissable for good, and off entirely with one tenant setting. No pop-up, no counter, no change
of wording when dismissed. **Nothing is sent to Kruse Consulting**: no condition, no count, no tenant name. The
customer writes if they want to. A partner-led organisation (`docs/PILOT.md`, partner-led pilot) can point the link
at its own consultancy; the conditions are the same.

### An idea for pricing

- **Fixed price per package, with a written result**, for the two that repeat: Domain start (result: one product at
  step 6 with a kept contract) and Platform set-up (result: the admin steps done and listed). A fixed price is honest
  only when the scope is the product's own steps; that is why the eight steps matter commercially.
- **Day rate** for Shared entity agreement, Source mapping, Quality review and Capacity review: their length depends on
  the customer's data and people.
- **No retainer tied to the subscription**, no "success fee" on capacity savings (it would reward promising a saving,
  which part 8 forbids), no service required to use any feature.
- Amounts are the founder's; none is written here, as in `docs/PRICING-NOTES.md`.

What stays a human decision: everything in this part. Whether to offer services at all through the product is the
founder's call, and Microsoft Marketplace's rules for mentioning services inside a listed workload are **Unverified**
here (not read this round; `docs/WORKLOAD-LISTING-AND-PAYMENT.md` is the place to check before any such line ships).

**Estimate and first build.** One round (S to M) for the conditions as data and the one line, after parts 2 and 3
exist; before that, nothing to build. First: write the two fixed packages down as a one-page scope each (founder),
because the product's line should link to something exact.

---

## 8. Capacity advice

The founder's ask: tips on which Fabric capacity suits the customer and how to save resources. The rule for this
part: **Krusgraph states facts it has read and the documented mechanism, with the customer's own numbers. It never
states a price, a saving or a percentage it has not measured in that customer's tenant.** Fabric bills in the
customer's currency under the customer's agreement; Krusgraph knows neither.

### What Krusgraph can read (Learn, opened 12 November 2026)

| Source | Gives | Needs | Verdict | Source |
|---|---|---|---|---|
| `GET /v1/workspaces/{id}` | `capacityId`, `capacityRegion`, `domainId` | Workspace viewer; `Workspace.Read.All` (the apps have it) | **Read today** | F5 |
| `GET /v1/capacities` | `sku`, `region`, `state`, only for capacities where the caller is admin or contributor | `Capacity.Read.All` (new scope) | Read when the user may; else "SKU not readable by you" | K1 |
| Job Scheduler: job instances | Per item: scheduled or manual, status, start, end, failure reason; the 100 most recent | `Item.Read.All` or the item type's scope | **Read** | K2 |
| Job Scheduler: schedules | Enabled, interval in minutes or daily, weekly, monthly times, owner | Same | **Read** | K3 |
| `krusgraph.health` | Per run: row counts, freshness (minutes since the last Delta commit that wrote rows), check results | The customer's lakehouse | **Read today** (`health.py`) | n200 |
| Delta history | Commit times per table | A Spark session, which costs capacity: read only inside the check notebook, which runs anyway | In the pipeline only | K4 |
| Capacity Metrics app | CU by item and operation over 14 days, throttling, 30-second timepoints | Capacity admin to install. "The semantic model … is only supported for use by the reports provided in the app. Any consumption from, usage of, or modification of the semantic model isn't supported" | **Not read.** A person reads it | K5, K6 |
| Chargeback app | CU by workspace, item, domain, user; same clause | Capacity admin | **Not read** | K7 |
| Capacity overview and operation events (Real-Time hub) | Every 30 seconds: SKU, base CU, CU used, the throttling percentages; per operation: workspace, item, CU | Capacity admin on the capacity; an eventstream the customer sets up; best effort, no backfill | Readable **only if the customer lands them in a table** and points Krusgraph at it. Later, optional | K8, K9 |
| A capacity metrics REST API | None found | Unverified | n/a | n/a |
| Azure Resource Manager (`Microsoft.Fabric/capacities`: get, update SKU, suspend, resume) | The capacity as an Azure resource | An Azure token (`management.azure.com`), Azure RBAC actions, and for scaling also capacity admin | **Never called.** Krusgraph asks for no Azure scope. Pause, resume and scale are a person's actions | K10, K11, K12 |

Mechanisms Learn documents, which the tips cite and do not restate as savings:

- **SKUs:** F2 to F2048 (and larger), capacity units equal to the number; billed per second with a one-minute minimum.
  On F64 or larger, users with a Free licence and viewer role can view Power BI content; below it they need Pro (K13).
- **Smoothing and throttling:** interactive work smoothed over 5 to 64 minutes, background over 24 hours; delay after
  10 minutes of future capacity used, interactive rejection after 60 minutes, everything rejected after 24 hours (K14).
- **Pause:** remaining overage and smoothed work "are summed, and added to your Azure bill"; a reservation's unused
  hours cannot be carried forward, so pausing a reserved capacity saves nothing (K11, K15).
- **Autoscale of an F capacity:** not documented; Learn offers manual scale, pause and resume, and capacity overage
  (generally available, billed at three times the pay-as-you-go rate up to a threshold; the two overage pages disagree
  on whether it is on by default) (K14, K16). Spark can be billed on demand per capacity instead of from the capacity's
  CU ("Autoscale Billing for Spark", now titled on-demand billing), a capacity admin's choice (K17).
- **Direct Lake guardrails per SKU:** up to F32, 300 million rows per table; F64, 1 500 million; above, more. Beyond
  them Direct Lake on OneLake fails to refresh, Direct Lake on SQL falls back to DirectQuery when fallback is on (K18).
- **Direct Lake against import:** a Direct Lake refresh "copies only metadata (framing)"; import copies the data.
  No CU figures comparing them were found: Unverified (K18, K19).
- **Notebook sessions:** with high concurrency, "only the initiating notebook or pipeline activity that starts the
  shared Spark application is billed"; in a pipeline a session tag groups up to 5 notebooks with the same lakehouse
  and settings. Sessions expire after 20 idle minutes by default; a starter pool's idle time is not billed (K20, K21).

### The tips: fixed rules per data product

Each tip is a row in the Data product page's Overview (and in `portfolio`), shown only when its condition is counted
true, with the numbers, the Learn link, and "what Krusgraph cannot see".

| # | Tip | Reads | Condition | Says (example) | Cannot see |
|---|---|---|---|---|---|
| C1 | Schedule against change rate | Schedule (K3), freshness rows in `krusgraph.health` | Over the last 14 days, fewer than 1 run in 4 found a new source commit | "The pipeline ran 336 times in 14 days. The source tables had new data before 14 of them. A daily schedule would have caught each within 24 hours." | Whether someone needs the hourly freshness |
| C2 | Runs that fill the interval | Job instances (K2) | Median run time above 80 % of the interval | "Median run 13 min on a 15 min schedule: runs can overlap" | Why it is slow |
| C3 | Failed and capacity-limited runs | Job instances; the `capacity_limit` class (`LIFECYCLE-DESIGN.md` 1.3) | Any in 14 days | "3 of 336 runs failed with a capacity error, all between 08:00 and 09:00" | What else ran then; that is in the Metrics app |
| C4 | One session for the pipeline's notebooks | The pipeline Krusgraph made (`pipeline.py`) | Its silver, gold and check notebooks run as separate sessions | "These three notebooks can share one Spark session (session tag). Learn: only the activity that starts the shared session is billed." | The measured difference: none claimed |
| C5 | Direct Lake guardrail | SKU (K1), row counts in `krusgraph.health` | A table above 80 % of the SKU's rows-per-table limit | "`order_lines` has 262 million rows. On F32 the limit is 300 million; above it the model falls back to DirectQuery or stops refreshing." | Growth beyond what the health table has recorded |
| C6 | Import model refreshed more often than the data changes | A model Krusgraph finds (`compare_semantic_model`), its refresh schedule, C1's change count | Import mode and more refreshes than source commits | "The model copies the data 24 times a day; the data changed twice. A Direct Lake model reads the Delta files and refreshes metadata only." | CU of either mode: Unverified, not stated |
| C7 | Hours when nothing Krusgraph built runs | Job instances of the product's items | No run in the same window on every one of 14 days | "Nothing in this data product ran between 19:00 and 05:00, or on a weekend, in 14 days." | Reports opened, Copilot, other workspaces on the capacity. So this is one input to a pause decision, never the decision |
| C8 | Trial or small SKU and what will not work | SKU | Trial, or below F64 | "Trial capacity: Copilot and the data engineering agent are not available. Below F64, report viewers need a Pro licence." | Licences people already hold |
| C9 | A smaller or larger SKU | **Only numbers the capacity admin enters or exports from the Metrics app**: peak and typical utilisation, throttling events, over which days | Entered | Arithmetic on those numbers and no more: "You entered: peak 31 % of F64 over 14 days, no throttling. F32 has half the capacity units; the same load would peak near 62 % of F32. Check before deciding: viewers need Pro below F64 (K13); `order_lines` is at 87 % of F32's Direct Lake limit (C5)." | Next month's load; prices |

Never: a currency amount, "save 40 %", a recommended SKU without the customer's measured utilisation, a tip that
pauses, scales or reschedules anything by itself. C9 without entered numbers shows nothing but "Enter your measured
utilisation to compare SKUs", with the link to Microsoft's own sizing pages and its SKU estimator (preview) (K22).

**What stays a human decision:** the schedule (the owner), pause and resume, the SKU, a reservation, capacity
overage, surge protection, on-demand Spark billing (the capacity admin and whoever pays the Azure bill). Krusgraph's
only own change is C4, and only in a pipeline it built, through the normal dry run and approval.

**Estimate and first build.** Three rounds. First (M): C1, C2, C3 and C7, from the health table and the two job calls;
no new scope if the apps' item scopes cover Job Scheduler reads (to check against `docs/SCOPES.md` in that round).
These need the pipeline to have run for 14 days somewhere, so the first evidence is the publisher's own tenant on
synthetic data, and the tips must say "14 days of runs needed" before that. Second (S to M): `Capacity.Read.All`, the
SKU, C5 and C8, with the guardrail table as data and its Learn date. Third (M): C9's entered numbers, and C4 after
the session tag's JSON field is read on Learn (not opened this round: Unverified). C6 waits for a customer who has
import models.

---

## 9. Data quality over the lifecycle, the OneLake catalog, Purview and Osmos

### 9.1 What Krusgraph already checks, run over time

| Check | Once (chat or editor) | Every pipeline run (`krusgraph.health`, n200) |
|---|---|---|
| Keys: NULLs and duplicates | `validate_plan` (`evidence.py`) | `key` |
| Orphans per link | `validate_plan` | `orphans` |
| Doubled totals: rows and sums before and after a join | `validate_plan`, amount levels (`level_measures.py`) | `join_rows`, `join_sums` |
| Row counts, with the previous run as baseline | n/a | `row_count` |
| Freshness from Delta history | n/a | `freshness` |
| Schema drift against the plan | `plan_drift`, the monitor | `drift` |
| Rows set aside | n/a | `quarantine` |

What "over the lifecycle" adds is not a new check but three readings of the same table:

1. **Trend per check:** the last 30 runs of one object as pass, warn, fail and the count ("orphans on
   `orders.customer_id`: 0, 0, 0, 14, 212"), so a slow decline is seen before it is a failure.
2. **Contract kept** (part 3): clauses joined to the latest run.
3. **Per Fabric domain** (part 1): the products' lines side by side, and across products the shared-entity
   interface checks (part 4).

S1's limit stands: the health table and alerts are unit-tested and have not been run in Fabric
(`docs/SCOPE-REVIEW.md` section 7, "more lifecycle"). **Running them once in the publisher's tenant and recording it
comes before any of 9.2 to 9.4.**

### 9.2 Publishing to the OneLake catalog

| What | Can Krusgraph write it | How, and the limit | Source |
|---|---|---|---|
| **Description** | Yes | Update Item, 256 characters, on the lakehouse, model, report and the other items with an update call (`catalog.py`, a draft since n116; nothing is sent today). The catalog search API searches descriptions, so this is what makes a product findable | T3, C4 |
| **Tags** | Apply yes, create no | Tags are applied by id and must exist: a Fabric admin (or a domain admin, for domain tags) creates them. At most 10 per item, 40 characters | T1, T2 |
| **Endorsement** | No | No documented call; a person promotes or certifies in Fabric | E1, E3 |
| **Tables and columns** | No | No public call sets a table's description or tags (`catalog.py`); Govern does not show tables (C5) | C5 |
| **A quality score field** | No | The catalog has no such field in the pages opened | Unverified (absence) |

The design, small on purpose:

- **Description = what it is, plus one dated quality line.** "Data product Sales orders v1.2.0, owner (name). 6
  tables, 5 keys, 7 links. Krusgraph check 12 Nov 2026: 31 of 34 contract clauses kept." The date is part of the
  sentence because a description goes stale: Krusgraph rewrites it when a person opens the product or clicks
  **Write description and tags** (step 5), as that person. The pipeline does not write it (whether a notebook's
  identity may call Update Item was not read: Unverified), so the sentence can be days old and says its day.
- **Tags = stable facts only.** `Krusgraph`, the data product's name, `Contract` once a contract is active. Never a
  health tag ("Healthy"): a tag has no date, and a wrong green tag in the catalog is worse than none.
- **Endorsement = evidence for a person.** The Data product page states what a reviewer would want: runs, clauses
  kept, since when. The person endorses in Fabric. Krusgraph shows the endorsement it can read (part 1) beside the
  health, so "Certified, and failing since Tuesday" is visible.
- **The health table is itself in the catalog.** `krusgraph.health` is a Delta table in the customer's lakehouse. A
  small semantic model and report over it per domain is ordinary Fabric content: found in the catalog, shared with
  Fabric's permissions, counted in Govern. This is the durable publication, and it needs no new API.

Scopes: the workload app's item scopes cover Update Item; `ItemMetadata.ReadWrite.All` or `Item.ReadWrite.All` for
tags, `Tag.Read.All` to list them (to check against `docs/SCOPES.md` in the round).

### 9.3 Microsoft Purview

**The finding that decides this section.** On 12 November 2026 every Purview data governance page opened on Learn
carries this notice (quoted from P1, page updated 12 November 2026): "Microsoft Purview Unified Catalog and classic
Microsoft Purview data governance capabilities (formerly Azure Purview) are being retired. Microsoft is consolidating
its data governance capabilities in Microsoft Fabric. You can no longer create new accounts, and existing capabilities
will remain in maintenance mode through November 12, 2027." The announcement it links to (aka.ms/DG-Deprecation) could
not be opened from this session: the timeline's detail, the migration path and the fate of the APIs are **Unverified**.
Fabric's own page already says "The OneLake catalog remains the primary experience for governing Fabric data, and
Microsoft Purview adds protection, audit, risk, and compliance coverage" (P9): sensitivity labels, DLP, audit and
insider risk are not what is being retired.

What exists until then, for a customer who already has it:

| Purview part | What it is | API | Roles and licence | Could Krusgraph publish into it | Source |
|---|---|---|---|---|---|
| **Unified Catalog**: governance domains (called business domains in the API), data products, glossary terms, critical data elements | A data product is "a kit of data assets"; assets come from the Data Map | Public **preview** only (`2026-03-20-preview`): `POST {endpoint}/datagovernance/catalog/dataProducts`, terms, business domains. Scope `https://purview.azure.net/.default`; Learn documents a service principal only. Delegated user tokens: Unverified | Data Product Owner or Data Steward in the governance domain; Governance Domain Creator for domains. Pay as you go by governed assets per day and processing units | Technically a data product and terms could be written from the contract and the ontology's names. **Not proposed**: preview API on a retiring service, a service principal the customer must make, and assets must first be scanned | P2, P3, P4, P5 |
| **Data Quality** | Rules per column, scans, scores rolled up to asset, data product and governance domain; six dimensions; 200 rules per asset; runs under Purview's managed identity | Public preview (`2026-01-12-preview`): create rules, schedule scans, get scores | Data Quality Steward (with Governance Domain Reader and Data Product Owner); billed per processing unit | **No documented way to publish someone else's results.** Scores come only from rules Purview runs. A `dataQualityScore` field exists in a request body; whether a caller's value is kept: Unverified | P1, P6 |
| **Data Quality, the other direction** | Purview can write failed rows and its catalog model (rules, pass and fail counts) to a Fabric lakehouse | Error records; self-serve analytics | Purview's identity as Contributor on the workspace | Krusgraph could **read** those tables beside its own. Not proposed first | P7 |
| **Data Map** | Atlas-style entities with custom attributes, business metadata, classifications, lineage | GA (`2023-09-01`): `POST {endpoint}/datamap/api/atlas/v2/entity` | Data Curator on the collection | A Krusgraph attribute on a scanned lakehouse entity is possible in principle. For Fabric, scans give item-level metadata; lakehouse tables get sub-item metadata but no sub-item lineage. **Not proposed** | P8, P10 |
| **Glossary** | Terms in a governance domain | In the Unified Catalog preview API (Terms) | Data Steward | As the first row | P3 |

**Recommendation: build nothing for Purview's data governance now.** Reasons: it is in maintenance mode with an end
date; its data quality has no door for outside results; its catalog API is preview and wants a service principal,
where Krusgraph works as the signed-in user; and Microsoft says where governance is going, which is where 9.2 already
writes. What to do instead:

1. Keep the contract and the health table in open, plain shapes (ODCS YAML, a Delta table), so that whatever Fabric
   offers next for data products, glossary or quality can be fed from them.
2. Watch for the Fabric-native successor (none found in the Fabric pages opened: Unverified) and write into it when
   it is documented: this is the design principle of `FABRIC-IQ-AT-SCALE.md` section 6.
3. For a customer who has Purview Data Quality today and asks: Kruse Consulting can show them how to point a Purview
   scan at `krusgraph.health` or read Purview's exported results beside it (a service of part 7, not a feature).
4. Sensitivity labels stay as `docs/SCOPES.md` describes: read, never set.

### 9.4 Osmos

**What it is, from Microsoft's own pages.** Microsoft announced the acquisition of Osmos on 5 January 2026 (Official
Microsoft Blog, "Microsoft announces acquisition of Osmos to accelerate autonomous data engineering in Fabric"; the
blog host could not be opened from this session, so title, address and date are from search results only: O3). On
Learn it is now the **Fabric data engineering agent (Project Osmos), in preview** (O1, ms.date 23 October 2026): "an
autonomous data engineering capability for Microsoft Fabric. It runs persistent tasks that plan, execute, and
validate data engineering work against Fabric resources you're authorized to access." A person states a project
outcome from GitHub Copilot CLI, Codex or Claude Code; the task runs in Fabric with Spark, creates and tests
notebooks, writes Delta tables, and can "check row counts, nulls, schemas, and other success criteria". It is
installed as a skill (`project-osmos`, from `microsoft/skills-for-fabric`), needs a paid capacity (not trial),
workspace Contributor and the Copilot and Azure OpenAI tenant setting, and consumes model tokens and Spark compute;
its quickstart's examples validate "key uniqueness, referential integrity, and revenue totals" (O2). Not for
production use, no service level, while in preview (O1).

**Where they meet.** Project Osmos's validation covers, inside one task, the same three things Krusgraph counts:
keys, orphans, totals. An organisation that builds with it will ask why it needs Krusgraph. The honest answer:

| | Project Osmos (as documented) | Krusgraph |
|---|---|---|
| What it is | An AI agent that does data engineering work | Rules and counts; no AI model |
| Who states what "right" means | The person, in the project outcome's prose | The plan and contract: each key and link with its rule, kept as a file |
| When it checks | During the task, against that task's success criteria | Every pipeline run, the same checks, with history |
| Same input, same result | Not promised (it "creates and evaluates multiple implementation options") | Yes |
| Cost | Model tokens and Spark | The customer's SQL and Spark for the counts |
| Status | Preview | See `claims.py`; health over time not yet run in Fabric |

**Complement, do not compete.** Krusgraph should not try to be the builder; Microsoft now ships one. Three places
where it fits beside it, none built, none tested, none for the site:

1. **The contract as the success criteria.** From an active contract Krusgraph writes the text a person can give as
   a project outcome: "these keys are unique, these links have no orphans, these sums are equal before and after the
   join". The agent gets exact criteria instead of prose; Krusgraph's part stays deterministic.
2. **An independent check after the build.** Whoever built the tables (a person, Project Osmos, a migration),
   `check` counts them against the plan. The builder is not the only one who checks its own work, and the result is
   in the health table with the rest.
3. **A failing check handed over as a task.** For `duplicate_keys` or `orphan_spike` the Lifecycle proposal could
   include a drafted project outcome ("profile `orders`, find why 212 rows have no customer, propose a fix, report
   before and after"), which a person may start in their own client. Krusgraph starts nothing.

Part 6's rules hold here doubly: the two skills can sit in the same agent, and Krusgraph's text must say what the
other is for, not steer away from it. Whether the two plugins work together in one Claude Code session is
**Unverified** (not tried).

### Estimate and first build (part 9)

Three rounds, after the health table has run in Fabric. First (M): send n116's description and tag calls at step 5,
with the dated quality line, behind the dry run. Second (M): the trend per check and the per-domain health report
(a model and report over `krusgraph.health`). Third (S): the contract as a project-outcome text (9.4, item 1), which
is a text export and useful with any agent. Purview: no round.

---

## 10. All parts: rounds, and what to build first

| Part | Rounds | First slice | Depends on |
|---|---|---|---|
| 1 Portfolio | 2 | The table across workspaces: domain, owner, step, health, version | Part 2 first round; `Domain.Read.All` |
| 2 Operating model | 2 | The step as derived data on every product and answer | Nothing new |
| 3 Contract | 2 | Contract in the item; clauses joined to the health rows | Health table run in Fabric |
| 4 Shared entities | 2 | `shared: true`, the register, the cross-product orphan count | Part 3 |
| 5 Rules from decisions | 3 | Link by column name and rejected link, from one `rules.json` | S1 mechanism 4 |
| 6 Agent guidance | 2 | Short instructions, two fixed lines per tool, the `AGENTS.md` block, the wording test | S1's tool-list cut |
| 7 Services | 1 | The conditions as data and one line; before it, two one-page scopes by the founder | Parts 2 and 3 |
| 8 Capacity advice | 3 | C1, C2, C3, C7 from the health table and job history | 14 days of runs somewhere |
| 9 Quality, catalog, Purview, Osmos | 3 | Description and tags sent at step 5 with a dated line | Health table run in Fabric |
| **Total** | **20** | | |

**Before any of it:** run the health table, the alerts and the drift step once in Fabric on synthetic data and record
it (S1 section 7). Parts 1, 3, 8 and 9 all read that table; today it has only unit tests.

**Then, in this order** (each is one round and useful alone):

1. Part 2, the step as data: cheap, and it gives every later part its place in the UI.
2. Part 3, the contract kept: turns the health table into the sentence an owner and a consumer both need.
3. Part 1, the portfolio table: the first thing a second domain asks for.
4. Part 6, guidance: small, and it lowers the risk in S1 section 2 (the wrong tool reached).
5. Part 5, rules O1 and rejected links: the first "it remembered".
6. Part 9, description and tags sent.
7. Part 8, the four tips that need no new scope.

Parts 4 and 7 and the later slices follow when a customer with two domains exists. No part needs AI.

## 11. Not to be said on the site until built and tested

Data mesh support; a portfolio or a view per Fabric domain; data contracts that are checked; organisation rules or
"learns from use"; capacity advice, savings or sizing; publishing quality to the OneLake catalog; any Purview
integration; anything about Osmos or the Fabric data engineering agent; services by Kruse Consulting inside the
product. None exists. `tests/test_site.py` should get these words when the first of them ships, not before.

## 12. Open questions for the founder

1. **Purview:** agree to build nothing for Purview's data governance, given Microsoft's retirement notice of 12
   November 2026 (maintenance mode through 12 November 2027)? Please read aka.ms/DG-Deprecation, which this session
   could not open, and say if it changes the answer.
2. **Osmos:** agree with "complement": Krusgraph as the contract and the independent, repeated check beside an AI
   builder, and no attempt to build with AI? Worth trying Project Osmos once in the publisher's tenant (needs paid
   capacity and the Copilot tenant setting) before the Microsoft meeting.
3. **Order:** is the list in section 10 right, or does capacity advice (part 8) come earlier for the customers you
   are talking to?
4. **Rule book:** one per organisation, as proposed, or one per Fabric domain with an organisation level above?
5. **Names in decisions:** show the person's name by default, or the role ("a steward") by default?
6. **Services line in the product:** wanted at all? If yes, the two fixed packages need a one-page scope each, and
   Marketplace's rules for it need reading first.
7. **New delegated scopes** this design would ask for, each only in its round: `Domain.Read.All`,
   `Capacity.Read.All`, `Tag.Read.All` and `ItemMetadata.ReadWrite.All`. Any you do not want to ask customers for?
8. **W0, W2, W3:** their design texts were not on `main`; if they exist elsewhere, parts 2, 5 and 6 should be read
   against them in a short follow-up.

## Sources

Opened on learn.microsoft.com on 12 November 2026 unless stated. "Date" is the page's `ms.date`; REST reference pages
carry a placeholder `ms.date`, so their "updated" date is given. Two pages were opened by the author directly (P1,
O1); the rest by three research passes of the same session, whose reports this text follows.

Fabric domains, endorsement, tags, catalog, lineage:

- F1. "Domains", fabric/governance/domains (2025-05-01, updated 2026-09-29).
- F2. Fabric REST, Admin / Domains (index updated 2026-11-09): List, Create (updated 2026-11-09), Assign Domain
  Workspaces By Ids, Role Assignments Bulk Assign (updated 2026-09-15). The other eleven operations were read in the
  index only.
- F3. Fabric REST, Core / Domains: List Domains, Get Domain (updated 2026-09-15).
- F4. Fabric REST, Core / Workspaces: Assign To Domain, Unassign From Domain (updated 2026-09-15).
- F5. Fabric REST, Core / Workspaces: Get Workspace (updated 2026-10-28).
- E1. "Endorsement overview", fabric/governance/endorsement-overview, and "Endorse Fabric and Power BI items",
  fabric/fundamentals/endorsement-promote-certify (2024-07-11, updated 2026-02-17).
- E2. "Enable item certification", fabric/admin/endorsement-certification-enable (2024-07-11, updated 2026-09-29).
- E3. Fabric REST, Core / Items, operation list (updated 2026-09-21) and Get Item (updated 2026-11-11): no endorsement
  operation or field.
- T1. "Tags in Microsoft Fabric", fabric/governance/tags-overview (2026-03-11, updated 2026-03-18).
- T2. Fabric REST: Admin / Tags, Bulk Create Tags; Core / Tags, List Tags and Apply Tags (updated 2026-09-15).
- T3. Fabric REST, Core / Items, Update Item (updated 2026-11-11).
- C1. "OneLake catalog overview", fabric/governance/onelake-catalog-overview (2026-08-26, updated 2026-09-29).
- C2. "Explore", fabric/governance/onelake-catalog-explore (2026-10-08, updated 2026-10-20).
- C3. "OneLake Catalog REST API Overview", rest/api/fabric/articles/onelakecatalog/overview (2026-03-12, updated
  2026-05-13).
- C4. Fabric REST, Core / Catalog, Search (preview; updated 2026-11-11).
- C5. "Govern and manage your Fabric data with the OneLake catalog", fabric/governance/onelake-catalog-govern
  (2026-08-26).
- L1. Fabric REST, Core / Items, Get Downstream Relations (beta; updated 2026-11-11).
- L2. Fabric REST, Admin / Items, List Item Access Details (preview; updated 2026-11-11).
- L3. Power BI REST, Admin, WorkspaceInfo PostWorkspaceInfo (updated 2025-03-25) and GetScanResult (updated
  2026-05-18); "Metadata scanning overview", fabric/governance/metadata-scanning-overview (2025-06-10).

Capacity:

- K1. Fabric REST, Core / Capacities, List Capacities (updated 2026-11-10).
- K2. Fabric REST, Core / Job Scheduler, List Item Job Instances (updated 2026-09-15).
- K3. Fabric REST, Core / Job Scheduler, List Item Schedules (updated 2026-11-10).
- K4. "Query Delta tables with time travel", fabric/data-engineering/delta-lake-time-travel (2026-05-18).
- K5. "What is the Microsoft Fabric Capacity Metrics app?", fabric/enterprise/metrics-app (2026-08-28).
- K6. "Install the Microsoft Fabric Capacity Metrics app", fabric/enterprise/metrics-app-install (2026-08-14).
- K7. "Chargeback app", fabric/enterprise/chargeback-app (2026-08-04).
- K8. Fabric capacity overview events, fabric/real-time-hub/explore-fabric-capacity-overview-events (2026-08-18), and
  capacity operation events, …/explore-fabric-capacity-operation-events (2026-08-21).
- K9. fabric/real-time-hub/fabric-events-subscribe-permission (2026-10-05).
- K10. Azure REST, Microsoft.Fabric, Fabric Capacities: Get, Update, Suspend (2026-10-23; api-version 2023-11-01).
  The Resume page was not opened.
- K11. "Pause and resume your capacity", fabric/enterprise/pause-resume (2026-04-20).
- K12. "Scale your capacity", fabric/enterprise/scale-capacity (2026-09-23).
- K13. "Understand Microsoft Fabric licenses and capacity", fabric/enterprise/licenses (2026-06-15).
- K14. "Understand capacity throttling and smoothing", fabric/enterprise/throttling (2026-08-14); surge protection,
  fabric/enterprise/surge-protection (2026-09-23).
- K15. "Save costs with Microsoft Fabric Capacity reservations",
  azure/cost-management-billing/reservations/fabric-capacity (2026-09-30).
- K16. Capacity overage: fabric/enterprise/capacity-overage-overview (2026-08-26) and enable-capacity-overage
  (2026-09-11).
- K17. On-demand (autoscale) billing for Spark, fabric/data-engineering/autoscale-billing-for-spark-overview
  (2026-03-05).
- K18. "Direct Lake overview", fabric/fundamentals/direct-lake-overview (2026-09-02).
- K19. "How Direct Lake works", fabric/fundamentals/direct-lake-how-it-works (2025-09-22).
- K20. High concurrency: fabric/data-engineering/high-concurrency-overview (2026-03-05),
  configure-high-concurrency-session-notebooks (2025-07-03) and …-notebooks-in-pipelines (2024-09-18).
- K21. fabric/data-engineering/billing-capacity-management-for-spark (2026-03-05).
- K22. "Plan your capacity size", fabric/enterprise/plan-capacity (2026-06-15); "Evaluate and optimize your Microsoft
  Fabric capacity", fabric/enterprise/optimize-capacity (2024-07-30); Fabric SKU Estimator (preview),
  fabric/enterprise/fabric-sku-estimator (2025-05-05).

Purview and Osmos:

- P1. "Data Quality in Microsoft Purview Unified Catalog", purview/unified-catalog-data-quality (2026-10-13, updated
  2026-11-12): the retirement notice, quoted in 9.3. Opened by the author.
- P2. "Learn about Microsoft Purview Unified Catalog", purview/unified-catalog (2026-10-13).
- P3. "Unified Catalog API (Public Preview)", rest/api/purview/unified-catalog-api-overview (2026-04-30); operation
  groups and Data Products / Create (2026-10-23).
- P4. "Data Governance Roles and Permissions in Microsoft Purview", purview/data-governance-roles-permissions
  (2026-10-13); "API authentication for Microsoft Purview data planes", purview/data-gov-api-rest-data-plane
  (2026-10-13).
- P5. "Billing in Microsoft Purview Data Governance", purview/data-governance-billing (2026-10-13).
- P6. "Unified Catalog - Data Quality API (Public Preview)", rest/api/purview/unified-catalog-data-quality
  (2025-12-12); supported sources, purview/unified-catalog-data-quality-supported-sources-file-formats.
- P7. purview/unified-catalog-data-quality-error-records; purview/unified-catalog-self-serve-analytics.
- P8. Purview REST, Data Map, Entity / Create Or Update (2026-10-23; api-version 2023-09-01).
- P9. "Use Microsoft Purview with Microsoft Fabric", fabric/governance/microsoft-purview-fabric (2026-08-26).
- P10. "Connect to your Microsoft Fabric tenant in same tenant as Microsoft Purview",
  purview/register-scan-fabric-tenant (2026-10-13); live view, purview/data-gov-live-view.
- O1. "What is Fabric data engineering agent (Project Osmos)? Preview",
  fabric/data-engineering/data-engineering-agent-overview (2026-10-23, updated 2026-10-29). Opened by the author.
- O2. "Get started with Project Osmos", fabric/data-engineering/data-engineering-agent-get-started (2026-10-23).
- O3. Official Microsoft Blog, 5 January 2026, "Microsoft announces acquisition of Osmos to accelerate autonomous data
  engineering in Fabric" (blogs.microsoft.com/blog/2026/01/05/…). **Not opened** (the host is not reachable from this
  session); title, address and date from search results. Press reports of the same week (Redmond Magazine, Neowin)
  were seen as search snippets only and nothing in this text rests on them.

Not reachable from this session: aka.ms, blogs.microsoft.com, blog.fabric.microsoft.com,
community.fabric.microsoft.com. Nothing was run against Fabric, Purview or any customer tenant in this round.
