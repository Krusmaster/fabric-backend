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
the session has expired). The site also serves the same identity as an MCP Server Card at
`https://krusgraph.com/mcp/server-card`, listed in `https://krusgraph.com/.well-known/ai-catalog.json`.
