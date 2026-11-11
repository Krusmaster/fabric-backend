# Promote a data product: dev → test → prod with Fabric's own tools

Round n198. A design text, docs only, nothing implemented. Written 11 November 2026. It follows the Data product page
(n198, `docs/WORKLOAD-DEV.md` section 16) and the Lifecycle design (`docs/LIFECYCLE-DESIGN.md`). Krusgraph is
independent; "works with Microsoft Fabric" describes compatibility only, and there is no partnership with Microsoft.
Krusgraph for Fabric uses no AI model, here too.

**Verified** means a public page was opened on 11 November 2026 and says it; the page is in Sources. **Unverified**
means no public page was found that says it.

## The idea in one line

Krusgraph does not build its own promotion. A data product lives in one workspace per stage, and Fabric's own **Git
integration** and **deployment pipelines** move it from dev to test to prod. Krusgraph prepares the dev workspace, shows
the steps, and on the Data product page of each stage says what is there and what is out of date.

## What moves with Fabric's tools

| Krusgraph output | Git integration | Deployment pipelines | Note |
|---|---|---|---|
| Silver and gold notebooks, the check notebook | Notebooks: Verified (S1) | Notebook: Verified (S2) | The tables and views they write are data: not copied (S3). The pipeline run fills them in each stage |
| Pipeline | Pipeline: Verified (S1) | Pipeline: Verified (S2) | Schedules: Unverified whether they travel; set them per stage (the Data product page's Turn off and Create's Schedule are per stage) |
| Semantic model | Preview, with exceptions (S1) | Supported if upgraded to enhanced metadata (S2) | Refresh schedule, role assignments and data source credentials are not copied (S3) |
| Report | Preview, with exceptions (S1) | Supported (S2) | Autobinds to the model in the target stage when that model is there (S3) |
| API for GraphQL | GraphQL: Verified (S1) | GraphQL: Verified (S2) | Its data source in the target stage: Unverified whether it rebinds to that stage's lakehouse |
| Ontology | IQ items, Ontology (preview): Verified (S1) | Ontology (preview): Verified (S2) | |
| Data agent | Data Agents: Verified (S1) | Data Agents: Verified (S2) | Publishing per stage stays a step in the stage (Unverified whether a published state travels) |
| App (Rayfin, preview) | Not listed (S1) | Not listed (S2) | Built per stage with its one command, as today |
| The Krusgraph Model item itself | Not listed (S1); a workload item's definition is stored "using the same format applied by public APIs and CI/CD processes" (S7) | Not listed (S2) | Unverified whether Git sync carries a workload item. Until it is verified, each stage has its own Krusgraph Model item |

Data is never copied by a deployment pipeline ("Data isn't copied. Only metadata is copied", S3). Neither is a
workspace's or an item's permissions.

## The REST APIs, and the scopes they need

All from `microsoft/fabric-rest-api-specs` (main, `platform/swagger.json`, read 11 November 2026) and the Learn pages
built from it (S4, S5). Delegated scopes, as the signed-in user.

| Step | API | Delegated scope |
|---|---|---|
| Connect the dev workspace to a Git repository | Git - Connect, Initialize Connection | `Workspace.ReadWrite.All` |
| Read what differs from Git | Git - Get Status | `Workspace.GitUpdate.All` or `Workspace.GitCommit.All` |
| Commit the workspace's changes | Git - Commit To Git | `Workspace.GitCommit.All` |
| Update a workspace from Git | Git - Update From Git | `Workspace.GitUpdate.All` |
| Create a deployment pipeline and its stages | Deployment Pipelines - Create, Update Stage | `Pipeline.ReadWrite.All` |
| Assign a workspace to a stage | Assign Workspace To Stage | `Pipeline.ReadWrite.All` and `Workspace.ReadWrite.All` |
| List what is in a stage | List Deployment Pipeline Stage Items | `Pipeline.Read.All` or `Pipeline.ReadWrite.All` |
| Deploy from one stage to the next | Deploy Stage Content (long-running) | `Pipeline.Deploy` |
| Follow a deployment | Get Deployment Pipeline Operation | `Pipeline.Read.All` or `Pipeline.ReadWrite.All` |

The workload app has none of these scopes today (it has `Workspace.Read.All` and the item scopes, `docs/SCOPES.md`).
Each would be added only for the round that uses it, and `Pipeline.Deploy` and `Workspace.GitCommit.All` only behind
an explicit choice by the customer's administrator.

## What stays a manual step

- **Git credentials and the repository.** Connecting needs the person's own Git provider credentials (Azure DevOps or
  GitHub, cloud only, S1). Krusgraph never holds them.
- **Deployment rules** (data sources and parameters per stage, S3): set in Fabric by the pipeline's admin. Krusgraph
  lists which items need one (the semantic model's and the API's source lakehouse) and the stage's lakehouse to point at.
- **Approving a deployment to prod.** A person deploys to prod. Krusgraph may show the dry run of what would change
  (List Stage Items in both stages, compared with the dev Data product page), never deploys to prod by itself.
- **Capacity and workspace per stage.** Creating a stage's workspace and assigning it to a capacity is for the
  capacity's or workspace's admin (S3).
- **Per-stage state that is not copied:** refresh schedules, credentials, role assignments (S3), and the pipeline's
  schedule (Unverified). The Data product page of each stage says which are missing.

## How Krusgraph would fit, later

1. **Read only (S).** On the Data product page: "This workspace is connected to Git (branch, last commit)" and "This
   workspace is stage Test of pipeline X" (Git - Get Connection; the stage from List Deployment Pipelines and Stages).
   Needs `Pipeline.Read.All`; `Workspace.Read.All` is already there.
2. **The steps, written for this data product (S).** The page lists the items to put under Git, the deployment rules to
   set, and what each stage still needs (schedule, refresh, publish of the agent), as a checklist. No new scope.
3. **Compare stages (M).** The items of this data product in dev and in test, side by side, with "out of date in test".
   Only reads.
4. **Deploy dev → test on a person's click (M).** Deploy Stage Content with exactly the items of this data product
   (selective deploy), a dry run first (the compare of step 3), the person's confirmation, and the operation followed to
   its end. Never to prod. Needs `Pipeline.Deploy`, behind the administrator's choice.

Open questions for Microsoft: whether a workload item (the Krusgraph Model) can be synced with Git and deployed; whether
a pipeline's schedules and a data agent's published state travel with a deployment.

## Sources (opened 11 November 2026)

- S1. Learn, "What is Microsoft Fabric Git integration?", fabric/cicd/git-integration/intro-to-git-integration (ms.date
  2026-09-01): supported Git providers and the list of supported items.
- S2. Learn, "Introduction to deployment pipelines", fabric/cicd/deployment-pipelines/intro-to-deployment-pipelines
  (ms.date 2026-09-24): supported items, two to ten stages.
- S3. Learn, "The deployment pipelines process", fabric/cicd/deployment-pipelines/understand-the-deployment-process
  (ms.date 2026-09-24): autobinding, what is copied, "Item properties that are not copied", deployment rules.
- S4. Learn, Fabric REST API, Core / Git (for example core/git/commit-to-git) and `platform/swagger.json` (operations
  Git_Connect, Git_InitializeConnection, Git_GetStatus, Git_CommitToGit, Git_UpdateFromGit with their scopes).
- S5. Learn, Fabric REST API, Core / Deployment Pipelines and `platform/swagger.json` (DeploymentPipelines_* operations,
  among them DeployStageContent with `Pipeline.Deploy`, AssignWorkspaceToStage, ListDeploymentPipelineStageItems).
- S6. Learn, Fabric REST API, Core / Items, Delete Item (core/items/delete-item), for the Data product page's Retire.
- S7. Learn, Microsoft Fabric Extensibility Toolkit, key concepts (fabric/extensibility-toolkit/key-concepts, ms.date
  2025-12-15): an item's definition is stored in the format used by public APIs and CI/CD processes.
