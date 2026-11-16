"""D2: screenshots of Krusgraph's chat cards (MCP Apps) for the directory listings, docs/DIRECTORY-SUBMISSION.md section 6.

Run from the repository root:  python docs/directory/shoot.py

Each card is the server's own card HTML, fed the answer of the real tool function on synthetic data: the shop schema of
fabric_backend/seed.py behind the fake Fabric of tests/golden_support.py (the same one the golden tests use), and the
SAP-shaped sample of fabric_backend/sap_sample.py (synthetic, not SAP data) for schema sap_sd. Nothing reaches Fabric,
Entra or the network. shoot_host.js frames each card the way a chat host does (light theme, the tool's name above the
card) and writes a PNG at 1280 and at 375 px wide, cropped to the app response, without the prompt. The prompt for each
image is in README.md beside the images, as the Claude carousel asks."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
OUT = ROOT / "docs" / "directory" / "screenshots"
HOST = Path(__file__).with_name("shoot_host.js")
SHOP = {"workspace": "demo", "source": "demo_lh", "schema": "shop"}
SAP = {"workspace": "demo", "source": "demo_lh", "schema": "sap_sd"}

# (file stem, tool, arguments, card module, the prompt a person types)
SHOTS = [
    ("01-start-shop", "start", {"sample": True}, "mcp_apps_start", "Start Krusgraph on the synthetic shop sample."),
    ("02-plan-shop", "plan_backend", SHOP, "mcp_apps_build", "Plan keys and relationships for schema shop in demo_lh."),
    ("03-check-shop", "validate_plan", SHOP, "mcp_apps", "Check the shop plan against the data."),
    ("04-plan-sap", "plan_backend", SAP, "mcp_apps_build", "How do the SAP sales tables in schema sap_sd connect?"),
    ("05-check-sap", "validate_plan", SAP, "mcp_apps", "Check the SAP tables in sap_sd against the rows."),
]


def _fake_fabric():
    """The golden tests' fake Fabric (REST and the SQL endpoint) for the shop, and the SAP-shaped sample for sap_sd."""
    import requests
    import golden_support as gs
    from fabric_backend import sap_sample, server
    from fabric_backend import platforms

    fake = gs.FakeFabric()
    for verb in ("get", "post", "patch"):
        setattr(requests, verb, getattr(fake, verb))
    sys.modules["pyodbc"] = gs.fake_pyodbc()
    server.auth.fabric = lambda ctx: "fabric-token"
    server.auth.sql = lambda ctx: "sql-token"
    server.limiter = None
    sap = sap_sample.source("sap_sd")
    shop_factory = server._execute_factory

    def factory(item, token):
        shop = shop_factory(item, token)

        def execute(sql, *a, **k):
            return (sap.execute if "sap_sd" in sql.lower() else shop)(sql, *a, **k)
        return execute
    server._execute_factory = factory
    platform = server._fabric.PLATFORM
    read = platform.read_schema
    platform.read_schema = lambda execute, schema: sap_sample.schema("sap_sd") if schema.lower() == "sap_sd" else read(execute, schema)
    return platforms


def main() -> int:
    os.environ.pop("KRUSGRAPH_MCP_APPS", None)              # the tools answer in text; the card reads that text
    _fake_fabric()
    import importlib
    from fabric_backend import server
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for stem, tool, args, module, _prompt in SHOTS:
            answer = getattr(server, tool)(**args)
            answer = answer if isinstance(answer, str) else json.dumps(answer)
            assert '"error"' not in answer[:200], (stem, answer[:400])
            card = importlib.import_module(f"fabric_backend.{module}").card_html()
            (tmp / "card.html").write_text(card, encoding="utf-8")
            (tmp / "input.json").write_text(json.dumps(args))
            (tmp / "result.json").write_text(json.dumps({"content": [{"type": "text", "text": answer}],
                                                         "structuredContent": json.loads(answer)}))
            for width in (1280, 375):
                out = OUT / f"{stem}-{width}.png"
                run = subprocess.run(["node", str(HOST), str(tmp / "card.html"), str(tmp / "input.json"), str(tmp / "result.json"),
                                      str(out), str(width), tool], capture_output=True, text=True, cwd=ROOT, timeout=120)
                if run.returncode != 0:
                    print(run.stdout, run.stderr, file=sys.stderr)
                    return 1
                print(stem, width, run.stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
