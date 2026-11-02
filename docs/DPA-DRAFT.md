# Data processing agreement: a draft template

**Status: draft. This is not legal advice.** It is a starting point for a data processing agreement between a customer
and Kruse Consulting AB for the hosted service at krusgraph.com, written by the project on 2 November 2026 from what
the code and the privacy policy say the service does. Before it is signed, a lawyer for each side reads it; the
brackets are what they fill in. The pricing page says a data processing agreement is available on request
(`fabric_backend/page_templates/pricing.html`); this is what "on request" means today.

Whether Krusgraph is a processor at all for a given customer is itself a question for that review: the service holds
no table contents, and what passes through it does so on the signed-in person's behalf, for the duration of a call. The
AI client the person uses (Claude, VS Code, Cursor, Glama, Lovable or another) is the customer's own vendor and is not
covered by this agreement.

## 1. Parties

- Controller: [customer's legal name, registration number, address].
- Processor: Kruse Consulting AB, [registration number], [address], Sweden.

## 2. Subject matter and duration

The processor provides the hosted Krusgraph service (the MCP server at `https://krusgraph.com/mcp` and
`https://krusgraph.com/mcp/connect`) to persons in the controller's Microsoft Entra tenant, for as long as the
controller's administrator consent for the Krusgraph app stands or until either party ends the service agreement.

## 3. Nature and purpose of the processing

On a signed-in person's request, the service reads metadata and, when asked, sample rows and query results from the
controller's Microsoft Fabric tenant, with that person's own permissions, and returns the result to the MCP client the
person connected. It infers keys and relationships, checks them against the rows, drafts files and, when the person asks
with `dry_run=false`, creates or updates items in the controller's Fabric workspace. Nothing is kept after the request
(source: `SECURITY.md`, `PRIVACY.md`).

## 4. Types of personal data and categories of data subjects

| Record | Personal data in it | Data subjects | Kept | Source |
| --- | --- | --- | --- | --- |
| Metadata, counts, sample rows and query results passing through a tool call | whatever the controller's tables hold; columns that look like personal data by name are masked unless the person asks (`show_personal_data=true`) | the persons in the controller's tables | not kept after the request | `fabric_backend/privacy.py`, `PRIVACY.md` |
| The signed-in person's access token and the tokens exchanged on their behalf | the person's identity claims (object id, tenant id, name, e-mail as Entra issues them) | the controller's users | in memory until shortly before expiry; never written | `fabric_backend/entra.py`, `docs/SECURITY.md` |
| Rate-limit counters | salted SHA-256 hashes of the user's object id and the tenant id | the controller's users | in memory, per replica | `fabric_backend/limits.py` |
| Usage record per tool call | none about the person; optionally a salted hash of the tenant id | — | as the log retention setting says (30 to 730 days) or not stored | `fabric_backend/usage.py`, `deploy/azure_containerapp.py` |
| Sign-in records for MCP clients other than Claude | the client's address, the Microsoft tokens of the sign-in (encrypted), Microsoft's refresh token (encrypted) | the controller's users who sign in from such a client | 10 minutes, 60 seconds, at most 90 days; deleted once used | `fabric_backend/registration_store.py`, `PRIVACY.md` |

The controller's Fabric tenant and the controller's own Entra sign-in logs are the controller's; the processor holds no
copy.

## 5. Obligations of the processor

1. Process personal data only on the controller's documented instructions, which are the tool calls the controller's
   signed-in persons make and this agreement.
2. Keep the measures in section 7 and tell the controller before changing them in a way that lowers protection.
3. Engage no other subprocessor than those in section 6 without telling the controller [notice period], and pass the
   same obligations on.
4. Help the controller answer data subjects' requests to the extent the processor holds anything, which for the records
   in section 4 is at most the sign-in records for MCP clients other than Claude, deletable on request.
5. Tell the controller without undue delay of a personal data breach it becomes aware of, with what is known at the
   time, through [contact address]; the processor's own reporting channel is in `SECURITY.md`.
6. Delete the records in section 4 that it still holds at the end of the agreement; there is nothing to return.
7. Make available the information needed to show compliance: this agreement, `docs/TRUST.md`,
   `docs/ISO27001-SELF-ASSESSMENT.md`, `docs/SECURITY.md`, and the open-source code itself (MIT), and allow an audit
   on [notice] within [scope]; the processor is one person and has no certification (see section 7).

## 6. Subprocessors

| Subprocessor | What | Where |
| --- | --- | --- |
| Microsoft (Azure) | Container Apps running the service; Log Analytics for usage records and console log when switched on; Table Storage for the sign-in records of MCP clients other than Claude; Key Vault for the client secret when switched on; Container Registry for the image | Sweden Central |

The AI client the person uses is the controller's own vendor and not a subprocessor under this agreement. Microsoft
Fabric is the controller's own Microsoft service.

## 7. Technical and organisational measures

What exists, with its source in the repository, is in `docs/TRUST.md`; what is in place, partly in place or missing
against ISO/IEC 27001:2022 Annex A is in `docs/ISO27001-SELF-ASSESSMENT.md`. In short: no table contents stored;
delegated permissions only; tokens in memory; encrypted sign-in records with their own key and retention; TLS; a
reviewed and tested sign-in layer; pinned dependencies with a weekly vulnerability audit and an SBOM; one region.
The processor holds no ISO 27001 or SOC 2 certification.

## 8. Transfers

Processing takes place in Azure, region Sweden Central. Microsoft's own terms govern any transfer Microsoft makes as a
platform provider; the processor does not transfer personal data elsewhere.

## 9. Term, changes and law

[Term, how changes are agreed, governing law and venue: for the lawyers.]

Signatures: [controller] [processor]
