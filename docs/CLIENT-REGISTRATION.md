# Sign-in for MCP clients other than Claude: client registration

Status: switched on at krusgraph.com on 27 October 2026 (`KRUSGRAPH_CLIENT_REGISTRATION`; code in
`fabric_backend/registration.py`, `registration_flow.py`, `registration_store.py`; tests in
`tests/test_client_registration.py`). In the maintainer's live test that day, Glama (with its client ID metadata
document), VS Code and Cursor signed in at `https://krusgraph.com/mcp/connect` and worked; Claude Code and ChatGPT
have not been tried. The flag stays off by default for anyone else who runs the server. This replaces the earlier
registration facade (`KRUSGRAPH_DCR`, removed in the same change), which handed every client the Entra app's client id
without a consent of its own and, when switched on, changed the metadata Claude reads.

## The problem

Claude connects with credentials Anthropic holds for the one multi-tenant Entra app, so it never registers. Every
other MCP client (VS Code, Cursor, Glama, Claude Code with a plain URL, ChatGPT) expects to obtain a client id from
the authorization server named in the resource's metadata, and Microsoft Entra ID offers neither of the automatic
ways: no Client ID Metadata Documents (CIMD) and no dynamic client registration (DCR, RFC 7591).

## What the specification says

From the MCP specification, version 2026-07-28 (the latest; `docs/specification/2026-07-28/basic/authorization/` in
modelcontextprotocol/modelcontextprotocol, read 27 October 2026), and MCP's Security Best Practices
(`docs/docs/2026-07-28/tutorials/security/security_best_practices.mdx`):

- **Order of registration** (client-registration): "1. Use pre-registered client information … 2. Use Client ID
  Metadata Documents if the Authorization Server indicates that it supports them (via
  `client_id_metadata_document_supported` …) 3. Use Dynamic Client Registration as a fallback … 4. Prompt the user".
- **CIMD**: "MCP clients and authorization servers **SHOULD** support OAuth Client ID Metadata Documents". The
  authorization server "**MUST** validate that the fetched document's `client_id` matches the URL exactly" and
  "**MUST** validate redirect URIs presented in an authorization request against those in the metadata document".
- **DCR**: "Dynamic Client Registration is deprecated. New implementations should use Client ID Metadata Documents
  instead."
- **Confused deputy** (security-considerations): "MCP proxy servers using static client IDs **MUST** obtain user
  consent for each dynamically registered client before forwarding to third-party authorization servers". The Best
  Practices add that the consent page "**MUST** clearly identify the requesting MCP client by name", "Show the
  registered `redirect_uri` where tokens will be sent", "Implement CSRF protection" and "Prevent iframing via
  `frame-ancestors` …"; consent cookies "**MUST** use `__Host-` prefix", be "Secure, HttpOnly, and SameSite=Lax",
  signed, and "Bind to the specific `client_id`"; the state "**MUST NOT** be set until **after** the user has approved
  the consent screen", and state values must be "single-use … and have a short expiration time (e.g., 10 minutes)".
- **Token passthrough**: "MCP servers **MUST NOT** accept any tokens that were not explicitly issued for the MCP
  server", and "The MCP server **MUST NOT** pass through the token it received from the MCP client."
- **PKCE**: clients "**MUST** use the `S256` code challenge method", and "If `code_challenge_methods_supported` is
  absent, the authorization server does not support PKCE and MCP clients **MUST** refuse to proceed."
- **Redirect addresses**: "All redirect URIs **MUST** be either `localhost` or use HTTPS." "Authorization servers
  **MUST** validate exact redirect URIs against pre-registered values". For CIMD clients, servers "**SHOULD** display
  additional warnings for `localhost`-only redirect URIs" and "**MUST** clearly display the redirect URI hostname
  during authorization", because "the metadata document proves control of a domain, but it cannot prove which local
  process is listening on a `localhost` redirect URI".
- **Refresh tokens**: "For public clients, authorization servers **MUST** rotate refresh tokens".
- **Mix-up**: "MCP authorization servers **SHOULD** include the `iss` parameter in authorization responses".
- **Authorization server binding**: pre-registered credentials are bound to the issuer, and Claude "uses only the
  first entry in your metadata's `authorization_servers`" (claude.com/docs/connectors/building/authentication).

From the CIMD draft (oauth-wg/draft-ietf-oauth-client-id-metadata-document, -02): the server "**MUST NOT** fetch a
Client ID Metadata Document URL … that resolve[s] to special-use IP addresses", "**MUST NOT** automatically follow
HTTP redirects", should read at most "5 kilobytes", "**MUST NOT** cache error responses", should "display the
hostname of the `client_id`", and a document must not carry a `client_secret` or any shared-secret
`token_endpoint_auth_method`.

## How the clients register today

Read 27 October 2026. "Confirmed" means a primary source (the client's own source or docs, or the live document);
the rest is marked.

| Client | Registration | Client id | Redirect addresses | Source |
| --- | --- | --- | --- | --- |
| VS Code (1.143) | stored or `oauth.clientId` → CIMD → DCR → asks the user | `https://vscode.dev/oauth/client-metadata.json` | `http://127.0.0.1:33418/`, another port when 33418 is taken; `https://vscode.dev/redirect`; `https://insiders.vscode.dev/redirect` | confirmed in microsoft/vscode `mainThreadAuthentication.ts`, `oauth.ts`, `loopbackServer.ts`; release notes 1.106 ("will automatically use that flow over DCR"); sends `resource` except to Microsoft hosts. The document itself was not fetched |
| Claude Code (2.1.311) | CIMD (since 2.1.81) → DCR → `--client-id` | `https://claude.ai/oauth/claude-code-client-metadata` | `http://localhost/callback`, `http://127.0.0.1/callback`, any port | confirmed: the document, fetched live; code.claude.com/docs/en/mcp |
| Claude (claude.ai, Desktop) | Anthropic-held client → CIMD → DCR | `https://claude.ai/oauth/mcp-oauth-client-metadata` | `https://claude.ai/api/mcp/auth_callback` | confirmed: the document, fetched live. Krusgraph's connector keeps the Anthropic-held credentials at `/mcp` |
| Cursor (3.14) | DCR, or a static `auth.CLIENT_ID` in `mcp.json`; CIMD "still on our radar" | — | desktop docs: `http://localhost:8787/callback`; DCR still registers `cursor://anysphere.cursor-mcp/oauth/callback` (users' reports); cloud agents `https://www.cursor.com/agents/mcp/oauth/callback` | cursor.com/docs/mcp through search excerpts only (cursor.com not reachable from the build environment); better-auth #10946, alpacahq/agentic #6 |
| Glama | CIMD, seen live on 27 October 2026 (users had reported DCR) | `https://glama.ai/api/app/mcp/oauth/client-metadata.json` | `https://glama.ai/api/app/mcp/oauth/callback`; inspector `https://glama.ai/mcp/inspector/oauth/callback` | the authorization request Glama sent to krusgraph.com, 27 October 2026; earlier reports: koala73/worldmonitor PR #9281, Usehourly #327 |
| ChatGPT | CIMD preferred | `https://chatgpt.com/oauth/client.json` (or per callback) | `https://chatgpt.com/connector_platform_oauth_redirect` | developers.openai.com/plugins/build/auth through a search excerpt |

So: CIMD covers VS Code, Claude Code, ChatGPT and Glama; Cursor needs DCR. Cursor's desktop DCR asks for a
private-use `cursor://` address, which the rules for this layer do not allow (only https and loopback); see Cursor in
`docs/OPERATIONS.md` section 6 for the static client id that works within the rules.

## The design

**A second address for the same server.** A client picks the authorization server from the resource's metadata, and
Claude takes the first entry. So `https://<domain>/mcp` keeps naming Entra (Claude's sign-in is byte for byte the same
in both modes; tests lock it), and `https://<domain>/mcp/connect` names Krusgraph's own authorization server
`https://<domain>/oauth`. Both addresses reach the same MCP endpoint and validate every token the same way.

**The flow** (`KRUSGRAPH_CLIENT_REGISTRATION=1`):

1. `POST /mcp/connect` without a token: `401` with `resource_metadata=".../.well-known/oauth-protected-resource/mcp/connect"`.
   That document names `https://<domain>/oauth`, whose RFC 8414 metadata is at
   `/.well-known/oauth-authorization-server/oauth`: `client_id_metadata_document_supported: true`, `S256` only,
   `token_endpoint_auth_methods_supported: ["none"]`, `authorization_response_iss_parameter_supported: true`, and a
   `registration_endpoint` only when `KRUSGRAPH_CLIENT_REGISTRATION_DCR=1`.
2. `GET /oauth/authorize`: the client id is a CIMD URL (fetched safely: https, a DNS name, no port, no query, every
   resolved address global, connection pinned to the vetted address, certificate checked, no redirects, 5 KB, cached
   per Cache-Control up to an hour, errors never cached) or a DCR client id signed by this server. The redirect address
   must match one the client registered: exact, except a loopback address on any port. An https address must be on
   the client id's host or under it, and every https host must be a plain DNS name. Then PKCE `S256`,
   `response_type=code`, `response_mode=query`, the `resource` (this address) and the scope are checked. Every error at
   this step is shown on this server's own page and never sent to the redirect address: anyone can publish a client
   with any redirect address, so before the user has approved a client the browser is never sent to it ("Open
   Redirection" in the specification; RFC 9700 section 4.11.1).
3. **Krusgraph's consent page** for that client: its name (control and direction characters removed), its domain
   (or "registered itself, name not verified" for DCR), the redirect address with its host in bold, a warning for a
   program on this computer, what the client gets, Allow and Deny. `frame-ancestors 'none'`, `X-Frame-Options: DENY`,
   a CSRF cookie, a signed form that names the client and expires after 10 minutes and works once.
4. Only after Allow: the sign-in is stored (10 minutes, single use), a cookie binds it to this browser, and the browser
   goes to Entra with this server's redirect address `https://<domain>/oauth/callback`, its own state and PKCE, and the
   scope `<MCP_PUBLIC_URL>/user_impersonation offline_access`. No `prompt=consent` and no `resource` go to Entra.
5. `/oauth/callback`: the state is taken (once), the browser must be the one that approved, Entra's code is redeemed
   with the app's secret, and the access token is validated exactly as `/mcp` validates tokens (signature, audience =
   this app, issuer per tenant, `user_impersonation`, allowed tenants). The approval is stored for this user (a keyed
   hash of tenant and object id), client and redirect address. The client gets a code of this server's (60 seconds,
   single use) with `state` and `iss`.
6. `POST /oauth/token`: for the code, the same client id, the same redirect address and the PKCE verifier, the client
   gets Entra's access token for this app (the same kind Claude holds) and a refresh token of this server's own. Entra's
   refresh token stays with the server, encrypted. A second use of a code revokes what the first got. Each refresh
   rotates the token; an old one coming back ends the whole line.
7. Next time, an approval for an **https** redirect address is remembered (180 days) and the page is skipped, but
   only for the same client, the same redirect address and the same client name, and the account that signs in at
   Entra must be the one that approved; otherwise the page is shown for that account. An approval for a program on
   this computer (a loopback address) is **not** remembered: any local program can use VS Code's client id and listen
   on a local port, so the page with its warning is shown at every new sign-in (the specification's "Localhost Redirect
   URI Risks"). A native client signs in again only when its refresh token runs out, so that is rare.

Not passed on, ever: the client's token goes nowhere but this server's validator; Fabric and SQL get their own
on-behalf-of tokens as before. Never issued: a client secret.

**Limits** (in memory per replica): per network (the right-most `X-Forwarded-For` entry, the one Container Apps'
ingress adds; an IPv6 address counts as its /64) `60/minute,600/hour` for authorize, consent, callback and token
together; per client and network `300/minute,6000/hour` (a client id is not a secret and VS Code's is shared by every
VS Code user, so a bucket for the client alone would let anyone lock all its users out); `10/hour` registrations per
network.

**Fetching a client's document** cannot tie the server up: the whole fetch, the name lookup included, ends after 6
seconds however slowly the client's host answers, at most four run at once per replica, and this layer's endpoints run
on eight threads of their own, apart from the threads the MCP tools use at `/mcp`.

## What is stored, and what it costs

| Record | Content | Kept |
| --- | --- | --- |
| txn | a sign-in on its way through Entra: the client's request, the Entra PKCE verifier, the browser binding's hash | 10 minutes, taken once |
| code | Krusgraph's code: client, redirect, PKCE challenge, the user hash, Entra's tokens encrypted (AES-GCM) | 60 seconds, taken once |
| used | that a code or a consent form was used | 10 minutes |
| family | a refresh line: client, user hash, the hash of the current refresh token, Entra's refresh token encrypted | at most 90 days |
| consent | user hash, client id, client name, the https redirect address, date (none for loopback addresses) | 180 days |

No names, e-mail addresses, IP addresses or tokens in clear. The store is Azure Table Storage (one table, the
container app's managed identity with "Storage Table Data Contributor" on that table only), because the app runs up to
two replicas and a code must work once across both; `memory` is for tests and a single replica. Cost: Table Storage
is billed per GB stored and per transaction, with no fixed fee for the account. A sign-in is about ten transactions
and the table stays far below a megabyte, so the expected bill is öre a month. The only price found while writing
this was $0.045 per GB-month for Standard LRS (East US, June 2026, a third-party summary of the Azure Retail Prices
API); check the current figure for Sweden Central at https://prices.azure.com/api/retail/prices with
`$filter=serviceName eq 'Storage' and armRegionName eq 'swedencentral' and contains(productName,'Tables')`.

One more secret: `KRUSGRAPH_REGISTRATION_KEY` (32 random bytes) encrypts the tokens in the store and signs the cookies
and DCR client ids. Key Vault (`KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI`) or a container app secret. A new key ends
every remembered approval, refresh line and DCR client id; nothing worse.

## Security review (27 October 2026)

An independent review of the code before release found, and the same change fixes, with a test for each:

1. **The real metadata fetch failed every time** (a keyword argument urllib3 does not take), so VS Code could never
   have signed in; the tests had replaced the fetch. Fixed, and now tested against a local TLS server with a
   certificate of its own (name check, no redirects, 5 KB, IPv4 first and the next address after a failure).
2. **A slow client host could hold threads for hours** (timeouts per read, not per fetch) and, through the shared
   thread pool, stall the MCP tools at `/mcp`. Fixed: a 6-second deadline for the whole fetch, enforced by a timer
   that shuts the socket (so a server that drips its headers is cut off too), a name lookup that holds one of four
   lookup slots until it really ends (new lookups are refused rather than queued), at most four fetches at once, and
   this layer's own threads.
3. **Anyone could lock all users of a shared client out** by sending garbage under VS Code's client id from a few
   addresses. Fixed: a client's bucket is per network; IPv6 counts per /64.
4. **Open redirect before the approval**: request errors were sent to the client's redirect address, which anyone can
   choose. Fixed: before the approval, every error is a page on this server.
5. **Characters in an https host could add directives to the page's Content-Security-Policy.** Fixed: https hosts
   and client id hosts must be plain DNS names, and the policy is built from the checked parts.
6. **Non-ASCII values in `state` or a refresh token gave a 500.** Fixed: exact patterns, and malformed values are a 400.
7. **A remembered approval for a loopback address** let a local program get a token without any page. Fixed: loopback
   approvals are not remembered.
8. **A brief Entra outage during a refresh ended the refresh line**, signing users out. Fixed: only Entra's definitive
   answers end a line; others are a 503 and the same refresh token works again.

The reviewer then checked the fixes: all eight confirmed, and the two gaps that second pass found (a server that
drips its headers, lookups queueing behind hung ones) are closed as described under 2, with tests. Also changed
after the review: `fullmatch` for the PKCE patterns, `WWW-Authenticate` on a 401 for Basic credentials,
`prompt=none` refused on the page when nothing is approved yet, combining marks in client names capped at two per
character, and the approval buttons armed after a second.

## Remaining risks

- **A token says nothing about the client.** The access token is Entra's, for this app; the server cannot tell which
  client holds it and cannot revoke one client's access token before it expires (about an hour). Refresh lines can be
  ended: by the user's administrator in Entra, or by a new server key.
- **Loopback impersonation.** Any program on the user's computer can use VS Code's client id and listen on a loopback
  port. The page warns ("Continue only if you started this sign-in … just now") and is shown at every sign-in to a
  local program; a user who clicks Allow for a program they did not start gives it a token. The specification accepts
  this for native clients, and PKCE keeps codes from being redeemed by anyone who did not start the flow.
- **Open CIMD.** Any https domain can be a client; the domain is on the page. `KRUSGRAPH_REGISTRATION_CLIENT_DOMAINS`
  restricts it to a list.
- **DCR names are unverified.** The page says so. DCR has its own flag.
- **A remembered approval skips the page** for 180 days for the same client, https redirect address and name,
  checked against the account that signs in.
- **Limits are per replica and per network.** With two replicas a network gets up to twice the limit; behind a CDN
  or Front Door (not used today) every user would share the edge's bucket, and the right-most `X-Forwarded-For` rule
  would need changing.
- **DCR client ids cannot be revoked one by one.** They are signed, not stored; a new server key revokes all of them
  (and everything else).
- **Double-click tricks.** The page cannot be framed, and its buttons take clicks only after a second, so a window
  swapped in under a double-click cannot land on Allow; a user who reads the page and clicks Allow is not protected
  from their own choice.
- **Cursor's desktop DCR address** (`cursor://`) is refused by the rules; Cursor needs a static client id until it
  supports CIMD or a loopback address. Allowing that one private-use address would be the maintainer's decision.
- **Fetching documents from Azure.** A client's host may refuse requests from cloud addresses (claude-code #84263
  reports Cloudflare 403s for claude.ai's documents from some cloud egress); then that client cannot sign in here.
- **Table Storage outage**: these clients cannot sign in while it lasts; Claude is unaffected.
- **Company web filters.** The approval page and Microsoft's sign-in open in the user's own browser; a filter on a
  company network can stop them (seen on 27 October 2026 as `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` on a company laptop
  while the server answered normally). Claude is not affected, because it reaches the server from Anthropic's side.

## Live test, 27 October 2026

The maintainer switched the layer on at krusgraph.com (`deploy/krusgraph.sh --client-registration`) and signed in
from Glama, VS Code and Cursor with the test account. On the way:

1. **The approval form was refused** ("The approval did not come from this server's own page"): the page said
   `Referrer-Policy: no-referrer`, so the browser sent `Origin: null` on the form's POST. The page now says
   `same-origin`, and `Origin: null` counts only with `Sec-Fetch-Site: same-origin` (295b436, with a test).
2. **The sign-in table refused every write** ("The sign-in service is briefly unavailable"): the expiry went as a
   JSON number typed Edm.Int64, which the Table service takes only as a string, and requests had no `x-ms-date`. Both
   fixed, and a store error now names the service's own error code (15bd7fd, with a test that enforces the rules).
3. **The identity had no role on the table.** The role assignment in the printed steps needs Owner or User Access
   Administrator; the maintainer's everyday account is Contributor, so it failed (unseen behind `--output none`) and
   the subscription's Owner assigned "Storage Table Data Contributor" on the table.
4. **A company laptop's web filter** stopped the approval page; from a private computer it worked.

After that, Glama's connection test turned "Healthy" (17:59), and VS Code and Cursor worked.
