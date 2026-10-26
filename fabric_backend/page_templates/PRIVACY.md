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
- It counts how its tools are used, anonymously: which tool, how the call ended and how long it took (see *Usage
  statistics* below). Never what you asked or what came back.

**What we process.**

| Data | Why | Kept |
| --- | --- | --- |
| Your access tokens | to call Fabric and SQL as you | in memory only, until shortly before they expire; never written to disk or logs |
| Workspace, item, table and column names | to build the plan and the GraphQL definition you asked for | only for the duration of the request |
| Query results you request | returned to your MCP client | not stored |
{{#IF RATE_LIMITS}}| Your user id and organisation id from the sign-in (`oid`, `tid`), as salted hashes | fair-use limits: how many calls per user and per organisation in the last minute and hour | in memory only, at most an hour; never written anywhere |
{{/IF}}| A usage record per tool call: the tool's name, the outcome (`ok` or the error kind), the duration, and for the creating tools whether it was a dry run{{#IF USAGE_ORG}}; plus a salted hash of your organisation's tenant id, so organisations can be counted{{/IF}} | counting use, errors and response times per tool | {{#IF LOGS_KEPT_DAYS}}in our Log Analytics workspace for {{LOGS_KEPT_DAYS}} days; totals in memory until the server restarts{{/IF}}{{#IF LOGS_NOT_KEPT}}not stored: the console stream only; totals in memory until the server restarts{{/IF}} |
{{#IF LOGS_NOT_KEPT}}| Technical console log: time, method, path, HTTP status and the connection's IP address — no headers, no tokens, no query text | operating and securing the service | not forwarded or stored by us; see *Logs* below |
{{/IF}}{{#IF LOGS_KEPT_DAYS}}| Technical console log: the usage records above, server errors and the platform's start/stop messages — no IP addresses, headers, tokens or query text | operating and securing the service | in our Log Analytics workspace for {{LOGS_KEPT_DAYS}} days; see *Logs* below |
{{/IF}}
We do not store your data, do not use it to train models, do not sell or share it, and do not combine it with other
data. Row-level data passes through the service only when you run a query, and only in the response to you.

**Usage statistics.** For each tool call the server records exactly these fields: `tool` (the tool's name), `outcome`
(`ok`, or the error kind such as `not_found` or `rate_limited`), `ms` (the duration) and, for the tools that create
something, `dry_run` (true or false){{#IF USAGE_ORG}}, and `org`: the first 16 characters of a SHA-256 hash of your
organisation's tenant id combined with a secret salt that stays on the server, which lets us count organisations without
writing the tenant id down{{/IF}}. Nothing else: no user id, no name or e-mail, no IP address, no workspace, item, table or
column names, no queries, no plans and no results. The record is one line on the server's console; the totals since the
server started are kept in memory and, when the operator turns it on, readable at a protected `/metrics` address.

**Logs.**{{#IF LOGS_NOT_KEPT}} The server writes a technical access line per request to its console (time, method, path, HTTP status and
the connection's IP address; never headers, tokens or query text), the usage record above, and the hosting platform keeps its own system log
about starting and stopping containers. The service runs in Azure Container Apps in an environment created *without a
log destination*: console and system logs are not sent to Log Analytics or to any storage we control, and we keep no
copy. The operator can watch the live console stream of a running container; nothing persists beyond that.{{/IF}}{{#IF LOGS_KEPT_DAYS}} The
server's console (the usage records above, server errors, and the hosting platform's messages about starting and stopping
containers) is sent to a Log Analytics workspace of ours in the same Azure region and deleted after {{LOGS_KEPT_DAYS}} days.
The per-request access line with IP addresses is turned off, so no IP address is kept there. Only the operator can read
the workspace.{{/IF}} We do not claim "zero logs": Microsoft retains platform-level metrics and diagnostics for Azure
resources under Microsoft's own terms, and Microsoft Entra ID records sign-ins in your organization's own tenant.

**Third parties.** The service runs on Microsoft Azure in the EU (Sweden Central). It calls Microsoft Fabric, Microsoft
Entra ID and Azure SQL on your behalf. When you use it from Claude, Anthropic's privacy policy covers what Claude does
with the responses. The website loads no third-party resources: fonts, scripts and images are served from {{DOMAIN}},
and there is no analytics or tracking.

**Your rights.** Under the GDPR you can ask what we hold about you and have it deleted; in practice we hold nothing
about you beyond the console log described above, and the usage records carry no user id. Write to {{CONTACT}}. You can complain to the Swedish
Authority for Privacy Protection (IMY).

**Changes.** We date every change to this page. Last updated: 2026-10-26.
