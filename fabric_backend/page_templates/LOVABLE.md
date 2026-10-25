# Use {{PRODUCT}} with Lovable

Lovable's Microsoft Fabric connector reads data from an existing **API for GraphQL** item in Fabric, one that already
has data and relationships. {{PRODUCT}}, used from Claude, plans that item from your tables and creates it. Lovable
then connects to it like any other API for GraphQL item.

{{PRODUCT}} and Lovable do not talk to each other. {{PRODUCT}} builds the item in your Fabric workspace; Lovable's own
connector reads it.

## Steps

1. **Create the API with {{PRODUCT}}.** In Claude, with the {{PRODUCT}} connector added ([get started](/start)), ask
   for a plan first, for example *"Plan a backend over the shop lakehouse"*. Nothing is deployed by a plan; check the
   keys and relationships and the rule behind each. Then say *"Create it as shop_api"*. {{PRODUCT}} creates one API for
   GraphQL item with nested relationships, or updates it if the name exists.
2. **Turn on introspection in Fabric.** Fabric creates the item with introspection off, and Lovable's connection test
   needs it. A workspace admin turns it on in the item's API settings. Fabric has no API for this yet, so
   {{PRODUCT}} cannot do it for you.
3. **Let Lovable's service principal query the item.** Lovable connects with a Microsoft Entra service principal
   (an app registration with a client secret), not with your own sign-in. Grant that principal *Run Queries and
   Mutations* on the item, and make sure your tenant allows service principals to call Fabric public APIs. This is
   the second manual portal step.
4. **Add it in Lovable's Fabric connector.** In Lovable, open Connectors, choose Microsoft Fabric and add a connection
   with the tenant ID, client ID, client secret and the item's endpoint URL (it ends in `/graphql`). Lovable runs an
   introspection query to check the connection.

Lovable's own guide lists every prerequisite and limit: https://docs.lovable.dev/integrations/microsoft-fabric

## Good to know

- **Lakehouse sources are read-only** through the API for GraphQL; writes work on warehouses and SQL databases.
  {{PRODUCT}} creates read-only items unless you ask for a writable one.
- **What Lovable sees** is what the item exposes, under the service principal's permissions.
- **{{PRODUCT}} is not a Lovable connector.** Adding {{PRODUCT}} itself as a custom MCP connector in Lovable is
  untested and not supported here: {{PRODUCT}} signs you in with a Microsoft Entra work account, and Entra does not
  offer the dynamic client registration that flow would need. Use {{PRODUCT}} from Claude, Claude Code or Cursor, and
  Lovable's Fabric connector in Lovable.

## Next

[Get started](/start) · [Docs](/docs) · [Try the demo graph](/explore)
