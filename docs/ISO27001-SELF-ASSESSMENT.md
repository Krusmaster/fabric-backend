# ISO/IEC 27001:2022 Annex A: a self-assessment, control by control

Krusgraph is not ISO 27001 certified, and this file does not make it so. It goes through the 93 controls of Annex A of
ISO/IEC 27001:2022 and says, for each, whether something in this repository answers it, with the file that shows it.
There is no score and no percentage: the point is to know which rows are empty. Written 2 November 2026 (round n76) by
reading the repository, not by an auditor and not against the live Azure subscription, whose configuration
(`deploy/krusgraph.json`) is not in the repository.

The context: one maintainer (Kruse Consulting AB), no employees, a hosted service in Azure that stores no table
contents, and an open-source repository changed by the maintainer and by coding agents under `CONTRIBUTING.md`.

Status words:

| Status | Swedish | Meaning |
| --- | --- | --- |
| in place | finns | something in the repository does what the control asks, and a test or a document shows it |
| partly | delvis | part of it exists; the row says what is missing |
| missing | saknas | nothing in the repository answers it |
| not applicable | ej relevant | the control is about something Krusgraph does not have (employees, premises, media) or that belongs to Microsoft's platform |

"Microsoft's" in a row means the control is met, if at all, by Azure as a platform; Microsoft's attestations are
Microsoft's (Microsoft Trust Center) and are not claimed here.

## A.5 Organizational controls

| Control | Title | Status | Where, and what is missing |
| --- | --- | --- | --- |
| 5.1 | Policies for information security | partly | `SECURITY.md` (reporting, what is stored, supported versions), `PRIVACY.md`, `CONTRIBUTING.md` (what never goes into the repository, what an agent must not do). No policy document that names itself as the information security policy, no review cycle. |
| 5.2 | Information security roles and responsibilities | partly | One maintainer is named in `SECURITY.md` and `CONTRIBUTING.md`; areas and owners per round in `CONTRIBUTING.md` ("Who works on what"); `docs/OPERATIONS.md` §9 says what a successor needs. No second named person. |
| 5.3 | Segregation of duties | missing | One person develops, reviews, deploys and operates. CI runs the tests on every push, but a person who can push can also deploy (`deploy/krusgraph.sh --update`). |
| 5.4 | Management responsibilities | partly | The maintainer is the management; the rules are written (`CONTRIBUTING.md`) and partly enforced by tests (`tests/test_site.py`, `tests/test_architecture.py`). |
| 5.5 | Contact with authorities | missing | No procedure for contact with a supervisory authority (for example on a personal-data breach). |
| 5.6 | Contact with special interest groups | missing | Vulnerability feeds arrive through Dependabot and `pip-audit` (`.github/dependabot.yml`, `.github/workflows/audit.yml`); no membership or contact beyond that. |
| 5.7 | Threat intelligence | partly | Weekly `pip-audit` of the image's pins and Dependabot alerts. Nothing beyond dependency advisories. |
| 5.8 | Information security in project management | partly | Every change follows `CONTRIBUTING.md` and the checklist in `.github/PULL_REQUEST_TEMPLATE.md`; the sign-in layer had a review (`docs/SECURITY.md`); the client-registration design is written against the MCP specification's requirements (`docs/CLIENT-REGISTRATION.md`). No security step required for every change. |
| 5.9 | Inventory of information and other associated assets | partly | Software: `deploy/constraints.txt`, the SBOM (`.github/workflows/sbom.yml`), `THIRD_PARTY_NOTICES.md`; Azure resources and secrets by name: `deploy/krusgraph.example.json`, `docs/OPERATIONS.md` §9 and `--doctor`; the environment variables the server reads: `docs/OPERATIONS.md` ("What the server reads from the environment"). No inventory of accounts, devices or the maintainer's own information. |
| 5.10 | Acceptable use of information and other associated assets | partly | `CONTRIBUTING.md`: no customer data, secrets or unbacked claims in the repository; no deployment or publishing by agents. Nothing about the use of the maintainer's own devices and accounts. |
| 5.11 | Return of assets | not applicable | No employees and no issued equipment. |
| 5.12 | Classification of information | partly | Customer data is classified by never being stored (`SECURITY.md`); columns that look like personal data are classified by rule P1–P6 (`fabric_backend/privacy.py`); a Fabric item's sensitivity label id is passed on (`docs/SCOPES.md`). No classification scheme for Krusgraph's own information (secrets, usage records, the registration store). |
| 5.13 | Labelling of information | partly | The sensitivity label id is read and named, never set (`docs/SCOPES.md`). No labelling of Krusgraph's own records. |
| 5.14 | Information transfer | partly | TLS with a managed certificate and HSTS on the hosted service (`docs/SECURITY.md` open question 10); nothing is sent by email; the tools' answers go only to the connected MCP client. No transfer agreement text beyond the privacy policy. |
| 5.15 | Access control | partly | Access to customer data is the person's own Fabric permissions through delegated scopes (`docs/SCOPES.md`); the MCP endpoint is behind the 401 guard (`fabric_backend/server.py`, `tests/test_security.py`); `/metrics` is bearer-only or a 404 (`fabric_backend/usage.py`). No written access-control rules for Azure, GitHub and the registrar; who has access is kept outside the repository (`docs/OPERATIONS.md` §9). |
| 5.16 | Identity management | partly | Users are identities in their own Entra tenant; the server adds none. For the maintainer's own identities nothing is written down. |
| 5.17 | Authentication information | partly | Secrets live as container-app secrets or in Key Vault, are never logged, and rotation is described (`docs/OPERATIONS.md` §2, §9; `fabric_backend/keyvault.py`; `test_tokens_and_secrets_never_reach_logs_or_stdout`). The reviewer account's set-up is documented (`deploy/SUBMISSION.md`). No password or MFA policy for the maintainer's accounts in the repository (Azure and Entra admin sign-in keep Microsoft's mandatory MFA, as `deploy/SUBMISSION.md` notes). |
| 5.18 | Access rights | partly | Revocation for customers is documented and needs nothing from Krusgraph (`fabric_backend/page_templates/it.html`); the roles a successor needs are listed (`docs/OPERATIONS.md` §9). No periodic review of the maintainer's own access rights. |
| 5.19 | Information security in supplier relationships | partly | Subprocessors are listed with what each holds (`docs/TRUST.md`). No supplier assessment beyond pointing at Microsoft's own material. |
| 5.20 | Addressing information security within supplier agreements | partly | Azure is used under Microsoft's standard terms; nothing negotiated. The AI client is the customer's own supplier (`docs/TRUST.md`). |
| 5.21 | Managing information security in the ICT supply chain | partly | Exact pins for the image (`deploy/constraints.txt`), weekly `pip-audit`, the SBOM, Dependabot for packages and Actions, licence notices generated from the pins (`THIRD_PARTY_NOTICES.md`), rules for copying code (`CONTRIBUTING.md`, "Reusing external code"). GitHub Actions are pinned by major version, not by commit; the vendored Pyodide bundle has recorded SHA-256 sums (`fabric_backend/static/pyodide/README.txt`) but no automated check of them. |
| 5.22 | Monitoring, review and change management of supplier services | partly | Dependency changes arrive as Dependabot pull requests merged after green CI (`CONTRIBUTING.md` table, Deployment area). No review of Azure's or Fabric's service changes beyond the preview notes (`docs/RISK-REGISTER.md` R7, `docs/ECOSYSTEM-WATCHLIST.md`). |
| 5.23 | Information security for use of cloud services | partly | One region, deployment as code, the resources and settings in `deploy/azure_containerapp.py`; a customer can run the code in their own subscription (`deploy/KRUSGRAPH-START.md`). No exit plan beyond that, no written cloud-use requirements. |
| 5.24 | Information security incident management planning and preparation | partly | How to report (`SECURITY.md`, `/.well-known/security.txt`); the one address that gets alerts (`docs/OPERATIONS.md` §4). No incident response plan with roles, steps and notification duties. |
| 5.25 | Assessment and decision on information security events | missing | No written criteria for what counts as an incident. |
| 5.26 | Response to information security incidents | partly | "Handled as soon as possible", fixes only in the latest version (`SECURITY.md`); the alert commands exist but have not been run (`docs/OPERATIONS.md` §4, `docs/SECURITY.md` open question 11). No runbook. |
| 5.27 | Learning from information security incidents | partly | `docs/SECURITY.md` records what the review found and fixed; `CHANGELOG.md` credits reporters. No incidents have occurred to learn from. |
| 5.28 | Collection of evidence | missing | Nothing on preserving logs or records after an incident; the usage lines carry no content by design, and console logs persist only when Log Analytics is on. |
| 5.29 | Information security during disruption | partly | `docs/OPERATIONS.md` §9 (continuity: access, configuration, where the secrets are, what cannot wait). Not rehearsed. |
| 5.30 | ICT readiness for business continuity | partly | The service can be rebuilt from the repository and `--from-azure` (`docs/OPERATIONS.md` §0, §9); `--backup` for the one table with state (§8.3); `min_replicas` in the configuration. None of §8 has been run against Azure; no recovery time stated. |
| 5.31 | Legal, statutory, regulatory and contractual requirements | partly | A privacy policy (`PRIVACY.md`), preview terms (`fabric_backend/page_templates/terms.html`), a DPA draft (`docs/DPA-DRAFT.md`), the MIT licence and third-party notices. None reviewed by a lawyer; the terms call themselves a short draft. |
| 5.32 | Intellectual property rights | in place | `LICENSE` (MIT), `THIRD_PARTY_NOTICES.md` generated from the pins and checked for staleness (`tools/third_party_notices.py --check`), licence files kept next to vendored assets (`fabric_backend/static/fonts/OFL-*.txt`, `fabric_backend/static/pyodide/README.txt`), and the rules for copying code in `CONTRIBUTING.md` ("Reusing external code"). |
| 5.33 | Protection of records | partly | Records are few by design: usage lines without content, retention by `log_retention_days` (`deploy/azure_containerapp.py`), the registration store with its own retention (`fabric_backend/registration_store.py`), git history for the code. No schedule for Krusgraph's own business records. |
| 5.34 | Privacy and protection of PII | partly | Personal-data columns masked by rule (`fabric_backend/privacy.py`, `tests/test_privacy.py`); a privacy page listing every record with purpose and retention, kept in step with the code by tests (`PRIVACY.md`, `tests/test_operations.py`); no user ids or IP addresses in usage lines. No data protection impact assessment, no records of processing beyond the privacy page. |
| 5.35 | Independent review of information security | missing | The sign-in review was done by the project itself (`docs/SECURITY.md`); the external review of round n73 concerned the website's copy, not security. |
| 5.36 | Compliance with policies, rules and standards for information security | partly | Tests enforce the rules that can be tested: no sales words or unbacked status words (`tests/test_site.py`), the engine's isolation (`tests/test_architecture.py`), the submission's numbers (`tests/test_submission.py`), the privacy page against the code (`tests/test_operations.py`). The rest of `CONTRIBUTING.md` is checked by reading. |
| 5.37 | Documented operating procedures | in place | `docs/OPERATIONS.md` (limits, Key Vault, usage, health and alerts, client sign-in, version tags, doctor, budget, backup, continuity), `deploy/KRUSGRAPH-START.md`, `docs/LIVE-TEST.md`, `docs/PUBLISHING.md`. The file says itself which steps have not been run against Azure. |

## A.6 People controls

| Control | Title | Status | Where, and what is missing |
| --- | --- | --- | --- |
| 6.1 | Screening | not applicable | No employees. |
| 6.2 | Terms and conditions of employment | not applicable | No employees. |
| 6.3 | Information security awareness, education and training | missing | Nothing documented for the maintainer; the rules for coding agents in `CONTRIBUTING.md` are the nearest thing. |
| 6.4 | Disciplinary process | not applicable | No employees. |
| 6.5 | Responsibilities after termination or change of employment | not applicable | No employees. |
| 6.6 | Confidentiality or non-disclosure agreements | missing | No NDA template in the repository; `docs/PILOT.md` says no customer data leaves the customer's tenant, which is a rule, not an agreement. |
| 6.7 | Remote working | partly | Operations are designed to run from Azure Cloud Shell without local copies of secrets (`docs/OPERATIONS.md` §0, §9). Nothing about the maintainer's own devices. |
| 6.8 | Information security event reporting | in place | `SECURITY.md`, `/.well-known/security.txt` (RFC 9116, `fabric_backend/discovery.py`), the same address on `/it`; the issue forms say a security problem does not go into a public issue (`.github/ISSUE_TEMPLATE/`). |

## A.7 Physical controls

Krusgraph has no premises, servers or media of its own; the service runs in Microsoft's datacentres. These rows are
Microsoft's, and Microsoft's attestations are not claimed here.

| Control | Title | Status | Where, and what is missing |
| --- | --- | --- | --- |
| 7.1 | Physical security perimeters | not applicable | Microsoft's (Azure, Sweden Central). |
| 7.2 | Physical entry | not applicable | Microsoft's. |
| 7.3 | Securing offices, rooms and facilities | not applicable | No office of Krusgraph's holds systems or records. |
| 7.4 | Physical security monitoring | not applicable | Microsoft's. |
| 7.5 | Protecting against physical and environmental threats | not applicable | Microsoft's. |
| 7.6 | Working in secure areas | not applicable | Microsoft's. |
| 7.7 | Clear desk and clear screen | missing | Nothing written for the maintainer's own workplace. |
| 7.8 | Equipment siting and protection | not applicable | Microsoft's. |
| 7.9 | Security of assets off-premises | missing | The maintainer's laptop and phone are the off-premises assets; nothing in the repository covers them. |
| 7.10 | Storage media | partly | No media of Krusgraph's; the one exported file with state, the registration backup, is git-ignored and its handling described (`docs/OPERATIONS.md` §8.3, `.gitignore`). |
| 7.11 | Supporting utilities | not applicable | Microsoft's. |
| 7.12 | Cabling security | not applicable | Microsoft's. |
| 7.13 | Equipment maintenance | not applicable | Microsoft's. |
| 7.14 | Secure disposal or re-use of equipment | not applicable | Microsoft's for the platform; no equipment of Krusgraph's holds customer data (none is stored). |

## A.8 Technological controls

| Control | Title | Status | Where, and what is missing |
| --- | --- | --- | --- |
| 8.1 | User endpoint devices | missing | The maintainer's devices are not covered by anything in the repository. |
| 8.2 | Privileged access rights | partly | The roles needed are named (Contributor on the resource group, owner of the Entra app, "Key Vault Secrets User", "Storage Table Data Reader/Contributor": `docs/OPERATIONS.md` §2, §6, §8, §9); the container app's managed identity reads Key Vault and the table instead of a person's credentials (`fabric_backend/keyvault.py`, `fabric_backend/registration_store.py`). Who holds the roles is outside the repository. |
| 8.3 | Information access restriction | in place | Delegated permissions only, every call as the signed-in person (`docs/SCOPES.md`); the 401 guard on exactly `/mcp` and `/mcp/`, path variants tested (`tests/test_security.py`); personal-data masking (`fabric_backend/privacy.py`). |
| 8.4 | Access to source code | partly | The source is public by design (MIT); write access is through the GitHub organisation; every change is on `main` after green CI (`CONTRIBUTING.md`). Who can push is outside the repository; no branch protection is described. |
| 8.5 | Secure authentication | in place | Microsoft Entra ID with OAuth 2.0 on-behalf-of; RS256 only; audience, issuer, expiry and scope checked; PKCE `S256` required and refresh tokens rotated for the clients that register themselves (`fabric_backend/entra.py`, `fabric_backend/registration.py`, `docs/SECURITY.md`, `docs/CLIENT-REGISTRATION.md`, `tests/test_security.py`, `tests/test_client_registration.py`). |
| 8.6 | Capacity management | partly | Rate limits per user and organisation (`fabric_backend/limits.py`); request bodies capped (`fabric_backend/server.py`); scaling and `min_replicas` in the deployment; a cost budget with `--budget` (`docs/OPERATIONS.md` §8.2, not run). No capacity measurements. |
| 8.7 | Protection against malware | partly | The server takes no file uploads; `/check` reads files in the visitor's browser only (`fabric_backend/browser_check.py`); the image is built from pinned packages. No scanning of the image or of the repository beyond `pip-audit`. |
| 8.8 | Management of technical vulnerabilities | in place | Exact pins (`deploy/constraints.txt`), weekly `pip-audit` (`.github/workflows/audit.yml`), Dependabot (`.github/dependabot.yml`), a reporting channel (`SECURITY.md`), fixes in the latest version only. |
| 8.9 | Configuration management | in place | The deployment is code with one configuration file and an example of it (`deploy/azure_containerapp.py`, `deploy/krusgraph.example.json`); `--from-azure` rebuilds the configuration from the running app and `--doctor` shows the state (`docs/OPERATIONS.md` §0, §8); the server's settings are listed in one place (`docs/OPERATIONS.md`, last section). |
| 8.10 | Information deletion | in place | No table contents stored; tokens in memory until expiry; the registration store deletes each record once used or at its retention (`fabric_backend/registration_store.py`); log retention by setting (`deploy/azure_containerapp.py`). |
| 8.11 | Data masking | in place | `fabric_backend/privacy.py` (rules P1–P6 and catalog tags), applied in `sample_rows`, drafted queries, gold views and the silver quarantine; `tests/test_privacy.py`. |
| 8.12 | Data leakage prevention | partly | Errors are scrubbed of tokens and secret-like pairs (`fabric_backend/errors.py`); usage lines carry no content (`fabric_backend/usage.py`); nothing logs headers (`docs/SECURITY.md`). The tools' answers go to whichever MCP client the person connected, which Krusgraph does not control (`docs/RISK-REGISTER.md` R2). |
| 8.13 | Information backup | partly | `--backup` exports the registration table and the restore is described (`docs/OPERATIONS.md` §8.3); nothing else holds state. Not yet run against Azure. |
| 8.14 | Redundancy of information processing facilities | partly | Azure Container Apps replicas (`min_replicas`); one region, no failover. |
| 8.15 | Logging | partly | Usage lines with the fields listed on the privacy page, the access line without IP addresses when logs go to Log Analytics, retention by setting (`fabric_backend/usage.py`, `deploy/azure_containerapp.py`). Whether Log Analytics is on for the live service is not in the repository. |
| 8.16 | Monitoring activities | partly | `/health` without sign-in (`fabric_backend/server.py`); the `az` commands for a 5xx alert and an availability test (`docs/OPERATIONS.md` §4), checked against the azure-cli source but not run. |
| 8.17 | Clock synchronisation | not applicable | Container Apps hosts are Microsoft's; no leeway is applied to token times (`docs/SECURITY.md` open question 7). |
| 8.18 | Use of privileged utility programs | not applicable | None in the image beyond what the `Dockerfile` installs; the server runs as an unprivileged user (`USER 10001`). |
| 8.19 | Installation of software on operational systems | in place | The image is built from the repository with exact pins and deployed only through `deploy/krusgraph.sh --update` by the maintainer (`Dockerfile`, `CONTRIBUTING.md`). |
| 8.20 | Networks security | partly | HTTPS ingress with a managed certificate and HSTS; the MCP endpoint reachable only at `/mcp` (`docs/SECURITY.md`). No private networking; ingress limits are Microsoft's and not verified (open question 2). |
| 8.21 | Security of network services | partly | Microsoft's for ingress and DNS; the app's own services are documented (`docs/OPERATIONS.md`). |
| 8.22 | Segregation of networks | not applicable | One container app, no internal network of Krusgraph's. |
| 8.23 | Web filtering | not applicable | The server calls only Microsoft's endpoints (login, Fabric, SQL, Key Vault, Table Storage) and GitHub for nothing; no user browsing passes through it. |
| 8.24 | Use of cryptography | in place | TLS by Container Apps; RS256 verification against Microsoft's JWKS (`fabric_backend/entra.py`); encrypted records in the registration store under a key of Krusgraph's own (`fabric_backend/registration_store.py`, `docs/CLIENT-REGISTRATION.md`); SHA-256 for every hashed id (`fabric_backend/usage.py`, `fabric_backend/limits.py`). No key management document beyond the rotation steps in `docs/OPERATIONS.md`. |
| 8.25 | Secure development life cycle | partly | `CONTRIBUTING.md`, the pull request checklist, CI on every push, the security review of the sign-in layer (`docs/SECURITY.md`). No security requirement step for every change. |
| 8.26 | Application security requirements | partly | The requirements the sign-in layer meets are listed with the test for each (`docs/SECURITY.md`); the client-registration layer is written against the MCP specification's MUSTs (`docs/CLIENT-REGISTRATION.md`). Nothing equivalent for the tools' own behaviour beyond "dry run, never delete". |
| 8.27 | Secure system architecture and engineering principles | in place | The engine never talks to a platform and a test enforces it (`docs/ARCHITECTURE.md`, `tests/test_architecture.py`); creating tools are dry run by default and never delete (`fabric_backend/server.py`); the server stores nothing by design (`SECURITY.md`). |
| 8.28 | Secure coding | partly | Token scrubbing, bounded caches, body limits, no logging on the auth path (`docs/SECURITY.md`, "What holds by design"). No written coding standard. |
| 8.29 | Security testing in development and acceptance | in place | `tests/test_security.py`, `tests/test_entra.py`, `tests/test_client_registration.py`, `tests/test_operations.py`, run by CI on every push (`.github/workflows/ci.yml`). |
| 8.30 | Outsourced development | partly | Coding agents change the repository under `CONTRIBUTING.md`, with the same identity, the same tests and the same prohibitions (no deployment, no publishing). No agreement with a supplier of development. |
| 8.31 | Separation of development, test and production environments | partly | Tests run locally and in CI against doubles and a synthetic schema; the demo workspace holds synthetic data (`fabric_backend/seed.py`, `docs/LIVE-TEST.md`); one production. The demo workspace is in the same tenant as production. |
| 8.32 | Change management | in place | Every change is a commit on `main` after `git pull --rebase` and a green suite, with an area claimed in `CONTRIBUTING.md`; CI runs on every push; `CHANGELOG.md` per version; deployment is a separate, manual step by the maintainer (`CONTRIBUTING.md`, `docs/OPERATIONS.md` §0). |
| 8.33 | Test information | in place | Only synthetic data: the shop schema (`fabric_backend/seed.py`), the SAP and Younium demos, the benchmark sets; customer data is forbidden in the repository (`CONTRIBUTING.md`) and screenshots are cropped of ids (`docs/MISSING-EVIDENCE.md`). |
| 8.34 | Protection of information systems during audit testing | missing | No audit has taken place and nothing is written about how one would be run against the service. |

## What to do with the empty rows

The rows marked missing are the list for the next pass, in the order a customer's IT department asks about them:
an incident response plan with roles and notification duties (5.24–5.26, 5.28), who has access and a review of it
(5.15–5.18, 8.2, 8.4), the maintainer's own devices (6.7, 7.7, 7.9, 8.1), and an independent review (5.35). None of
them is answered by writing a document alone; each needs the thing itself and then the file that shows it, and the
row moves only then.
