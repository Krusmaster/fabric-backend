# Trying the Krusgraph Model as a B2B guest, before the name is registered

Round n209, 11 November 2026. For the publisher's administrators (Kruse Consulting AB, in its own tenant): how outside
Fabric users try the **Krusgraph Model** item of the development workload **`Org.Krusgraph`** as Microsoft Entra B2B
guests in the publisher's tenant, before Microsoft registers the permanent name `Krusgraph.Modeler`
(`docs/WORKLOAD-PUBLISH.md`, step 1). The same summary is on the site at `https://krusgraph.com/pilot/fabric`.

The guests work in the publisher's tenant, in **one dedicated workspace**, on **synthetic data only**. They do not need
anything in their own tenant, and nothing of theirs is read. This page says nothing about who the guests are.

Krusgraph is published by Kruse Consulting AB. It is not affiliated with Microsoft, Microsoft does not endorse
Krusgraph, and the workload is not listed in Fabric's Workload Hub. Nothing on this page is a claim about speed,
certification, partnership or endorsement. Nothing on this page has been run with a guest yet: the steps come from the
Learn pages in the source table and from the publisher's own runs of `Org.Krusgraph` (`docs/WORKLOAD-DEV.md`, "Hosted").

Sources `[Gn]` are in the table at the end, all read on learn.microsoft.com on **11 November 2026**. Anything Learn does
not state is marked **Unverified**.

## Why a guest and not the guest's own tenant

`Org.Krusgraph` is an organisational workload: Microsoft's manifest page says to use `Org.` "if you don't intend to
publish to other tenants" (`docs/WORKLOAD-LISTING-AND-PAYMENT.md`, L2). Until `Krusgraph.Modeler` is registered, the
item runs only in the tenant that uploaded it. A B2B guest signs in to that tenant with their own work account and uses
the item there. Uploading an `Org.*` package in another organisation's tenant is Path C of `docs/PILOT-ONBOARDING.md`,
which stays **Unverified** and is not used here.

## Before you start

- `Org.Krusgraph` uploaded and activated in the publisher's tenant on the **hosted** path (`docs/WORKLOAD-DEV.md`,
  "Hosted", steps 1 to 5): the editor served from `https://workload.krusgraph.com`. Developer mode is not suitable for
  guests: DevGateway serves the editor from `localhost` on the publisher's own machine.
- A Fabric capacity (an F SKU) for the trial workspace.
- The roles for the steps below: a Fabric administrator for the tenant settings, a User Administrator (or Guest Inviter)
  in Microsoft Entra for the invitations [G1], and the workspace's Admin.

## 1. A dedicated workspace with synthetic data only

1. Create a new workspace for the trial only (for example `krusgraph-guest-trial`) and assign it to the F capacity. Do not
   reuse a workspace that holds anything else, and never put a customer's or an employer's data in it.
2. In it, create a lakehouse `shop_lh` with **Lakehouse schemas** on, and load the synthetic shop sample the repository
   ships, exactly as in `docs/WORKLOAD-DEV.md`, section 2:

   ```python
   %pip install git+https://github.com/Krusmaster/fabric-backend
   from fabric_backend.seed import seed
   seed(spark, schema="shop")
   ```

   Seven tables of invented shop data appear under the schema `shop` (`fabric_backend/seed.py`).
3. Make sure `Org.Krusgraph` is added to the capacity of this workspace (OneLake catalog → Govern → Workloads →
   `Org.Krusgraph`, or the workload's **Manage capacities**). Learn: "Only workspaces that have this capacity assigned
   can create this workload item." [G5]

## 2. Invite the guests in Microsoft Entra

Use **planned** invitations: Fabric's workspace access list does not send invitations itself. Learn: "The workspace
access list doesn't support ad hoc invites. Use the planned invites approach to add these users to your organization.
After the external user becomes a guest in your organization, add them to the workspace access list." [G2]

1. Microsoft Entra admin center, as at least a User Administrator: **Entra ID → Users → Invite external user** [G1].
2. Enter the guest's email address and display name; tick **Send invite message**; **Review and invite** → **Invite**.
   Learn: "After you send the invitation, the user account is automatically added to the directory as a guest." [G1]
3. The guest opens the invitation email and selects **Accept invitation**, then **Accept** [G1].
4. Put the guests in one Entra security group for the trial (for example `krusgraph-guest-trial`). The tenant settings
   below and the workspace role use that group, so removing someone later is one change.

Learn notes that guests who use this capability "should have a work or school account", and that guests using social
identities have more limitations [G2].

## 3. Let guest users use Fabric

Fabric admin portal (**OneLake catalog → Govern → Configurations → Tenant settings** [G3]), **Export and sharing
settings**:

- **Guest users can access Microsoft Fabric**: on. Learn: "When you turn on this setting, Microsoft Entra
  Business-to-Business (Microsoft Entra B2B) guest users can access Fabric. If you turn off this setting, B2B guest users
  receive an error when trying to access Fabric and any Fabric items they have permissions to." and "Use the specific
  security groups option to control which B2B guest users can access Fabric." [G3] Apply it to the trial's security
  group (plus whatever groups already rely on it).
- **Guest users can browse and access Fabric content**: optional. Learn: "Guest users who have been assigned workspace
  roles or specific item permissions continue to have those roles and/or permissions, even if this setting is
  disabled." [G3] A workspace role (step 5) is enough; leave this setting as it is.
- **Users can invite guest users to collaborate through item sharing and permissions** is not needed: the invitations
  are made in Entra (step 2). It "only controls the ability to invite through Fabric" [G3].

## 4. The additional-workloads tenant settings

Same place, section **Additional workloads**. Learn's names [G4]:

- **Users can see and work with additional workloads not validated by Microsoft**: on, for the publisher's own people and
  the trial's security group. Learn: "Turn on this setting to allow users to see and work with additional workloads not
  validated by Microsoft. Make sure that you only add workloads from publishers that you trust to meet your
  organization's policies." [G4]
- **Capacity admins and contributors can add and remove additional workloads**: on, for the publisher's own
  administrators only (guests do not add workloads). Learn: "Capacity admins or individuals granted Contributor
  permission in Capacity settings can add and remove additional workloads in capacities." [G4]
- **Workspace admins can add and remove additional workloads (preview)**: only if the tenant uses it to add the workload
  to the workspace; not for guests [G4].

Learn's description of both add-and-remove settings: "When users interact with a workload, their data and access
tokens, including name and email, are sent to the publisher. Sensitivity labels and protection settings including
encryption aren't applied to items created with workloads." [G4] Tell the guests this before the trial; `/it` on the
site says what Krusgraph keeps and for how long.

Learn's page on adding workloads names older forms of the two main settings ("Capacity admins and contributors can add
and remove Partner workloads", "Users can see and work with unvalidated partner workloads") and says "Only users who are
in a relevant security group can use unverified workload items, regardless of who created or added the workload." [G5]
The names in the tenant-settings index [G4] are the ones used above.

**Unverified:** that a B2B guest in the scope of "Users can see and work with additional workloads not validated by
Microsoft" sees **Krusgraph Model** under **+ New item** for an `Org.*` workload; no Learn page says how these settings
apply to guests. **Unverified:** whether a guest must consent to the workload's Entra app on first use, or whether the
publisher's admin consent already covers guests in the publisher's tenant. Learn says only: "The first time a user
works with a workload, they must consent to use the Microsoft Entra ID application. Tenant admins can consent on behalf
of the organization by accessing or creating the workload's item type." [G5]

## 5. Workspace roles for the guests

Workspace → **Manage access** → add the trial's security group (or each guest, once they are in the directory [G2]).

- **Contributor** for guests who create Krusgraph Model items and the outputs. Learn's table gives Contributor the rights
  to create and modify warehouse and database items, read lakehouse data through OneLake APIs, Spark and the Lakehouse
  explorer (ReadAll), and write or delete pipelines and notebooks, but not to add people or delete the workspace [G8].
- **Viewer** for guests who only look. Learn: Viewer can "Connect to SQL analytics endpoint of Lakehouse or the
  Warehouse" but not read lakehouse data "through OneLake APIs and Spark (ReadAll)" [G8].
- Keep **Admin** and **Member** for the publisher's own people: Admin can "Add or remove people, including other
  admins" and Member can "Add members or others with lower permissions" [G8].

**Unverified:** which role the Krusgraph Model item itself needs for each output when the user is a guest; the editor
runs with the signed-in person's own Fabric permissions, so the rights above apply, but no run with a guest has been
made.

## 6. The link with `?ctid=<tenant id>`

A guest who opens `app.fabric.microsoft.com` lands in their own home tenant. Send them a link that names the publisher's
tenant. Learn: "Every Microsoft Entra tenant has a globally unique identifier (GUID) known as the *tenant ID*. In
Fabric, it's known as the *customer tenant ID (CTID)*. The CTID is appended to the end of the tenant URL." and "URLs that
you provide to external users (for example, to view a Power BI report) must append the CTID parameter in order to access
the correct tenant." [G6] The value is in the Fabric portal under **Help & Support (?) → About Microsoft Fabric** [G6];
Learn's B2B page calls it the **Tenant URL** and says "Share the tenant URL with your allowed guest users." [G2]

Send the guests:

```
https://app.fabric.microsoft.com/groups/<workspace id>?ctid=<tenant id>
```

with the trial workspace's id (the GUID after `/groups/` in its address) and the publisher's tenant id. **Unverified:**
the exact form above. Learn says the CTID parameter is appended but does not spell out the query string for a workspace
address; copy the **Tenant URL** from the About dialog [G2][G6] and check the link with one guest before sending it to
the rest. A guest with access to several tenants can also switch with the tenant switcher (profile picture → **Switch**)
[G2].

## 7. Licences: Power BI items on a capacity smaller than F64

The Krusgraph Model item, the lakehouse, the API for GraphQL, notebooks and pipelines are non-Power BI Fabric items. A
**semantic model** and a **report** are Power BI items [G7].

What Learn states [G7]:

- "Lets you create and share non-Power BI Fabric items when the workspace runs on a Fabric (F) or Trial capacity.
  Doesn't remove Power BI viewing requirements on F capacities smaller than F64." (the Free licence)
- "To create Power BI items in a workspace other than *My workspace* and share them, you need a Power BI Pro or a Power BI
  Premium Per-User (PPU) license, or a Power BI individual trial."
- "On F SKUs smaller than F64, each user viewing Power BI content must have Pro, PPU, or an individual trial. On F64 or
  larger, users with only a Free license and a viewer role can view Power BI content."

So on an F2 to F32 capacity, a guest who creates the semantic model or the report from the Krusgraph Model item, or who
opens them, needs Pro, PPU or an individual trial. With only a Free licence a guest can still create the Krusgraph Model
and its non-Power BI outputs.

Where the guest's licence can come from, per Learn's B2B page [G2]: "Assign a Power BI Pro or a Premium Per User (PPU)
license" from the publisher's tenant ("Assigning a Power BI Pro or PPU license from your organization to a guest user
lets that guest user view content shared with them."), or "Use a guest's Power BI Pro or PPU license" ("The guest user
might already have a Power BI Pro or PPU license that their own organization assigned to them."). Before assigning
licences to guests Learn says to "consult the Product Terms site to ensure you're in compliance with the terms of your
licensing agreement with Microsoft" [G2].

**Unverified:** that a licence assigned in the guest's **home** tenant lets the guest **create** semantic models and
reports in the publisher's workspace. Learn's B2B page describes both licence sources for viewing shared content; it does
not say so for creating Power BI items. If the trial includes the semantic model or the report, the safe choice is a Pro
or PPU licence assigned in the publisher's tenant, or a trial that leaves those two outputs out. Learn also lists
"Direct publishing from Power BI desktop to the Power BI service" among the experiences guests do not have [G2]; the
Krusgraph Model creates its items through Fabric's REST API, not from Desktop.

## 8. During the trial

- Guests work only in the trial workspace, on the `shop` schema of `shop_lh`.
- If something does not work, they write to hello@krusgraph.com with the text the screen showed. No table contents.
- The publisher's admin keeps the list of who was invited in Entra, not in this repository.
- What the server sees of a guest (round n210, unit tests with guest-shaped tokens only, `tests/test_n210_guest.py`): the
  token the Fabric host gives the editor is issued by the publisher's tenant, so its `tid` is the publisher's tenant
  id. `KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS`, when set, must hold the **publisher's** tenant id; a guest's home tenant on
  that list lets nobody in. The licence check (`KRUSGRAPH_ENTITLEMENTS`) is the publisher's tenant's as well. "By whom"
  in outputs.json and the page's **Me** button use the token's name, else its sign-in name, else its email (a guest's
  `#EXT#` sign-in name is read back to the home address); never a tenant or object id.
- The Krusgraph connector in Claude (`/mcp`) is not part of the trial: it signs a guest in to their own home tenant, so
  it cannot reach the trial workspace.

## 9. After the trial: what to remove

In this order:

1. **Workspace access**: remove the trial's security group (or each guest) from **Manage access**.
2. **Licences** assigned to guests in the publisher's tenant (step 7): unassign them in the Microsoft 365 admin center.
   **Unverified:** Learn's B2B page links to assigning licences, not to removing them; it is the ordinary unassign.
3. **The guest accounts**: Microsoft Entra admin center → **Entra ID → Users**, select each guest, **Delete user**.
   Learn: "When no longer needed, delete the test guest user." [G1] Then delete the trial's security group.
4. **The workspace**: delete the trial workspace (Admin role: "Update and delete the workspace." [G8]), with the
   Krusgraph Model items, `shop_lh` and every output made in it. Delete the Krusgraph Model items before the workload
   is ever deactivated (`docs/WORKLOAD-DEV.md`, section 7).
5. **Tenant settings**: take the trial's group out of the scope of "Guest users can access Microsoft Fabric" and "Users
   can see and work with additional workloads not validated by Microsoft"; turn "Guest users can access Microsoft
   Fabric" off again if nothing else needs it. Learn: "If you disable the setting, existing guest users in your
   organization continue to have access to any items they already had access to" (about the invite setting) [G2], which
   is why the guest accounts are deleted in step 3 and not only the settings changed.
6. **Krusgraph's side**: the server keeps nothing per guest beyond what `/it` lists; nothing to remove in the repository.

## Sources

All read on learn.microsoft.com on **11 November 2026**. "Learn commit" is the `git_commit_id` the page reports.

| # | Title (`ms.date`; updated) | URL | Learn commit | What it says that this page relies on |
| --- | --- | --- | --- | --- |
| G1 | Quickstart: Add a guest user and send an invitation (2026-04-24; 2026-05-08) | https://learn.microsoft.com/entra/external-id/b2b-quickstart-add-guest-users-portal | `3456eb7` | "A role that allows you to create users in your tenant directory, such as at least a Guest Inviter role or a User Administrator."; "Browse to **Entra ID** > **Users**."; "Select **Invite external user** from the menu."; "After you send the invitation, the user account is automatically added to the directory as a guest."; "When no longer needed, delete the test guest user." |
| G2 | Distribute Power BI content to external guest users with Microsoft Entra B2B (2025-11-03; 2026-05-27) | https://learn.microsoft.com/fabric/enterprise/powerbi/service-admin-entra-b2b | `ba4992d` | "The workspace access list doesn't support ad hoc invites. Use the planned invites approach to add these users to your organization."; "Assign a Power BI Pro or a Premium Per User (PPU) license."; "Use a guest's Power BI Pro or PPU license."; "Share the tenant URL with your allowed guest users."; guests do not have "Direct publishing from Power BI desktop to the Power BI service" |
| G3 | Export and sharing tenant settings (2026-04-08; 2026-09-29) | https://learn.microsoft.com/fabric/admin/service-admin-portal-export-sharing | `80a24c9` | "When you turn on this setting, Microsoft Entra Business-to-Business (Microsoft Entra B2B) guest users can access Fabric."; "Use the specific security groups option to control which B2B guest users can access Fabric." |
| G4 | Tenant settings index, "Additional workloads" (2026-08-28; 2026-11-05) | https://learn.microsoft.com/fabric/admin/tenant-settings-index | `68b2996` | The settings "Users can see and work with additional workloads not validated by Microsoft", "Capacity admins and contributors can add and remove additional workloads", "Workspace admins can add and remove additional workloads (preview)"; "When users interact with a workload, their data and access tokens, including name and email, are sent to the publisher." |
| G5 | Add a Microsoft Fabric workload (2026-04-29; 2026-04-30) | https://learn.microsoft.com/fabric/workload-development-kit/more-workloads-add | `fb19ffa` | "Only workspaces that have this capacity assigned can create this workload item."; "Only users who are in a relevant security group can use unverified workload items, regardless of who created or added the workload."; "The first time a user works with a workload, they must consent to use the Microsoft Entra ID application." |
| G6 | Power BI implementation planning: Tenant setup, "Tenant ID for external users" (2024-12-30; 2026-03-11) | https://learn.microsoft.com/power-bi/guidance/powerbi-implementation-planning-tenant-setup | `3f20253` | "In Fabric, it's known as the *customer tenant ID (CTID)*. The CTID is appended to the end of the tenant URL."; "URLs that you provide to external users (for example, to view a Power BI report) must append the CTID parameter in order to access the correct tenant." |
| G7 | Understand Microsoft Fabric licenses and capacity (2026-06-15; 2026-11-10) | https://learn.microsoft.com/fabric/enterprise/licenses | `5a18c28` | "To create Power BI items in a workspace other than *My workspace* and share them, you need a Power BI Pro or a Power BI Premium Per-User (PPU) license, or a Power BI individual trial."; "On F SKUs smaller than F64, each user viewing Power BI content must have Pro, PPU, or an individual trial." |
| G8 | Roles in workspaces in Microsoft Fabric (2026-04-24; 2026-08-18) | https://learn.microsoft.com/fabric/fundamentals/roles-workspaces | `2c679c1` | The role table: Admin "Update and delete the workspace." and "Add or remove people, including other admins."; Contributor creates and modifies items and reads lakehouse data (ReadAll); Viewer connects to the SQL analytics endpoint only |

### Unverified (no Learn page read says so)

| # | Statement | Why |
| --- | --- | --- |
| U1 | A B2B guest in scope of the additional-workloads settings sees and can use an `Org.*` workload's item | [G4][G5] describe the settings, not how they apply to guests |
| U2 | Whether a guest must consent to the workload's Entra app, or the publisher's admin consent covers guests | [G5] speaks of "a user" and "tenant admins" only |
| U3 | The exact link form `https://app.fabric.microsoft.com/groups/<workspace id>?ctid=<tenant id>` | [G6] says the CTID parameter is appended; it does not spell out the query string |
| U4 | A Pro or PPU licence from the guest's **home** tenant lets the guest **create** semantic models and reports in the publisher's workspace | [G2] describes the guest's own licence for viewing shared content only |
| U5 | Which workspace role the Krusgraph Model needs per output for a guest | No run with a guest yet |
| U6 | The steps to unassign a licence from a guest | [G2] links to assigning licences only |
