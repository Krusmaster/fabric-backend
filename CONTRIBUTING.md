# Contributing

Krusgraph is open source (MIT) and run as a hosted service by Kruse Consulting AB. These rules apply to everyone who
changes this repository — people and coding agents alike. If you are an agent: read this file before your first
commit and again after every `git pull`.

## Before every push

1. `git pull --rebase` onto the latest `main`. Keep both sides of a conflict unless one is clearly obsolete; say which
   in the commit message.
2. Run the whole suite: `python -m pytest -q`. Push only when it is green.
3. Commit as the maintainer: `git -c user.name="Gustav Kruse" -c user.email="fagerstagustav@gmail.com" commit ...`.
   No co-author, session or "generated with" lines in commit messages or PR texts.

## What never goes into the repository

- Customer or employer data of any kind: names, table names, workspace/tenant/subscription ids, figures. Examples
  and tests use the synthetic shop schema in `fabric_backend/seed.py`.
- Secrets, tokens, client secrets, or `deploy/krusgraph.json` (tenant-specific, git-ignored; see
  `deploy/krusgraph.example.json`).
- Claims the product cannot back: no invented customers, quotes, logos or numbers, no "partner", "certified" or
  "endorsed by Microsoft", nothing presented as tested that was not.

## What an agent must not do

- Deploy, or call Azure, Entra, DNS or Fabric with real credentials. Deployment is `bash deploy/krusgraph.sh
  --update`, run by the maintainer.
- Publish anywhere (MCP registry, directories, package indexes) or send email.
- Delete branches, tags or releases, or rewrite history on `main`.

## Who works on what

Several sessions may work on this repository on the same day. To avoid editing the same files at once, the current
owner of an area is listed here. Change an area you do not own only when the maintainer asks you to.

| Area | Files | Owner now |
| --- | --- | --- |
| Website | `fabric_backend/page_templates/`, `fabric_backend/static/`, `fabric_backend/pages.py`, `fabric_backend/use_cases.py`, `discovery.py`, site routes in `server.py` | n59 (Website: /use-cases, tagline, security.txt) |
| MCP tools and errors | `fabric_backend/server.py` (tools), `errors.py`, `entra.py` | open |
| Engine | `infer.py`, `graphql.py`, `schema.py`, `rayfin.py`, `deploy.py`, `dialects.py`, `platforms/`, `databricks_drafts.py` | open |
| Deployment | `deploy/`, `Dockerfile` | open |
| SAP pack | `fabric_backend/packs/`, `fabric_backend/sap_pack.py`, `fabric_backend/sap_demo.py`, `fabric_backend/exports.py` | open |
| Docs and submission | `README.md`, `docs/`, `deploy/SUBMISSION.md` | open |

"open" means nobody has claimed it; claim an area by editing this table in its own small commit before you start,
and set it back to "open" when you are done.

Rounds are numbered nNN, and the number appears in the claim and release commits. Before a round claims, run
`git log origin/main --oneline --grep "nNN claims"` and take the next number that has not been used.

## Verified, and how

When you state that something works, say where and when it was verified: unit tests, a local server, or the live
service against a Fabric workspace with synthetic data. The hosted connector's first connection (Claude → Entra →
Fabric) was on 25 October 2026; what counts as tested end to end is the run of 27 October 2026 (30 tools, read-only,
as drafts or as dry runs, then one creating call the maintainer approved: create_backend updated shop_api in place; the
first such run was on 26 October). Each tool's status is in
`fabric_backend/tool_status.py`, and the site, the docs and the tools' own notes render from it. `docs/LIVE-TEST.md` is
the checklist for the next run.
