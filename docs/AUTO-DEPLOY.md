# Automatic deployment: the one-time setup

CD1, 16 November 2026. `.github/workflows/deploy.yml` deploys `main` to the container app behind krusgraph.com after CI
is green. It does what the maintainer does by hand with `bash deploy/krusgraph.sh --from-azure --update` in Cloud Shell,
using the same code in `deploy/azure_containerapp.py`:

1. `az acr build` of the commit, in Azure, tagged with the source tag;
2. the container app pointed at the new image, with `KRUSGRAPH_BUILD` set to that tag. Nothing else changes: no
   secret, domain, certificate, Entra setting, scale setting or other environment variable;
3. the checks of `--update`: `/healthz` reports the new build, then the home page, `/docs`, `/privacy`, the OAuth
   metadata and `POST /mcp` answering 401 with the login requirement.

When a step fails after the snapshot, the workflow points the app back at the image that ran before
(`deploy/auto_deploy.py rollback`), runs the same checks against the old build, and opens an issue with the outcome.
One deployment runs at a time. A newer commit replaces one that is still waiting, and a commit that is no longer
`main`'s tip is skipped. A running deployment is never cancelled.

Still manual: the Fabric workload package upload, changes in `deploy/krusgraph.json` (scale, flags, workload or
marketplace settings), `--workload-host`, `--key-vault`, secrets and domains. Those are `bash deploy/krusgraph.sh --update`
in Cloud Shell as before.

Until the steps below are done, the workflow is dormant. Every run stops in its first job with the line "Automatic
deployment is not set up" and makes no Azure call.

## The steps (about 10 minutes)

Use the Azure portal in Krusgraph's directory (the tenant the container app is in).

### 1. An identity for GitHub (3 min)

1. **Microsoft Entra ID → App registrations → New registration.** Name `krusgraph-github-deploy`, *Accounts in this
   organizational directory only*, no redirect URI. **Register.**
2. On its Overview page, copy the **Application (client) ID** and the **Directory (tenant) ID**.
3. **Certificates & secrets → Federated credentials → Add credential.**
   - Scenario: *GitHub Actions deploying Azure resources*
   - Organization `Krusmaster`, Repository `fabric-backend`, Entity type *Branch*, GitHub branch name `main`
   - Name `github-main`. The subject shown must be `repo:Krusmaster/fabric-backend:ref:refs/heads/main`.
   - **Add.**

Do not create a client secret: GitHub signs in with a short-lived token that only runs from `main` of this repository
can get.

(Instead of an app registration you can use a user-assigned managed identity: **Managed Identities → Create** in the
same resource group, then **Federated credentials → Add credential** with the same values. Use its client ID below.
Do not reuse the identity the container app pulls images with.)

### 2. Access to the resource group only (2 min)

1. **Resource groups →** the group that holds the container app, registry and environment → **Access control (IAM)
   → Add → Add role assignment.**
2. Role **Contributor** (tab *Privileged administrator roles*). Members: *User, group, or service principal* →
   **Select members** → `krusgraph-github-deploy`. **Review + assign.**

Assign it on the resource group, not on the subscription. Contributor cannot assign roles or read Entra, so the
workflow can build images and update the app, and nothing else in the subscription.

### 3. GitHub repository variables (4 min)

GitHub → **Krusmaster/fabric-backend → Settings → Secrets and variables → Actions → Variables tab → New repository
variable**, six times:

| Name | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | Application (client) ID from step 1 |
| `AZURE_TENANT_ID` | Directory (tenant) ID from step 1 |
| `AZURE_SUBSCRIPTION_ID` | the subscription of the resource group |
| `KRUSGRAPH_RESOURCE_GROUP` | the resource group's name |
| `KRUSGRAPH_APP` | the container app's name |
| `KRUSGRAPH_AUTO_DEPLOY` | `on` |

None of these is a secret, and nothing goes under *Secrets*. The subscription, resource group and app names are the
ones `bash deploy/krusgraph.sh --from-azure` prints in Cloud Shell. They stay in GitHub's settings and never go into
the repository.

### 4. One test run (1 min plus the build)

GitHub → **Actions → Deploy → Run workflow** (branch `main`). The *deploy* job takes about as long as `--update` does
in Cloud Shell. It ends with "Hemsida, dokumentation, sekretessida och MCP-inloggningskrav svarar korrekt." and the
build id. After that, every green CI run on `main` deploys on its own.

## Switch it off

- **Pause:** set the variable `KRUSGRAPH_AUTO_DEPLOY` to `off` (or delete it). Runs then stop in the first job and
  nothing is deployed. Set it back to `on` to resume.
- **Stop the workflow:** Actions → Deploy → **…** → *Disable workflow*.
- **Remove access:** delete the role assignment from step 2 and the federated credential from step 1 (or the whole
  app registration). Deployment is then `bash deploy/krusgraph.sh --update` in Cloud Shell only, as before CD1.

## When a deployment fails

The workflow opens an issue named "Automatic deployment of <commit> failed". It shows which step failed and whether
the rollback brought the previous build back with passing checks. If the rollback did not pass, look at the revisions in
Azure Container Apps and run `bash deploy/krusgraph.sh --doctor` in Cloud Shell.
