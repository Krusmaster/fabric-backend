# Pilot day: Krusgraph's checklist

Round WB9, 23 November 2026. The day-of checklist for Krusgraph's side of a pilot. The customer's steps, the paths and
the admin consent link are in `docs/PILOT-ONBOARDING.md`; what Krusgraph reads and stores is in `docs/TRUST-PACK.md`.
No customer names, prices or notes go in this repository: they are kept in Krusgraph's private business repository.

## The day before

- [ ] The customer's **tenant id** (a GUID), from their Entra admin. Not the domain name.
- [ ] Path chosen (A, B or C, `docs/PILOT-ONBOARDING.md`, "Choose the path").
- [ ] Path B: the tenant is under **Selected tenants** for Krusgraph.Modeler in the workload's publishing settings
      (Fabric admin portal, Workloads). Fabric can take about 10 minutes to show a change: check again after that.
- [ ] The customer's Entra admin has granted admin consent once (the link in `docs/PILOT-ONBOARDING.md`, Path B step 4).
- [ ] The customer's Fabric admin has turned on the tenant setting for workloads not validated by Microsoft, for the
      pilot users' group.
- [ ] A workspace on an F capacity or a trial, with the pilot users as Contributor or higher, and one lakehouse.

## At the start of the call (5 minutes)

- [ ] The user opens a new Krusgraph Model item and runs **Is everything ready? Check this workspace** on the first
      screen. It reads, as the user, and changes nothing:
  - admin consent: the permissions on the user's sign-in;
  - Fabric capacity: whether the workspace has one (Workspaces - List Workspaces, `capacityId`);
  - workspace access: whether the user can list its items;
  - a lakehouse: whether there is one to choose.
  The tenant setting is shown as **unknown**: no documented API reads it without a Fabric administrator. If the user
  could open the item, it is on for them.
- [ ] Fix whatever is **Missing** before going on. The same check is `POST /workload/v1/selfcheck {workspace}`.

## The session (30 minutes)

Follow "The first session" in `docs/PILOT-ONBOARDING.md`, on one of these:

- the **shop sample** (Path A: `start` with `sample=true`), when the customer has no data ready;
- **SAP demo data**: in the review, *Dry run: Load SAP demo data*, then *Create the notebook*. Krusgraph creates the
  sap_demo36 notebook and does not run it; the user runs it in Fabric (synthetic, SAP-shaped tables, made-up names),
  then chooses the new schema;
- the customer's own test data, when they have it.

## Afterwards (same day)

- [ ] Write down what was unclear, without table contents, in the private business repository.
- [ ] Anything that blocked the session that the self-check did not catch becomes a backlog item.
- [ ] Agree the date of the next session.
