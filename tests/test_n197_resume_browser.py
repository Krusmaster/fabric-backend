"""Round n197: a reload in the middle of a Create step resumes the same run, in Chromium (tests/n197_resume_browser.js).

The engine's routes (workload_api.routes, with the Fabric doubles of tests/test_workload_create.py and the operation
store in memory) run in a real HTTP server next to a small page that speaks the editor's protocol: POST /build with
Prefer: respond-async, the operation id kept in the item's saved state (localStorage here), POST /operation until the
step ends. The step is held for a few seconds; the page is reloaded meanwhile. Checked: the reloaded page finds the
operation (by its id and among the item's operations), reads it to its end with the item created, /build was sent
once, and no request was held open longer than 30 seconds."""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("jwt")
pytest.importorskip("uvicorn")

from test_workload_api import SRC, WL, FakeJWKS, FakeOBO, keys, tok  # noqa: E402,F401
from test_workload_create import Workspace, _review  # noqa: E402
import golden_support as gs  # noqa: E402
from fabric_backend import operations, registration_store, server, workload_api, workload_host  # noqa: E402
from fabric_backend.entra import Validator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEM = "11111111-2222-3333-4444-555555555555"

PAGE = """<!doctype html><meta charset="utf-8"><title>resume</title><body><script>
const TOKEN = %(token)s, BODY = %(body)s, ITEM = %(item)s;
const seen = [];
let longest = 0;
async function post(route, body, prefer) {
  const t = Date.now();
  const r = await fetch("/workload/v1/" + route, { method: "POST", body: JSON.stringify(body),
    headers: Object.assign({ Authorization: "Bearer " + TOKEN, "Content-Type": "application/json" }, prefer ? { Prefer: "respond-async" } : {}) });
  longest = Math.max(longest, Date.now() - t);
  seen.push(route);
  document.body.dataset.seen = JSON.stringify(seen);
  document.body.dataset.longest = String(longest);
  return { status: r.status, json: await r.json() };
}
async function follow(op) {
  document.body.dataset.op = op;
  for (;;) {
    const s = (await post("operation", { operation_id: op })).json;
    document.body.dataset.state = s.status;
    if (s.status === "done") { document.body.dataset.created = String((s.answer.created || []).length); return; }
    if (s.status === "lost") return;
    await new Promise((r) => setTimeout(r, 200));
  }
}
(async () => {
  const kept = localStorage.getItem("create_run");
  if (kept) {
    document.body.dataset.resumed = "1";
    const listed = (await post("operation", { item_id: ITEM })).json;
    document.body.dataset.listed = String(listed.operations.filter((o) => o.operation_id === kept).length);
    await follow(kept);
    return;
  }
  const r = await post("build", BODY, true);
  localStorage.setItem("create_run", r.json.operation_id);   // the editor keeps it in create_run.ops
  await follow(r.json.operation_id);
})();
</script></body>"""


@pytest.fixture
def served(keys, monkeypatch):
    import requests
    import uvicorn
    from starlette.applications import Starlette
    from starlette.responses import HTMLResponse
    from starlette.routing import Route
    if not shutil.which("node"):
        pytest.skip("node is not installed")
    priv, pub = keys
    operations.use_store(registration_store.MemoryStore())
    monkeypatch.setattr(server, "MODEL_DEFINITION_PAUSES", (0, 0, 0))
    monkeypatch.setattr(workload_host, "same_host_origin", lambda origin: True)     # the page is served from 127.0.0.1
    fake = Workspace()
    for verb in ("get", "post", "patch"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setitem(__import__("sys").modules, "pyodbc", gs.fake_pyodbc())
    monkeypatch.setattr(server, "limiter", None)
    builds = []
    real = workload_api.run_build_many

    def held(req):                                   # the step runs a few seconds, long enough to reload in the middle
        builds.append(req["only"])
        time.sleep(3)
        return real(req)
    monkeypatch.setattr(workload_api, "run_build_many", held)
    engine = workload_api.routes(WL, Validator(WL, FakeJWKS(pub)), FakeOBO())
    from starlette.testclient import TestClient
    rv = _review(TestClient(Starlette(routes=engine)), priv)
    body = {**SRC, "review": rv, "outputs": [{"kind": "silver_notebook", "name": "demo_lh_silver"}], "only": ["silver_notebook"],
            "dry_run": False, "skip_built": True, "item_id": ITEM, "create_id": "c1", "pending": []}
    token = tok(priv, exp=int(time.time()) + 3600)
    html = PAGE % {"token": json.dumps(token), "body": json.dumps(body), "item": json.dumps(ITEM)}
    app = Starlette(routes=engine + [Route("/page", lambda r: HTMLResponse(html))])
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", builds
    finally:
        srv.should_exit = True
        t.join(timeout=10)
        operations.use_store(None)


def test_a_reload_in_the_middle_of_a_create_step_resumes_the_same_operation(served):
    base, builds = served
    run = subprocess.run(["node", str(ROOT / "tests" / "n197_resume_browser.js"), base], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[-3000:]
    out = json.loads(run.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["before"].get("state") != "done"                                     # reloaded while the step ran
    after = out["after"]
    assert after["resumed"] == "1" and after["op"] == out["before"]["op"]
    assert after["listed"] == "1"                                               # among the item's operations
    assert after["state"] == "done" and after["created"] == "1"
    assert "build" not in after["seen"]                                         # nothing sent again after the reload
    assert builds == [["silver_notebook"]]
    assert after["longest"] < 30_000
