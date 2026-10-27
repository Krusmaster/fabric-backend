# Security review: sign-in and the MCP endpoint

Scope: `fabric_backend/entra.py` (token validation, on-behalf-of exchange), `Auth` in `fabric_backend/server.py`,
the 401 guard and the security wrapper in `build_app()`. Reviewed on 25 October 2026 against the code, with unit
tests (`tests/test_security.py`, `tests/test_entra.py`, `tests/test_site_extras.py`); nothing here was run against
the live service or Entra.

## How sign-in works

Claude obtains an access token for the Entra app (audience = the app, scope `user_impersonation`) and sends it as
`Authorization: Bearer …` to `/mcp`. The guard validates it before the MCP transport sees the request: RS256
signature against Microsoft's published keys (`login.microsoftonline.com/common/discovery/v2.0/keys`), `exp`,
`nbf`/`iat`, audience (the Application ID URI, the client id, or `api://<client id>`), issuer
`https://login.microsoftonline.com/<tid>/v2.0` for the token's own `tid`, the optional tenant allow-list, and the
delegated scope `user_impersonation` in `scp`. Each tool call validates the token again and exchanges it on the
user's behalf for a Fabric or SQL token, which is cached in memory per (SHA-256 of the user's token, scope) until
two minutes before it expires. The server stores nothing on disk and never writes a token anywhere.

## Verified by tests

| Case | Result | Test |
| --- | --- | --- |
| Wrong audience (another API, another app, a list without ours) | 401, `invalid_token` | `test_wrong_audience_is_rejected` |
| Wrong issuer (v1 `sts.windows.net`, another tenant's issuer, `iss` and `tid` disagreeing, no `iss`) | rejected | `test_wrong_issuer_is_rejected` |
| Expired token; `nbf` in the future; no `exp` | rejected | `test_expired_and_not_yet_valid_tokens_are_rejected` |
| Tenant not on `ENTRA_ALLOWED_TENANTS` | rejected; an allowed tenant in any letter case accepted | `test_tenant_not_on_the_allow_list_is_rejected` |
| No `scp`, other scopes only, near-misses, app-only `roles` | rejected | `test_token_without_the_delegated_scope_is_rejected` |
| `alg: none`, HS256 signed with the public key (key confusion), header-only strings | rejected (only RS256 is accepted) | `test_alg_none_and_key_confusion_are_rejected` |
| Altered signature, altered payload with the old signature, a key Entra never published | rejected | `test_altered_signature_and_altered_payload_are_rejected` |
| Error text never contains the token | holds | `test_token_errors_never_quote_the_token` |
| Every HTTP method on `/mcp` without a valid token | 401 with `WWW-Authenticate` + `resource_metadata`; HSTS and nosniff on the 401 | `test_guard_answers_401_for_every_method_and_token_shape` |
| Path variants (`/mcp/`, `/mcp?x`, `/MCP`, `/mcp/x`, `//mcp`, `/mcp/../mcp`, `/%6dcp`, NUL) | 401, 404 or 405; the MCP handler is never reached unauthenticated | `test_guard_cannot_be_walked_around_with_path_variants` |
| 256 KB bearer value, 768 KB JWT-shaped value | 401 in milliseconds, nothing echoed | `test_oversized_authorization_header_is_refused_fast_and_not_echoed` |
| 100 KB header through uvicorn/h11 (the image's HTTP server) | answered 401 without echo, server healthy afterwards; a 1 MB header line is refused with 400 by h11 (observed, not asserted) | `test_oversized_headers_through_the_real_http_server` |
| Declared body over 4 MiB; chunked body growing past 4 MiB | 413 before reading; 413 at the first chunk over the limit | `test_request_bodies_are_capped_even_without_content_length` |
| Two users, same scope; same user after a new sign-in; tokens differing by one character | separate cache entries, never crossed; the cache holds hashes | `test_on_behalf_of_cache_never_shares_tokens_between_users` |
| Cache bounded (`MAX_CACHED_TOKENS`): expired entries dropped first, then the oldest half | holds | `test_on_behalf_of_cache_is_bounded_and_keeps_the_newest_entries` |
| Failed exchange; token endpoint answering without `access_token` | `TokenError` without the user's token | `test_on_behalf_of_failures_do_not_leak_the_user_token` |
| Rejected sign-in, accepted sign-in and a failing tool call, with every logger at DEBUG and stdout/stderr captured | no token, no client secret in logs or output; the user gets `kind: sign_in`/`consent` | `test_tokens_and_secrets_never_reach_logs_or_stdout` |
| Exception messages carrying bearer tokens, `client_secret=`, `X-Fabric-SQL-Token:` | scrubbed by the error layer | `test_error_layer_scrubs_tokens_and_secrets_from_messages` |

## Found and fixed in this review

- **Issuer compared case-sensitively against a lower-cased tenant id.** A token whose `iss` carried the tenant GUID
  in upper case was rejected although it came from an allowed tenant. Entra emits lower-case GUIDs, so this was a
  robustness gap, not an exposure; the comparison is now case-insensitive on both sides.
- **`Authorization: Bearer` with nothing after it answered `error="invalid_token"`.** RFC 6750 §3.1 wants
  `invalid_request` for malformed credentials; `invalid_token` tells Claude to refresh a token it never sent. Fixed
  in the guard.
- **Request bodies were capped only when `Content-Length` was declared.** A chunked request could make the MCP
  transport buffer an unbounded JSON body. The security wrapper now counts the bytes it hands to the app and answers
  413 at the first chunk over `MAX_BODY_BYTES` (4 MiB), whatever the headers say.
- **On-behalf-of cache eviction dropped everything when nothing had expired** (the comment said "then oldest").
  5 000 distinct tokens in one hour would have emptied the cache for every user on each new sign-in. It now drops
  expired entries first and then the oldest half.
- **A token-endpoint answer without `access_token` raised a bare `KeyError`.** Now a `TokenError`, so the user
  gets `kind: sign_in` with a hint instead of `unexpected`.

## What holds by design

- Only RS256 is accepted; `alg: none` and HMAC key confusion cannot pass (`jwt.decode(..., algorithms=["RS256"])`).
- Required claims: `exp`, `iss`, `aud`, `tid`; `nbf` and `iat` are checked when present; no leeway.
- Signing keys come from Microsoft's JWKS endpoint, cached for an hour; an unknown `kid` triggers at most one
  refresh per 30 seconds (PyJWT 2.15.1 `cooldown_duration`, pinned in `deploy/constraints.txt`), so a flood of
  tokens with random key ids cannot turn the server into a JWKS-fetching loop.
- The client secret is a dataclass field with `repr=False`; `EntraConfig` never prints it. Nothing in the server
  logs headers: uvicorn's access log carries method, path and status only, and the code has no logging of its own
  on the auth path.
- Every tool error goes through `errors.scrub`, which removes JWT-shaped strings, `Bearer …` values and
  `authorization`/`x-fabric-sql-token`/`client_secret` header-like pairs, then caps the length.
- Discovery documents (`/.well-known/oauth-protected-resource`, `/mcp/server-card`, `llms.txt`, the site) stay
  public; the guard covers exactly `/mcp` and `/mcp/`, and the MCP transport is reachable nowhere else.

## Closed on 26 October 2026 (round n10, unit-tested, not yet deployed)

| Was open | Now | Where | Test |
| --- | --- | --- | --- |
| 3. Rate limiting | Per user (`oid`) and per organisation (`tid`): token buckets, defaults 30/minute and 600/hour per user, 120/minute and 3000/hour per organisation, configurable or off (`KRUSGRAPH_RATE_*`). A refused call runs nothing and answers `kind: rate_limited` with `retry_after`. Only tool calls count, after the 401 guard: `initialize`, `tools/list`, the site and the sign-in challenge are never limited. Ids are kept as salted hashes in memory. | `fabric_backend/limits.py`, the tool wrapper in `server.py` | `test_rate_limit_through_mcp_never_touches_the_401_flow` and the `limits` tests in `tests/test_operations.py` |
| 4. Secret storage | The client secret can live in Azure Key Vault, read with the container app's managed identity (`ENTRA_CLIENT_SECRET_KEYVAULT_URI`, `AZURE_CLIENT_ID`); cached in memory for an hour (a failed re-read after the hour keeps the secret held, so a short Key Vault outage does not stop sign-ins), re-read at once when Entra rejects it (rotation without a new revision). Without the setting, as before. `deploy/krusgraph.sh --key-vault` sets it up; removing the old container-app secret is a manual step after checking. | `fabric_backend/keyvault.py`, `entra.py`, `deploy/azure_containerapp.py`, `docs/OPERATIONS.md` | the Key Vault and `--key-vault` tests in `tests/test_operations.py` |
| (new) Monitoring | `/health` without sign-in that says nothing about the server; az commands for a 5xx alert on the container app and an availability test with an alert in `docs/OPERATIONS.md` (parameters checked against the azure-cli source, not run). | `server.py`, `docs/OPERATIONS.md` | `test_health_needs_no_sign_in_and_says_nothing_about_the_server` |
| (new) Usage statistics | One line per tool call with tool, outcome kind, duration and dry run, optionally a salted organisation hash; `/metrics` is a 404 unless a 32+ character token is set, then bearer-only. No user id, no IP, no names, no queries or results; the privacy page lists the fields and changes with the settings. When console logs go to Log Analytics, the access line with IP addresses is turned off. | `fabric_backend/usage.py`, `PRIVACY.md` | `test_no_content_reaches_the_usage_line_or_metrics`, `test_privacy_page_lists_exactly_what_is_counted_and_follows_the_settings` |

## Open questions (not fixable from this repository, or a product decision)

1. **Revocation.** A token stays valid until its `exp` (Entra access tokens: 60–90 minutes). Disabling a user or
   revoking sessions in Entra takes effect at the next token, not at once. Continuous Access Evaluation would need
   the server to request and honour CAE claims; not implemented.
2. **Header limits at the edge.** Inside the container, h11 answered a 100 KB header normally and refused a 1 MB
   header line with 400. Azure Container Apps' ingress (Envoy) has its own request-header limits in front of that;
   they are not configurable from this repository and were not verified.
3. **Rate limiting (partly closed, above).** Signed-in tool calls are limited per user and per organisation. Still
   open: unauthenticated requests are not limited by the app (each invalid token costs one RSA verification, about a
   millisecond, and no network call; a flood is a CPU and ingress question for Container Apps); the counters are per
   replica, so with two replicas a user can briefly reach twice the limit; bearer/service-principal mode (no Entra)
   has no identity to limit by. Fabric's own 429s are passed on as `kind: throttled`.
4. **Secret storage (closed once `--key-vault` has run, above).** Until then `ENTRA_CLIENT_SECRET` is a container-app
   secret, readable by anyone who can read the app's configuration. After it, anyone with "Key Vault Secrets User" on
   the vault or the right to change the app's identity can read it. The secret Anthropic holds for the directory is the
   same value in any case, so a rotation means giving Anthropic the new value too.
5. **Bearer mode.** Without Entra configuration the server trusts whatever bearer token and `x-fabric-sql-token`
   header the caller sends and forwards them to Fabric and SQL. That is the local/private-network mode and must
   not be exposed publicly; `ENTRA_REQUIRED=true` (set by the deploy script) makes a missing Entra configuration
   stop the server instead.
6. **Multi-tenant by default.** With `ENTRA_ALLOWED_TENANTS` empty, any organisation whose administrator consented
   can sign in and reach its own Fabric data. That is the connector-directory model; a private deployment should
   set the allow-list.
7. **Clock skew.** No leeway is applied to `exp`/`nbf`. Container Apps hosts are NTP-synchronised; if a freshly
   issued token were ever rejected as immature, a leeway of a few seconds is the fix (`jwt.decode(..., leeway=…)`).
8. **`KRUSGRAPH_DEBUG_ERRORS`** adds the exception class name to tool errors. It is off by default and should stay
   off in production; it never adds messages or tokens.
9. **Client registration for MCP clients other than Claude** (`KRUSGRAPH_CLIENT_REGISTRATION=1`, off by default).
   Krusgraph runs a small authorization server at `/oauth` in front of the one Entra app for clients that sign in at
   `/mcp/connect`; every client shares that Entra app, so Krusgraph's own consent page per client (name, domain,
   redirect address) is the control against the confused deputy. It holds Entra's tokens encrypted for 60 seconds
   and Entra's refresh tokens encrypted for up to 90 days in Azure Table Storage, under one key of its own
   (`KRUSGRAPH_REGISTRATION_KEY`). The access token a client gets is Entra's, so the server cannot tell which client
   holds it or revoke one before it expires; loopback addresses can be claimed by any local program (the page warns).
   The full list of remaining risks is in `docs/CLIENT-REGISTRATION.md`. On at krusgraph.com since 27 October 2026
   (Glama, VS Code and Cursor signed in that day); off by default elsewhere.
10. **HSTS** is `max-age=31536000` without `includeSubDomains`/`preload`; the apex serves the site and the MCP
   endpoint, and nothing else is under the domain. Adding preload is a DNS/ownership decision, not a code one.
11. **The alerts and Log Analytics are not set up yet.** `docs/OPERATIONS.md` has the commands; until they are run,
   a 5xx or an outage is noticed only by users, and the usage lines exist only in the live console stream.
12. **`/metrics` and the usage salt are container-app secrets.** Like the client secret before Key Vault, anyone who
   can read the app's configuration can read them; neither gives access to customer data (the salt lets someone with
   a tenant id check whether that organisation appears in the usage lines).
13. **The paid-plan check is dormant.** `KRUSGRAPH_ENTITLEMENTS=1` makes it decide per tenant id from an environment
   variable or Azure Table Storage; with the table, a storage outage refuses the paid features (never the free ones)
   for as long as it lasts. Not exercised against a real table.

## Rerunning

```
python -m pytest -q tests/test_security.py tests/test_entra.py tests/test_site_extras.py tests/test_operations.py
```
