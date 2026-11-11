# Krusgraph pilot onboarding

For a pilot customer's Fabric admin, Entra admin and first users, and for Krusgraph. Round n199, 10 November 2026
(replaces the n176 version of this file). The same administrator steps are on the site at `https://krusgraph.com/pilot/fabric`.
What Krusgraph reads, stores and signs in with, and what is not in place yet, is in `docs/TRUST-PACK.md`.

Krusgraph is published by Kruse Consulting AB. It is not affiliated with Microsoft, and the workload is not listed in
Fabric's Workload Hub. Nothing in this guide is a claim about speed, certification or endorsement.

## Who does what

| Role | Who | Does |
| --- | --- | --- |
| Fabric admin | The customer | Tenant settings, the capacity, the test workspace |
| Entra admin | The customer (Global Administrator or Privileged Role Administrator) | Admin consent for the Krusgraph app; revoking it at the end |
| User | The customer (one or two people) | Signs in, runs the first session, gives feedback |
| Krusgraph | Kruse Consulting AB | Adds the tenant to its lists, runs the first session with the user, answers questions, removes the tenant at the end |

## Choose the path

| Path | What the customer uses | Status today |
| --- | --- | --- |
| **A** | The MCP server (Krusgraph for Claude, or another MCP client) and the website, against the customer's own Fabric | **Available now** |
| **B** | The Krusgraph Model item inside Fabric (`Krusgraph.Modeler`), published to the customer's tenant | **After Microsoft registers the name** `Krusgraph.Modeler` (`docs/WORKLOAD-PUBLISH.md`, step 1) |
| **C** | The customer's admin uploads an `Org.*` package in their own tenant | **Unverified. Do not ask a customer to do this** until confirmed with Microsoft |

## Prerequisites (all paths)

| What | Who | Note |
| --- | --- | --- |
| A Fabric capacity (F SKU or trial) | Fabric admin | Power BI Pro alone is not enough |
| A test workspace on that capacity | Fabric admin | Test or sample data only for the pilot |
| A lakehouse in that workspace, with tables in a schema | Fabric admin or user | The SQL analytics endpoint is used for column names and counts |
| Contributor (or higher) on the workspace for the user | Fabric admin | Needed to create items; reading and dry runs need less |
| The right to grant admin consent | Entra admin | Global Administrator or Privileged Role Administrator |
| HTTPS (port 443) to `krusgraph.com` and `workload.krusgraph.com` | Customer's network team, if outbound traffic is filtered | Both hosted in Azure, Sweden Central |
| Private Link off for the tenant (Path B) | Fabric admin | The workload is blocked where Private Link is on |

If there is no suitable data, Krusgraph's synthetic shop schema can be loaded (`fabric_backend/seed.py`).

## Path A (today): the MCP server and the website

1. **Krusgraph** sends the customer `docs/TRUST-PACK.md` and the page `https://krusgraph.com/it`. The /it page shows
   the Krusgraph app's client id, its delegated permissions, the live log retention and how to revoke.
2. **Entra admin** grants admin consent once for the organisation. The URL pattern:

   ```
   https://login.microsoftonline.com/<your tenant id>/adminconsent?client_id=<Krusgraph app client id from /it>
   ```

   The consent screen lists the delegated permissions. They are, with why, in `docs/TRUST-PACK.md` section 5
   ("Krusgraph for Claude"): `User.Read`; Fabric `Workspace.Read.All`, `Item.Read.All`, `GraphQLApi.ReadWrite.All`,
   `GraphQLApi.Execute.All`, `Notebook.ReadWrite.All`, `DataPipeline.ReadWrite.All`, `Item.ReadWrite.All`; Azure SQL
   Database `user_impersonation`. All are delegated: every call runs as the signed-in person.
3. **User** adds the connector `https://krusgraph.com/mcp` in Claude (custom connector), or signs in from another MCP
   client at `https://krusgraph.com/mcp/connect` where that is switched on. Steps: `https://krusgraph.com/start`.
4. **User** may also use `https://krusgraph.com/check`: it runs in the browser, and files dropped there are not uploaded
   (`fabric_backend/browser_check.py`).
5. **Data note for the customer.** On this path, the tools' answers (names, counts, and any sample rows or query results
   the user asks for) go to the user's MCP client and its AI provider (Anthropic for Claude). That is the customer's
   own vendor, under the customer's own agreement. If that is not acceptable, use Path B, or self-host
   (`deploy/KRUSGRAPH-START.md`).
6. **To revoke:** Entra admin centre → **Enterprise applications** → the Krusgraph app → **Permissions** (remove), or
   **Properties → Delete**. Tokens already issued expire within 60 to 90 minutes.

## Path B (after Microsoft registers Krusgraph.Modeler): the item in Fabric

The steps below follow `docs/WORKLOAD-PUBLISH.md` (steps 4 and 5, A2 and A4). Until step 1 of that runbook is solved,
this path cannot start.

1. **User or admin** sends the customer's tenant id to hello@krusgraph.com. It is in the Entra admin centre,
   **Overview → Tenant ID**.
2. **Krusgraph** adds the tenant id in two places: Fabric's **Publish → Selected tenants** list for `Krusgraph.Modeler`
   (20 tenants at most), and the server's `workload_allowed_tenants`. Then publishes. Fabric says it can take up to 10
   minutes before the workload shows. Krusgraph tells the customer when both are done. The tenant id is kept only in the
   git-ignored deploy file, never in the repository.
3. **Fabric admin** turns on, in the admin portal, **Tenant settings → Additional workloads**:
   - **Users can see and work with additional workloads not validated by Microsoft**, for the whole organisation or a
     security group of the pilot users. Microsoft's text asks the admin to trust the publisher first.
   - **Capacity admins and contributors can add and remove additional workloads** (or the preview setting for
     workspace admins, where the tenant has it), for the people who add Krusgraph.
   - Then, for the pilot capacity, the capacity admin allows the Krusgraph workload as the capacity settings ask.
   - Optional, only if the pilot wants an App output: **Enable Fabric App Items (preview)** (`docs/RAYFIN-APP.md`).
4. **Entra admin** grants admin consent for the workload app, once:

   ```
   https://login.microsoftonline.com/<your tenant id>/adminconsent?client_id=853a0cf0-7d35-42b7-b384-26178755a72a
   ```

   An admin can also select **Consent** on the workload in Fabric's **Manage my tenant**. The delegated permissions and
   why each is needed: `docs/TRUST-PACK.md` section 5 ("Krusgraph for Fabric"). `DataPipeline.Execute.All` (Run once,
   Schedule) and `Dataset.ReadWrite.All` (one refresh) are optional; without them Create still works and the editor
   says what to do by hand.
5. **User** creates the first item: in the test workspace, **+ New item → Krusgraph Model**, gives it a name. The editor
   opens.
6. **User** runs the first Create, with Krusgraph, in the first session below.
7. **If something fails:** write to hello@krusgraph.com with the error text, and the kind and hint the editor shows. Do
   not send table contents or screenshots of real data. If the editor says *"Krusgraph is not turned on for your
   organisation yet."*, step 2 is not finished; nothing was read or changed.

## Path C (open question, Unverified): an Org.* package in the customer's own tenant

The idea: the customer's Fabric admin uploads an `Org.*` workload package in their own tenant, under **Govern →
Workloads → Upload workload**, and that package points at Krusgraph's hosted editor and engine and at Krusgraph's
workload app. It would not need Microsoft to register `Krusgraph.Modeler`.

**Do not ask any customer to do this until Microsoft has confirmed it in writing.** What speaks against it today:
Microsoft's manifest page says to use `Org.` "if you don't intend to publish to other tenants", and to register a full
workload name "for publishing across tenants" (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, L1 and L2).

What would have to be true, each **Unverified**:

| # | Must be true | Why it is in doubt |
| --- | --- | --- |
| 1 | Microsoft's terms allow a vendor's `Org.*` package to be uploaded and used in a customer's tenant | Learn describes `Org.` as organisational, not cross-tenant |
| 2 | Fabric accepts a package whose frontend and Application ID URI are on `krusgraph.com` when the uploading tenant has not verified that domain | The general requirements ask for a verified custom domain, and the frontend on a subdomain of it (`docs/WORKLOAD-FEASIBILITY.md`, S8) |
| 3 | Sign-in works: the workload app has redirect URIs `https://app.fabric.microsoft.com/workloadSignIn/<customer tenant>/Org.<name>` (and `app.powerbi.com`) for that customer | Today they exist only for Kruse Consulting's own tenant (`docs/WORKLOAD-PUBLISH.md`, A1) |
| 4 | The server accepts the customer's tenant and that workload's Application ID URI | Possible by configuration (`workload_allowed_tenants`, `workload_app_id_uri`), but untested for another tenant |
| 5 | The `Org.*` name the customer confirms does not collide with or block a later `Krusgraph.Modeler` install | Unknown |
| 6 | Updates: each new version must be uploaded again by the customer's admin | Learn says each upload needs a new version; who carries that work is a support question |

## The first session (30 minutes)

User and Krusgraph together, on a call, on test or sample data. On Path A the same steps are done with the MCP tools
(`plan_backend`, `validate_plan`, `review_plan`, the `create_*` tools with `dry_run=true`, then `dry_run=false`).

| Time | Step | What the user does | What to look at |
| --- | --- | --- | --- |
| 0 to 5 | Open | Open the Krusgraph Model item; choose the lakehouse and the schema | The schemas listed are the ones the user can see |
| 5 to 12 | Check | Run the check against the rows | Counts only: rows, empty values, duplicates, orphans. No row value is shown |
| 12 to 18 | Review | Accept or reject each proposed key and relationship | Each proposal names the rule that found it |
| 18 to 23 | Dry run | Choose the outputs; read the dry run | "Nothing was created or changed in Fabric." Names and what each item will hold |
| 23 to 27 | Create | Choose Create | Each card shows what was created, and the steps left to do in Fabric |
| 27 to 30 | Results | Open the new items in the workspace; reopen the Krusgraph Model item | The summary is kept in `outputs.json` and shown again |

Write down what was unclear. Krusgraph keeps the notes without table contents.

## What we ask of the customer

- **A contact**: one person for the pilot, and the Fabric and Entra admins' names.
- **A test workspace**: on a capacity, with a lakehouse of test or sample data.
- **A schema export, only with permission**: if Krusgraph is to look at the customer's schema outside the session, the
  customer sends a metadata-only export (table and column names and types, declared keys; no rows), and only with the
  data owner's written yes. `docs/CONNECT-DESIGN.md` §1.5 describes the read-only query. Where Krusgraph keeps such a
  file, and for how long: **To confirm by the founder**; it is deleted at the end of the pilot.
- **Feedback**: what worked, what did not, what is missing.
- A data processing agreement, if the customer's process needs one before the pilot: a template is to be drafted with a
  lawyer (`docs/TRUST-PACK.md` section 9).

## How the pilot ends

| Step | Who |
| --- | --- |
| Tell Krusgraph the pilot is over | User or contact |
| Remove the tenant id from the Publish tab (and publish again) and from `workload_allowed_tenants` | Krusgraph |
| Remove admin consent: Entra admin centre → Enterprise applications → the Krusgraph app or the Krusgraph workload app → Permissions, or Properties → Delete | Entra admin |
| Turn off "Users can see and work with additional workloads not validated by Microsoft", if nothing else needs it | Fabric admin |
| Delete the Krusgraph Model items, and the items they built if not wanted (Krusgraph deletes nothing on its own; the data product page's Delete from Fabric needs a dry run and the data product's name typed) | User or workspace admin |
| Delete what Krusgraph holds: any schema export and session notes; the tenant id from the deploy file. Logs age out at the retention on `/it` | Krusgraph |
| Confirm in writing what was deleted, with the date | Krusgraph |

## One-page checklist

**Before**

- [ ] Path chosen (A today, B after the name is registered; not C)
- [ ] Contact named; Fabric admin and Entra admin named
- [ ] `docs/TRUST-PACK.md` and `https://krusgraph.com/it` sent to the customer
- [ ] Data processing agreement in place, if the customer needs one
- [ ] Capacity, test workspace, lakehouse with test or sample data
- [ ] User has Contributor on the test workspace
- [ ] `krusgraph.com` and `workload.krusgraph.com` reachable on port 443

**Path A**

- [ ] Admin consent granted for the Krusgraph app
- [ ] Connector added at `https://krusgraph.com/mcp` (or `/mcp/connect`)
- [ ] Customer told where the tools' answers go (their AI client)

**Path B**

- [ ] Tenant id sent to Krusgraph
- [ ] Krusgraph: tenant on the Publish tab and on `workload_allowed_tenants`; customer told
- [ ] "Users can see and work with additional workloads not validated by Microsoft" turned on
- [ ] Capacity allows the workload
- [ ] Admin consent granted for app `853a0cf0-7d35-42b7-b384-26178755a72a`
- [ ] **+ New item → Krusgraph Model** works

**First session**

- [ ] Check, review, dry run, Create, results
- [ ] Notes kept, without table contents

**End**

- [ ] Tenant removed from both lists
- [ ] Admin consent removed
- [ ] Items deleted, if not wanted
- [ ] Schema export and notes deleted; written confirmation sent
