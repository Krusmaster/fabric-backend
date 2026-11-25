"""Shared test setup: no test reaches Fabric by accident."""
import os

import pytest

# SM4: modules that read the listing when they are imported see every tool (see _every_tool_listed below)
os.environ["KRUSGRAPH_ADVANCED_TOOLS"] = "1"


LATE_THREAD_SECONDS = 60


@pytest.fixture(autouse=True)
def _no_thread_outlives_its_test(monkeypatch):
    """LFD9b: a read the server leaves to finish on its own (a caretaker report's section past the budget, AP3b; a
    workspace hint past HINT_BUDGET) goes on in its thread after the call answered. In a test run that thread called
    server._workspace_items about 4 s after its test, inside the next test on the same xdist worker, which had patched it
    (test_w4_tenant_followups: a foreign workspace in `seen`). Each test ends only when such threads have finished,
    still with its own test doubles (monkeypatch is undone after this fixture)."""
    yield
    from fabric_backend import guided_care, server
    import threading
    import time
    end = time.monotonic() + LATE_THREAD_SECONDS
    late = [t for t in threading.enumerate()
            if t is not threading.current_thread() and t.name.startswith((guided_care.CARE_THREADS, server.HINT_THREADS))]
    for t in late:
        t.join(max(0.0, end - time.monotonic()))
    still = [t.name for t in late if t.is_alive()]
    assert not still, f"threads still running {LATE_THREAD_SECONDS} s after the test: {still}"


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


@pytest.fixture(autouse=True)
def _every_tool_listed(request, monkeypatch):
    """SM4: by default tools/list holds 16 tools (fabric_backend/tool_listing.py). The older tests judge every tool as
    a client lists it, so they run with KRUSGRAPH_ADVANCED_TOOLS=1; tests/test_sm4_* and the click-through of the
    guided path (tests/test_wb15_click_through.py) run with the default listing."""
    name = request.node.module.__name__.rsplit(".", 1)[-1] if request.node.module else ""
    if name.startswith("test_sm4_") or name == "test_wb15_click_through":
        monkeypatch.delenv("KRUSGRAPH_ADVANCED_TOOLS", raising=False)
    else:
        monkeypatch.setenv("KRUSGRAPH_ADVANCED_TOOLS", "1")
