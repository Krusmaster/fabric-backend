# Incident response for Krusgraph

Round n211, 11 November 2026. A short, realistic process for a one-person supplier: Kruse Consulting AB runs the
hosted Krusgraph service (`https://krusgraph.com`, `https://workload.krusgraph.com`) and has one person who does
everything. It is written so that a customer under NIS2 or the Swedish cybersecurity act can see what to expect from
Krusgraph when something goes wrong, and so that the founder knows what to do on the day.

**Status: a proposal.** The notification target in section 4 is **not a promise** until the founder confirms it and it
is written into the customer agreement or DPA. Nothing here is legal advice. Why customers ask:
`docs/SECURITY-SUPPLIER.md` §1.

Scope: the hosted service and the workload engine that Kruse Consulting AB runs. A customer's self-hosted
installation is the customer's own system; for it, Krusgraph's part is fixing vulnerabilities in the code and saying so
(`SECURITY.md`, `/security`).

## 1. Detect

Where an incident can come from, and what exists today:

| Source | What | Status today |
| --- | --- | --- |
| Reports | A vulnerability report to `gustav@krusgraph.com` (`SECURITY.md`, `/.well-known/security.txt`); a customer telling us | In place |
| Alerts | Two Azure Monitor alerts to one email address: the server answers 5xx, and `/health` fails from two of three locations (`docs/OPERATIONS.md` §4) | **Written, not yet switched on** (`docs/SECURITY.md`, open question 11) |
| Logs | Content-free route and usage lines in Log Analytics (no token, body, table contents, item names, user id or IP) (`docs/TRUST-PACK.md` §2) | When Log Analytics is switched on; retention on `/it` |
| Dependencies | Weekly `pip-audit`, Dependabot pull requests, GitHub security advisories (`.github/workflows/audit.yml`, `.github/dependabot.yml`) | In place |
| Microsoft | Azure Service Health, Microsoft Entra and Fabric notices to the subscription and tenant owner | Depends on the founder's notification settings in Azure; **to confirm** |

What the logs can and cannot show: since they carry no content by design, they show *that* a route was called, its
outcome and duration, not *what* data passed. That limits both what an attacker could take from them and what an
investigation can reconstruct.

## 2. Assess

Write down the time you became aware (UTC). That is the moment customers' own clocks may depend on.

Then answer, in a short note kept with the incident:

1. **What happened**, as far as known: a vulnerability reported, an exploit seen, an outage, a leaked secret, a
   compromised dependency, a problem at Microsoft.
2. **Is it real?** Reproduce safely, against Krusgraph's own tenant only.
3. **What could be affected**: confidentiality (tokens, the MCP sign-in records, metadata or sample rows passing
   through), integrity (items Krusgraph creates in a customer's workspace), availability (the service is down).
4. **Which customers**: all tenants, the workload tenants on the allow-list, MCP users, or none. Usage lines carry
   at most a salted hash of the tenant id, so "which tenants" may only be answerable as "all who used it in the window".
5. **Severity**, simply:
   - **High**: a customer's data, tokens or Fabric items may have been reached by someone else, or Krusgraph may have
     created or changed something the person did not choose. Notify (section 4).
   - **Medium**: a vulnerability that could have allowed that but there is no sign it was used; or an outage longer than
     a working day. Notify the customers concerned, with what is known.
   - **Low**: no customer impact (a fixed bug, a short outage). Record it; mention it in the changelog.

When unsure, treat it as the higher level.

## 3. Contain

The switches that exist today, from the narrowest to the widest. All are in the founder's hands; commands are in
`docs/OPERATIONS.md` and `docs/WORKLOAD-PUBLISH.md`.

| Switch | Effect | How |
| --- | --- | --- |
| Remove one tenant from the workload allow-list | The engine stops answering that tenant at once | `workload_allowed_tenants` in `deploy/krusgraph.json`, then `bash deploy/krusgraph.sh --update` (`docs/WORKLOAD-PUBLISH.md`, "Withdrawing a pilot") |
| Turn off sign-in for MCP clients other than Claude | `/mcp/connect` and its refresh tokens stop | `KRUSGRAPH_CLIENT_REGISTRATION=0` (`docs/OPERATIONS.md` §6) |
| Rotate the registration key | Every stored MCP sign-in record becomes unreadable; those users sign in again | Replace `KRUSGRAPH_REGISTRATION_KEY` (or its Key Vault secret); a new key ends the stored sign-ins (`docs/CLIENT-REGISTRATION.md`) |
| Rotate the Entra client secret | A leaked secret stops working | Entra → App registrations → Certificates & secrets; update Key Vault or the setting (`docs/OPERATIONS.md` §2) |
| Unpublish the workload | Fabric hides the workload | Fabric's Publish tab (`docs/WORKLOAD-PUBLISH.md`) |
| Take the service off the internet | Nothing answers; customers' own Fabric items keep running | `az containerapp ingress disable -n $APP -g $RG` (enable again with `ingress enable`) |
| Roll back | Run the previous code | Check out the last good commit of `main` and run `bash deploy/krusgraph.sh --update` (`docs/OPERATIONS.md` §0); no version has been tagged yet (§7) |

A customer can always act on its own side as well: remove admin consent or delete the app in Entra; tokens already
issued expire within 60 to 90 minutes (`docs/TRUST-PACK.md` §8). Say so in the notice when it helps.

Keep evidence before changing things where you can: export the relevant Log Analytics lines and the Container App's
revision list and activity log, and note the time of each action.

## 4. Notify affected customers

**Proposal for the founder to confirm:** a first notice to each affected customer **without undue delay, and within
24 hours** of becoming aware that the customer is or may be affected, at **High** or **Medium**; the aim is the same
working day. Then an update when something material changes, and a closing note when the incident is over.

Why this target: a covered customer may itself have to send an early warning to its authority within 24 hours of
becoming aware of a significant incident (NIS2 Article 23; MCFFS 2026:8 in Sweden). Krusgraph cannot decide whether an
incident is significant *for the customer*; the notice gives the customer what it needs to decide quickly. The founder
should only confirm a number that can be met alone, including weekends and holidays; if not, name a deputy or say
"next working day" honestly.

Channel: email from the founder's address to the contact the customer gave (pilot onboarding or the contract), and
the customer's Entra or Fabric admin where known. For a widespread problem, also a line on the site.

What the notice contains:

1. That this is a security incident notice from Kruse Consulting AB about Krusgraph, and a reference number.
2. When it started (if known) and when Kruse Consulting AB became aware, in UTC.
3. What happened, in plain words, and what is not yet known.
4. What may be affected for this customer: which service (workload, MCP), which kind of information (tokens,
   metadata, counts, sample rows, items created), and the time window.
5. What Krusgraph has done (containment) and what it will do next.
6. What the customer can do now (for example remove consent in Entra, check items created in the window).
7. Whether personal data may be involved, for the customer's own GDPR assessment.
8. When the next update will come, and the contact: the founder, `gustav@krusgraph.com`.

Do not wait for a full picture to send the first notice; say what is not known.

GDPR: where Kruse Consulting AB is processor and a personal data breach is involved, the DPA's breach clause
(`docs/DPA-DRAFT.md` §5, item 5) applies on top of this; the customer, as controller, decides about notifying the
supervisory authority.

## 5. After the incident

Within two weeks, a short written review (blameless): timeline, cause, what worked, what did not, and the changes
made. Fixes go in as ordinary commits with tests; `CHANGELOG.md` records the fix and credits the reporter if they wish.
Send the affected customers a short final note with the outcome, so they can complete their own final report (NIS2:
one month after their notification). Update `docs/RISK-REGISTER.md` and, if a row changed, `docs/TRUST-PACK.md`.

## 6. What the founder must decide

1. **The notification target** in section 4: confirm it, or change it to one that can be met alone.
2. **The security contact address**: keep `gustav@krusgraph.com`, or add a role address such as
   `security@krusgraph.com`.
3. **Switch on the alerts and Log Analytics** (`docs/OPERATIONS.md` §4), so incidents are detected by more than
   reports.
4. **A deputy** or a fallback for when the founder is unavailable (`docs/OPERATIONS.md` §9), or say plainly that there
   is none.
5. **The DPA breach clause** (channel and time limit), with a lawyer, consistent with section 4.
6. Turn on Azure Service Health notifications to the founder's address.
