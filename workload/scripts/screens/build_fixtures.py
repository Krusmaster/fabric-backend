"""Krusgraph Model editor screenshots: the engine's answers on seed.py's synthetic shop schema, as JSON fixtures.

The website docs show the Model editor (workload/Workload/app/items/ModelItem/) on the synthetic shop schema. A live
Fabric capture is not possible, so harness.tsx renders the editor's own view components with the answers this script
gets from the real engine, through the same /workload/v1 routes the editor calls (fabric_backend/workload_api.py:
/review, /check, /build). Only the Fabric REST API and the SQL endpoint are doubles: tests/golden_support.py's
FakeFabric (the golden workspace, lakehouse demo_lh) and its SQLite-backed pyodbc with seed.py's rows, exactly as
tests/test_workload_api.py, test_workload_check.py and test_workload_build.py run them. No number here is typed in.

Writes workload/scripts/screens/fixtures/:
    review.json    ReviewView: source, the review checked against the rows (/check), its map (MapData)
    outputs.json   OutputsView: the choices (every output, the names the preview uses) and the data product
    preview.json   PreviewView: the dry run of every output with the data product (/build, dry_run true)
    flow.json      FlowView: workload/Workload/app/items/ModelItem/flow.fixture.json (build_flow_fixture.py), and
                   the box to unfold

Run from the repository root:  python workload/scripts/screens/build_fixtures.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "workload/scripts/screens/fixtures"
FLOW_FIXTURE = ROOT / "workload/Workload/app/items/ModelItem/flow.fixture.json"
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

# The outputs the preview builds, every kind the editor offers (buildWords.KINDS), named as the tests name them.
OUTPUTS = [{"kind": "silver_notebook", "name": "shop_silver"}, {"kind": "gold_views", "name": "shop_gold"},
           {"kind": "pipeline", "name": "shop_flow"}, {"kind": "semantic_model", "name": "shop_sales"},
           {"kind": "report", "name": "shop_report"}, {"kind": "graphql", "name": "shop_model_api"},
           {"kind": "ontology", "name": "shop_onto"}, {"kind": "data_agent", "name": "shop_agent"}]
PRODUCT = "Shop sales"
OPEN_BOX = "silver:orders"          # the box FlowView unfolds in the screenshot (its silver notebook cell)


class _JWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key})()


class _OBO:
    """The on-behalf-of exchange, faked: the Fabric and SQL doubles take any token."""

    def token(self, user_token, tenant, scope):
        return f"obo:{scope}"


def client():
    """The /workload/v1 routes on the Fabric and SQL doubles; returns (post, source request)."""
    import jwt
    import requests
    from cryptography.hazmat.primitives.asymmetric import rsa
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    import golden_support as gs
    from fabric_backend import server, workload_api
    from fabric_backend.entra import Validator, WorkloadConfig

    tid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    uri = f"api://localdevinstance/{tid}/Org.Krusgraph/Ab"
    wl = WorkloadConfig("99999999-8888-7777-6666-555555555555", "wl-secret", uri)
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        setattr(requests, verb, getattr(fake, verb))
    sys.modules["pyodbc"] = gs.fake_pyodbc()
    server.limiter = None
    app = Starlette(routes=workload_api.routes(wl, Validator(wl, _JWKS(priv.public_key())), _OBO()))
    tc = TestClient(app)

    def post(path: str, body: dict) -> dict:
        claims = {"aud": uri, "iss": f"https://login.microsoftonline.com/{tid}/v2.0", "tid": tid,
                  "exp": int(time.time()) + 600, "scp": "user_impersonation", "oid": "user-1"}
        token = jwt.encode(claims, priv, algorithm="RS256")
        r = tc.post(workload_api.PREFIX + path, json=body,
                    headers={"Authorization": f"Bearer {token}", "Origin": "https://app.fabric.microsoft.com"})
        if r.status_code != 200:
            raise SystemExit(f"{path}: {r.status_code} {r.text[:400]}")
        return r.json()

    src = {"workspace": gs.WS, "source": "demo_lh", "source_name": "demo_lh", "schema": "shop"}
    source_def = {"version": 1, "platform": "fabric", "workspaceId": gs.WS, "itemId": gs.LH, "itemType": "Lakehouse",
                  "displayName": "demo_lh", "schema": "shop"}
    return post, src, source_def


def write(name: str, data: dict) -> None:
    text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
    (OUT / name).write_text(text, encoding="utf-8")
    print(f"wrote {(OUT / name).relative_to(ROOT)} ({len(text)} characters)")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    post, src, source_def = client()

    reviewed = post("/review", src)
    checked = post("/check", {**src, "review": reviewed["review"]})
    write("review.json", {"source": source_def, "review": checked["review"], "map": checked["map"],
                          "check": checked["check"], "counts": checked["counts"]})

    preview = post("/build", {**src, "review": checked["review"], "outputs": OUTPUTS, "dry_run": True,
                              "product": {"name": PRODUCT}, "created": []})
    if preview["refused"]:
        print(f"note: {preview['refused']} output(s) refused in the dry run", file=sys.stderr)
    write("preview.json", {"answer": preview})

    # OutputsView: one choice per kind, every one chosen, with the names the dry run above used (as choicesFor makes
    # them from the item's saved outputs: {type, name, enabled}); the data product on.
    write("outputs.json", {"choices": [{"type": o["kind"], "name": o["name"], "enabled": True} for o in OUTPUTS],
                           "product": {"on": True, "name": PRODUCT}, "created": []})

    # n177: the flow of the same dry run, so the flow image shows what the review and preview images show (R5's
    # ship_to_id included; flow.fixture.json is planned without rows)
    flow = preview["flow"]
    if not any(n["id"] == OPEN_BOX and n.get("code") for n in flow["nodes"]):
        raise SystemExit(f"{OPEN_BOX} has no code in the dry run's flow; choose another box")
    write("flow.json", {"flow": flow, "open": OPEN_BOX})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
