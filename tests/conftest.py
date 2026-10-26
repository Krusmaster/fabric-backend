"""Shared test setup: no test reaches Fabric by accident."""
import pytest


@pytest.fixture(autouse=True)
def _no_existing_api_lookup(monkeypatch):
    """create_backend looks for an existing API of the same name before it writes. Tests that do not mock that
    lookup get "no such API", so they never call Fabric; tests of the guard mock it themselves."""
    from fabric_backend import server
    monkeypatch.setattr(server, "_existing_api", lambda workspace, name, headers: None)
