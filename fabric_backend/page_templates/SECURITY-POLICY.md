# Vulnerability disclosure policy

How to report a security problem in {{PRODUCT}}, and what to expect. Published by Kruse Consulting AB, Sweden. The
same address is in [/.well-known/security.txt](/.well-known/security.txt) (RFC 9116).

## How to report

Email **[gustav@krusgraph.com](mailto:gustav@krusgraph.com)**, in English or Swedish. Please include:

- what you found and where (the hosted service at krusgraph.com, the Fabric workload, or the open-source code);
- how to reproduce it, step by step;
- the version or commit, if it concerns the code;
- how to reach you, and whether you want to be credited.

Do not open a public GitHub issue for a vulnerability.

## What is in scope

- The hosted service: `https://krusgraph.com` (site and MCP endpoint) and `https://workload.krusgraph.com` (the
  Fabric workload's engine).
- The open-source code at [{{GITHUB}}]({{GITHUB}}), latest version.

Out of scope: Microsoft Fabric, Microsoft Entra ID, Azure and AI clients such as Claude (report those to their vendors),
and installations someone else runs from the code (tell us too, so the code can be fixed).

## Testing rules

- Test only against your own tenant, your own data and your own accounts. Never against other people's tenants or data.
- No denial of service, no load testing, no social engineering, no physical attacks.
- Stop and report as soon as you see data that is not yours; do not keep, copy or share it.
- Give us reasonable time to fix before you publish.

Research done in good faith under these rules is welcome, and a report made under them is treated as help.

## What to expect

{{PRODUCT}} is maintained by one person. There is no bug bounty and no fixed response time. Reports are read and
answered as soon as possible; we keep you informed and agree a disclosure date with you. Fixes go into the latest version only (the hosted
service runs the current code). You are credited in the changelog if you wish.

If a report shows that customers may be affected, they are told under the incident process in
[docs/INCIDENT-RESPONSE.md]({{GITHUB}}/blob/main/docs/INCIDENT-RESPONSE.md).

## More

- [Security and data](/trust): what passes through {{PRODUCT}}, what is stored, and what is and is not in place.
- [SECURITY.md]({{GITHUB}}/blob/main/SECURITY.md) in the repository: the same policy, with supported versions.
- [docs/SECURITY-SUPPLIER.md]({{GITHUB}}/blob/main/docs/SECURITY-SUPPLIER.md): for customers asking a supplier about
  security under NIS2 and the Swedish cybersecurity act.
