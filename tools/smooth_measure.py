"""Round SM1: measure the guided path (taps, seconds, words per step) on the synthetic SAP demo, locally.

Runs the real hosted tools behind tests/wb15_fake.py's seams (no Fabric, no write possible) and clicks one Start
Krusgraph card with tools/smooth_measure.js, on the careful path and the lazy path, at 390 x 800 and 1280 x 900.

    python tools/smooth_measure.py [--shots DIR] [--out FILE.json]

The numbers are what docs/SMOOTH/AUDIT.md reports. They measure the product's own time on a laptop; a real host adds
the model's turn, the network and the SQL endpoint's latency on top (see AUDIT.md).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    import pytest
    import wb15_fake as fake
    from fabric_backend import flow_state, mcp_apps_start

    mp = pytest.MonkeyPatch()
    fake.install(mp)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):                                   # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                out = fake.call(body["name"], body.get("arguments") or {})
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    card = ROOT / "build" / "smooth_card.html"
    card.parent.mkdir(exist_ok=True)
    card.write_text(mcp_apps_start.card_html(), encoding="utf-8")
    if a.shots:
        Path(a.shots).mkdir(parents=True, exist_ok=True)
    runs = []
    try:
        for path in ("careful", "lazy", "shop"):
            for w, h in ((390, 800), (1280, 900)):
                flow_state.clear()
                r = subprocess.run(["node", str(ROOT / "tools" / "smooth_measure.js"), str(card),
                                    str(httpd.server_address[1]), str(w), str(h), path, a.shots],
                                   capture_output=True, text=True, timeout=600, cwd=ROOT)
                if r.returncode:
                    print(r.stderr[-3000:], file=sys.stderr)
                    return 1
                runs.append(json.loads(r.stdout))
    finally:
        httpd.shutdown()
        mp.undo()
    text = json.dumps(runs, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    for run in runs:
        print(f"\n{run['path']} at {run['width']} px")
        for s in run["steps"]:
            print(f"  {s['key']:<14} taps={s['taps']:<3} t={s['seconds']:>6}s words={s['words']:<4} "
                  f"buttons={s['buttons']:<2} ({s['buttonWords']} words) scroll={s['scroll']}  | {s['line'][:70]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
