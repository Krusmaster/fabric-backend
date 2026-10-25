# Krusgraph pilot package

A bounded pilot: one customer, one Fabric workspace, one agreed outcome. This document is what a partner or a
customer gets before a pilot starts. It states what is in, what is out, what the customer must have, and what
they receive. Prices appear only as **proposals to test**, clearly marked; nothing here is a price list.

## Goal

Within the pilot the customer sees their own tables as an explainable graph, reviews the inferred keys and
relationships with the rule behind each one, and ends with an API for GraphQL item in their workspace that Claude
(or Lovable, Cursor, Claude Code) can query. The customer leaves with a plan file they can re-run, and a short
write-up of what the engine got right, what it left unlinked, and what they had to confirm by hand.

## Scope

| In | Out |
| --- | --- |
| One Fabric workspace, one source (lakehouse, warehouse, SQL database or mirrored database), one schema | Multiple workspaces, cross-source joins, SAP schemas (see [sap-ontology](https://github.com/Krusmaster/sap-ontology)) |
| Up to ~60 tables | Row-level security design, data modelling changes, performance tuning of the SQL endpoint |
| Keys and relationships inferred, reviewed together, ambiguous and unlinked columns resolved with `keys=` / `confirmed=` | Writing application code (Lovable app, Rayfin app); generating Rayfin entities is in, building the app is not |
| One API for GraphQL item created or updated in place | Anything that deletes or renames items |
| Read-only queries from Claude to verify the result | Mutations, write-back, ETL |
| The two manual portal steps (introspection, item permissions) done together with the customer | Tenant administration beyond the one-time admin consent |

## Deliverables

1. **Plan**: the engine's output for the agreed schema, as JSON and as a Mermaid ER diagram, with every key and
   relationship labelled K0–K3 / R0–R3 and the list of ambiguous and unlinked columns.
2. **Review record**: which suggestions were accepted, skipped or overruled, and why. Accepted is not verified;
   the record says what was checked against data and what was not.
3. **The API for GraphQL item** in the customer's workspace, created from the reviewed plan, with introspection on
   and permissions granted as agreed.
4. **Connection card**: endpoint, the identity used, and the three example queries that were run during the pilot.
5. **Write-up** (2–4 pages): what worked, what the engine missed, what a wider rollout would need. Names and
   shapes of tables only; no row data, no customer identifiers in anything that leaves the customer's tenant.

## What the customer needs to have

- A Fabric capacity (trial is fine) and a workspace the pilot users can open.
- A source with tables that have *names*: inference works on names, so `VBELN`-style columns need a dictionary
  (out of scope here).
- An Entra administrator willing to grant the one-time admin consent for the Krusgraph app, or to run the
  open-source server in the customer's own tenant instead (both work; the second keeps everything in-house).
- One person who knows the data and can say which of two candidate tables a column points at.
- Two 90-minute working sessions.

## How a pilot runs

1. **Connect** (session 1, first half): admin consent, add the connector in Claude, `list_sources`, pick the source.
2. **Explore**: `plan_backend` on the schema. Read the summary together: how many keys were found, which tables
   are keyless, which columns are ambiguous or unlinked.
3. **Review**: go through every R2/R3 relationship and every ambiguous or unlinked column. Decide `keys=` for
   composite keys and `confirmed=[...]` for the links the rules could not make. Record the decisions.
4. **Build** (session 2): `create_backend` with the agreed overrides, the two portal steps, three queries from
   Claude that answer real questions. Hand over the plan file, the record and the write-up a week later.

## Not included

Hosting of anything beyond the API for GraphQL item that Fabric itself hosts; support after the pilot beyond
answering questions by email for 30 days; any statement that the inferred relationships are correct for purposes
the customer did not review. The engine infers from names and says so on every link.

## Price levels — proposals to test, not a price list

These are *hypotheses* to try with the first pilots, to be marked as such in any offer. They may be wrong in
either direction and will be revised after three pilots.

| Proposal | Content | Why test it |
| --- | --- | --- |
| **Guided pilot** (proposal: 15 000 SEK ex. VAT) | the two sessions, the deliverables above, up to ~60 tables | tests whether a fixed, bounded price lowers the threshold for a first conversation |
| **Self-run pilot** (proposal: 0 SEK) | the customer runs the open-source engine themselves with the docs and the demo; one hour of questions by email | tests how far the docs carry on their own |
| **Partner-led pilot** (proposal: the partner's own rate; Krusgraph charges nothing) | a consultancy runs the pilot with their customer using this package | tests whether partners pick it up without a programme |

What is *not* proposed: per-seat licences, per-query fees or a hosted tier with SLAs. There is nothing behind
such promises today, and the website says so (contributions open soon; no payment connected).

## Risks to name up front

- A lakehouse has no declared keys, so a schema with generic column names (`id`, `code`, `ref`) yields few links;
  the plan will say so and the pilot then becomes mostly `confirmed=` work.
- Introspection and item permissions are portal clicks until Fabric exposes an API; the customer's admin must be
  in the room or on call.
- Claude's connector sign-in needs the Entra app to be consented in the customer's tenant; some organisations take
  days to approve that. The in-house option avoids it.
- Things do fail in session 1: a workspace without capacity, an account without access, a source whose SQL
  endpoint is still provisioning. Each tool answers such a call with `error`, `kind` and `hint` (what happened,
  a stable code, what to do next), so the fix is usually a portal click rather than a debugging session.
