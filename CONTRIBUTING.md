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
- Pricing, sales, customers, marketing drafts and business analysis go to Krusmaster/krusgraph-business (private),
  never to this repo.

## What an agent must not do

- Deploy by hand, or call Azure, Entra, DNS or Fabric with real credentials. Deployment is the workflow
  `.github/workflows/deploy.yml` once the maintainer has switched it on (`docs/AUTO-DEPLOY.md`), and otherwise
  `bash deploy/krusgraph.sh --update`, run by the maintainer.
- Merge a pull request that the section "Merging and deploying" below does not allow a round to merge.
- Publish anywhere (MCP registry, directories, package indexes) or send email.
- Delete branches, tags or releases, or rewrite history on `main`.

## Who works on what

Several sessions may work on this repository on the same day. To avoid editing the same files at once, the current
owner of an area is listed here. Change an area you do not own only when the maintainer asks you to.

| Area | Files | Owner now |
| --- | --- | --- |
| Website | `fabric_backend/page_templates/`, `fabric_backend/static/`, `fabric_backend/pages.py`, `fabric_backend/concepts.py`, `fabric_backend/use_cases.py`, `discovery.py`, site routes in `server.py` | n242 holds `sap.html` and the new files `static/media/krusgraph-sap-to-report*` only (the approved SAP film on /sap, with captions); the rest is open |
| MCP tools and errors | `fabric_backend/server.py` (tools), `errors.py`, `entra.py` | open |
| Engine | `infer.py`, `graphql.py`, `schema.py`, `rayfin.py`, `deploy.py`, `dialects.py`, `platforms/`, `databricks_drafts.py` | open |
| Deployment | `deploy/`, `Dockerfile`, `.github/` | open |
| Pipeline jobs and permissions | `fabric_backend/pipeline_jobs.py`, `fabric_backend/access.py`, `fabric_backend/report.py` | open; BL35 holds the new `fabric_backend/workspace_access.py` only (workspace roles and sensitivity labels proposed, dry run only; `access.py` is read, not edited) |
| SAP pack | `fabric_backend/packs/`, `fabric_backend/sap_pack.py`, `fabric_backend/sap_demo.py`, `fabric_backend/exports.py` || open |
| Catalog publish | `fabric_backend/catalog_publish/` | open |
| Docs and submission | `README.md`, `docs/`, `deploy/SUBMISSION.md` | open; M1 holds new files under `docs/marketing/` only (marketing drafts: a fictional industrial case on synthetic data, LinkedIn posts, a film script, taglines, a home page section; nothing applied to the site or `llms.txt`); W9 holds the one new file `docs/INTEGRATE-AND-HEAL-DESIGN.md` (a design for connecting sources to OneLake and for self-healing data products by rules; docs only, nothing built); not the site, not the editor); BL35 holds the new `docs/WORKSPACE-ACCESS.md` and one CHANGELOG.md line only |
| Tests | `tests/` | open; BL35 holds the new `tests/test_bl35_workspace_access.py` only |
| Workload | `workload/` (the Fabric workload, a fork of Microsoft's starter kit), `fabric_backend/workload_api.py`, the workload routes in `server.py`, `docs/WORKLOAD-DEV.md` | open |
| Marketplace | `fabric_backend/marketplace.py`, `fabric_backend/entitlements.py`, the marketplace routes in `server.py`, `docs/MARKETPLACE-SETUP.md`, `tests/test_marketplace.py` | open |
| Hub readiness | `docs/HUB-ATTESTATION.md`, `docs/HUB-READINESS.md`, `tools/hub_readiness.py`, `.github/workflows/hub-readiness.yml` (new files only; no `workload/` code, no site, no engine) | open |
| Evolution | `docs/EVOLUTION.md`, `tools/evolution/`, `tests/test_e1_*` (how Krusgraph gets better by rules: the design, the score comparison that fails on a lower score and its baseline, the evolution-log tool, the case-record schema) | open |
| Social media | `social/` (new; published images for the founder's social accounts, no code) | open; FV2 holds the new folder `social/films/2026-11-22-few-taps/` only (a silent 9:16 film with text and a synthesized sound bed, and its source; needs-gustav) |
| Krusgraph CLI | the new `fabric_backend/krusgraph_cli.py`, the new `fabric_backend/skills/SKILL.md`, the `krusgraph` console script and the skill's package-data line in `pyproject.toml`, the new `docs/CLI.md`, the new `docs/drafts/cli-hub-entry.md`, the new `tests/test_cl1_*`, one CHANGELOG.md line | open |
| Rayfin | `fabric_backend/rayfin.py`, the `rayfin` command in `cli.py`, `examples/rayfin/`, `tests/test_rayfin_app.py`, `tests/fixtures/rayfin_check/`, the Rayfin tests in `tests/test_fabric_backend.py`, the `rayfin` part of `tests/golden/`, the Rayfin section of `README.md`, the Rayfin row in `tools/third_party_notices.py` || open |

"open" means nobody has claimed it; claim an area by editing this table in its own small commit before you start,
and set it back to "open" when you are done.

Rounds are numbered nNN, and the number appears in the claim and release commits. Before a round claims, run
`git log origin/main --oneline --grep "nNN claims"` and take the next number that has not been used.

## Deployment

Dependabot opens one grouped pull request per ecosystem and month (`.github/dependabot.yml`: pip, pip in `deploy/`,
GitHub Actions, npm in `workload/Workload`). Nobody has to approve them: a Deployment round rebases each PR onto `main`, waits for green CI and
squash-merges it; a red PR is fixed in place when the cause is a simple consequence of the update (a changed default in
an action, a dropped Python version), and closed with a comment that says what is needed otherwise. `main` has no
branch protection rules, and the way of working needs none: CI runs on every push and every PR, and a round verifies
that `main` is green after each merge before the next. Every action in `.github/workflows/` is pinned by commit with its version in a
comment (`tests/test_b2_supply_chain.py`); take a new one's commit from `git ls-remote` of its tag. CI's `notices` job runs `python tools/third_party_notices.py
--check --from-installed`, so a pip PR that changes a pin in `deploy/constraints.txt` is red until
`THIRD_PARTY_NOTICES.md` is regenerated on its branch (`python tools/third_party_notices.py`): a simple consequence,
fixed in place. The job also stops on a dependency under the AGPL or the SSPL, which is not fixed in place.
## Merging and deploying

The maintainer's decision of 16 November 2026: code with green tests may be merged and deployed automatically.

**A round may merge its own pull request into `main`** when all of these hold:

- every CI job on the pull request's current head is green, including *path-guard*;
- the pull request touches only code, tests and public docs, and `tools/path_guard.py` finds nothing protected;
- the branch is up to date with `main` (update it and wait for CI again if `main` has moved);
- nothing in the round wrote to a Fabric tenant other than the demo tenant.

Use the repository's usual merge method (a merge commit; Dependabot PRs are squashed, as above). Then check that
`main` is green before the next merge.

**Never merged by a round.** The round adds the label `needs-gustav` to the pull request and stops; the maintainer
merges it. This applies to a pull request that touches any of the following:

- `social/`, or marketing copy meant for publishing (`docs/marketing/` and the like);
- pricing or sales material, including the pricing page. Pricing and sales material do not belong in this repository at
  all (see "What never goes into the repository");
- the legal pages' text: privacy, terms, cookies, the security policy page, `legal.py`, the DPA draft and the licences;
- the workload name or manifest identity: `workload/Workload/Manifest/`, the package build scripts, `server.json`
  (for example `Krusgraph.Modeler`, PR #26);
- secrets or permissions: `.github/workflows/`, `deploy/` scripts, `Dockerfile`, `entra.py`, `access.py`,
  `SECURITY.md`;
- the deletion or retention of user data (`registration_store.py`, `usage.py`);
- a major version bump of a dependency (`deploy/constraints.txt`, `pyproject.toml`,
  `workload/Workload/package.json`; for 0.x versions a new minor counts as major);
- this section, `tools/path_guard.py` or the pull request template.

A Fabric write to a tenant other than the demo tenant cannot be seen in a diff. A round that made one labels its pull
request `needs-gustav` itself.

**The rule is enforced.** `.github/workflows/path-guard.yml` runs `tools/path_guard.py` on every pull request and on every
label change. It fails when a protected path or a major bump has no `needs-gustav` label. The rules come from the base
branch, so a pull request cannot loosen the check that judges it. A change to the rules is itself protected.
`tests/test_cd1_path_guard.py` tests the check.

**Deploying.** After a push to `main` whose CI run is green, `.github/workflows/deploy.yml` builds the image in Azure
and updates the container app, the same way `bash deploy/krusgraph.sh --from-azure --update` does. It runs the same
health checks (the home page, docs, privacy, the MCP login requirement, the build id at `/healthz`). If they fail, it
rolls back to the previous image automatically and opens an issue. One deployment runs at a time, and commits that are
superseded while waiting are skipped. It signs in with GitHub's OIDC token, so no stored secret is needed. It stays
dormant until the maintainer has done the one-time steps in `docs/AUTO-DEPLOY.md`, which also says how to switch it
off. The Fabric workload package upload stays manual.

## Reusing external code

Depending on a package (a pin in `deploy/constraints.txt`, an extra in `pyproject.toml`) and copying code into this
repository are different acts. `THIRD_PARTY_NOTICES.md` covers the first and is generated by
`python tools/third_party_notices.py` from the pins (`--check` fails when it is stale; run it after a pin changes). For
the second:

- Copy only from a repository whose `LICENSE` file you have opened and read **at the pinned commit you copy from**, and
  write that commit, the file and the licence in the commit message and in a comment at the top of the copied code.
- Keep the notices: the copyright line and the licence text or its reference travel with the code, and the package or
  repository is added to `THIRD_PARTY_NOTICES.md` (the vendored section) in the same commit.
- No code under the AGPL or the SSPL, in any amount, however small the piece. Using such a server next to Krusgraph is a
  user's choice; its code never comes here.
- Never copy from a repository whose licence cannot be verified: no licence file, a licence file that does not match
  the metadata, or a page that could not be opened. "GitHub says MIT" is metadata, not a licence file.
- Reading another project's documentation to learn how an API behaves is fine and is cited the way `docs/` does it
  (source, file, date); reading its code to reproduce it is copying and follows the rules above.

The Fabric workload in `workload/` is a fork of Microsoft's starter kit `microsoft/fabric-extensibility-toolkit` at commit
`dacab1b391d03010ba61a0446126d05515c487f0` (6 August 2026), whose `LICENSE` (MIT, Copyright (c) Microsoft Corporation)
was opened and read at that commit and is kept as `workload/LICENSE`. The kit's `Workload/`, `scripts/` and `tools/` were
copied; the HelloWorld item became the Model item and its editor was rewritten; other changes carry a `Krusgraph:`
comment. It is listed in `THIRD_PARTY_NOTICES.md` (vendored section). The permanent name, the founder's decision of 9
November 2026, is `Krusgraph.Modeler` (`docs/WORKLOAD-PUBLISH.md`), and the package builds it by default (W12); the
development workload `Org.Krusgraph` is built with `--name Org.Krusgraph`. The package builds only these two; no other `Krusgraph.*` name is used anywhere (the first upload reserves a name for good),
and only the founder uploads.

`docs/ECOSYSTEM-WATCHLIST.md` keeps the related MCP servers with their licence as observed or "not verified".

## Issues, pull requests and conduct

- Issues use the forms in `.github/ISSUE_TEMPLATE/`: **Bug** (which example or which file, without customer data),
  **Feature**, and **A wrong relationship** (table, column, the rule that was shown, what was right). A security problem
  goes the way `docs/SECURITY.md` says, not into a public issue.
- A pull request follows `.github/PULL_REQUEST_TEMPLATE.md`, which repeats the rules above as a checklist: the claim, an
  own worktree, a green suite, no customer data, the sales-word test (`tests/test_site.py`, `SALES`), no deployment.
- The code of conduct is the Contributor Covenant 2.1, `CODE_OF_CONDUCT.md`; reports go to hello@krusgraph.com.

## The guided path is clicked through

Gustav, 19 November 2026: the chat path worked and looked good on 12 November, and then five rounds in a week each
changed the cards and tested only their own part. So no round may merge a change that breaks the path: the
click-through `tests/test_wb15_click_through.py` (with `tests/wb15_click_through.js` and `tests/wb15_fake.py`) clicks
the Start Krusgraph card's own buttons on the synthetic SAP demo from step 1 to the confirmation step, at 390 px, light
and dark. It runs in CI's `test` job with the other browser tests and is a required check: in CI it fails, rather than
skips, when Chromium does not start. A change to a card (`mcp_apps*.py`), to `start_flow.py`, `coach.py`, `next_rules.py`
or to how the tools are wrapped in `server.py` keeps it green; when the path is meant to change, change the test in the
same pull request and say why.

## Verified, and how

When you state that something works, say where and when it was verified: unit tests, a local server, or the live
service against a Fabric workspace with synthetic data. The hosted connector's first connection (Claude → Entra →
Fabric) was on 25 October 2026; what counts as tested end to end is the run of 27 October 2026 (30 tools, read-only,
as drafts or as dry runs, then one creating call the maintainer approved: create_backend updated shop_api in place; the
first such run was on 26 October). Each tool's status is in
`fabric_backend/tool_status.py`, and the site, the docs and the tools' own notes render from it. `docs/LIVE-TEST.md` is
the checklist for the next run.
