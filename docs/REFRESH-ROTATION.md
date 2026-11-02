# Refresh-token rotation at /mcp/connect, and Glama's sign-out of 2 November 2026

Round n82, an investigation: no code was changed. The tests that back each statement are in
`tests/test_refresh_rotation.py`; they run against fake answers only (the mocked Entra and store of
`tests/test_client_registration.py`, the fake `az` of `tests/test_azure_deployment.py`). No Azure, Entra, DNS or Fabric
call was made, and no log was read: the logs are the maintainer's to read (the commands are at the end).

## What happened

Glama's connection test for `https://krusgraph.com/mcp/connect` was Healthy from 27 October 2026 (`docs/LIVE-TEST.md`,
section 4). On 2 November 2026, around 07:16 UTC, it changed to "Missing credentials: No OAuth access token" and "The
server ended this connection" (reported by Gustav). Glama's first message is Glama's own: it holds no usable access
token, which is what a client says when a refresh was refused and it dropped its credentials.

## How the rotation works today

`fabric_backend/registration_flow.py`, `Layer._refresh`, with the store in `fabric_backend/registration_store.py`:

- Our refresh token is `<line id>.<secret>`. The line (store kind `family`, Table Storage `krusgraphoauth` on the hosted
  service) keeps the client id, a keyed hash of the user, the SHA-256 of the current secret and Entra's refresh token,
  sealed with the server's key (AES-GCM, `registration.Keys`). It lives at most 90 days from the first sign-in.
- A refresh reads the line and its ETag, checks client id and hash, calls Entra with Entra's refresh token, checks the
  new access token, then replaces the line with a new secret's hash, on the condition that the ETag is unchanged.
- A secret that does not match the stored hash deletes the line: "an old or stolen token, the whole line ends here".
  An ETag conflict answers `invalid_grant` ("used by another request at the same moment") and leaves the line. A final
  Entra answer (`invalid_grant`, `interaction_required` and others in `ENTRA_ERRORS_FINAL`) deletes the line; any other
  Entra error is a 503 and the line stays. A store error is a 503.

## Answers, with the test behind each

**The same refresh token twice, one after the other (a retry after a lost answer).** The whole line dies. The first
request rotates RT1 to RT2 and answers; if that answer is lost (a cut connection, a replica that stops, a client that
times out during a cold start and tries again), the retry with RT1 no longer matches, the line is deleted, and RT2,
which the client never saw, is dead too. The client must sign in again.
`test_a_retry_with_the_old_token_after_a_lost_answer_ends_the_whole_line`,
`test_the_same_token_twice_in_quick_succession_ends_the_line_when_the_first_has_rotated`.

**The same refresh token twice, in parallel (both read before either writes).** It depends on Entra:

- If Entra accepts its refresh token a second time, one request wins the conditional write and the other gets
  `invalid_grant` without deleting the line. The winner's token works. A client that keeps the loser's error and drops
  the winner's token is signed out although the line is alive.
  `test_parallel_with_an_entra_that_accepts_its_refresh_token_twice_one_wins_and_the_line_survives`.
- If Entra redeems its refresh token once, the loser's Entra call is refused with `invalid_grant`, a final answer, and
  the loser deletes the line, killing the winner's fresh token as well: both fail and the line is dead.
  `test_parallel_with_an_entra_that_takes_its_refresh_token_once_both_fail_and_the_line_dies`.
  Which of the two Microsoft Entra does for this app was not verified here.

**A store failure between Entra's answer and our write.** 503, and RT1 still matches; but Entra's new refresh token
was not kept, so the retry sends Entra the one it has just redeemed. With an Entra that accepts it, the line renews;
with one that does not, it dies. `test_a_store_failure_while_writing_the_rotation_is_a_503_and_the_retry_depends_on_entra`.

**An Entra refusal and an Entra outage.** A refusal (its refresh token expired or revoked, a password change, a
sign-in frequency policy, consent withdrawn) ends the line; an outage keeps it.
`test_an_entra_refusal_ends_the_line_and_an_outage_does_not`.

**A deployment: the rows and the key.**

- The rows are in Table Storage and outlive every revision, restart and scale to zero; nothing deletes a live line:
  the purge (`TableStore._purge`) deletes only rows whose expiry has passed, and a line expires 90 days after its
  first sign-in (Glama's: late January 2027). `test_lines_in_the_table_survive_a_new_revision_with_the_same_key`.
  With `KRUSGRAPH_REGISTRATION_STORE=memory` every line is lost at a restart
  (`test_the_memory_store_loses_every_line_at_a_restart`); the hosted service uses Table Storage
  (`docs/OPERATIONS.md`, section 6).
- The key is stable across `bash deploy/krusgraph.sh --update`: it sends the image, the build tag and the plain
  settings, never a secret and no `KRUSGRAPH_REGISTRATION_*` value. A **full run** (without `--update`) writes a
  manifest whose only secret is the Entra secret and keeps only plain registration values, so a key held as the app
  secret `registration-key` is gone afterwards and the layer turns itself off; switching it on again with step 3 of
  `--client-registration` (`openssl rand -base64 32`) makes a new key, and every line becomes unreadable and is deleted
  at its next refresh. A key in Key Vault (`KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI`, a plain value, a versionless
  secret URI) survives a full run, unless a new version of the secret is written.
  `test_update_keeps_the_key_and_the_table_and_a_full_run_drops_the_key_held_as_an_app_secret`,
  `test_a_new_key_makes_every_line_unreadable_and_deletes_it_at_its_next_refresh`.
- A new revision does cut connections in flight. A refresh cut after our write and before the answer reached Glama
  is the lost answer of the first case.

**Commits of 1 and 2 November 2026.** Nothing in them touches the refresh path. Read from `origin/main` (history from 26
October): `fabric_backend/registration_flow.py` changed only in 1d6d0b1 (2 November, 08:15 UTC, after the sign-out),
which adds the admin-consent page to the callback and does not touch `/oauth/token`; `registration.py`,
`registration_store.py`, `keyvault.py` and `entra.py` did not change. The one change to what runs in the image is
6c453a7 (2 November, 00:13 UTC): sse-starlette 3.5.1 to 3.6.0 in `deploy/constraints.txt`, which serves the MCP stream,
not `/oauth/token`; it matters only if it was deployed, and then through the new revision (the lost-answer case), not
through its code. Deployments are not in git: whether one ran near 07:16 UTC is in Azure.

## Causes, ranked

1. **Reuse detection after a lost answer or a double send** (most likely). The mechanism is proven by the tests; that
   it happened is not. It fits "The server ended this connection" and a client that then says it has no token. Triggers
   near 07:16 UTC: a new revision (a deployment) cutting a refresh in flight; a scale from zero (`min_replicas` 0 is the
   default) making Glama time out and retry; or Glama refreshing twice at once (its health check and a session).
   **Needs logs:** `krusgraph.client_registration.refresh_reused` with `client` `glama.ai` around 07:16 UTC, and a
   revision or replica start at that time.
2. **A parallel refresh with an Entra that redeems once.** Proven as a mechanism; whether Entra behaves that way is not.
   **Needs logs:** `token_issued` (grant `refresh_token`) followed within a second by `token_refused` with "did not
   renew the sign-in (invalid_grant)" for `glama.ai`.
3. **Entra refused the refresh.** An expired or revoked Entra refresh token, a password reset, a Conditional Access
   sign-in frequency, a change to the app's consent. **Needs logs:** `token_refused` with "did not renew", and Entra's
   non-interactive sign-in log for the test account and this app at 07:16 UTC (the AADSTS code says which).
4. **A new key or the layer switched off** (a full run, or step 3 run again). Proven as a mechanism. **Needs logs:**
   `token_refused` "can no longer be read", or `/oauth/token` answering 404 after a revision start; the revision list
   and the app's secret names say whether a full run happened.
5. **Lost rows.** Ruled out for the hosted service by the code: Table Storage, a purge that touches only expired rows.
   It would need someone deleting the table or its rows.

## Proposal for Gustav (not implemented)

An overlap window on the rotation, 60 seconds, as a change to `Layer._refresh` with tests:

- At each rotation keep, in the line, the hash of the secret just used (`prev_hash`), until when it counts
  (`prev_until`, now + 60 s), and the answer just given, sealed with the server's key like Entra's token already is
  (`prev_answer`: access token, expiry, new secret).
- A secret that matches `prev_hash` before `prev_until`, from the same client id: answer `prev_answer` again. No Entra
  call, no new rotation, no new branch of the line; log `refresh_replayed`. After the window, reuse ends the line as
  today.
- An ETag conflict: read the line again; if the other request rotated from the same secret, answer its `prev_answer`
  instead of `invalid_grant`.
- An Entra refusal: before deleting, read the line again; if its ETag has moved since this request read it, another
  request has rotated it, so answer as for a conflict instead of deleting the line someone else just renewed.

That covers causes 1 and 2 and the store failure. Two smaller steps beside it: `min_replicas` 1 removes the cold starts
that make clients retry (it costs one replica always on), and `log_analytics_workspace` keeps the console lines, so
the next case can be answered from logs.

**Security consequence.** Rotation exists so that a stolen refresh token is detected when the thief or the owner uses
it a second time. With the window, a stolen old token used within 60 seconds of the owner's refresh is not detected:
it gets the same tokens the owner just got (an access token that lasts about an hour and the current refresh token),
not a new branch, and only with the client id the line belongs to. Outside the window detection is as today. The cost
at rest is one more sealed access token per line for 60 seconds. Rotation itself stays, as the MCP authorization
specification requires for public clients (`docs/CLIENT-REGISTRATION.md`). Without a window, a dropped answer signs
the user out, which is what the tests show today.

## For Gustav: reading the logs (by hand; nothing here was run)

```bash
az containerapp revision list -n krusgraph -g rg-krusgraph --query "[].{name:name, created:properties.createdTime, active:properties.active}" -o table
```

```bash
az containerapp logs show -n krusgraph -g rg-krusgraph --type system --tail 300
```

With Log Analytics (`docs/OPERATIONS.md`, section 3; in a workspace whose table has no `_CL`, the column is `Log`), in the workspace:

```kusto
ContainerAppConsoleLogs_CL
| where ContainerAppName_s == "krusgraph" and TimeGenerated between (datetime(2026-11-02 06:30) .. datetime(2026-11-02 08:00))
| where Log_s startswith "{\"event\":\"krusgraph.client_registration."
| project TimeGenerated, RevisionName_s, Log_s
| order by TimeGenerated asc
```

Then Entra's sign-in log (Microsoft Entra admin center, Sign-in logs, non-interactive, filtered to the app) for
07:00–07:30 UTC. Whatever the cause, Glama's line is gone now: Glama signs in again from its connector.
