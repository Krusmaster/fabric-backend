# The GitHub MCP Registry (github.com/mcp) and other directories

Round R1, 12 November 2026. Nothing in this round was published, submitted or emailed; every step below is the
founder's, on his **private laptop** (never the work computer).

## The short version

- Krusgraph **is** in the official MCP Registry: `com.krusgraph/krusgraph`, versions 0.6.0, 0.7.0 and 0.8.0, 0.8.0
  marked latest, status active (read from `https://registry.modelcontextprotocol.io/v0.1/servers?search=krusgraph`
  on 12 November 2026). The steps that got it there are in [PUBLISHING.md](PUBLISHING.md).
- Krusgraph is **not** on github.com/mcp: `https://github.com/mcp?search=krusgraph` answered "No MCPs found matching
  "krusgraph"" on 12 November 2026.
- github.com/mcp is not a full copy of the official registry. It showed 770 servers that day; the official registry
  held 62,833 latest entries, 37,749 of them remote-only like ours. Being published is needed, and it is not enough.
- So there is no new `server.json` to write and no new name to verify. What is left is three things, in this order:
  decide the remote URL (below), publish the next version, and ask GitHub to list it.

## How github.com/mcp gets its entries

What could be read, and what could not:

| Source | Date | What it says |
| --- | --- | --- |
| github.com/mcp itself | read 12 November 2026 | "Servers and tools from the community that connect models to files, APIs, databases, and more." 770 servers. No submission form, no link to a publishing guide. |
| Microsoft Learn, "Publish a .NET MCP server to the MCP Registry", https://learn.microsoft.com/en-us/dotnet/ai/quickstarts/publish-mcp-registry | page dated 4 March 2026 | "The Official MCP Registry is an *upstream data source* for the MCP ecosystem. Other MCP registries, such as the GitHub MCP Registry, will soon use the Official MCP Registry as a source of MCP server listings." |
| GitHub Blog, "How to find, install, and manage MCP servers with the GitHub MCP Registry", https://github.blog/ai-and-ml/generative-ai/how-to-find-install-and-manage-mcp-servers-with-the-github-mcp-registry/ | about October 2025 | Seen through a search summary, not read in full (github.blog was outside this session's network): publish to the open registry and "downstream registries (like GitHub's) automatically pick up updates". |
| MCP Registry docs, registry aggregators, https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/registry-aggregators.mdx | read 12 November 2026 | How any downstream registry reads the official one: `GET /v0.1/servers`, hourly at most, with `updated_since`. GitHub is not named. |
| docs.github.com | not read | Outside this session's network. If GitHub documents a nomination route, it is there; look before step 4 below. |

What was observed on 12 November 2026, which is stronger than the texts:

- The entries on github.com/mcp carry official-registry names (`com.microsoft/microsoft-fabric`,
  `com.techfabric.databricks/field-guide`), and the listing page shows the README of the GitHub repository the
  registry entry names. So the official registry is the source of the data.
- A small remote server from another company is listed: `com.techfabric.databricks/field-guide` (DNS namespace, remote
  URL, first published 19 October 2026, a public GitHub repository named in `server.json` from 22 October). Its
  sibling `com.techfabric/techfabric`, published the same day **without** a `repository`, is not listed.
- Three other remote servers with a public GitHub repository, published on 20 October 2026, are not listed
  (searches for "audo", "howseen", "membase" returned nothing). Krusgraph has had a `repository` since 0.6.0 and is
  not listed either.
- One public account of how a listing happened: a comment under a DEV Community post of 3 November 2026
  (https://dev.to/zordhalo/where-to-list-your-mcp-server-from-someone-who-just-did-it-3kcj) says github.com/mcp "did
  not pick anything up from the official registry on its own", that the author "nominated our server by email to
  partnerships@github.com", and that it was approved five days later. One person's comment, about a local server;
  GitHub has not confirmed this route in anything read here.

Conclusion: github.com/mcp reads the official registry and GitHub chooses which entries to show. A public GitHub
repository in `server.json` looks necessary. There is no submission of its own that could be found; the nomination by
email is the one route anyone has reported. The VS Code MCP gallery is fed from github.com/mcp (same comment), so a
listing there is also how Krusgraph would appear in VS Code.

## The name: keep `com.krusgraph/krusgraph`

| | `com.krusgraph/krusgraph` (chosen, published) | `io.github.Krusmaster/krusgraph` |
| --- | --- | --- |
| Proof | A DNS TXT record on the apex of krusgraph.com (in place since 26 October 2026), or a file at `https://krusgraph.com/.well-known/mcp-registry-auth` | `mcp-publisher login github`, a device code in the browser |
| Says | the owner of krusgraph.com publishes this | the GitHub account Krusmaster publishes this |
| Cost | a private key to keep safe; a lost key means a new pair and a new TXT record | none, and no key |
| Survives | a move of the repository to another account or organisation | nothing but that account (the namespace is case sensitive and tied to the login) |

The domain name is the product's name and matches the remote URL's domain; the registry checks the namespace, not the
URL, so this match is the only thing that ties the entry to krusgraph.com. Changing now would create a second entry
beside the three published versions and break the Glama listing, which uses the same name. GitHub login stays the
fallback if the key and the DNS access were both lost.

## server.json as it stands

`server.json` at the repository root is unchanged by this round. It is valid against the registry's current schema,
2025-12-11 (the changelog at
https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/CHANGELOG.md lists nothing newer
than 2025-12-11 outside a draft; read 12 November 2026). `tests/test_r1_mcp_registry.py` validates it against a copy of
that schema in `tests/fixtures/r1/`.

- `name`, `title`, `websiteUrl`, `repository`: as published.
- `description`: "See how your tables connect: the rule behind every proposed link, and the counts from the check."
  (96 characters; the limit is 100). It makes no claim about speed, compliance or endorsement, and says nothing about
  AI: the rules are fixed rules, and over MCP the model is the user's own client. The registry still shows the
  description of 0.8.0 as it was published on 28 October ("Turn Microsoft Fabric tables into an explainable graph and
  a GraphQL API."), because a published version cannot be changed. The new text goes out with the next version.
- `remotes`: one entry, `streamable-http`, `https://krusgraph.com/mcp`. The schema has no field for OAuth; a client
  finds the sign-in from the server's own metadata. `headers` is for API keys and stays out.
- `packages`: left out. `pyproject.toml` defines `fabric-backend` with the stdio command `fabric-backend-mcp`, but it
  is not on PyPI (`https://pypi.org/pypi/fabric-backend/json` answered 404 on 12 November 2026), and the registry
  verifies a package by fetching it. With a first PyPI release: add a `packages` entry (`registryType` `pypi`,
  `identifier` `fabric-backend`, the version, `transport` `stdio`) and the line `<!-- mcp-name: com.krusgraph/krusgraph -->`
  in `README.md`, which is how the registry checks that a PyPI package belongs to the name.

### One decision before the next publish: which URL

The entry names `https://krusgraph.com/mcp`. That URL works for Claude with the credentials Anthropic holds, and it
does not let a client register itself; VS Code, Cursor and Copilot do exactly that, which is why `README.md` and
`/docs` send them to `https://krusgraph.com/mcp/connect` ([CLIENT-REGISTRATION.md](CLIENT-REGISTRATION.md)). The
people who find a server on github.com/mcp install it into VS Code and Copilot. With the entry as it is, their
install would point at the URL that refuses them.

Recommendation: in the version that is nominated, the remote is `https://krusgraph.com/mcp/connect`. That is a
change to `server.json` and to two tests outside this round's claim (`tests/test_site.py`,
`test_server_json_matches_the_package_and_the_card`, and `tests/test_plugin.py`, which pins the plugin's URL to
`remotes[0].url`), and it should be tried first: add the `/mcp/connect` URL in VS Code by hand and sign in. Not done
here, on purpose: it changes what is published, which is the founder's call.

## The founder's steps

On the private laptop. Nothing here needs the work computer, and nothing here runs in CI.

**0. GitHub account.** Turn on two-factor authentication at https://github.com/settings/security before
**6 December 2026**, the date GitHub has given for the account; after it, GitHub limits the account until it is on.
The DNS login below does not use GitHub, but the release tag, the repository and any GitHub login to the registry do.
(The date is the one in GitHub's notice to the account; it could not be checked against docs.github.com from here.)

**1. Install mcp-publisher** (latest release seen: v1.8.9, 10 November 2026).

```bash
brew install mcp-publisher
# or, macOS and Linux without Homebrew:
curl -L "https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_$(uname -s | tr '[:upper:]' '[:lower:]')_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" | tar xz mcp-publisher && sudo mv mcp-publisher /usr/local/bin/
mcp-publisher --help
```

On Windows: download `mcp-publisher_windows_amd64.tar.gz` from
https://github.com/modelcontextprotocol/registry/releases/latest, `tar xf` it, and run `.\mcp-publisher.exe`.

**2. Verify the namespace.** The TXT record is already on krusgraph.com; check it, then log in with the private key
that belongs to it (kept outside the repository since 26 October).

```bash
dig +short TXT krusgraph.com        # expect a line: "v=MCPv1; k=ed25519; p=<the public key>"
PRIVATE_KEY="$(openssl pkey -in key.pem -noout -text | grep -A3 "priv:" | tail -n +2 | tr -d ' :\n')"
mcp-publisher login dns --domain krusgraph.com --private-key "${PRIVATE_KEY}"
```

OpenSSL 3 is needed (on macOS, `brew install openssl@3` and use that binary). If `key.pem` is gone, make a new pair
and replace the record; the record's value is the line this prints after `TXT`:

```bash
openssl genpkey -algorithm Ed25519 -out key.pem
PUBLIC_KEY="$(openssl pkey -in key.pem -pubout -outform DER | tail -c 32 | base64)"
echo "krusgraph.com. IN TXT \"v=MCPv1; k=ed25519; p=${PUBLIC_KEY}\""
```

Add it as a TXT record on the apex (`@`) at the DNS provider, wait until `dig` shows it, remove the old record, and
log in as above. The value holds the public key and is safe to show; `key.pem` is not and never goes into the
repository. The alternatives the registry accepts: the same line as a file at
`https://krusgraph.com/.well-known/mcp-registry-auth` with `mcp-publisher login http --domain krusgraph.com
--private-key ...`, or `mcp-publisher login github` for a name under `io.github.Krusmaster/`.

**3. Publish the next version.** 0.8.0 is published and cannot be published again. With the next release (the
version raised in `pyproject.toml`, `fabric_backend/__init__.py` and `server.json`, deployed, and the URL decision
above made), from the repository root:

```bash
python -m pytest -q tests/test_r1_mcp_registry.py tests/test_site.py
mcp-publisher validate
mcp-publisher publish
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph/krusgraph"
```

The last line should show the new version with `"isLatest":true` and the new description. The login token lasts a few
minutes; log in again (step 2) if `publish` says it has expired.

**4. Ask GitHub to list it.** Look at docs.github.com for a nomination route first (search "GitHub MCP Registry").
If there is none, the reported route is an email to partnerships@github.com. A text to start from:

> Subject: MCP Registry nomination: com.krusgraph/krusgraph
>
> Hello. I would like to nominate Krusgraph for the GitHub MCP Registry (github.com/mcp).
> Name in the official MCP Registry: com.krusgraph/krusgraph
> (https://registry.modelcontextprotocol.io/v0.1/servers?search=com.krusgraph/krusgraph)
> Repository (public, MIT): https://github.com/Krusmaster/fabric-backend
> Remote server: <the URL in the published entry>, Streamable HTTP, sign-in with a Microsoft work account (OAuth).
> What it does: reads the tables in a Microsoft Fabric workspace and shows how they connect, with the rule behind
> every proposed link and the counts from the check.
> Publisher: Kruse Consulting AB, hello@krusgraph.com.
> Gustav Kruse

Send it from the address that owns the GitHub account. No claim of a partnership, and no numbers that are not in the
repository.

**5. Check the listing.**

- Official registry: the `curl` in step 3, or https://registry.modelcontextprotocol.io and search "krusgraph".
- GitHub: https://github.com/mcp?search=krusgraph, and after a listing `https://github.com/mcp/com.krusgraph/krusgraph`.
  The page shows this repository's `README.md`, so its top is what a visitor reads.
- VS Code: the MCP servers gallery in the Extensions view, search "krusgraph"; install from there and sign in once,
  to see that the listed URL works.

**6. Later versions.** The registry's rules (https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/versioning.mdx,
read 12 November 2026): every publish needs a version string not used before; a published version and its metadata
cannot be changed; plain semantic versions are sorted and the highest is marked latest; ranges (`^1.2`, `1.x`, `>=1`)
are refused. A change of text alone therefore also needs a new version; a suffix such as `0.8.0-1` is accepted but
sorts **before** 0.8.0 and is not marked latest, so use the next patch version. Each release: steps 2 and 3. GitHub's
listing follows the official registry; if it shows an old version a day later, say so in the same email thread.

## Other directories

Listed for the founder; none was submitted to. "Not read" means the site was outside this session's network, and the
line rests on the DEV Community post named above (3 November 2026) and must be checked on the site itself.

| Directory | State for Krusgraph | What it asks for |
| --- | --- | --- |
| Official MCP Registry, registry.modelcontextprotocol.io | published, 0.8.0 latest | `server.json`, a verified namespace, `mcp-publisher publish`. No review, no fee. |
| GitHub MCP Registry, github.com/mcp (feeds the VS Code gallery) | not listed | The official registry entry with a public GitHub repository, and GitHub's choice; steps 3 to 5. |
| Glama, glama.ai | listed since 27 October 2026 (`deploy/SUBMISSION.md`) | Imports the official registry. Ownership through `/.well-known/glama.json`, which the site serves. |
| Claude Connectors Directory, https://claude.com/docs/connectors/building/submission (read 12 November 2026) | pack in `deploy/SUBMISSION.md` | Portal claude.ai/directory/manage, "MCP connector". A remote HTTPS server, OAuth 2.0, a `title` and `readOnlyHint` or `destructiveHint` on every tool, documentation URL, privacy policy URL, support contact, icon, a test account for reviewers with a filled workspace, any paid Claude plan, ten portal steps with seven policy acknowledgments. Listed as a Community connector after an automatic scan; some get a person's review. |
| Claude plugin directory | not submitted ([PUBLISHING.md](PUBLISHING.md)) | The folder `plugin/krusgraph` as a plugin bundle, submitted after the connector and paired with it. |
| Microsoft: Azure API Center's partner MCP list, https://learn.microsoft.com/en-us/azure/api-center/register-discover-mcp-server (page dated 29 May 2026) | not listed | "A curated list of partner MCP servers"; the page gives no way for a third party to apply. A customer can register `https://krusgraph.com/mcp/connect` in their own API Center by hand (title, summary, runtime URL, environment), and from there into their Microsoft Foundry tool catalog. Worth one sentence in `/docs`; nothing to submit. |
| Microsoft: Marketplace | separate work ([MARKETPLACE-SETUP.md](MARKETPLACE-SETUP.md)) | The Fabric workload offer, not an MCP list. |
| Smithery, smithery.ai | not read | A remote server is published by URL from Smithery's CLI or site, with an account; Smithery connects to the server to read the tools, so its client must be able to sign in at `/mcp/connect`. |
| mcp.so | not read | A web form: name, URL, description. |
| PulseMCP, pulsemcp.com | not read | Believed to read the official registry; check whether Krusgraph is already there before doing anything. |
| ChatGPT app directory | not submitted | Review. Organisation and domain verification, a public HTTPS server, website, support, privacy and terms URLs, test cases, a video for the reviewer, a test account without MFA (a Microsoft work account without MFA needs thought). |
| Docker MCP Catalog, awesome-remote-mcp-servers (GitHub) | not submitted | A pull request to the list's repository, reviewed by its maintainers. |

Order of value, as a recommendation: GitHub (VS Code and Copilot are where Fabric developers are), then the Claude
Connectors Directory (the pack is ready), then a look at PulseMCP and Smithery. The rest can wait.
