"""n82, changed in n83: what happens to a refresh line at /oauth/token (registration_flow.Layer._refresh) when the
same refresh token comes twice, and what a deployment does to the lines; against fake answers only (the mocked Entra and
store of tests/test_client_registration.py, and the fake `az` of tests/test_azure_deployment.py). n82's investigation is
docs/REFRESH-ROTATION.md (Glama's sign-out of 2 November 2026); n83 implements its proposal, the overlap window, and
these tests show the new behaviour.

Our refresh token is `<line id>.<secret>`; the line (store kind "family") keeps the hash of the current secret and
Entra's refresh token, sealed with the server's key. Each refresh replaces the hash (rotation, conditional on the ETag
the request read). Since n83 the line also keeps, for REFRESH_OVERLAP (60) seconds, the hash of the secret just used and
the answer just given, sealed: that secret, from the line's own client, gets the same answer again (no Entra call, no
new rotation, `refresh_replayed`). Any other secret that does not match, or that one after the window, deletes the
line ("an old or stolen token")."""
import base64
import json
import time

import pytest

pytest.importorskip("jwt")

from fabric_backend import registration as reg, registration_flow as flow, registration_store  # noqa: E402
from fabric_backend.entra import challenge, protected_resource_metadata  # noqa: E402
from tests.test_client_registration import (ACCEPT, BASE, CFG, GLAMA, INIT, VSCODE, client, env, keys, mcp_call,  # noqa: E402,F401
                                            redeem, sign_in, tok)

REDIRECT = "http://127.0.0.1:33418/"
PRE_N83_FIELDS = {"client_id", "user", "hash", "rt", "until"}


def _signed_in(c, env_):
    code, verifier, _ = sign_in(c, env_["entra"], VSCODE, REDIRECT)
    r = redeem(c, VSCODE, REDIRECT, code, verifier)
    assert r.status_code == 200, r.text
    return r.json()["refresh_token"]


def _refresh(c, rt, client_id=VSCODE):
    return c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": client_id,
                                        "resource": f"{BASE}/mcp/connect"})


def _lines(env_):
    return env_["store"].count("family")


def _line(env_, rt):
    return env_["store"].get("family", rt.split(".")[0])


def _entra_refreshes(env_):
    return sum(1 for d in env_["entra"].token_requests if d["grant_type"] == "refresh_token")


def _later(monkeypatch, seconds):
    """Move this layer's clock (the window's) forward; Entra's tokens, the store and the validator keep real time."""
    real = time.time
    monkeypatch.setattr(flow, "_now", lambda: real() + seconds)


def _events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{\"event\"")]


# ------------------------------------------------------------------ 1. the same token twice, one after the other -----
def test_a_retry_with_the_old_token_after_a_lost_answer_gets_the_same_answer_again(env, capsys):
    """The client sends RT1, the server rotates to RT2 and answers, the answer is lost (a cut connection, a replica that
    stops, a client timeout during a cold start); the client sends RT1 again inside the window. It gets the very same
    answer (the same access token and RT2): no Entra call, no new rotation (the line is not written), no new branch,
    and `refresh_replayed` in the log. RT2 then goes on as usual."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        assert set(_line(env, rt1)[0]) == PRE_N83_FIELDS                       # a fresh line has no window yet
        first = _refresh(c, rt1)
        assert first.status_code == 200
        rt2 = first.json()["refresh_token"]
        assert rt2 != rt1 and rt2.split(".")[0] == rt1.split(".")[0]          # same line, new secret
        calls, (row, etag) = _entra_refreshes(env), _line(env, rt1)
        capsys.readouterr()
        again = _refresh(c, rt1)                                               # the answer above was "lost"
        assert again.status_code == 200
        assert again.json()["refresh_token"] == rt2 and again.json()["access_token"] == first.json()["access_token"]
        assert 0 < again.json()["expires_in"] <= first.json()["expires_in"]
        assert _entra_refreshes(env) == calls                                  # no Entra call
        assert _line(env, rt1) == (row, etag)                                  # no rotation, the line untouched
        assert [e["event"] for e in _events(capsys)] == ["krusgraph.client_registration.refresh_replayed"]
        assert mcp_call(c, again.json()["access_token"]).status_code == 200
        nxt = _refresh(c, rt2)
        assert nxt.status_code == 200 and _lines(env) == 1


def test_the_same_token_twice_in_quick_succession_gets_one_answer_and_the_line_lives(env):
    """Two requests with RT1 that do not overlap inside the server (two tasks of one client that each refresh): both
    get the same answer, and the line lives on with RT2."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        a, b = _refresh(c, rt1), _refresh(c, rt1)
        assert a.status_code == b.status_code == 200 and a.json() == b.json()
        assert _refresh(c, a.json()["refresh_token"]).status_code == 200 and _lines(env) == 1


def test_after_the_window_the_old_token_ends_the_line_as_before(env, capsys):
    """61 seconds after the rotation, RT1 is reuse again: the whole line is deleted (RT2 with it), `refresh_reused`."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        rt2 = _refresh(c, rt1).json()["refresh_token"]
        _later(env["monkeypatch"], flow.REFRESH_OVERLAP + 1)
        capsys.readouterr()
        again = _refresh(c, rt1)
        assert again.status_code == 400 and "already used" in again.json()["error_description"]
        assert "access_token" not in again.json() and _lines(env) == 0
        events = [e["event"].rsplit(".", 1)[1] for e in _events(capsys)]
        assert "refresh_reused" in events and "refresh_replayed" not in events and "token_issued" not in events
        assert "unknown, expired or revoked" in _refresh(c, rt2).json()["error_description"]


def test_the_window_reaches_one_rotation_back_only(env):
    """RT1 -> RT2 -> RT3 inside a minute: RT2 is the secret the last rotation used and is replayed; RT1 is two rotations
    back, which no retry explains, and ends the line. Rotation and its reuse detection stay."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        rt2 = _refresh(c, rt1).json()["refresh_token"]
        rt3 = _refresh(c, rt2).json()["refresh_token"]
        assert _refresh(c, rt2).json()["refresh_token"] == rt3
        assert _refresh(c, rt1).json()["error"] == "invalid_grant" and _lines(env) == 0


# ------------------------------------------------------------------ 2. the same token twice, in parallel -------------
def _second_request_inside_entra(env_, c, rt, entra_accepts_reuse: bool):
    """Run a second refresh with the same token while the first one waits for Entra (both have read the line, neither
    has written): the closest a test gets to two requests in parallel on two threads or two replicas."""
    entra, real = env_["entra"], env_["entra"].post
    out = {}

    def post(data):
        if data.get("grant_type") == "refresh_token" and "second" not in out:
            out["second"] = None
            out["second"] = _refresh(c, rt)                    # B runs to the end while A is inside Entra
        if entra_accepts_reuse and data.get("grant_type") == "refresh_token":
            entra.refresh.setdefault(data["refresh_token"], entra.user)   # Entra lets an old refresh token work again
        return real(data)
    entra.post = post
    first = _refresh(c, rt)
    entra.post = real
    return first, out["second"]


def test_parallel_with_an_entra_that_accepts_its_refresh_token_twice_the_loser_gets_the_winner_s_answer(env, capsys):
    """Both requests read the line; the second (B) reaches the store first and rotates it; the first (A) then fails the
    ETag check, reads the line again, sees that B rotated from the same secret and answers with B's answer instead of
    invalid_grant. Both hold the same tokens and the line lives."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        capsys.readouterr()
        a, b = _second_request_inside_entra(env, c, rt1, entra_accepts_reuse=True)
        assert a.status_code == b.status_code == 200 and a.json() == b.json()
        replayed = [e for e in _events(capsys) if e["event"].endswith("refresh_replayed")]
        assert [e["when"] for e in replayed] == ["conflict"]
        assert _lines(env) == 1 and _refresh(c, b.json()["refresh_token"]).status_code == 200


def test_parallel_with_an_entra_that_takes_its_refresh_token_once_the_line_is_not_deleted(env, capsys):
    """With an Entra that redeems its own refresh token once (the mocked Entra does; whether Microsoft Entra does is not
    verified here): B wins at Entra and rotates the line; A's Entra call is refused with invalid_grant. Before deleting,
    A reads the line again: its ETag has moved, so another request renewed it; A answers with B's answer and the line
    (and B's fresh token) lives."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        capsys.readouterr()
        a, b = _second_request_inside_entra(env, c, rt1, entra_accepts_reuse=False)
        assert a.status_code == b.status_code == 200 and a.json() == b.json()
        assert [e["when"] for e in _events(capsys) if e["event"].endswith("refresh_replayed")] == ["entra_refused"]
        assert _lines(env) == 1 and _refresh(c, b.json()["refresh_token"]).status_code == 200


def test_an_entra_refusal_after_someone_else_changed_the_line_does_not_delete_it(env):
    """Entra refuses, and meanwhile the line was written by something other than a rotation from this secret: its ETag
    moved, so this request answers as for a conflict (invalid_grant) and leaves the line to whoever renewed it."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        store, entra, real = env["store"], env["entra"], env["entra"].post

        def post(data):
            row, _ = _line(env, rt1)
            store.put("family", rt1.split(".")[0], row, ttl=3600)          # a new version of the line (a new ETag)
            raise flow.EntraError("invalid_grant", "AADSTS70008: refresh token expired")
        entra.post = post
        r = _refresh(c, rt1)
        entra.post = real
        assert r.status_code == 400 and "at the same moment" in r.json()["error_description"]
        assert _lines(env) == 1


# ------------------------------------------------------------------ 3. what the window must not give away ------------
def test_another_client_id_never_gets_the_stored_answer_and_still_ends_the_line(env, capsys):
    """RT1 inside the window from another client id: no answer, no token, and the line ends as reuse did before."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        assert _refresh(c, rt1).status_code == 200
        capsys.readouterr()
        r = _refresh(c, rt1, client_id=GLAMA)
        assert r.status_code == 400 and r.json()["error"] == "invalid_grant" and "access_token" not in r.json()
        assert "refresh_token" not in r.json() and _lines(env) == 0
        events = [e["event"].rsplit(".", 1)[1] for e in _events(capsys)]
        assert "refresh_reused" in events and "refresh_replayed" not in events and "token_issued" not in events


def test_no_token_in_clear_in_the_table_or_the_log(env, capsys):
    """The row holds hashes and sealed values only: no access token, none of our refresh tokens or secrets, no Entra
    refresh token; the log names the event and the client host, never a token. With the server's key alone the stored
    answer cannot be read either: its inner seal needs the old secret, which the table does not hold."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        first = _refresh(c, rt1).json()
        again = _refresh(c, rt1).json()
        assert again == first
        row, _ = _line(env, rt1)
        stored = json.dumps({str(k): v[0] for k, v in env["store"]._rows.items()})
        secrets_seen = [first["access_token"], rt1, first["refresh_token"], rt1.split(".")[1],
                        first["refresh_token"].split(".")[1], *env["entra"].refresh]
        for value in secrets_seen:
            assert value not in stored
        log = capsys.readouterr().out
        for value in secrets_seen:
            assert value not in log
        k = reg.keys_from_env()
        outer = k.open(f"family-answer:{rt1.split('.')[0]}:{row['prev_hash']}:{row['prev_until']}", row["prev_answer"])
        assert set(outer) == {"a"} and first["access_token"] not in json.dumps(outer)


def test_after_the_window_the_stored_answer_is_never_opened_and_the_next_rotation_replaces_it(env, monkeypatch):
    """Past prev_until the stored answer is not opened (the reuse ends the line); moving prev_until in the table breaks
    the seal, whose associated data names it; and the next rotation after the window overwrites the old answer."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        rt2 = _refresh(c, rt1).json()["refresh_token"]
        family = rt1.split(".")[0]
        row, etag = _line(env, rt1)
        opened = []
        real_open = flow.Layer._replay

        def spy(self, *a, **k):
            out = real_open(self, *a, **k)
            opened.append(out is not None)
            return out
        monkeypatch.setattr(flow.Layer, "_replay", spy)
        # someone with write access to the table stretches the window: the seal no longer opens
        env["store"].replace("family", family, {**row, "prev_until": row["prev_until"] + 3600}, etag)
        _later(monkeypatch, flow.REFRESH_OVERLAP + 1)
        r = _refresh(c, rt1)
        assert r.status_code == 400 and "access_token" not in r.json() and opened == [False] and _lines(env) == 0

    with client(env=env) as c:                                             # the next rotation after the window
        rt1 = _signed_in(c, env)
        monkeypatch.setattr(flow, "_now", time.time)
        rt2 = _refresh(c, rt1).json()["refresh_token"]
        old = _line(env, rt1)[0]["prev_answer"]
        _later(monkeypatch, flow.REFRESH_OVERLAP + 1)
        assert _refresh(c, rt2).status_code == 200
        new = _line(env, rt1)[0]
        assert new["prev_answer"] != old and new["prev_hash"] == reg.sha256_hex(rt2.split(".")[1])


def test_a_line_written_before_the_window_still_works(env):
    """A row with only the pre-n83 fields (client_id, user, hash, rt, until), as the table holds them today: it
    refreshes, gains the window's fields at that rotation, and a retry right after is replayed. Malformed window fields
    are ignored, never trusted."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        family = rt1.split(".")[0]
        row, etag = _line(env, rt1)
        assert set(row) == PRE_N83_FIELDS
        first = _refresh(c, rt1)
        assert first.status_code == 200
        assert {"prev_hash", "prev_until", "prev_answer"} <= set(_line(env, rt1)[0])
        assert _refresh(c, rt1).json() == first.json()
        row, etag = _line(env, rt1)
        env["store"].replace("family", family, {**row, "prev_until": "never", "prev_answer": None}, etag)
        assert _refresh(c, rt1).json()["error"] == "invalid_grant" and _lines(env) == 0


# ------------------------------------------------------------------ 4. Claude's way in is not this --------------------
@pytest.mark.parametrize("on", [False, True])
def test_claude_s_path_through_mcp_is_unchanged_by_the_window(env, on):
    """Claude signs in with Entra directly at /mcp: the same metadata and challenge as without the layer, Entra's own
    token works, and nothing it does reads or writes a refresh line."""
    with client(on=on, env=env) as c:
        if on:
            rt1 = _signed_in(c, env)
            assert _refresh(c, rt1).status_code == 200 and _refresh(c, rt1).status_code == 200    # a replay happened
        rows = dict(env["store"]._rows)
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            r = c.get(path)
            assert r.status_code == 200 and r.json() == protected_resource_metadata(CFG)
        r = c.post("/mcp", json=INIT, headers=ACCEPT)
        assert r.status_code == 401 and r.headers["www-authenticate"] == challenge(CFG)
        r = c.post("/mcp", json=INIT, headers={**ACCEPT, "Authorization": f"Bearer {tok(env['priv'])}"})
        assert r.status_code == 200 and '"serverInfo"' in r.text
        assert c.get("/.well-known/oauth-authorization-server").status_code == 404
        assert dict(env["store"]._rows) == rows


# ------------------------------------------------------------------ Entra and the store during a refresh --------------
def test_an_entra_refusal_ends_the_line_and_an_outage_does_not(env):
    """Entra's final answers (invalid_grant: its refresh token expired, revoked, a password change, a sign-in frequency
    policy) delete the line; an outage (a 5xx, a timeout) is a 503 and the same token works again."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        entra, real = env["entra"], env["entra"].post
        entra.post = lambda data: (_ for _ in ()).throw(flow.EntraError("temporarily_unavailable", "AADSTS90033"))
        assert _refresh(c, rt1).status_code == 503 and _lines(env) == 1
        entra.post = lambda data: (_ for _ in ()).throw(flow.EntraError("invalid_grant", "AADSTS50173: the grant was revoked"))
        r = _refresh(c, rt1)
        entra.post = real
        assert r.status_code == 400 and "did not renew" in r.json()["error_description"] and _lines(env) == 0


@pytest.mark.parametrize("entra_accepts_reuse", [True, False])
def test_a_store_failure_while_writing_the_rotation_is_a_503_and_the_retry_depends_on_entra(env, monkeypatch, entra_accepts_reuse):
    """The table refuses the write (an outage) after Entra has answered: the client gets 503 and keeps RT1, which still
    matches the stored hash. But Entra's new refresh token was not kept, so the retry sends Entra the one it has just
    redeemed: an Entra that accepts it again renews the line; one that takes it once answers invalid_grant, and the line
    is deleted."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        store, entra = env["store"], env["entra"]
        real_replace, real_post = store.replace, entra.post
        if entra_accepts_reuse:
            def post(data):
                if data.get("grant_type") == "refresh_token":
                    entra.refresh.setdefault(data["refresh_token"], entra.user)
                return real_post(data)
            entra.post = post
        monkeypatch.setattr(store, "replace", lambda *a, **k: (_ for _ in ()).throw(registration_store.StoreError("HTTP 503")))
        assert _refresh(c, rt1).status_code == 503 and _lines(env) == 1
        monkeypatch.setattr(store, "replace", real_replace)
        r = _refresh(c, rt1)
        entra.post = real_post
        if entra_accepts_reuse:
            assert r.status_code == 200 and _lines(env) == 1
        else:
            assert r.status_code == 400 and "did not renew" in r.json()["error_description"] and _lines(env) == 0


# ------------------------------------------------------------------ a deployment -------------------------------------
def test_lines_in_the_table_survive_a_new_revision_with_the_same_key(env):
    """A new revision (an image update, a restart, a scale from zero) builds a new app around the same table and the
    same key: the line is read and rotates as before."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
    with client(env=env) as c2:                                                # the "new revision"
        r = _refresh(c2, rt1)
        assert r.status_code == 200 and _lines(env) == 1


def test_a_new_key_makes_every_line_unreadable_and_deletes_it_at_its_next_refresh(env):
    """KRUSGRAPH_REGISTRATION_KEY (or its Key Vault secret) replaced, e.g. by running step 3 of --client-registration
    again (`openssl rand -base64 32`): the stored Entra token cannot be opened, the line is deleted, sign in again."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
    env["monkeypatch"].setenv("KRUSGRAPH_REGISTRATION_KEY", base64.b64encode(b"n" * 32).decode())
    with client(env=env) as c2:
        r = _refresh(c2, rt1)
        assert r.status_code == 400 and "can no longer be read" in r.json()["error_description"] and _lines(env) == 0


def test_the_memory_store_loses_every_line_at_a_restart(env, monkeypatch):
    """KRUSGRAPH_REGISTRATION_STORE=memory: a new process (a revision, a restart, a scale to zero and back) starts
    empty; every client must sign in again. The hosted service uses Table Storage (docs/OPERATIONS.md, section 6)."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
    fresh = registration_store.MemoryStore()
    monkeypatch.setattr(registration_store, "from_env", lambda: fresh)
    with client(env=env) as c2:
        assert "unknown, expired or revoked" in _refresh(c2, rt1).json()["error_description"]


def test_update_keeps_the_key_and_the_table_and_a_full_run_drops_the_key_held_as_an_app_secret():
    """deploy/azure_containerapp.py: --update sends only the image, the build tag and the plain settings (no secret, no
    KRUSGRAPH_REGISTRATION_*), so the key and the table stay. A full run writes a manifest whose secrets are the Entra
    secret alone and whose environment keeps only plain registration values: a key held as the app secret
    `registration-key` is gone afterwards (the layer turns itself off), and switching it on again with a new key ends
    every line. A key in Key Vault (KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI, a plain value) survives a full run."""
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("azure_containerapp_n82", pathlib.Path(__file__).resolve().parents[1] / "deploy" / "azure_containerapp.py")
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    env_ = d.plain_env({"domain": "krusgraph.test", "client_id": "cid", "product_name": "Krusgraph", "contact_email": "a@b.test"}, "src-x")
    assert not any(k.startswith("KRUSGRAPH_REGISTRATION") or k == "KRUSGRAPH_CLIENT_REGISTRATION" for k in env_)
    existing = {"properties": {"configuration": {"ingress": {}, "secrets": [{"name": "entra-secret"}, {"name": "registration-key"}]},
                               "template": {"containers": [{"env": [
                                   {"name": "KRUSGRAPH_CLIENT_REGISTRATION", "value": "1"},
                                   {"name": "KRUSGRAPH_REGISTRATION_STORE", "value": "https://st.table.core.windows.net/krusgraphoauth"},
                                   {"name": "KRUSGRAPH_REGISTRATION_KEY", "secretRef": "registration-key"}]}]}}}
    config = {"app": "krusgraph", "location": "swedencentral", "domain": "krusgraph.test", "client_id": "cid",
              "product_name": "Krusgraph", "contact_email": "a@b.test", "min_replicas": 0}
    m = d.make_manifest(config, "env-id", "identity-id", "reg.test", "img", "secret", existing, "src-x")
    names = {e["name"] for e in m["properties"]["template"]["containers"][0]["env"]}
    assert {"KRUSGRAPH_CLIENT_REGISTRATION", "KRUSGRAPH_REGISTRATION_STORE"} <= names       # the table is kept
    assert "KRUSGRAPH_REGISTRATION_KEY" not in names                                        # the key held as a secret is not
    assert [s["name"] for s in m["properties"]["configuration"]["secrets"]] == ["entra-secret"]
    assert m["properties"]["template"]["scale"]["minReplicas"] == 0                         # scale to zero by default
