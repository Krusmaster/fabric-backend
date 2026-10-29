# Privacy policy — {{PRODUCT}}

*Template. Replace {{PRODUCT}}, {{DOMAIN}}, {{CONTACT}} and publish at https://{{DOMAIN}}/privacy before submitting. The
Claude directory rejects a submission without a live privacy policy.*

{{PRODUCT}} is operated by Kruse Consulting AB, Sweden{{ORGNR_PAREN}}. This page explains what passes through the
service, how access tokens and technical logs are handled, and which other services are involved. Contact: {{CONTACT}}.

## What the service does

{{PRODUCT}} is a remote MCP server. When you use it from Claude (or another MCP client), it reads the metadata of the
Microsoft Fabric items you choose and infers keys and relationships. Only when you ask for it does it count or read
rows, run a read-only GraphQL query, or create or update an item in your Fabric workspace.

## Your Microsoft account

You sign in with your own Microsoft Entra work account. The service exchanges that sign-in for Microsoft Fabric and
Azure SQL access tokens on your behalf (OAuth 2.0 on-behalf-of). It acts as you, within two limits: the delegated
permissions your administrator granted (listed under [What it accesses](/docs#what-it-accesses): reading workspaces,
items and the SQL analytics endpoint, running your GraphQL queries, and creating or updating the API for GraphQL item
or the views you ask for), and what your own account may do in Fabric. It cannot reach anything your account cannot.
Your organization's administrator grants this once and can revoke it at any time in Microsoft Entra ID (Enterprise
applications). A summary for your IT department, with each permission in plain words, is at [/it](/it).

## Metadata, samples and query results

What the service reads from Fabric depends on the tool you ask for:

- **Metadata.** Workspace, item, table and column names and types, read to build the plan, a draft or the definition
  you asked for. Some tools also read the definitions of items in the workspace (GraphQL APIs, semantic models, data
  agents, views) to describe them or to show what builds on a table.
- **Checks against the rows.** `validate_plan`, `suggest_relationships` and `data_dictionary` with `validate=true` run
  counting queries in Fabric. Only the counts come back, not the row values.
- **Sample rows.** `sample_rows` returns up to 20 rows of one table, with long text shortened. Columns whose name looks
  like personal data (a person's name, e-mail, telephone, national identity number, address, birth date; one rule per
  pattern, judged by the column's name and never by its values) come back as `***` unless you ask with
  `show_personal_data=true`. `answer_query_draft` and the gold views leave those columns out the same way.
- **Sensitivity labels.** When Fabric returns a Microsoft Purview sensitivity label on the source item, it comes with
  the item's metadata as the label's id only; `sample_rows` and `validate_plan` name it. The service does not look the
  label up anywhere else.
- **A semantic model's definition.** `compare_semantic_model` reads the definition of the model you name (its tables,
  columns, measures and relationships; no rows), or the definition files you pass it.
- **Query results.** `query_graphql` returns the results of the query you ran.
- **What you create.** The creating tools write the definition you asked for into your Fabric workspace.
  `export_item_definitions` returns the same definitions as files and sends them nowhere: no call goes to GitHub, Azure
  DevOps or any other Git provider.

All of this passes through the service's memory on its way to your MCP client, in the response to your request, and
is then discarded. {{#IF NO_CLIENT_REGISTRATION}}The service has no database, no cache on disk and no file storage of its own.{{/IF}}{{#IF CLIENT_REGISTRATION}}Apart from the few sign-in records described under
*Sign-in from MCP clients other than Claude* below, the service has no database, no cache on disk and no file storage
of its own, and none of what Fabric returns is ever stored.{{/IF}} It counts how its
tools are used, anonymously: which tool, how the call ended and how long it took (see *Usage statistics* below), never
what you asked or what came back.

## Access tokens

Your access tokens are validated and exchanged in memory. They are never written to disk, never logged, and are
dropped shortly before they expire.
{{#IF CLIENT_REGISTRATION}}
When you sign in from an MCP client other than Claude, the service obtains the Microsoft tokens for that sign-in
itself and hands the access token to your client. Until your client collects them (at most 60 seconds) they are kept
encrypted; Microsoft's refresh token stays encrypted with the service for as long as your client keeps renewing its
access, at most 90 days, and is never given to the client. Details below.
{{/IF}}
## What we process

| Data | Why | Kept |
| --- | --- | --- |
| Your access tokens | to call Fabric and SQL as you | in memory only, until shortly before they expire; never written to disk or logs |
| Workspace, item, table and column names, and item definitions | to build the plan, the draft or the definition you asked for | only for the duration of the request |
| Counts from the checks, sample rows and query results you request | returned to your MCP client | not stored |
{{#IF CLIENT_REGISTRATION}}| Sign-in records for MCP clients other than Claude: a sign-in in progress (the client's address, its redirect address and its request); the Microsoft tokens of a finished sign-in, encrypted; Microsoft's refresh token, encrypted, with a hash of the refresh token your client holds | signing in from VS Code, Cursor and other MCP clients through {{DOMAIN}}/mcp/connect | in {{REGISTRATION_WHERE}}: 10 minutes, 60 seconds, and at most 90 days, each deleted once used |
| Your approval of an MCP client that receives the answer at a web address: a keyed hash of your user and organisation ids (not the ids themselves), the client's address, name and redirect address, and the date | not asking you again at every sign-in | the same place, 180 days |
| A cookie in your browser on {{DOMAIN}} with the same keyed hash, signed; and two short-lived cookies that protect the approval form and the sign-in | recognising your earlier approval; stopping forged approvals | 180 days, and 10 minutes, in your browser |
| The IP address of a sign-in request, as a salted hash | limits on sign-in attempts per network | in memory only, about an hour; never written anywhere |
{{/IF}}{{#IF RATE_LIMITS}}| Your user id and organisation id from the sign-in (`oid`, `tid`), as salted hashes | fair-use limits: how many calls per user and per organisation in the last minute and hour | in memory only, until about an hour after your last call; never written anywhere |
{{/IF}}| A usage record per tool call: the tool's name, the outcome (`ok` or the error kind), the duration, and for the creating tools whether it was a dry run{{#IF USAGE_ORG}}; plus a salted hash of your organisation's tenant id, so organisations can be counted{{/IF}} | counting use, errors and response times per tool | {{#IF LOGS_KEPT_DAYS}}in our Log Analytics workspace for {{LOGS_KEPT_DAYS}} days; totals in memory until the server restarts{{/IF}}{{#IF LOGS_NOT_KEPT}}not stored: the console stream only; totals in memory until the server restarts{{/IF}} |
| A page-view record when one of the pages `/`, `/check`, `/explore`, `/start` or `/partners` is served: the path and nothing else (no IP address, referrer, browser or query string); on `/check`, a record that the engine loaded and one that a check finished, without any file, file name, table or column name | counting visits to the site and how often /check is used | {{#IF LOGS_KEPT_DAYS}}in our Log Analytics workspace for {{LOGS_KEPT_DAYS}} days{{/IF}}{{#IF LOGS_NOT_KEPT}}not stored: the console stream only{{/IF}} |
{{#IF LOGS_NOT_KEPT}}| Technical console log: time, method, path, HTTP status and the connection's IP address — no headers, no tokens, no query text | operating and securing the service | not forwarded or stored by us; see *Technical logs* below |
{{/IF}}{{#IF LOGS_KEPT_DAYS}}| Technical console log: the usage records above, server errors and the platform's start/stop messages — no IP addresses, headers, tokens or query text | operating and securing the service | in our Log Analytics workspace for {{LOGS_KEPT_DAYS}} days; see *Technical logs* below |
{{/IF}}
We do not store your data, do not use it to train models, do not sell or share it, and do not combine it with other
data. Row values pass through the service only when you ask for sample rows or run a query, and only in the response
to you.

## Usage statistics

For each tool call the server records exactly these fields: `tool` (the tool's name), `outcome`
(`ok`, or the error kind such as `not_found` or `rate_limited`), `ms` (the duration) and, for the tools that create
something, `dry_run` (true or false){{#IF USAGE_ORG}}, and `org`: the first 16 characters of a SHA-256 hash of your
organisation's tenant id combined with a secret salt that stays on the server, which lets us count organisations without
writing the tenant id down{{/IF}}. Nothing else: no user id, no name or e-mail, no IP address, no workspace, item, table or
column names, no queries, no plans and no results. The record is one line on the server's console; the totals since the
server started are kept in memory and, when the operator turns it on, readable at a protected `/metrics` address.

The site writes one more kind of line: `path` when `/`, `/check`, `/explore`, `/start` or `/partners` is served, and on
`/check` a `step` that is either `loaded` (the engine started in your browser) or `done` (a check finished). `/check`
sends this as a request for an image whose address carries only that word; your files, their names and their tables and
columns stay in your browser.{{#IF LOGS_KEPT_DAYS}} Like the usage records, these lines are deleted after {{LOGS_KEPT_DAYS}} days.{{/IF}}

The start page can download `/check`'s engine (Pyodide and the engine, the same files `/check` loads) before you open `/check`, so that it
starts sooner: only when your pointer or keyboard focus reaches a link to `/check`, or when the page has been still for a
few seconds on a fast connection that has not asked to save data. These are ordinary requests for public files; they
carry nothing from you, write no usage record, and the files stay in your browser's cache.

## Technical logs

{{#IF LOGS_NOT_KEPT}}The server writes a technical access line per request to its console (time, method, path, HTTP status and
the connection's IP address; never headers, tokens or query text), the usage record above, and the hosting platform keeps its own system log
about starting and stopping containers. The service runs in Azure Container Apps in an environment created *without a
log destination*: console and system logs are not sent to Log Analytics or to any storage we control, and we keep no
copy. The operator can watch the live console stream of a running container; nothing persists beyond that.{{/IF}}{{#IF LOGS_KEPT_DAYS}}The
server's console (the usage records above, server errors, and the hosting platform's messages about starting and stopping
containers) is sent to a Log Analytics workspace of ours in the same Azure region and deleted after {{LOGS_KEPT_DAYS}} days.
The per-request access line with IP addresses is turned off, so no IP address is kept there. Only the operator can read
the workspace.{{/IF}} We do not claim "zero logs": Microsoft retains platform-level metrics and diagnostics for Azure
resources under Microsoft's own terms, and Microsoft Entra ID records sign-ins in your organization's own tenant.

{{#IF CLIENT_REGISTRATION}}## Sign-in from MCP clients other than Claude

Claude signs in directly with Microsoft. Other MCP clients (VS Code, Cursor, Glama and others) sign in through the
service's own sign-in at {{DOMAIN}}/oauth, in front of Microsoft. Before you are sent to Microsoft, {{PRODUCT}} shows a page
naming the client, its domain and where the answer goes, and asks you to approve it. For a client that receives the
answer at a web address, the approval is remembered for that client and that address for 180 days; for a program on
your own computer you are asked every time. To identify a client, the service fetches the client's published
metadata document from the client's own domain (for example vscode.dev); that request carries nothing about you.

What is stored, and for how long, is in the table above: no names, no e-mail addresses, no IP addresses and no
tokens in clear. The records live in {{REGISTRATION_WHERE}}, which only the service can read.
The cookies are strictly necessary for the sign-in and are not used for anything else. To withdraw an approval or
end a client's sign-in, write to {{CONTACT}}; your organisation's administrator can also revoke the app in Microsoft
Entra ID, which ends every renewal.

{{/IF}}## Third parties: Microsoft and your MCP client

The service runs on Microsoft Azure in the EU (Sweden Central). It calls Microsoft Fabric, Microsoft Entra ID and Azure
SQL on your behalf; Microsoft handles that under its own terms. Your MCP client receives the responses: when you use
the service from Claude, Anthropic's privacy policy covers what Claude does with them. The website loads no third-party
resources: fonts, scripts and images are served from {{DOMAIN}}, and there is no analytics or tracking.

## Contact and requests

**Your rights.** Under the GDPR you can ask what we hold about you and have it deleted; in practice we hold nothing
about you beyond the console log described above{{#IF CLIENT_REGISTRATION}} and, when you sign in from an MCP client other than Claude, the
sign-in records described above{{/IF}}, and the usage records carry no user id. Write to {{CONTACT}}. You can complain to the Swedish
Authority for Privacy Protection (IMY).

**Changes.** We date every change to this page. Last updated: 2026-10-28.
