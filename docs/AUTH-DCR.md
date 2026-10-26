# Sign-in for agents outside Claude: dynamic client registration

Status: design decided and implemented behind a flag that is **off by default** (`KRUSGRAPH_DCR`, see
`fabric_backend/dcr.py`, tests in `tests/test_dcr.py`). Unit-tested; not yet tried with a real agent. Nothing in
today's sign-in for Claude changes while the flag is off, and the Entra app is not touched by code at all.

## The problem

Claude connects through the directory with *Anthropic-held client credentials*: Anthropic holds the client secret
of the one multi-tenant Entra app, so Claude never needs to register itself. Every other agent that speaks MCP
(Lovable's custom MCP connectors, Cursor, Claude Code with a plain URL, future ones) follows the MCP authorization
spec: it reads the protected-resource metadata, finds the authorization server, and expects to obtain a client id
there. The spec's order of preference (2025-11-25 revision, `basic/authorization.mdx`): pre-registered client
information first, then a Client ID Metadata Document (CIMD) if the server advertises
`client_id_metadata_document_supported`, then dynamic client registration (RFC 7591) if there is a
`registration_endpoint`, then asking the user. Microsoft Entra ID offers none of the automatic routes: no RFC 7591
endpoint and no CIMD. Cursor, by its users' reports, attempts registration automatically and fails with
"incompatible auth server" when there is no registration endpoint (forum.cursor.com, thread 110638; a configuration
with a static client id was reported there but not confirmed to work). Lovable's custom MCP connector offers OAuth
as the default and a bearer token or API key as alternatives (docs.lovable.dev/integrations/custom-mcp); whether its
OAuth path registers dynamically or lets the user type a client id is not stated on the page we could read, so it is
**unconfirmed**.

## The options

| | A. Own authorization server with DCR, federating to Entra | B. CIMD | C. Pre-registered client per agent, behind a DCR facade (chosen) |
| --- | --- | --- | --- |
| How it works | Krusgraph issues its own tokens; clients register with it (RFC 7591); the user is redirected to Entra; Krusgraph keeps the Entra tokens and maps them to its own | The client publishes a metadata document at an HTTPS URL and uses that URL as `client_id`; the authorization server fetches it | The maintainer registers each agent's redirect URI on the one Entra app as a public client. The server publishes RFC 8414 metadata whose authorize and token endpoints are Entra's and a registration endpoint that answers the app's client id when the redirect URIs are on the allow-list |
| What is stored | Client registrations, authorization codes, refresh tokens or Entra tokens per user, keys for signing own tokens | Nothing new on our side, but Entra would have to accept URL client ids, which it does not; so in practice this also needs option A's server in front of Entra | Nothing. No client database, no issued secret, no token of ours |
| Security risks | The biggest new surface: a token service of our own (key management, replay, token theft from storage, confused deputy when mapping tokens); it also breaks the promise "the server stores nothing" | As A, plus trust in whatever URL a client claims | A shared public client id: any software whose redirect URI is on the allow-list can start a sign-in as "Krusgraph". That is the same situation as any public client; PKCE binds the code to the party that started the flow and Entra enforces the redirect URI exactly. The consent screen shows the Krusgraph app name, not the agent's. The allow-list is therefore the control, and loopback entries (desktop agents) are the loosest part of it |
| Operations | A real identity service to run, monitor, patch and back up | As A | Two environment variables and, per new agent, one redirect URI added to the Entra app by the maintainer |
| Fits the spec | Yes, fully | Yes, once an AS supports it | Yes: a registration endpoint and metadata as RFC 7591 / 8414 describe; clients cannot tell the difference |

**Recommendation: C.** It keeps the storage promise, adds no token service, and is reversible (turn the flag off).
A should be revisited only if an agent needs its own client identity on the consent screen or Entra rejects
the flow below for a reason we cannot work around.

## How C works (`KRUSGRAPH_DCR=1`)

1. `GET /.well-known/oauth-protected-resource` lists `https://krusgraph.com` first and Entra second in
   `authorization_servers`. (With the flag off it lists Entra only, exactly as today.)
2. `GET /.well-known/oauth-authorization-server` (RFC 8414): `issuer` is `https://krusgraph.com`;
   `authorization_endpoint` and `token_endpoint` are Entra's `organizations` v2.0 endpoints;
   `registration_endpoint` is `https://krusgraph.com/oauth/register`; `code_challenge_methods_supported` is `S256`;
   `token_endpoint_auth_methods_supported` is `none`; `client_id_metadata_document_supported` is `false`.
3. `POST /oauth/register` (RFC 7591): the body's `redirect_uris` must all be allowed by `KRUSGRAPH_DCR_REDIRECTS`
   (exact https URIs, or a loopback origin `http://127.0.0.1` / `http://localhost` that matches any port and path, as
   RFC 8252 section 7.3 allows for native apps). The answer is `201` with `client_id` = the Entra app's client id,
   `token_endpoint_auth_method: "none"`, the grant types `authorization_code` and `refresh_token`, and the scope
   `<MCP_PUBLIC_URL>/user_impersonation offline_access`. Anything else is a `400` with the RFC's `invalid_redirect_uri`
   or `invalid_client_metadata`. Bodies over 16 KB are refused.
4. The agent runs the authorization-code flow with PKCE against Entra as a public client, gets an access token for
   the Krusgraph app, and calls `/mcp` with it. The server validates it exactly as it validates Claude's tokens
   (audience, issuer per tenant, `user_impersonation`), then exchanges it on behalf of the user for Fabric and SQL.

What the maintainer does on the Entra app, once per agent (not done by any code here):

- Authentication -> Add a platform -> *Mobile and desktop applications* (loopback and custom redirect URIs) or *Web*
  for an https callback such as the one Lovable shows when adding a custom MCP connector; add the exact URI.
- Advanced settings -> *Allow public client flows* = Yes.
- Put the same URIs in `KRUSGRAPH_DCR_REDIRECTS` (comma-separated) and set `KRUSGRAPH_DCR=1` in the deploy config.

## Risks and open points, in plain words

- **Resource indicators.** MCP clients must send `resource=https://krusgraph.com/mcp` on the authorize and token
  requests (RFC 8707). Entra's v2.0 endpoints are documented to reject the legacy `resource` parameter in some
  flows. Claude works today against the same Entra endpoints, so either Claude omits it or Entra tolerates it; for
  other agents this is **unverified**. If an agent is refused on that parameter, the fallback is a token-endpoint
  proxy on krusgraph.com that strips `resource` and forwards to Entra; it would not store anything either, but it
  would see the tokens pass through, so it is not in this change.
- **Issuer.** Tokens carry Entra's issuer, not `https://krusgraph.com`. MCP clients do not validate access tokens
  (they are opaque to them) and the resource server validates them as Entra tokens, so this is consistent with the
  spec's token-audience rules; a client that compares the metadata `issuer` with the token's `iss` would differ.
  Unverified against real agents.
- **Shared client id.** See the table. Keep the allow-list short; prefer exact https URIs; remove loopback entries
  when no desktop agent needs them.
- **Consent.** First use from a new tenant still needs the tenant admin's consent for the Krusgraph app, the same
  as for Claude (`docs/SCOPES.md`, admin-consent URL).
- **Lovable bearer-token fallback.** Lovable can also connect with a bearer token. A user can mint a token for the
  Krusgraph app in a consented tenant with the Azure CLI (`az account get-access-token --resource <Application ID
  URI>`; the token lasts about an hour). That is a workaround for a test, not a product path; unverified.

## Verification plan (for the maintainer, nothing here has run live)

1. Deploy with `KRUSGRAPH_DCR=1` and `KRUSGRAPH_DCR_REDIRECTS=http://127.0.0.1`. Check that Claude still signs in
   and that `GET https://krusgraph.com/.well-known/oauth-authorization-server` answers.
2. Cursor: add `https://krusgraph.com/mcp` as a remote MCP server. Expected: registration succeeds, the Microsoft
   sign-in opens, the tools appear. Note the exact loopback URI Cursor used (from the Entra sign-in logs) if it fails.
3. Lovable: Connectors -> Custom MCP -> URL `https://krusgraph.com/mcp`, OAuth. Note the callback URI Lovable
   shows, add it to the Entra app and to the allow-list, retry.
4. If Entra rejects `resource`, record the AADSTS code and reconsider the token-endpoint proxy.
