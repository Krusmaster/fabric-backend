# Claude plugin packages

`krusgraph/` is the Claude plugin for Krusgraph: the hosted connector (`https://krusgraph.com/mcp`) bundled with the
skill `fabric-graph-backend` and the commands `/krusgraph:plan`, `/krusgraph:document` and
`/krusgraph:explain-schema`. It plans keys and relationships for a Microsoft Fabric source, checks them against the
data, creates the GraphQL API when you say so, and writes the hand-over documents from the same plan.

It requires a Microsoft Fabric workspace and a Microsoft Entra work account; the connector signs you in with
Microsoft and runs with your permissions.

Install for one Claude Code session: `claude --plugin-dir plugin/krusgraph`. Validate before a release:
`claude plugin validate --strict plugin/krusgraph`. `tests/test_plugin.py` checks the manifest, the server reference
and the skill and command frontmatter in CI. The package is not published yet; `docs/PUBLISHING.md` describes how
it is submitted as a plugin bundle next to the connector when the maintainer decides to.

Details, requirements and data handling: `krusgraph/README.md`.
