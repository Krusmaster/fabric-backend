# Build a Lovable app on your Fabric tables

Three steps, the way they ran on 30 October 2026 against a Fabric workspace with synthetic data (workspace `demo`,
lakehouse `demo_lh`, schema `shop`; the record is `docs/LIVE-TEST.md`, section 6). {{PRODUCT}} as a custom MCP connector
in Lovable plans, checks and creates the API for GraphQL item; three settings in Microsoft Entra and the Fabric portal
let an app's service principal query it; Lovable's own Microsoft Fabric connector reads it. The API item in your
workspace is what joins the two.

| Step | Where | Done by | Status |
| --- | --- | --- | --- |
| 1. Plan, check and create the API | Lovable's chat, with {{PRODUCT}} as a custom MCP connector | {{PRODUCT}}, when you ask | Lovable as an MCP client: {{LOVABLE_MCP_STATUS}} |
| 2. The three portal steps | Microsoft Entra and the Fabric portal | you or an administrator, by hand | introspection has no API; {{PRODUCT}} sets none of the three |
| 3. Connect Lovable's Fabric connector | Lovable | you, by hand | Lovable reading the API: {{LOVABLE_API_STATUS}} |

## 1. Plan, check and create the API from Lovable's chat

{{#IF CLIENT_REGISTRATION}}In Lovable, open **Connectors**, choose the **Custom** card labelled **MCP** and enter `{{CONNECT_URL}}` as the server URL,
with OAuth (the default). **Add & authorize** opens {{PRODUCT}}'s own approval page, which names Lovable and where the
answer goes, and then Microsoft's sign-in with your work account. {{PRODUCT}} registers Lovable as a client itself
(dynamic client registration), so nothing is set up on the Entra app for it, and every call runs with your own Fabric
permissions. Lovable's guide to custom MCP connectors: [docs.lovable.dev/integrations/custom-mcp](https://docs.lovable.dev/integrations/custom-mcp).{{/IF}}{{#IF NO_CLIENT_REGISTRATION}}This deployment has client registration switched off, so Lovable cannot sign in to {{DOMAIN}} itself: plan, check and
create in Claude with the {{PRODUCT}} connector instead ([get started](/start)) and continue at step 2. On krusgraph.com
the address for Lovable and other clients that register themselves is `https://krusgraph.com/mcp/connect` (switched on
since 27 October 2026; Lovable's guide to custom MCP connectors: [docs.lovable.dev/integrations/custom-mcp](https://docs.lovable.dev/integrations/custom-mcp)).{{/IF}}

In the chat, ask for the plan first, then the check, then the item:

1. *"Plan the tables in schema shop of demo_lh in workspace demo."* `plan_backend` answers with the keys and
   relationships and the rule behind each; it creates nothing.
2. *"Check the plan against the data."* `validate_plan` counts duplicate key values, references with no matching row
   and the total that doubles, in the rows.
3. *"Create it as shop_api."* `create_backend` creates one API for GraphQL item with nested relationships, or updates it
   in place when the name exists. {{CREATE_API_STATUS}}.

On 30 October 2026 the same chat went on to `create_semantic_model` and `create_report`; an app needs neither.

## 2. The three portal steps

The app does not use your sign-in. Lovable's Fabric connector calls the API with a Microsoft Entra **service
principal**, so three settings are made by hand, as Microsoft's own pages describe them (*Connect to the API for GraphQL
with a service principal* and *Introspection* on Microsoft Learn):

1. **Microsoft Entra: an app registration with a client secret.** Skip redirect URIs and API permissions, create a
   client secret, and note the tenant id, the client id and the secret value. A Fabric tenant administrator must have
   *Service principals can use Fabric APIs* enabled under Developer settings, once per tenant.
2. **The Fabric workspace: Contributor for that app.** Workspace → Manage access → add the app registration with the
   Contributor role. (The narrower alternative is *Run Queries and Mutations* on the API item plus read access to the
   lakehouse.) `app_readiness` cannot read permissions and says so, with this click path.
3. **The API item: introspection on.** shop_api → Settings → Introspection → on → Confirm. Fabric creates the item with
   introspection off, Lovable's connection test needs it, and Fabric has no API for the setting: the one step that
   cannot be scripted. `app_readiness` probes it.

## 3. Connect Lovable's Microsoft Fabric connector

In Lovable, open **Connectors**, choose **Microsoft Fabric** and enter the tenant id, the client id, the client secret
and the API item's endpoint URL (in the item's settings; it ends in `/graphql`). Lovable runs an introspection query to
test the connection. Lovable's documentation says the credentials are stored in Lovable's gateway and never reach the
browser or the app's frontend, and that every app and builder on the connection queries Fabric as the same principal:
rows a user may not see are the app's job to hide (see [App access](/docs#app-access)). Lovable reading the API:
{{LOVABLE_API_STATUS}}.

Lovable's own guide lists every prerequisite and limit: https://docs.lovable.dev/integrations/microsoft-fabric

## Good to know

- **Lakehouse sources are read-only** through the API for GraphQL; writes work on warehouses and SQL databases.
  {{PRODUCT}} creates read-only items unless you ask for a writable one.
- **What Lovable sees** is what the item exposes, under the service principal's permissions.
- **Without Lovable's connector:** `app_starter` gives a Lovable prompt, the queries and a Supabase edge function that
  keeps the secret on the server side. The whole chain, with who does each step and what still blocks, is in the
  repository's `docs/LOVABLE-END-TO-END.md`.

## Next

[Get started](/start) · [Docs](/docs) · [Try the guided demo](/check?example=sample&guide=1)
