"""n241: verify_build's two Power BI reads against a real model, opt-in, and a skip (never a failure) when the sign-in
lacks Dataset.Read.All / Dataset.ReadWrite.All.

The rest of verify_build's tests use test doubles (tests/test_n229_verify_build.py). This one runs only when a person
sets KRUSGRAPH_LIVE_POWERBI_TOKEN (a delegated Power BI access token), KRUSGRAPH_LIVE_WORKSPACE and KRUSGRAPH_LIVE_MODEL;
CI sets none of them. Until the app registration has the Power BI permission Dataset.Read.All or Dataset.ReadWrite.All
in Microsoft Entra, the test skips and says so.
"""
import base64
import json
import os

import pytest

from fabric_backend import verify_build as vb

NEEDED = ("Dataset.Read.All", "Dataset.ReadWrite.All")
MISSING = ("verify_build live check skipped: the token has neither Dataset.Read.All nor Dataset.ReadWrite.All. Add one "
           "of them (delegated, Power BI Service) to the app registration in Microsoft Entra and grant consent, then "
           "sign in again.")


def _scopes(token: str) -> set[str]:
    try:
        body = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except (IndexError, ValueError):
        return set()
    return set(str(claims.get("scp") or "").split())


def _token(scp: str) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc({'scp': scp})}.x"


def test_scopes_are_read_from_the_token():
    assert _scopes(_token("Workspace.Read.All Dataset.Read.All")) == {"Workspace.Read.All", "Dataset.Read.All"}
    assert _scopes("not-a-jwt") == set()


def test_a_403_from_power_bi_names_the_missing_permission():
    said = vb.model_state(RuntimeError("HTTP 403"))["said"]
    assert "HTTP 403: " in said and "Dataset.Read.All or Dataset.ReadWrite.All" in said and "Entra" in said
    assert "Dataset" not in vb.model_state(RuntimeError("timed out"))["said"]


def test_live_refresh_history_reads_or_skips_with_a_clear_message():
    token, ws, model = (os.environ.get(k, "") for k in
                        ("KRUSGRAPH_LIVE_POWERBI_TOKEN", "KRUSGRAPH_LIVE_WORKSPACE", "KRUSGRAPH_LIVE_MODEL"))
    if not (token and ws and model):
        pytest.skip("verify_build live check not configured: set KRUSGRAPH_LIVE_POWERBI_TOKEN, KRUSGRAPH_LIVE_WORKSPACE "
                    "and KRUSGRAPH_LIVE_MODEL to run it")
    if not _scopes(token) & set(NEEDED):
        pytest.skip(MISSING)
    import requests
    r = requests.get(f"https://api.powerbi.com/v1.0/myorg/groups/{ws}/datasets/{model}/refreshes?$top=1",
                     headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if r.status_code in (401, 403):
        pytest.skip(MISSING + f" (Power BI answered HTTP {r.status_code})")
    r.raise_for_status()
    assert vb.model_state(list(r.json().get("value") or []))["state"] in (vb.VERIFIED, vb.DIFFERS)
