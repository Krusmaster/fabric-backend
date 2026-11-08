# Krusgraph workload for Microsoft Fabric (phase 1)

The **Krusgraph Model** item: in a Fabric workspace, **+ New item → Krusgraph Model** opens this editor inside Fabric.
Choose a lakehouse, review the keys and relationships Krusgraph found (open items first, K and R rule pills, Accept and
Reject), see a dry run and create an API for GraphQL. The engine is the Python server in this repository
(`fabric_backend/workload_api.py`); the editor calls it with a token Fabric issues for the workload's own Entra app.

- How to run it in your own tenant, and remove it again: [`docs/WORKLOAD-DEV.md`](../docs/WORKLOAD-DEV.md)
- Why it is built this way: [`docs/WORKLOAD-FEASIBILITY.md`](../docs/WORKLOAD-FEASIBILITY.md)
- Unit tests: `cd Workload && npm ci --ignore-scripts && npm test` (definition load and save, the version field)

## Origin and licence

A fork of Microsoft's starter kit [`microsoft/fabric-extensibility-toolkit`](https://github.com/microsoft/fabric-extensibility-toolkit)
at commit `dacab1b391d03010ba61a0446126d05515c487f0` (6 August 2026), MIT, Copyright (c) Microsoft Corporation. The
licence text is in [`LICENSE`](LICENSE) and travels with the copied files; Microsoft's own README is
[`README.starter-kit.md`](README.starter-kit.md). Copied: the kit's `Workload/`, `scripts/` and `tools/`. Changed: the
HelloWorld item is now the Model item (`Workload/Manifest/items/ModelItem/`, `Workload/app/items/ModelItem/`), the
manifest texts, and lines marked `Krusgraph:` (engine settings in `.env.template` and `webpack.config.js`, the dev
server's forwarding of `/workload/v1`, the test set-up).

The development workload name is `Org.Krusgraph`. Do not upload a `Krusgraph.*` name: the first upload reserves it
for good, and that is the founder's decision.
