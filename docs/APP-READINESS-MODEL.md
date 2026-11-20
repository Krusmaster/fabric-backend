# app_readiness for a semantic model: before an app is built from it in Power BI Desktop for Apps

Round FA1, 19 November 2026. Microsoft documents **Power BI Desktop for Apps (preview)**, a separate desktop
application that builds a Fabric app from one or more existing Power BI semantic models: you describe the app in chat,
its agent generates it, you review and edit it, and you publish it to a Fabric workspace. Every app built there starts
from a semantic model, so the model's tables, measures and relationships are what the app's numbers rest on.

`app_readiness` now takes `semantic_model` (a name or id, read with Fabric's documented getDefinition in TMDL) besides
`api`. It needs the same delegated permission as `compare_semantic_model` (SemanticModel.ReadWrite.All or
Item.ReadWrite.All). It answers with checks by fixed rules, no AI model, and changes
nothing. Each check names its basis:

- **microsoft_learn**: the requirement is stated on a Learn page, linked in `source`;
- **krusgraph**: Krusgraph's own rule for a model people can trust; Microsoft does not state it as a requirement;
- **not_documented**: Microsoft's pages do not say whether the app builder's agent reads it; information only.

Verified: unit tests (`tests/test_fa1_model_readiness.py`, `workload/.../fa1NextSteps.test.tsx`) on synthetic models.
Not run against Power BI Desktop for Apps or a live Fabric workspace in this round.

## The checks and their sources

| Check | Status it can have | Basis | What the source says |
| --- | --- | --- | --- |
| `hosted` | ok, info | microsoft_learn | "Power BI Desktop for Apps doesn't create or modify semantic models. Use an existing semantic model hosted in the Power BI service. Connections to local semantic models aren't supported." [1] |
| `tables` | ok, missing | microsoft_learn | The template's starting prompt: "Query the semantic model metadata before writing DAX. Don't guess table, measure, or column names." [5] |
| `measures` | ok, missing | microsoft_learn | "Use fields and measures that exist in the connected semantic model. Don't replace a failed connector query with mock data." [5] |
| `format_strings` | ok, missing, info | microsoft_learn | "The template can reuse semantic model format strings across chart axes, tooltips, data labels, cards, and data grid cells." [5] |
| `relationships` | ok, missing | krusgraph | Not a stated requirement. Krusgraph's rule: a table in no relationship cannot be filtered by the others. |
| `keys` | ok, info | krusgraph | Not a stated requirement. Krusgraph marks a key (`isKey`) only where the plan's key is unique in the rows. |
| `date_table` | ok, info | krusgraph | Not a stated requirement. A marked date table (`dataCategory: Time`) gives every measure the same month and year. |
| `descriptions` | info | not_documented | Learn does not say whether the app builder's agent reads descriptions. |
| `row_level_security` | info | microsoft_learn | "Semantic models support delegated authentication only." [6] Whether a role's filter applies inside the app was not tested. |
| `prep_data_for_ai` | info | not_documented | AI data schema, verified answers and AI instructions are documented for Copilot in Power BI [8]; Learn does not say Power BI Desktop for Apps reads them. |
| `permissions` | unknown | microsoft_learn | "You need Build permission on each semantic model you connect to your app." "People who use your app need Read permission on each connected semantic model." [3] |
| `tenant_settings` | unknown | microsoft_learn | The Power BI Desktop for Apps tenant setting (on by default) [7], the Fabric Apps tenant setting [2], and "The Semantic Model Execute Queries REST API tenant setting enabled." [5] |
| `workspace_capacity` | unknown | microsoft_learn | "Publishing to Pro workspaces is coming soon. For now, choose a workspace on Fabric capacity." [4] |

`unknown` means Fabric's REST API gives Krusgraph no documented way to read it; the check names the portal path.

## The Model editor's next step

Once the Model item has built a semantic model, its next steps add **Build an app in Power BI Desktop for Apps**:
guide only, a link to [1], with the Fabric app item's icon (`fabric_apps_24_item.svg` from `@fabric-msft/svg-icons`,
already in `fabricIcons.json`) beside the words "Apps · App". Krusgraph builds nothing for it. No product logo is used.

## Sources (read 19 November 2026; the page's own `ms.date` in brackets)

1. What is Power BI Desktop for Apps (preview)? <https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/overview> [6 Nov 2026]
2. What is Fabric Apps? <https://learn.microsoft.com/fabric/apps/overview> [15 Sep 2026, updated 17 Nov 2026]
3. Create and edit a report app in Power BI Desktop for Apps (preview) <https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/create-app> [30 Oct 2026]
4. Publish a Fabric app and manage access (preview) <https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/publish-app> [30 Oct 2026]
5. Create an app connected to a semantic model <https://learn.microsoft.com/fabric/apps/data-apps-template> [15 Sep 2026]
6. Connect Fabric Apps to Fabric data <https://learn.microsoft.com/fabric/apps/connectors> [15 Sep 2026]
7. Copilot and Agent admin settings, "Users can use Power BI Desktop for Apps (preview)" <https://learn.microsoft.com/fabric/admin/service-admin-portal-copilot#power-bi-desktop-for-apps> [3 Nov 2026]
8. Prepare your data for AI (preview) <https://learn.microsoft.com/power-bi/create-reports/copilot-prepare-data-ai> [26 May 2026]

Also read: Set up Power BI Desktop for Apps (preview) <https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/setup>
[6 Nov 2026] (Windows 11, Power BI Desktop November 2026 or later, Power BI and GitHub sign-in, a GitHub Copilot
licence), and Choose a licensing option for Fabric Apps <https://learn.microsoft.com/fabric/apps/licensing> [25 Oct 2026].

What these pages do not say, so Krusgraph does not claim it: which model metadata the app builder's agent reads
beyond tables, columns, measures and format strings; whether it can use MCP servers or other external tools (the setup
page shows "agent mode", "tool permissions" and an AI model picker, without a list of tools).
