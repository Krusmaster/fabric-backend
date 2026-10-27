# Publishing to the MCP Registry

`server.json` in the repository root describes the hosted server for the official MCP Registry
(https://registry.modelcontextprotocol.io). **Published on 26 October 2026 as `com.krusgraph/krusgraph` 0.6.0
(status active).** These are the steps, for the owner of krusgraph.com to run by hand (Azure Cloud Shell works:
the binary is `mcp-publisher_linux_amd64`). Nothing here runs in CI. The TXT record on krusgraph.com holds the public
key; the private key is kept outside the repository — if it is lost, make a new pair and replace the record.

The name `com.krusgraph/krusgraph` is a domain namespace, so ownership is proven with a DNS TXT record on
**krusgraph.com** (the apex, not a subdomain). The source for these steps is the registry's own guide:
https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/authentication.mdx

## Before you start

- `server.json` is up to date: `version` matches `pyproject.toml`, `remotes[0].url` is the live MCP URL, and
  `description` is at most 100 characters. `python -m pytest -q` checks all three.
- The remote URL answers publicly (the registry requires a remote server to be publicly reachable).
- OpenSSL 3 or later for Ed25519 (on macOS: `brew install openssl@3` and use that binary).

## 1. Install mcp-publisher

```bash
brew install mcp-publisher
# or the prebuilt binary:
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher
mcp-publisher --help
```

## 2. Create a key pair

Keep `key.pem` out of the repository (store it in a password manager or key vault).

```bash
MY_DOMAIN="krusgraph.com"
openssl genpkey -algorithm Ed25519 -out key.pem
PUBLIC_KEY="$(openssl pkey -in key.pem -pubout -outform DER | tail -c 32 | base64)"
echo "${MY_DOMAIN}. IN TXT \"v=MCPv1; k=ed25519; p=${PUBLIC_KEY}\""
```

## 3. Add the TXT record

At the DNS provider for krusgraph.com, add a TXT record on the apex (`@`) with the value printed above:

```
v=MCPv1; k=ed25519; p=<PUBLIC_KEY>
```

Wait for it to propagate (`dig +short TXT krusgraph.com`). If you ever rotate the key, remove the old record.

## 4. Log in with DNS

```bash
MY_DOMAIN="krusgraph.com"
PRIVATE_KEY="$(openssl pkey -in key.pem -noout -text | grep -A3 "priv:" | tail -n +2 | tr -d ' :\n')"
mcp-publisher login dns --domain "${MY_DOMAIN}" --private-key "${PRIVATE_KEY}"
```

## 5. Validate and publish

From the repository root:

```bash
mcp-publisher validate
mcp-publisher publish
```

Then check the entry:

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph/krusgraph"
```

## For each release

Bump `version` in both `pyproject.toml` and `server.json`, deploy, then repeat step 5 (log in again with step 4 if
the session has expired). Tag the released commit `v<version>` (`git tag v0.6.0 && git push origin v0.6.0`): the drift
monitor's notebook installs the library at the tag of the server's version by default (`library_ref`,
[NOTEBOOKS.md](NOTEBOOKS.md)), and fails at its `%pip` cell when the tag is missing. The site also serves the same identity as an MCP Server Card at
`https://krusgraph.com/mcp/server-card`, listed in `https://krusgraph.com/.well-known/ai-catalog.json`.

## The Claude plugin bundle (not yet submitted)

`plugin/krusgraph/` is a Claude plugin: the connector reference (`.mcp.json` -> `https://krusgraph.com/mcp`), the
skill `fabric-graph-backend` and three commands. It is tested in CI (`tests/test_plugin.py`) and not published.
When the maintainer decides to list it, the directory takes it as a **plugin bundle** next to the connector
(claude.com/docs/directory/publish, read 26 October 2026: "For your own product, make two submissions: the server as
an MCP connector, then the plugin bundle whose skills teach Claude how to use it"; when both come from the same
organisation they can be paired, and people who have both "see one set of tools rather than two" because the bundle
points at the same URL).

1. Validate locally: `claude plugin validate --strict plugin/krusgraph` (Claude Code 2.1.281 or later also checks
   `.mcp.json`). The portal applies more checks than the CLI.
2. Try it: `claude --plugin-dir plugin/krusgraph` in a session; on claude.ai, zip the folder (the folder as the single
   top-level entry) and upload it under Customize > Plugins > Add > Upload plugin; connect the connector from the
   plugin's Connectors tab. The commands carry `argument-hint` in their frontmatter: Claude Code accepts it
   (`claude plugin validate --strict` passed with Claude Code 2.1.295 on 26 October 2026), but the documentation for
   claude.ai skill uploads lists only `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools`.
   Whether that limit applies to commands inside a plugin is not confirmed; the zip upload is the test, before step 3.
3. Submit: the repository must be public (it is); open https://claude.ai/directory/manage, **Submit new**,
   **Plugin bundle**, point it at this repository and the folder `plugin/krusgraph`, work through the plugin
   pre-submission checklist (README of at least 40 words, a licence: `"license": "MIT"` is in the manifest). The
   first organisation to submit a repository folder holds the listing, so submit from the one that should own it.
4. After publishing, a new version is a commit on the tracked branch with `version` raised in
   `.claude-plugin/plugin.json`; the directory scans it and serves it once published.

Until it is published the docs page says "coming soon"; nothing on the site claims a listing.
