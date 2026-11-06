# Krusgraph and Myriade: how relationships are found and what is shown as evidence

Internal note, round n113, 6 November 2026. Not linked from the site. Goal: let the maintainer compare honestly. Sources
are public only: Myriade's website (www.myriade.ai, including `/llms.txt` and `/docs`), its public GitHub repository
`myriade-ai/myriade`, and the launch post on dev.to. No account was created, nothing was signed up for, no demo was
booked and nobody was contacted.

Two kinds of statement are kept apart below:

- **Claimed**: what Myriade's own pages say, with the link and a verbatim quote of under 15 words. Not verified here.
- **Observed**: what was run or read in this round, with the command, file or commit.

## 1. What Myriade says it does (claimed)

All pages read on 6 November 2026.

### How relationships are found

| Claim | Source | Quote |
| --- | --- | --- |
| An agent pass maps relationships as part of discovery | [llms.txt](https://www.myriade.ai/llms.txt) | "AI agents reverse-engineer your schema, sample your data, detect anomalies, map table relationships" |
| The inputs of that pass | [llms.txt](https://www.myriade.ai/llms.txt) | "They use statistical analysis, existing metadata (dbt, prior catalogs), data samples, and min/max distributions." |
| Relationships come from JOINs in query history | [Data catalog automation](https://www.myriade.ai/solutions/data-catalog-automation) | "AI discovers table relationships from actual JOIN patterns in queries" |
| The same, in the step list | [Data catalog automation](https://www.myriade.ai/solutions/data-catalog-automation) | "Maps relationships automatically from JOIN patterns in queries" |
| Joins are inferred and kept in a context layer | [vs Microsoft Fabric](https://www.myriade.ai/vs/microsoft-fabric) | "Joins are inferred automatically and mapped within the context layer." |
| Agents query the data and follow relationships | [Home page](https://www.myriade.ai/) | "they query the data and follow the relationships between tables" |
| Relationships feed descriptions of tables | [Complete catalog](https://www.myriade.ai/complete-catalog) | "cross-references table relationships to infer the true business logic." |
| The product reads query history | [GitHub README](https://github.com/myriade-ai/myriade) | "understands warehouse schemas, relationships, metadata, and query history" |

### What is shown as evidence

| Claim | Source | Quote |
| --- | --- | --- |
| A value-overlap figure on a join, in the page's illustration | [Complete catalog](https://www.myriade.ai/complete-catalog) | "-- High overlap detected" … "-- 98.5% match" |
| Unclear points go to people rather than being guessed | [vs Microsoft Fabric](https://www.myriade.ai/vs/microsoft-fabric) | "genuine ambiguities that Myriade surfaces for your team to confirm" |
| People review what the agents wrote | [llms.txt](https://www.myriade.ai/llms.txt) | "Your data team reviews, corrects, approves." |
| Answers name their tables | [llms.txt](https://www.myriade.ai/llms.txt) | "Every answer is sourced and verified against cited tables." |
| Quality tests can come from a relationship (example: `ship_date > order_date`) | [Quality control](https://www.myriade.ai/quality-control) | "Inferred from Relationship" |
| Integrity is among the quality dimensions | [Quality control](https://www.myriade.ai/quality-control) | "Checks for Completeness, Timeliness, Validity, Integrity, Accuracy, and Consistency" |
| Duplicates are among the issues it looks for | [vs Microsoft Fabric](https://www.myriade.ai/vs/microsoft-fabric) | "Data quality issues (duplicates, inconsistencies)" |

The page illustration is a mock-up (a `JOIN fact_tickets t ON t.sku = stg.col_a` line beside "98.5% match"); it shows
the kind of evidence intended, not a run.

### Data access, deployment and licence

| Claim | Source | Quote |
| --- | --- | --- |
| The model sees structure and samples, not full tables | [Security](https://www.myriade.ai/security) | "the AI only sees your table structure and a few samples" |
| Sample size through its MCP server | [Docs: MCP](https://www.myriade.ai/docs/mcp) | "samples are capped at 20 rows" |
| Fabric is a listed source | [llms.txt](https://www.myriade.ai/llms.txt) | "Snowflake, BigQuery, Databricks, Redshift, Fabric, Oracle" |
| dbt stays the source of truth | [llms.txt](https://www.myriade.ai/llms.txt) | "Your dbt project remains the source of truth." |
| Using the MCP server needs an account | [Docs: Claude × PostgreSQL](https://www.myriade.ai/docs/mcp/claude/postgresql) | "A Myriade account on app.myriade.ai (or on your self-hosted instance)." |
| Self-hosting is on request | [GitHub README](https://github.com/myriade-ai/myriade) | "Myriade is self-hosted on request" |
| The images are private | [GitHub README](https://github.com/myriade-ai/myriade) | "Images are private" |
| The earlier open-source release needed an LLM key (15 July 2025) | [dev.to launch post](https://dev.to/benderv/myriade-the-analytic-agent-for-your-database-1lcg) | "you will need your own Anthropic apikey." |
| Current licence restriction | [LICENSE](https://github.com/myriade-ai/myriade/blob/main/LICENSE) | "Use the Software to create a competing product or service" |

Not found in any page read: a statement about foreign keys declared in the database, about primary-key or uniqueness
checks, about counting rows that point at nothing (orphans in the Krusgraph sense; the home page's "orphan columns"
are about unused columns), or about a sum repeated by a join (the total that doubles). Absence on these pages is not
evidence that the product lacks it.

`docs.myriade.ai` answered 502 through this session's proxy; the docs read here are under `www.myriade.ai/docs`.

## 2. What was run (observed)

### Myriade: nothing was run

- The public repository `myriade-ai/myriade` at `37b569c` (2 November 2026) holds only install scripts, Kubernetes
  manifests, a README and a licence. The install line takes a key that Myriade sends per customer, and the images are
  private. The MCP server needs an account. Neither can be used without an account.
- The source was public until commit `88c2a31` (15 December 2025, "chore: remove source code, keep Docker
  installation docs"). The open-source version announced on 15 July 2025 starts only with an Anthropic API key, i.e. a
  credential this round may not enter. Since 1 December 2025 (`5772272`) the licence is a proprietary agreement whose
  §3(c) forbids using the software to build a competing product. So nothing of Myriade was installed or run, and no
  Myriade output on the shop data exists.
- Read, not copied, at the last public source commit `40d8c553` (parent of `88c2a31`; licence at that commit: the
  proprietary agreement): no module for relationship inference was found by searching for foreign key, relationship,
  primary key and reference; the analyst agent's instructions (`service/chat/chat_template.txt`) tell it, before
  documenting a table, to "Cross-reference with related tables". That suggests relationships were handled by the model
  working through tools at that time; it says nothing certain about the product as it is now.

### Krusgraph: the engine on the synthetic shop data

Commit `ec9a45e`, `fabric_backend.infer.plan` on `fabric_backend.seed.schema("shop")` (seven tables), the checks of
`validate_plan` (`fabric_backend.evidence.validate`) on `seed.rows()` in an in-memory SQLite database (`demo._demo_db`),
`suggest_relationships` (`graphs.suggest`, via `demo.demo_suggestions`) and the total that doubles
(`amounts.demo()` on `seed.AMOUNT_DEMO`). Run without any keys given; the run with `order_items` keys given
(`demo.DEMO_KEYS`) gives the same result except that the `order_items` key rule is K1 instead of K5.

## 3. Side by side

"—" in the Myriade column means: not run (see above), so there is no output to put there.

### Keys

| Table | Krusgraph key (rule) | Checked on the rows | Myriade |
| --- | --- | --- | --- |
| customers | customer_id (K2) | unique in all 10 rows, 0 NULLs | — |
| categories | id (K2) | unique in all 3 rows, 0 NULLs | — |
| products | product_id (K2) | unique in all 8 rows, 0 NULLs | — |
| addresses | address_id (K2) | unique in all 17 rows, 0 NULLs | — |
| orders | order_id (K2) | unique in all 60 rows, 0 NULLs | — |
| order_items | order_id + line_no (K5: header reference plus a line-number column) | unique in all 134 rows, 0 NULLs | — |
| audit_log | none: reported as keyless | — | — |

### Relationships and orphans

| Relationship | Krusgraph rule | Rows with a value | Orphans | Myriade |
| --- | --- | --- | --- | --- |
| products.category_id → categories.id | R1 | 8 | 0 | — |
| addresses.customer_id → customers.customer_id | R1 | 17 | 0 | — |
| orders.customer_id → customers.customer_id | R1 | 60 | 0 | — |
| order_items.order_id → orders.order_id | R1 | 134 | 0 | — |
| order_items.product_id → products.product_id | R1 | 134 | 0 | — |
| audit_log.customer_id → customers.customer_id | R1 | 40 | 0 | — |

Summary line from `validate_plan`: "6 of 6 keys unique, 6 of 6 relationships hold without orphans". The synthetic shop
has no orphans by construction, so this run does not exercise the orphan count with a non-zero result.

`orders.ship_to_id` matches no naming rule and stays out of the plan. `suggest_relationships` proposes, without adding
it: orders.ship_to_id → addresses (score 3.94; reasons: same type as addresses.address_id, an address role name,
closes the triangle orders → customers ← addresses), checked on the rows: 60 of 60 values exist in addresses
(15 distinct); runner-up customers with 35 of 60.

### The total that doubles

`seed.AMOUNT_DEMO`: one order with `order_amount` 1 000 and two lines of 600 and 400.

| | Krusgraph | Myriade |
| --- | --- | --- |
| SUM(orders.order_amount) over the join with order_lines | 2 000 | — |
| Summed per order (`WHERE EXISTS`) | 1 000 | — |
| SUM(line_amount) | 1 000 | — |
| Finding | header amount on `orders`, 2 lines per order on average and at most (rule R1 on order_lines.order_id) | no public statement found |

## 4. Differences

Based on what Myriade claims and what Krusgraph was observed to do; Myriade's side is not verified.

1. **Where a relationship comes from.** Krusgraph: declared keys first, then fixed naming rules (K0–K5, R0–R5), each
   relationship carrying its rule; columns no rule links are reported or suggested, not added. Myriade (claimed): LLM
   agents that combine samples, statistics, existing metadata (dbt, catalogs) and JOIN patterns from query history.
   Query history is an input Krusgraph does not use; Krusgraph's result is reproducible from names alone and does not
   depend on a model.
2. **What stands as evidence.** Krusgraph: the rule name, and on request counts from the rows (rows with a value,
   orphans, duplicates, NULLs) with the SQL that produced them. Myriade (claimed): a value-overlap percentage in its
   illustration, cited tables in answers, and human review of what the agent proposes; agents ask the team when
   unsure.
3. **What the output is for.** Krusgraph turns the plan into Fabric items and drafts (GraphQL API, semantic model,
   ontology, views, notebooks, dbt tests) and flags the total that doubles. Myriade (claimed) uses relationships inside
   a context layer for a catalog, quality checks, natural-language analytics with citations and dbt changes; it covers
   many warehouses, including Fabric.

What Myriade says it does that Krusgraph does not: learn from query history; write and keep catalog descriptions and
sync them back to a catalog; answer questions as an analyst agent; continuous monitoring with alerts; FinOps reports;
dbt pull requests; ask the team questions as part of its workflow.

What Krusgraph does that no Myriade page read here mentions: a named, deterministic rule per key and relationship;
orphan, uniqueness and NULL counts per relationship and key; the total that doubles with the wrong and the right sum;
creating Fabric items (API for GraphQL, semantic model, ontology, views, data agent) from the plan; an open-source
(MIT) engine that runs offline without an account.

## 5. Open questions

- Does Myriade read foreign keys declared in the database, and do they take precedence over inferred ones?
- What does the "98.5% match" on the catalog page measure (share of source values found in the target, or the other
  way round), on how many rows, and is the figure shown per relationship in the product?
- Are orphan rows counted and shown, and can a relationship be rejected because of them?
- Does it detect a sum repeated by a join (header amount over line rows), in answers or in quality checks?
- How are composite keys and tables without a key handled?
- Is a relationship from query history kept apart from one inferred from data, and is the source shown?
- How does "opendata.myriade.ai/paris" (linked from llms.txt as "Try on open data") show relationships? Not opened in
  this round: the host is outside this session's network list.
- With access granted by Myriade (an evaluation instance), the shop data from `fabric_backend/seed.py` could be loaded
  into PostgreSQL and both sides of section 3 filled in. That needs an account and is the maintainer's decision.
