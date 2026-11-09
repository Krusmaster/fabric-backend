# Krusgraph in Microsoft Fabric: what a pilot's administrator does

For the Fabric or Microsoft Entra administrator of an organisation taking part in the Krusgraph pilot in Microsoft
Fabric. The same steps are on the site at `https://krusgraph.com/pilot/fabric`. Round n176, 9 November 2026.

Krusgraph adds one item type to Fabric, **Krusgraph Model**. It is published by Kruse Consulting AB to a small number of
selected organisations as `Krusgraph.Modeler`. It is not listed in Fabric's Workload Hub and has not been validated by
Microsoft; that is why step 2 is needed. Kruse Consulting AB is not affiliated with Microsoft.

Do the steps in this order. Each one is done once for the organisation.

## 1. Send us your tenant id

Your tenant id is shown in the Microsoft Entra admin centre, **Overview → Tenant ID**. Send it to
hello@krusgraph.com. We add it in two places: Fabric's list of selected tenants for the workload, and the list of
organisations our server answers. We reply when both are done; Fabric says it can take up to 10 minutes after that
before the workload shows.

Until your tenant is on both lists, people in your organisation either do not see Krusgraph, or see the message
*"Krusgraph is not turned on for your organisation yet."* in the editor, with your tenant id. Nothing is read or changed
in that case.

## 2. Turn on the Fabric tenant setting for workloads not validated by Microsoft

In the Fabric admin portal, **Tenant settings → Additional workloads**:

- **Users can see and work with additional workloads not validated by Microsoft**: turn it on, for the whole
  organisation or for a security group of the people in the pilot. Microsoft's text asks you to make sure you trust the
  publisher first.
- **Capacity admins and contributors can add and remove additional workloads** (or, where your tenant has it, the
  preview setting that lets workspace admins add workloads): turn it on for the people who will add Krusgraph to a
  capacity or workspace.

Then, for the capacity the pilot workspace runs on, the capacity's administrator allows the Krusgraph workload as
Fabric's capacity settings ask. Microsoft's admin page notes that with these settings on, data and access tokens,
including name and email, are sent to the publisher of the workload. `https://krusgraph.com/it` says what Krusgraph
keeps and for how long.

The workload needs a workspace on a Fabric capacity. It does not run on Power BI Pro alone, and it is
blocked where Private Link is turned on.

## 3. Grant admin consent for the Krusgraph workload app

The editor calls our engine with your users' own permissions (delegated, on their behalf). For that, a Global
Administrator or Privileged Role Administrator grants consent once for the organisation. Open this link, with your own
tenant id in place of `<your tenant id>`:

```
https://login.microsoftonline.com/<your tenant id>/adminconsent?client_id=853a0cf0-7d35-42b7-b384-26178755a72a
```

The consent screen lists the delegated permissions the app asks for: Fabric (Power BI Service) permissions to read the
workspace and lakehouse and to create the items a user chooses to build, Azure SQL Database to read the lakehouse's SQL
endpoint, and sign-in. Every call runs as the person using the editor, with that person's Fabric rights; Krusgraph can
reach nothing that person cannot. The list of permissions and why each is needed is on `https://krusgraph.com/it`.

To withdraw it later: Microsoft Entra admin centre → **Enterprise applications** → the Krusgraph app → **Properties →
Delete**, or remove its permissions.

## 4. Allow the two addresses through your network

If your organisation filters outbound web traffic, allow HTTPS (port 443) to:

- `krusgraph.com`
- `workload.krusgraph.com` (the editor that opens inside Fabric, and its engine)

Both are hosted in Azure, Sweden Central. Nothing else needs to be opened; Fabric itself is reached as usual.

## 5. Create a Krusgraph Model

In a workspace on the Fabric capacity: **+ New item → Krusgraph Model**. Give it a name. The editor opens; choose a
lakehouse in the same workspace and a schema, and Krusgraph proposes keys and relationships, each with the rule that
found it. You accept or reject each one, and see a dry run of what would be created before anything is.

We suggest a first try on a lakehouse with test or sample data. Any screenshots we send of these steps use the synthetic
shop schema from Krusgraph's open source code, not anyone's real data.

## If something does not work

Write to hello@krusgraph.com with what the screen said (the error text, and the kind and hint if the editor shows them).
Do not send table contents or screenshots of real data.

## Leaving the pilot

Tell us, and we remove your tenant id from both lists. You can also remove the admin consent (step 3) and turn the
tenant setting (step 2) off yourself at any time.
