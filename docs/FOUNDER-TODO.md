# What only the founder can do

Settings and steps outside the repository that no session can change: GitHub settings, releases and anything that
needs the founder's own sign-in. Round n205, 10 November 2026. Tick an item off by deleting it in a commit.

## GitHub repository settings (Krusmaster/fabric-backend)

So that someone who finds the repository sees at once what it is (the reviewer of 10 November 2026 found the idea
strong and the biggest obstacle to be trust, not technology).

1. **Description** (the gear next to *About* on the repository's front page):
   `Krusgraph: keys and relationships for Microsoft Fabric tables, checked against the rows`
2. **Website** (same dialog): `https://krusgraph.com`
3. **Topics** (same dialog): `microsoft-fabric`, `mcp`, `graphql`, `data-modeling`, `power-bi`, `krusgraph`
4. **A GitHub Release for the current version**: *Releases* → *Draft a new release* → tag `v0.8.0` on `main` (the
   version in `pyproject.toml`, `fabric_backend/__init__.py` and `server.json`), title `v0.8.0`, notes from the 0.8.0
   section of `CHANGELOG.md`. Only the founder publishes releases (`CONTRIBUTING.md`: agents do not publish anywhere).

## After this round's push

- Redeploy so that krusgraph.com serves `/trust`, the new footer link, the paragraph on `/pricing`, the comparison on
  `/choose` and the "(experimental)" titles in the tool list: `bash deploy/krusgraph.sh --update`.
- The repository stays public under the MIT licence (the founder's decision of 10 November 2026).
