"""Shared test setup: no test reaches Fabric by accident."""
import pytest


@pytest.fixture(autouse=True)
def _no_existing_api_lookup(monkeypatch):
    """create_backend looks for an existing API of the same name before it writes. Tests that do not mock that
    lookup get "no such API", so they never call Fabric; tests of the guard mock it themselves."""
    from fabric_backend import server
    monkeypatch.setattr(server, "_existing_api", lambda workspace, name, headers: None)


@pytest.fixture(autouse=True)
def _no_create_remembered():
    """n227: the hosted server remembers a create whose outcome it does not know and does not send the same definition
    again (server._RECENT). Tests share one process, so each starts and ends with nothing remembered."""
    from fabric_backend import server
    server._RECENT.clear()
    yield
    server._RECENT.clear()


def docs_all(client) -> str:
    """n86a: /docs is split into sub-pages; the whole docs text is all of them together."""
    from fabric_backend.pages import docs_pages
    return "".join(client.get(x["path"]).text for x in docs_pages())


@pytest.fixture(autouse=True)
def _no_onelake(monkeypatch):
    """CSN2: the hosted plan looks for CSN files in the lakehouse's Files (csn_onelake.py). No test reaches OneLake:
    the one network call answers 404 (no such folder), so the plan is made as before; tests of the reader fake it."""
    from fabric_backend import csn_onelake

    class _Missing:
        status_code = 404

    monkeypatch.setattr(csn_onelake, "_http_get", lambda url, **kw: _Missing())


@pytest.fixture(autouse=True)
def _no_flow_kept():
    """WB15: the guided path's shared state (flow_state.py) lives in memory; each test starts and ends with none."""
    from fabric_backend import flow_state
    flow_state.clear()
    yield
    flow_state.clear()
