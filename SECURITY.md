# Security policy

## Reporting a vulnerability

Email **gustav@krusgraph.com** — the same address as in `https://krusgraph.com/.well-known/security.txt`. Please
include what you found, how to reproduce it, and which version or commit it concerns. Do not open a public GitHub
issue for a vulnerability, and do not test against other people's tenants or data.

Krusgraph is maintained by one person (Kruse Consulting AB). There is no fixed response time and no bug bounty; reports
are read and handled as soon as possible, and you are credited in `CHANGELOG.md` if you wish.

## Supported versions

Only the latest version is supported: the hosted service at krusgraph.com, which runs the current `main`, and the
most recent version in `CHANGELOG.md` (the `version` in `pyproject.toml`). Fixes are not backported to older versions.

## What the service stores

No customer data. The server reads a customer's Fabric metadata and data on the signed-in user's behalf, while a tool
call runs, and keeps nothing on disk: no tables, rows, queries, results or tokens. On-behalf-of tokens are held in
memory only, keyed by a hash, until shortly before they expire. Usage lines carry the tool name, the outcome and the
duration, and at most a salted hash of the tenant id. Details: `docs/SECURITY.md` (sign-in and the MCP endpoint) and
`docs/OPERATIONS.md` section 3 (usage statistics).

## What the repository does

- Dependabot watches the Python dependencies and the GitHub Actions used here (`.github/dependabot.yml`).
- A weekly `pip-audit` checks the image's exact versions in `deploy/constraints.txt` (`.github/workflows/audit.yml`).
- A CycloneDX SBOM of those versions is built on every push to `main` and on every version tag, and kept as a workflow
  artifact (`.github/workflows/sbom.yml`).

Krusgraph holds no security certification (no SOC 2, no ISO 27001).
