# Decision rules: your team's decisions become rules

Round L1, 16 November 2026. Layer 3 of the integration strategy: Krusgraph gets better from use. When a team accepts
or rejects a proposed key or link, that decision becomes a deterministic, explainable rule for that tenant, so the next
plan proposes the right thing directly and says why. **No AI and no machine learning**: a rule is a stored decision,
matched by names, applied in a fixed order; nothing is trained, scored or estimated. The design this builds on is
[DOMAINS-DESIGN.md](DOMAINS-DESIGN.md), part 5 ("Smarter from use, without AI"), shapes 1 to 4 of its closed list,
and the case record of [EVOLUTION.md](EVOLUTION.md) is left as it is (no case record is written by this round).

Verified in unit tests only (`tests/test_l1_decision_rules.py`, the synthetic shop seed in SQLite, so the counts are
real rows). Not run against Fabric, not deployed, not on the hosted service.

## 1. What a decision is

`record_decision` (local MCP server) keeps one row per decision:

| Field | What it holds |
| --- | --- |
| tenant | a SHA-256 digest of the tenant id, never the id itself. Every read and write names it |
| scope | where it was decided: platform / database / schema, lower case (`fabric-odbc/shop_lh/shop`) |
| kind, item | `key` or `link`, with the id plan_backend and review_plan use (`key:orders`, `rel:orders.ship_to_id>addresses`) |
| names | the table and columns, or source, source columns, target, target columns; for a link also a digest of the source table's column names (to recognise it renamed, section 3) |
| fingerprint | a digest of the column names of the tables involved, at the time: the plan says when they changed since |
| decision | `accepted` or `rejected` |
| role | `steward`, `owner`, `engineer`, `analyst` or `reviewer`. A role, never a person's name or id: anything else is refused |
| reason | short free text, at most 300 characters; not for personal data |
| at | when, UTC |
| evidence | what the rows said at that moment (one counting query, the same SQL as validate_plan): rows, NULLs and distinct values for a key; rows with a value and orphans for a link. Counts only, never a value |
| undone_at, undone_role | set when the decision is undone; the row stays as history |

The latest decision on an item is the rule; an undone one is not. For a link, a later accepted link from the same
source column to another target replaces the earlier one.

## 2. What a rule does to the next plan

Every planning tool of the local server (plan_backend, validate_plan, review_plan, the drafts) plans through the same
hook (`mcp_server._plan_on` → `decisions.plan`), so the rules reach all of them.

| Decision | Effect | Shown as |
| --- | --- | --- |
| Accepted link | proposed directly, before the name rules, rule **`decided`** | the relationship's note: "decided by your team on 16 November 2026 (steward): accepted; ship_to_id holds address ids"; evidence state "given, not counted" |
| Accepted key | the table's key, before the name rules, rule **`decided`** | listed under `decisions.applied` with the same words |
| Rejected link | not proposed (also taken out of `plan.proposed`) | listed under `decisions.suppressed` with the decision and its reason |
| Rejected key | the key is taken out, the table becomes key-less, and the links inferred into that key go with it | `decisions.suppressed`, `how: "key rejected"` for each link |

Rules of the rules:

1. **Rows outrank rules.** An accepted key or link is "given, not counted" until validate_plan counts it. When the
   rows contradict it, validate_plan's answer lists it under `decisions.contradicted_by_rows` with what the rows say now
   and how to undo it ("Your team accepted this link, but the rows now say: 25 of 60 rows (41.7%) point at nothing").
   It is never trusted silently and never removed silently: a person decides again.
2. **The call wins.** `keys=` and `confirmed=` in a call win over a decision on the same table or source column; the
   decision is listed under `not_applied` with why. A rejection of something the source declares (K0, R0) or the call
   confirms is not applied either: it is kept and listed under `conflicts`.
3. **Gone is said, not guessed.** A decision whose table or column is not in the schema now is listed under
   `not_applied` with the missing name. A decision whose tables changed since (another column set) still applies and
   says `changed_since`.
4. **Deterministic.** The same schema and decisions give the same plan, in the same order (tested).
5. **Undo.** `record_decision(undo=<id>)` undoes one decision; the next plan proposes by the other rules again.
   `list_decisions` shows every decision of the tenant with its id, role, date, reason, evidence and whether it was
   undone.

The plan's summary gets one line ("2 decision(s) of your team applied as rules (rule "decided"): ..."), and
plan_backend and validate_plan carry `decisions` with `applied`, `suppressed`, `conflicts`, `not_applied` and the same
in short lines.

## 3. Name patterns: only one, and shown

A rejected link follows its source table renamed: when the decided table is not in the schema now and **exactly one**
table has exactly the columns it had when the decision was made, that table is read as the renamed one and the same
link from it is not proposed, with `how: "pattern"` and the sentence that says why ("audit_log is not in the schema now
and audit_events has exactly the columns audit_log had when the decision was made: read as audit_log renamed").
With another column set, or two such tables, nothing generalises and the decision is listed as not applied.

Nothing else generalises. In particular a rejected `audit_log.customer_id → customers` does **not** suppress
`orders.customer_id → customers`: same column name, another table, another meaning. The broader shapes of
DOMAINS-DESIGN part 5 (a link by column name across tables, keys by table pattern, organisation rules promoted by a
steward) are not built.

## 4. Where decisions are kept

| Where | How |
| --- | --- |
| Local MCP server | one SQLite file on the user's machine: `KRUSGRAPH_DECISIONS` (default `~/.krusgraph/decisions.sqlite`, created only when the first decision is recorded; `off` turns decisions off). `KRUSGRAPH_TENANT` names the tenant (default `local`); one file can hold several tenants and each sees only its own |
| Tests | `decisions.Store(":memory:")` or a temporary file |
| Hosted service | **not stored.** The hosted service keeps no customer content (the trial row holds a tenant id and salted hashes only, [BILLING-MODEL.md](BILLING-MODEL.md)), and decision rows hold table and column names. The way to keep them for a hosted or workload user is in the customer's own tenant (DOMAINS-DESIGN part 5: a rule book item, or the review file passed back as `previous`); not built |

Per-tenant isolation: every query filters on the tenant digest; another tenant's decision id is answered exactly as an
id that does not exist (it cannot be read, applied or undone); scopes keep two databases or schemas of one tenant apart.

## 5. Cross-tenant learning: not built

Learning across customers (a decision at one customer helping another) is **not built**, and nothing in this round
sends a decision anywhere. If it is ever built, it would be:

- **opt-in** per tenant, off by default, switched on by the customer's administrator and switched off again at any time;
- **anonymised** before it leaves the tenant: no tenant id, no person, no reason text, no row values, no counts that
  identify a customer, and no table or column names except those of a published standard system (the shared form of
  the case record, [EVOLUTION.md](EVOLUTION.md), "Sharing: opt-in, and what the shared form is");
- **under a DPA** that names it as a purpose, with the processor deriving nothing for its own purposes otherwise
  ([DPA-DRAFT.md](DPA-DRAFT.md), and the wording EVOLUTION.md drafts for it);
- still rules, counts and provenance: a shared pattern would be shown with how many tenants it rests on, and the
  receiving tenant's rows would still count it.

What travels between customers today is only what Kruse Consulting curates and publishes itself: the packs
([PACKS.md](PACKS.md)), which name public sources.

## 6. Not built in this round

- The hosted server's tools (`fabric_backend/server.py`) and the Fabric workload do not read or record decisions.
- review_plan's file does not yet mark a `decided` item as accepted on its own (it shows the rule `decided` with
  review status "proposed"); silver de-duplication treats a `decided` key as not checked (it removes rows only on K0,
  K1 and R5 keys).
- Promoting a decision to an organisation rule, switching a rule off with a diff, the "questioned" mark after repeated
  rejections, keys by table pattern, links by column name across tables.
- The case-record writer of EVOLUTION.md.
