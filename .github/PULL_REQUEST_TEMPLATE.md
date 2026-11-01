<!-- The rules are in CONTRIBUTING.md. Keep the headings; replace the text under each. -->

## What this changes

One paragraph: what it does, for whom, and which area of the table in CONTRIBUTING.md it touches.

## Checklist (CONTRIBUTING.md)

- [ ] **Claim.** The area in CONTRIBUTING.md's table was "open" or mine; I claimed it in its own small commit with my round number (`nNN claims …`), and I set it back to "open" in a commit at the end.
- [ ] **Own worktree.** I worked in a worktree of my own, added files by name (`git add <files>`, never `git add -A`) and rebased before pushing (`git pull --rebase`).
- [ ] **Green suite.** `python -m pytest -q` is green on the rebased branch, without skipping or disabling a test. CI has run on every push.
- [ ] **No customer data.** No customer or employer names, table names, workspace / tenant / subscription ids, figures or row values. Examples and tests use the synthetic shop schema (`fabric_backend/seed.py`) or the other synthetic sets.
- [ ] **The sales-word test.** No page or document uses the words `tests/test_site.py` rules out (`SALES`: "AI-powered", "zero-ETL", "seamless", "effortless", "enterprise-grade" and the rest), no "unique" or "only" as a claim, nothing presented as tested that was not, no "partner", "certified" or "endorsed by Microsoft". A tool's status word is the one in `fabric_backend/tool_status.py`.
- [ ] **No deployment and no secrets.** Nothing here deploys, calls Azure, Entra, DNS or Fabric, publishes anywhere or sends email. No tokens, no `deploy/krusgraph.json`.
- [ ] **Commits** are by the maintainer's identity as CONTRIBUTING.md says, with no co-author, session or "generated with" lines.

## Verified, and how

Where and when: unit tests, a local server, a local Spark, or the live service against the demo workspace with synthetic data (date, build). What was not run.
