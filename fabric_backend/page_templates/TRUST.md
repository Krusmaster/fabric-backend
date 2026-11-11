# Security and data

For a buyer's security, privacy and procurement team: what passes through {{PRODUCT}}, what is stored, where it runs,
the permissions it asks for, how to take them back, and what is and is not in place today. Written from the trust pack
in the repository ([docs/TRUST-PACK.md]({{GITHUB}}/blob/main/docs/TRUST-PACK.md)), where every statement names the file
that shows it.

**{{PRODUCT}} holds no certification.** There is no ISO 27001 certificate, no SOC 2 report and no penetration test yet.
Nothing on this page claims a certification, an audit or a partnership with Microsoft or anyone else. {{PRODUCT}} is
published by Kruse Consulting AB, Sweden, run by one person, and open source under the MIT licence: everything below
can be checked in the code.

## In short

- No table contents are stored. Names, counts and the sample rows or query results you ask for pass through the
  service's memory to your own tool and are not kept.
- Every call runs as the signed-in person, with that person's own Fabric rights (delegated permissions only).
- The hosted service runs in Microsoft Azure, Sweden Central (EU).
- Nothing is created in Fabric without a dry run first and your explicit go-ahead. No tool deletes anything.
- An administrator can revoke access in Microsoft Entra at any time.

## What passes through, and what is stored

{{PRODUCT}} reads workspace, lakehouse, schema, table and column names and data types, and the counts from the check
against your rows: rows, empty values, duplicates, references with no matching row. The check returns counts, never a
value. In {{PRODUCT}} for Claude (the MCP connector), when you ask, it also reads up to 20 sample rows of one table and
the results of read-only GraphQL queries; columns that look like personal data by name are masked unless you ask for
them.

| What | Where | What it holds | How long |
| --- | --- | --- | --- |
| Table contents | Nowhere | Nothing: rows and results pass through memory during the call | Not kept |
| The reviewed plan (Krusgraph for Fabric) | The Krusgraph Model item, in your own Fabric workspace | Accepted keys and relationships, the chosen source, the ids of items built. No token, no row value | Until you delete the item |
| Items {{PRODUCT}} builds | Your own Fabric workspace | Ordinary Fabric items (notebooks, views, pipeline, semantic model, report, API, ontology, data agent) | Until you delete them; {{PRODUCT}} never does |
| Access tokens | Server memory only | On-behalf-of tokens for Fabric and SQL | Until shortly before they expire; never written to disk or logs |
| Usage and route logs | Azure Log Analytics, Sweden Central, when switched on | Tool or route, outcome, duration. No user id, no IP address, no table contents, no item names | The configured retention (shown on [For your IT department](/it#stored)) |
| Sign-in records for MCP clients other than Claude | Azure Table Storage, Sweden Central, encrypted with {{PRODUCT}}'s own key | The sign-in in progress and Microsoft's tokens | 10 minutes for a sign-in; at most 90 days for a refresh token |

[Check my tables](/check) runs entirely in your browser: the files you drop are not uploaded.

## Where it runs

- Microsoft Azure, region Sweden Central (EU), one Azure Container App.
- Fabric public cloud. Customers in every Fabric region reach the same service in Sweden Central; names and counts are
  processed there in transit.
- What {{PRODUCT}} builds stays in your workspace, in your region.
- You can run the same open-source code in your own Azure subscription and region with one script, so that nothing
  passes through Kruse Consulting.

## Sub-processors

| Sub-processor | What | Where |
| --- | --- | --- |
| Microsoft (Azure) | Container Apps (the service), Log Analytics (logs, when switched on), Table Storage (MCP sign-in records), Key Vault, Container Registry | Sweden Central |

Microsoft Fabric is your own Microsoft service, not a sub-processor of {{PRODUCT}}. When you use {{PRODUCT}} from an
AI client such as Claude, the tools' answers go to that client and its AI provider (Anthropic for Claude) under your
own agreement with them: {{PRODUCT}} sends no data to an AI provider itself. Krusgraph for Fabric uses no AI model.

## Sign-in and delegated permissions

- Microsoft Entra ID only, with the person's own work account. No local accounts, no passwords.
- Delegated permissions only: {{PRODUCT}} exchanges the person's token on their behalf for a Fabric or SQL token, so it
  can reach nothing that person cannot reach. Neither Entra app has application permissions.
- Tokens are checked before anything runs: signature against Microsoft's keys, expiry, audience, issuer, the delegated
  scope and the tenant allow-list.
- No long-lived tokens for Krusgraph for Fabric. The one exception is on the MCP path: for MCP clients other than
  Claude, Microsoft's refresh token is kept encrypted for at most 90 days.

The permissions the Krusgraph app asks for, and why each one, are listed on
[For your IT department](/it#permissions); per tool, with the Fabric REST operation behind each, in
[docs/SCOPES.md]({{GITHUB}}/blob/main/docs/SCOPES.md). The Fabric workload's permissions are in the
[trust pack]({{GITHUB}}/blob/main/docs/TRUST-PACK.md) (section 5).

## How to revoke access

| Step | Who | Effect |
| --- | --- | --- |
| Remove admin consent, or delete the app (Entra admin centre → Enterprise applications → the Krusgraph app) | Your Entra admin | No new tokens; a token already issued expires within 60 to 90 minutes |
| Disconnect the connector | The person | Their AI client stops calling {{PRODUCT}} |
| Delete the Krusgraph Model items and anything {{PRODUCT}} built | A user or workspace admin | Removes the stored plan and the items; {{PRODUCT}} never deletes them itself |
| Turn off the tenant setting for additional workloads | Your Fabric admin | The workload is hidden |
| Ask us to remove your tenant from the allow-list | Kruse Consulting AB | The engine stops answering your tenant at once |

## What is and is not in place

| Item | Status today |
| --- | --- |
| ISO/IEC 27001 | Not held. A self-assessment against the Annex A controls exists; it is not a certification |
| SOC 2 | Not held |
| Penetration test or independent security assessment | Not done |
| Fabric workload vendor attestation (Krusgraph.Modeler) | Draft: written, not signed, not accepted by Microsoft |
| Fabric workload name Krusgraph.Modeler | Not registered yet |
| Entra publisher verification, Krusgraph app (MCP) | Verified publisher Kruse Consulting AB, as shown on [For your IT department](/it#verified-publisher); it confirms who publishes the app, not its security |
| Entra publisher verification, workload app | Not yet |
| Privacy review | Not done |
| Conditional Access | Not tested |
| Data processing agreement | A project draft exists; the legal text is to be written with a lawyer |
| Business continuity and disaster recovery plan | Not written; no RTO or RPO |
| Service level agreement | None. Support by email, best effort, one person |

## Answers to a standard security questionnaire

Today = in place. Planned = written down as a step, not done. Open = not stated here yet; ask us and we answer in
writing.

| # | Question | Status | Answer |
| --- | --- | --- | --- |
| 1 | How do users authenticate? | Today | Microsoft Entra ID only, the person's own work account. No local accounts, no passwords |
| 2 | Is MFA supported or enforced? | Today | Enforced by your own Entra policies at sign-in; {{PRODUCT}} does not weaken them |
| 3 | Conditional Access? | Planned | Not tested yet |
| 4 | Least privilege, role-based access? | Today | Delegated permissions only; every call runs with the person's own Fabric rights; creating needs the person's own role in the workspace |
| 5 | Can access be revoked? | Today | Remove admin consent or delete the app in Entra; existing tokens expire within 60 to 90 minutes |
| 6 | Tenant isolation? | Today | Tokens are validated per tenant; the workload engine serves only allow-listed tenants; on-behalf-of tokens are cached per user, never shared |
| 7 | Encryption in transit? | Today | HTTPS only; plain HTTP is refused; HSTS; storage TLS 1.2 minimum |
| 8 | Encryption at rest? | Today, partly | No customer data is stored. MCP sign-in records are encrypted by the application with its own key. Azure's own encryption at rest for Storage and Log Analytics: Open |
| 9 | Key and secret management? | Today, partly | The client secret can live in Azure Key Vault, read by managed identity, and is never logged. Whether the live service uses Key Vault: Open |
| 10 | What customer data do you store? | Today | None from tables. Metadata and counts pass through memory during a call; the item's state stays in your workspace |
| 11 | Do you use customer data to train AI models? | Not applicable | {{PRODUCT}} trains no model; Krusgraph for Fabric uses no AI model |
| 12 | Data location? | Today | Azure Sweden Central (EU) only |
| 13 | Data deletion on request or at contract end? | Today, partly | You delete your items yourself; we remove your tenant id from our lists; logs age out at the retention setting. Deleting log lines earlier on request: Open |
| 14 | Logging and monitoring? | Today, partly | Content-free usage and route logs and a health endpoint; alerting is written down but not yet switched on |
| 15 | Log retention? | Open | A setting from 30 to 730 days; the live value is on [For your IT department](/it#stored) |
| 16 | Backups? | Today, partly | Your state lives in your Fabric, not with us. The service is rebuilt from the public repository with one script |
| 17 | Business continuity and disaster recovery? | Planned | No written plan, RTO or RPO yet |
| 18 | Incident response? | Today, partly | A reporting address, a [disclosure policy](/security), security.txt and a written [incident process]({{GITHUB}}/blob/main/docs/INCIDENT-RESPONSE.md); the time to notify customers is a proposal, not yet confirmed |
| 19 | Breach notification to customers? | Open | To be set in the data processing agreement (channel and time limit) |
| 20 | Vulnerability management? | Today | Pinned dependencies, a weekly audit of them, Dependabot, an SBOM on every push |
| 21 | Penetration testing? | Planned | Not done |
| 22 | Secure development? | Today | Open source; automated tests on every push, including token validation; error text scrubbed of tokens |
| 23 | Who has access to production? | Open | One person maintains the service; Azure and Entra admin sign-in use Microsoft's mandatory MFA |
| 24 | Background checks, security training? | Not applicable | One-person company |
| 25 | Container and host hardening? | Today | Runs as an unprivileged user; request bodies capped; framing and CORS limited to Fabric and Power BI; no cookies |
| 26 | Rate limiting, abuse protection? | Today, partly | Per user and per tenant on MCP tool calls |
| 27 | Sub-processors? | Today | Microsoft Azure only, for the hosted service |
| 28 | Certifications? | Not held | No ISO 27001, no SOC 2, no other |
| 29 | Private Link, private networking? | Not applicable today | The service is on the public internet; you can run the MCP server in your own Azure instead |
| 30 | Change management? | Today | Every change is a commit on GitHub with tests in CI; versions in the changelog |

## For customers under NIS2 and the Swedish cybersecurity act

If your organisation is covered by NIS2 or the Swedish cybersecurity act (cybersäkerhetslagen, SFS 2025:1506), you
have to manage security in your supply chain and will ask {{PRODUCT}}, as a supplier, what is in place. Kruse
Consulting AB is a one-person company and probably not itself covered; {{PRODUCT}} holds no certification and no approval
from any authority, and this is not legal advice.

| Document | What it says | Status |
| --- | --- | --- |
| [Supplier security pack]({{GITHUB}}/blob/main/docs/SECURITY-SUPPLIER.md) | What {{PRODUCT}} is in your supply chain, roles (you are information owner of your data; Kruse Consulting AB is system owner of the hosted service), what is and is not in place, subcontractors, and a table against the Article 21 measures | Written; the legal sources are to be re-read against the primary texts before it is sent |
| [Incident response]({{GITHUB}}/blob/main/docs/INCIDENT-RESPONSE.md) | How an incident is detected, assessed, contained and told to affected customers, and what the notice contains | Written; the notification time is a proposal, not yet confirmed |
| [Vulnerability disclosure policy](/security) and [security.txt](/.well-known/security.txt) | How to report a security problem | In place |

Not in place yet: a signed data processing agreement, an external penetration test, a service level agreement and any
certification.

## Reporting a security issue

Write to [{{CONTACT}}](mailto:{{CONTACT}}); the rules are in the [vulnerability disclosure policy](/security) and in
[SECURITY.md]({{GITHUB}}/blob/main/SECURITY.md). See also
the [privacy policy](/privacy) and [For your IT department](/it).
