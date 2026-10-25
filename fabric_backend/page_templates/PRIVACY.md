# Privacy policy — {{PRODUCT}}

*Template. Replace {{PRODUCT}}, {{DOMAIN}}, {{CONTACT}} and publish at https://{{DOMAIN}}/privacy before submitting. The
Claude directory rejects a submission without a live privacy policy.*

**Who we are.** {{PRODUCT}} is operated by Kruse Consulting AB, Sweden{{ORGNR_PAREN}}. Contact: {{CONTACT}}.

**What the service does.** {{PRODUCT}} is a remote MCP server. When you use it from Claude (or another MCP client) it
reads the table and column names of Microsoft Fabric items you choose, infers keys and relationships, and — only when
you ask it to — creates or updates an API for GraphQL item in your Fabric workspace and runs read-only GraphQL queries
against it.

**Whose permissions.** You sign in with your own Microsoft Entra work account. The service exchanges that sign-in for
Microsoft Fabric and Azure SQL access tokens on your behalf (OAuth 2.0 on-behalf-of). It can see and change exactly what
your own account can, and nothing else. Your organization's administrator grants this once and can revoke it at any
time in Microsoft Entra ID (Enterprise applications).

**The data path.** Everything the service handles passes through its memory and nowhere else:

- Your access tokens are validated and exchanged in memory. They are never written to disk, never logged, and are
  dropped shortly before they expire.
- Workspace, item, table and column names are read from Fabric to build the plan or the GraphQL definition you asked
  for, returned to your MCP client, and then discarded.
- When you run a query, the rows you asked for travel from Fabric through the service to your MCP client in that one
  response. They are not kept.
- The service has no database, no cache on disk and no file storage of its own.

**What we process.**

| Data | Why | Kept |
| --- | --- | --- |
| Your access tokens | to call Fabric and SQL as you | in memory only, until shortly before they expire; never written to disk or logs |
| Workspace, item, table and column names | to build the plan and the GraphQL definition you asked for | only for the duration of the request |
| Query results you request | returned to your MCP client | not stored |
| Technical console log: time, method, path, HTTP status and the connection's IP address — no headers, no tokens, no query text | operating and securing the service | not forwarded or stored by us; see *Logs* below |

We do not store your data, do not use it to train models, do not sell or share it, and do not combine it with other
data. Row-level data passes through the service only when you run a query, and only in the response to you.

**Logs.** The server writes a technical access line per request to its console (time, method, path, HTTP status and
the connection's IP address; never headers, tokens or query text), and the hosting platform keeps its own system log
about starting and stopping containers. The service runs in Azure Container Apps in an environment created *without a
log destination*: console and system logs are not sent to Log Analytics or to any storage we control, and we keep no
copy. The operator can watch the live console stream of a running container; nothing persists beyond that. We do not
claim "zero logs": Microsoft retains platform-level metrics and diagnostics for Azure resources under Microsoft's own
terms, and Microsoft Entra ID records sign-ins in your organization's own tenant.

**Third parties.** The service runs on Microsoft Azure in the EU (Sweden Central). It calls Microsoft Fabric, Microsoft
Entra ID and Azure SQL on your behalf. When you use it from Claude, Anthropic's privacy policy covers what Claude does
with the responses. The website loads no third-party resources: fonts, scripts and images are served from {{DOMAIN}},
and there is no analytics or tracking.

**Your rights.** Under the GDPR you can ask what we hold about you and have it deleted; in practice we hold nothing
about you beyond the live console stream described above. Write to {{CONTACT}}. You can complain to the Swedish
Authority for Privacy Protection (IMY).

**Changes.** We date every change to this page. Last updated: 2026-10-25.
