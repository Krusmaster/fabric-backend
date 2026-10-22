# Privacy policy — {{PRODUCT}}

*Template. Replace {{PRODUCT}}, {{DOMAIN}}, {{CONTACT}} and publish at https://{{DOMAIN}}/privacy before submitting. The
Claude directory rejects a submission without a live privacy policy.*

**Who we are.** {{PRODUCT}} is operated by Kruse Consulting AB, Sweden (org. nr {{ORGNR}}). Contact: {{CONTACT}}.

**What the service does.** {{PRODUCT}} is a remote MCP server. When you use it from Claude (or another MCP client) it
reads the table and column names of Microsoft Fabric items you choose, infers keys and relationships, and — only when
you ask it to — creates or updates an API for GraphQL item in your Fabric workspace and runs read-only GraphQL queries
against it.

**Whose permissions.** You sign in with your own Microsoft Entra work account. The service exchanges that sign-in for
Microsoft Fabric and Azure SQL access tokens on your behalf (OAuth 2.0 on-behalf-of). It can see and change exactly what
your own account can, and nothing else. Your organization's administrator grants this once and can revoke it at any
time in Microsoft Entra ID (Enterprise applications).

**What we process.**

| Data | Why | Kept |
| --- | --- | --- |
| Your access tokens | to call Fabric and SQL as you | in memory only, until shortly before they expire; never written to disk or logs |
| Workspace, item, table and column names | to build the plan and the GraphQL definition you asked for | only for the duration of the request |
| Query results you request | returned to your MCP client | not stored |
| Technical request logs: time, path, HTTP status — no headers, no tokens, no query text | operating and securing the service | 30 days (Azure Log Analytics) |

We do not store your data, do not use it to train models, do not sell or share it, and do not combine it with other
data. Row-level data passes through the service only when you run a query, and only in the response to you.

**Third parties.** The service runs on Microsoft Azure in the EU (Sweden Central). It calls Microsoft Fabric, Microsoft
Entra ID and Azure SQL on your behalf. When you use it from Claude, Anthropic's privacy policy covers what Claude does
with the responses.

**Your rights.** Under the GDPR you can ask what we hold about you and have it deleted; in practice the request logs
above hold no personal data beyond your connection's IP address. Write to {{CONTACT}}. You can complain to the Swedish Authority for Privacy Protection (IMY).

**Changes.** We date every change to this page. Last updated: {{DATE}}.
