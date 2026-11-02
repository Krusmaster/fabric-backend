"""n82: what happens to a refresh line at /oauth/token (registration_flow.Layer._refresh) when the same refresh token
comes twice, and what a deployment does to the lines; against fake answers only (the mocked Entra and store of
tests/test_client_registration.py, and the fake `az` of tests/test_azure_deployment.py). The investigation these tests
back is docs/REFRESH-ROTATION.md (Glama's sign-out of 2 November 2026). They pin today's behaviour, faults included: a
change to the rotation (an overlap window, docs/REFRESH-ROTATION.md, proposal) changes them on purpose.

Our refresh token is `<line id>.<secret>`; the line (store kind "family") keeps the hash of the current secret and
Entra's refresh token, sealed with the server's key. Each refresh replaces the hash (rotation, conditional on the ETag
the request read); a secret that does not match the stored hash deletes the line ("an old or stolen token")."""
import base64

import pytest

pytest.importorskip("jwt")

from fabric_backend import registration_flow as flow, registration_store  # noqa: E402
from tests.test_client_registration import (BASE, VSCODE, client, env, keys, redeem, sign_in)  # noqa: E402,F401

REDIRECT = "http://127.0.0.1:33418/"


def _signed_in(c, env_):
    code, verifier, _ = sign_in(c, env_["entra"], VSCODE, REDIRECT)
    r = redeem(c, VSCODE, REDIRECT, code, verifier)
    assert r.status_code == 200, r.text
    return r.json()["refresh_token"]


def _refresh(c, rt):
    return c.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": rt, "client_id": VSCODE,
                                        "resource": f"{BASE}/mcp/connect"})


def _lines(env_):
    return env_["store"].count("family")


# ------------------------------------------------------------------ the same token twice, one after the other --------
def test_a_retry_with_the_old_token_after_a_lost_answer_ends_the_whole_line(env):
    """The client sends RT1, the server rotates to RT2 and answers, the answer is lost (a cut connection, a replica that
    stops, a client timeout during a cold start); the client sends RT1 again. That is reuse: the line is deleted, so RT2
    (which the client never saw) is dead as well, and the next refresh with anything fails: the client must sign in."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        assert _lines(env) == 1
        first = _refresh(c, rt1)
        assert first.status_code == 200
        rt2 = first.json()["refresh_token"]
        assert rt2 != rt1 and rt2.split(".")[0] == rt1.split(".")[0]          # same line, new secret
        # the answer above is "lost": the client still holds rt1 and tries again
        again = _refresh(c, rt1)
        assert again.status_code == 400 and again.json()["error"] == "invalid_grant"
        assert "already used" in again.json()["error_description"]
        assert _lines(env) == 0                                                # the whole line is gone
        late = _refresh(c, rt2)
        assert late.status_code == 400 and "unknown, expired or revoked" in late.json()["error_description"]


def test_the_same_token_twice_in_quick_succession_ends_the_line_when_the_first_has_rotated(env):
    """Two requests with RT1 that do not overlap inside the server (the second arrives after the first has replaced the
    hash, e.g. two tasks of one client that each refresh): the second is taken for a stolen token and ends the line;
    the first request's answer (RT2) is then worthless too."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        a = _refresh(c, rt1)
        b = _refresh(c, rt1)
        assert a.status_code == 200 and b.json()["error"] == "invalid_grant"
        assert _refresh(c, a.json()["refresh_token"]).json()["error"] == "invalid_grant"
        assert _lines(env) == 0


# ------------------------------------------------------------------ the same token twice, in parallel ----------------
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


def test_parallel_with_an_entra_that_accepts_its_refresh_token_twice_one_wins_and_the_line_survives(env):
    """Both requests read the line; the second (B) reaches the store first and rotates it; the first (A) then fails the
    ETag check and answers invalid_grant "used by another request at the same moment", without deleting the line. B's
    token works. A client that keeps A's error (and drops B's token) is signed out although the line is alive."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        a, b = _second_request_inside_entra(env, c, rt1, entra_accepts_reuse=True)
        assert b.status_code == 200
        assert a.status_code == 400 and "at the same moment" in a.json()["error_description"]
        assert _lines(env) == 1
        assert _refresh(c, b.json()["refresh_token"]).status_code == 200      # the winner's token goes on
        assert _refresh(c, rt1).json()["error"] == "invalid_grant" and _lines(env) == 0   # and RT1 once more ends it


def test_parallel_with_an_entra_that_takes_its_refresh_token_once_both_fail_and_the_line_dies(env):
    """With an Entra that redeems its own refresh token once (the mocked Entra does; whether Microsoft Entra does is not
    verified here): B wins at Entra and rotates the line; A's Entra call is refused with invalid_grant, a final answer,
    so A deletes the line, and B's fresh token is dead before the client uses it."""
    with client(env=env) as c:
        rt1 = _signed_in(c, env)
        a, b = _second_request_inside_entra(env, c, rt1, entra_accepts_reuse=False)
        assert b.status_code == 200
        assert a.status_code == 400 and "did not renew the sign-in (invalid_grant)" in a.json()["error_description"]
        assert _lines(env) == 0
        assert _refresh(c, b.json()["refresh_token"]).json()["error"] == "invalid_grant"


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
