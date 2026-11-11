# Krusgraph as a supplier: a security pack for customers under NIS2 and the Swedish cybersecurity act

Round n211, 11 November 2026. For a customer's security, procurement or compliance team that has to manage security in
its supply chain and is asking Kruse Consulting AB, as a supplier, what is in place. Written from the repository as it
stands; every statement names the file or page that shows it.

**What this document is not.** It is not legal advice and it does not say that Krusgraph, or a customer using it,
meets any law. Krusgraph is **not** certified, audited or approved by any authority, and nothing here claims
compliance with NIS2 or the Swedish act. It says what the public texts say, what a supplier is typically asked, and what Krusgraph has and does
not have today. Whether a customer is covered by the act, and what it must ask of its suppliers, is for the customer
and its own advisers to decide.

Companion documents: `docs/INCIDENT-RESPONSE.md` (what happens if something goes wrong),
`docs/TRUST-PACK.md` (the full trust pack and the 30 questionnaire answers), `/trust` on the site, `SECURITY.md` and
`/security` (how to report a vulnerability), `/.well-known/security.txt`.

## 1. What the texts say (sources)

Read on 11 November 2026. Several primary hosts could not be opened from the session this was written in; each such
line is marked **Unverified** with the host that must be allowed to check it. The founder or a reader should open the
primary text before relying on a line.

| # | Source | Status |
| --- | --- | --- |
| S1 | Directive (EU) 2022/2555 (NIS2), Official Journal L 333, 27.12.2022, `https://eur-lex.europa.eu/eli/dir/2022/2555/oj/eng` | **Unverified** in this session: `eur-lex.europa.eu` did not resolve. The article summaries below follow the published text as known to the author; check them against EUR-Lex |
| S2 | Cybersäkerhetslag (2025:1506), `https://www.riksdagen.se/sv/dokument-och-lagar/dokument/svensk-forfattningssamling/cybersakerhetslag-20251506_sfs-2025-1506/` | **Unverified**: `www.riksdagen.se` (and `lagen.nu`) did not resolve. Number and dates from search results that quote it |
| S3 | Cybersäkerhetsförordning (2025:1507) | **Unverified**, as S2 |
| S4 | MCFFS 2026:1 (registration and identification), MCFFS 2026:8 (incident reporting), MCFFS 2026:11 (security measures and management training), MCFFS 2026:12 (security audits and scanning), on `https://www.mcf.se` and `https://www.ncsc.se/sv/radgivning-och-stod/cybersakerhetslagen-nis2/reglering-av-cybersakerhetslagen/` | **Unverified**: `www.mcf.se`, `www.ncsc.se` did not resolve. Numbers, subjects and dates from search results that quote the PDFs |

**NIS2 (S1).**

- *Who is covered (Article 2, Annexes I and II).* Entities in the sectors of Annex I ("sectors of high criticality") and
  Annex II ("other critical sectors") that are at least a **medium-sized enterprise** under Article 2 of the Annex to
  Commission Recommendation 2003/361/EC, with exceptions that apply regardless of size. In that Recommendation a small
  enterprise has fewer than 50 staff and an annual turnover or balance sheet of at most EUR 10 million; anything above
  that is medium-sized or larger. Partner and linked enterprises count (a group's figures can bring a small subsidiary in).
- *Manufacturing is covered* (Annex II, point 5): medical devices and in vitro diagnostic medical devices; computer,
  electronic and optical products (NACE C26); electrical equipment (C27); machinery and equipment n.e.c. (C28); motor
  vehicles, trailers and semi-trailers (C29); other transport equipment (C30). Annex II also lists chemicals and the
  production, processing and distribution of food. A manufacturer of that kind with 50 or more staff is typically an
  "important entity".
- *Risk-management measures (Article 21).* Appropriate and proportionate technical, operational and organisational
  measures, on an all-hazards approach, including at least (a) risk analysis and information system security policies;
  (b) incident handling; (c) business continuity (backup, disaster recovery, crisis management); (d) **supply chain
  security**, including the security aspects of the relationship with each direct supplier or service provider;
  (e) security in acquisition, development and maintenance, including vulnerability handling and disclosure;
  (f) assessing the effectiveness of the measures; (g) basic cyber hygiene and training; (h) cryptography and
  encryption; (i) human resources security, access control and asset management; (j) multi-factor authentication,
  secured communications and secured emergency communications where appropriate. Article 21(3): for (d), the entity
  takes into account each direct supplier's specific vulnerabilities, the overall quality of its products and its
  cybersecurity practices, including secure development.
- *Management (Article 20).* The management body approves the measures, oversees them, can be held liable, and follows
  training.
- *Reporting (Article 23).* For a **significant incident**, to the CSIRT or competent authority: an **early warning
  without undue delay and within 24 hours** of becoming aware; an **incident notification within 72 hours** with an
  initial assessment; an intermediate report on request; a **final report within one month** of the notification (a
  progress report if the incident is still ongoing). Where appropriate, the entity also informs the recipients of its
  services.
- Member states had to transpose by 17 October 2024 (Article 41).

**Sweden (S2 to S4), Unverified as above.**

- NIS2 is implemented by the **cybersäkerhetslag (SFS 2025:1506)** and the **cybersäkerhetsförordning (SFS
  2025:1507)**, in force **15 January 2026**. The act replaces the 2018 act on information security for essential and
  digital services.
- The regulations (föreskrifter) were issued by **Myndigheten för civilt försvar (MCF)** as MCFFS: 2026:1 on
  registration (from 2 February 2026); 2026:8 on incident reporting (from 1 July 2026; early warning within 24 hours,
  final report one month after the notification or after the incident was handled); 2026:11 on security measures and
  management training (from **1 October 2026**); 2026:12 on security audits and scanning. Search results say the
  responsibility for these regulations moved to the **FRA's National Cyber Security Centre (NCSC)** on 1 July 2026,
  with the MCFFS numbers kept; that rests on secondary sources.
- On suppliers, secondary summaries of MCFFS 2026:11 say: before acquiring a system or outsourcing information
  processing, the entity assesses and handles the risks, makes sure the supplier meets the relevant cybersecurity
  requirements, and judges whether they can be met for the whole contract term; contracts signed before 1 October 2026
  are to be supplemented with cybersecurity requirements where possible; risks from subcontractors are handled too.
- **Roles.** The product owner's question named *informationsägare* and *systemägare*. These are established terms in
  Swedish information security practice; whether MCFFS 2026:11 uses them in its own text could not be checked here
  (**Unverified**). This pack uses them in their ordinary sense (section 3).

**Is Kruse Consulting AB itself covered?** Probably not, and this is for the founder to confirm with a lawyer: it is a
one-person company, far below the medium-sized threshold, and the categories that apply regardless of size (for
example trust services, DNS, top-level domain registries, public electronic communications) do not describe it. Its
customers can be covered, and then they ask Krusgraph the questions in this pack.

## 2. What Krusgraph is in a customer's supply chain

| Way of using it | What the customer depends on | Who runs it |
| --- | --- | --- |
| **Krusgraph for Fabric** (the workload, the item *Krusgraph Model* inside Microsoft Fabric), `https://workload.krusgraph.com` | A hosted engine called while a person has the item open; it reads metadata and counts and creates Fabric items the person chooses after a dry run | Kruse Consulting AB, on Microsoft Azure (Sweden Central) |
| **Krusgraph for Claude** (the hosted MCP server), `https://krusgraph.com/mcp` | A hosted service the person's own AI client calls with the person's delegated sign-in | Kruse Consulting AB, on Microsoft Azure (Sweden Central) |
| **Self-hosted** (the open-source code, MIT) | Software the customer deploys in its own Azure subscription with `deploy/krusgraph.sh` | The customer. Kruse Consulting AB runs nothing; it is the author of open-source software |

The workload and the hosted MCP server share one engine and one hosted service (`docs/TRUST-PACK.md` §1). What
Krusgraph builds (notebooks, views, pipeline, semantic model, report, API, ontology, data agent) are ordinary Fabric
items in the customer's own workspace and keep running without Krusgraph (`docs/LIFECYCLE-DESIGN.md` §0): if the
hosted service is down, the customer's pipelines and reports are not affected; only new reviews and Creates wait.

## 3. Roles

| Role | Who | What that means here |
| --- | --- | --- |
| Information owner (*informationsägare*) of the customer's data | **The customer** | It owns its tables, decides who may read them in Fabric, and decides whether to use Krusgraph at all |
| System owner (*systemägare*) of the hosted service and the workload | **Kruse Consulting AB** | It runs and changes the hosted service, decides its settings, and answers for its security |
| System owner of a self-hosted installation | **The customer** | Kruse Consulting AB supplies the code only |
| Security contact | **The founder of Kruse Consulting AB** (one person), by role | `gustav@krusgraph.com`, the address in `SECURITY.md` and `/.well-known/security.txt`. Whether to add a role address such as `security@krusgraph.com` is a founder decision (section 8) |
| GDPR roles (working position) | Customer controller, Kruse Consulting AB processor for the hosted service | `docs/DPA-DRAFT.md`; to be confirmed by each side's lawyer |

## 4. What is in place today

Each line names the file or page that shows it.

| Measure | What it is | Shown in |
| --- | --- | --- |
| Delegated permissions only | Every call runs as the signed-in person with that person's own Fabric rights (on-behalf-of); no application permissions | `fabric_backend/entra.py`, `docs/SCOPES.md`, `docs/TRUST-PACK.md` §4–5 |
| No table contents stored | Names and counts pass through memory; the check returns counts, never values; up to 20 sample rows and read-only query results on the MCP path only when the person asks, not kept | `SECURITY.md`, `docs/TRUST-PACK.md` §2, `/trust` |
| Content-free logs with a set retention | Route and usage lines with no token, body, table contents, item names, user id or IP; retention a setting of 30 to 730 days | `fabric_backend/usage.py`, `workload_api.py` (`log`), `deploy/azure_containerapp.py`; live value on `/it` |
| Revoke | The customer's Entra admin removes consent or deletes the app; Kruse Consulting AB removes the tenant from its allow-list and the engine stops answering at once | `docs/TRUST-PACK.md` §8, `docs/WORKLOAD-PUBLISH.md` ("Withdrawing a pilot") |
| Tenant allow-list | The workload engine answers only listed tenants | `fabric_backend/entra.py` |
| Hosting region | Microsoft Azure, Sweden Central (EU) | `deploy/krusgraph.example.json`, `deploy/azure_containerapp.py` |
| Open source | All code public under MIT; the customer can read it and run it itself | `LICENSE`, `deploy/KRUSGRAPH-START.md` |
| Dry run before writes | Every creating action is a dry run first, and nothing is created until the person goes ahead; no tool deletes anything in Fabric | `docs/TRUST.md` ("What the tools may change"), `docs/TRUST-PACK.md` §4 |
| Token validation | Signature, expiry, audience, issuer, scope and tenant checked before anything runs; tested | `docs/SECURITY.md`, `tests/test_security.py`, `tests/test_entra.py` |
| Encryption in transit | HTTPS only, HSTS, TLS 1.2 minimum on storage | `deploy/azure_containerapp.py` |
| Dependency and supply-chain hygiene of the code | Exact pins, weekly `pip-audit`, Dependabot, an SBOM on every push, rules for copying external code | `deploy/constraints.txt`, `.github/workflows/audit.yml`, `.github/workflows/sbom.yml`, `CONTRIBUTING.md` |
| Vulnerability disclosure | A reporting address, a disclosure policy and `security.txt` (RFC 9116) | `SECURITY.md`, `/security`, `/.well-known/security.txt` |
| Incident process | A written process for a one-person supplier; the notification target is still a proposal | `docs/INCIDENT-RESPONSE.md` |
| No AI by default | Krusgraph for Fabric uses no AI model | `fabric_backend/offering.py` (`NO_AI`) |

## 5. Subcontractors

| Subcontractor | For what | Where |
| --- | --- | --- |
| Microsoft (Azure) | Container Apps, Log Analytics (when switched on), Table Storage (MCP sign-in records), Key Vault, Container Registry | Sweden Central |
| The customer's own AI provider (for example Anthropic for Claude) | Only on the opt-in Claude path: the tools' answers go to the person's AI client. That provider is the **customer's** supplier under the customer's own agreement, not Krusgraph's subcontractor; Krusgraph sends no data to an AI provider itself | — |

Microsoft Fabric is the customer's own Microsoft service. GitHub hosts the source code and CI; it holds no customer
data. Source: `docs/TRUST-PACK.md` §7, `docs/TRUST.md`.

## 6. What is not in place yet

Said plainly, so a customer can weigh it:

- **No signed data processing agreement (DPA).** `docs/DPA-DRAFT.md` is a project draft, not legal text.
- **No external penetration test** or independent security assessment.
- **No service level agreement.** Support by email, best effort, one person.
- **No certification**: no ISO/IEC 27001, no SOC 2. A self-assessment against ISO 27001 Annex A exists
  (`docs/ISO27001-SELF-ASSESSMENT.md`); it is not a certification.
- **No written business continuity or disaster recovery plan**, no RTO or RPO. `docs/OPERATIONS.md` §9 says what someone
  else needs if the maintainer is unavailable.
- **Alerts and Log Analytics not yet switched on** on the live service (`docs/SECURITY.md`, open question 11).
- **One person.** No separation of duties, no deputy, no on-call rota.
- **Incident notification target not yet confirmed** (`docs/INCIDENT-RESPONSE.md`).

## 7. Article 21 measures and what Krusgraph has

Read as: what a covered customer typically asks a supplier about under each point, and the honest answer. "Has" means
something is in place for Krusgraph's own service; it does not say the customer's own obligation is met.

| Art. 21(2) | Has | Does not have yet |
| --- | --- | --- |
| (a) Risk analysis and information system security policies | A risk register (`docs/RISK-REGISTER.md`), a sign-in security review (`docs/SECURITY.md`), an ISO 27001 Annex A self-assessment | A formal, approved security policy document |
| (b) Incident handling | A reporting address, `security.txt`, a written process (`docs/INCIDENT-RESPONSE.md`) | A confirmed notification time; alerts switched on; a test of the process |
| (c) Business continuity, backup, disaster recovery | Customer state lives in the customer's Fabric; built items run without Krusgraph; the service rebuilds from the public repo with one script; `--backup` for the sign-in table | A written BC/DR plan with RTO/RPO; a backup run against the live subscription |
| (d) Supply chain security | Subcontractors listed (section 5); exact dependency pins, `pip-audit`, Dependabot, SBOM; this pack | Supplier assessment beyond Microsoft's own material; Dependabot for the editor's npm packages |
| (e) Secure acquisition, development, maintenance; vulnerability handling and disclosure | Open source, tests in CI on every push, token validation tested, error text scrubbed of tokens; disclosure policy and `security.txt` | External penetration test; a coordinated-disclosure time limit agreed with reporters |
| (f) Assessing effectiveness | Tests; the self-assessment; the trust pack kept true commit by commit | A periodic review or external audit |
| (g) Cyber hygiene and training | Delegated access, MFA through Entra, unprivileged container, request size caps | Training records (one-person company) |
| (h) Cryptography and encryption | HTTPS only, HSTS, TLS 1.2 minimum; MCP sign-in records encrypted with the application's own key; secrets in Key Vault when switched on | Written cryptography policy; confirmation of Azure's at-rest encryption for the live resources |
| (i) HR security, access control, asset management | Delegated permissions only, tenant allow-list, everything deployed as code | Named access review; asset inventory beyond the deploy script |
| (j) MFA, secured communications | Sign-in only through Microsoft Entra, under the customer's own MFA and policies; Azure and Entra admin under Microsoft's mandatory MFA | Conditional Access tested; a secured emergency channel beyond email and phone |

## 8. What the founder must decide

1. **Notification target** to customers after a confirmed incident (proposal in `docs/INCIDENT-RESPONSE.md` §4).
2. **Security contact address**: keep `gustav@krusgraph.com`, or add a role address such as `security@krusgraph.com`
   (then update `fabric_backend/discovery.py` `SECURITY_CONTACT`, `SECURITY.md` and its test together).
3. **DPA**: have a lawyer turn `docs/DPA-DRAFT.md` into a template, including the breach clause (channel and time limit).
4. Whether and when to buy an external penetration test.
5. Confirm with a lawyer that Kruse Consulting AB is not itself an entity under the act.

## 9. Keeping this true

When a file named here changes, the line changes in the same commit. Section 1 is re-read against the primary texts
(EUR-Lex, riksdagen.se, ncsc.se) before this pack is sent to a customer, and the date is updated.
