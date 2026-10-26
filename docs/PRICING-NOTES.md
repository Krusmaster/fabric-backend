# Pricing notes (internal, not on the site)

Status: a document only. Nothing in the code measures, meters, bills or knows about accounts, and this note does
not change that. It is the basis for a decision the maintainer has not taken.

## What a free tier and a paid tier could contain

The split that follows the product's own shape: reading is free, creating and operating is paid. Reading is what
makes someone trust the tool; creating is where it saves a day of work; operating is what a company pays for
monthly.

| | Free | Paid (per user or per workspace) |
| --- | --- | --- |
| Read-only tools: `list_workspaces`, `list_sources`, `list_tables`, `plan_backend`, `sample_rows`, `validate_plan`, `join_path`, `analyze_schema`, `suggest_relationships`, `describe_backend`, `query_graphql` | yes, one workspace at a time | yes |
| Hand-over drafts: `semantic_model_draft`, `data_dictionary`, `dbt_schema`, `rayfin_connector`, `ontology_draft`, `app_starter`, `app_readiness` | yes, with a visible footer naming the product in the generated files | yes, without the footer |
| Creating tools: `create_backend`, `create_semantic_model`, `create_views`, `create_data_agent` | `create_backend` for one API per workspace, the others dry run only | all, unlimited |
| `plan_drift`, `lineage` | `plan_drift` yes; `lineage` no | yes, and `lineage` across all items of the workspace |
| Several workspaces in one session, a team's shared connections | no | yes |
| Operations: a daily drift check of the APIs a team created, mail when an API would change, the `impact` of a planned schema change before it is deployed | no | yes (this is the feature that justifies a monthly price; it does not exist yet) |
| The local server and the command line (open source, MIT) | always free, no sign-in | n/a |
| Support | the support page | a named contact, response within a working day |

Counting queries (`validate_plan`, `suggest_relationships`) cost the customer's own Fabric capacity, not ours; that
stays true in both tiers and should be said on the pricing page.

Prices are not proposed here. The reference points to compare against are the per-user prices of the tools a
consultant would otherwise use for the same hand-over work (modelling and documentation tools), and what a day of
that consultant costs; both are known to the maintainer and not written down in this repository.

## What has to be measured per user for this to work

Only what the tiers need, never the content of a call:

- **Who**: the user's object id and tenant id from the validated token (`oid`, `tid`), and the workspace id a call
  names. Nothing about the data: no table names, no query text, no results.
- **What**: the tool name, the outcome kind (`ok`, or the error `kind` the tool answered with), the duration, and for
  creating tools whether it was a dry run.
- **When**: a timestamp. From these three a monthly count per user and per workspace of calls per tool follows,
  which is what a tier limit ("one API per workspace", "lineage is paid") and a usage page need.
- **Nothing else**: not the plan, not the counts a validation found, not the generated TMDL, not the GraphQL
  query. The privacy policy currently says the server stores nothing; a tier model changes that sentence to "stores
  the call records above for N months" and must say so before the first record is written.

Retention: long enough to bill a month and answer a dispute (ninety days is enough), then deleted; aggregated
counts may be kept longer without the user id.

## What it requires technically

1. **A store.** Today there is none by design (in-memory only). The smallest honest option is one table in a Fabric
   SQL database or Azure SQL in the publisher's own tenant, written by the server after each call (fire and forget,
   with a bounded queue so a slow store never slows a tool). The server's `KRUSGRAPH_*` flags pattern applies:
   `KRUSGRAPH_METERING=0` by default.
2. **Entitlement.** A tier per tenant (the simplest unit: the admin who consented is the one who pays) or per user,
   read at call time from the same store and cached in memory for a few minutes. A free tenant hitting a paid tool
   gets the existing error format: `kind: plan_required` with a hint naming the page to upgrade on. No tool changes
   its behaviour otherwise, so the open-source server keeps working for anyone who self-hosts without the flag.
3. **Billing.** Outside the server: an invoice from the company's accounting, or a hosted checkout page that writes
   the tenant's tier into the store. No card data ever touches this code.
4. **A usage page**, per signed-in user, showing their own counts (the same records), and an export for the admin
   of a tenant. This is also what the directory's connector dashboard shows per tool for us; the two should agree.
5. **Terms.** A terms-of-service page and the privacy policy update above; the plugin manifest has a
   `termsOfServiceUrl` field waiting for it.
6. **Tests.** The metering writer with the store mocked, the entitlement check per tool, and a test that proves no
   content field (schema, query, result) ever reaches the store, in the style of the existing "no token reaches the
   logs" tests.

## What not to do

- Do not meter by rows or by data volume; the customer already pays Fabric for that, and measuring it means
  looking at the data.
- Do not make the read-only tools paid; the free tier is the demo and the trust.
- Do not add accounts of our own; the Entra sign-in is the account.
- Do not build any of this before the directory listing is decided and a first paying conversation has happened.
