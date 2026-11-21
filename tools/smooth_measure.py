"""Round SM1: measure the guided path (taps, seconds, words per step) on the synthetic SAP demo, locally.

Runs the real hosted tools behind tests/wb15_fake.py's seams (no Fabric, no write possible) and clicks one Start
Krusgraph card with tools/smooth_measure.js, on the careful path and the lazy path, at 390 x 800 and 1280 x 900.

    python tools/smooth_measure.py [--shots DIR] [--out FILE.json]
    python tools/smooth_measure.py --tools [--out FILE.json]     # SM4: tools listed and the cards' dead ends, no browser
    python tools/smooth_measure.py --combine [--out FILE.json]   # SM7: SAP + CRM on the fixture, layout (b), no browser

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


def combine(argv: list[str]) -> int:
    """SM7: SAP + CRM on the multi-lakehouse fixture, layout (b), server side (no browser, as SM6 measured layout (a)):
    Start -> the two sources as one plan -> Decide -> Accept the match -> the dry run -> Dry run everything. Per tap:
    the stage, the seconds so far, the card's words; then the match counts and what the model dry run combined."""
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args(argv)
    import pytest
    from fixtures import multi_lakehouse as mlh
    from fabric_backend import flow_state, server
    runs = []
    for _ in range(a.runs):
        mp = pytest.MonkeyPatch()
        mlh.install(mp, "b")
        flow_state.clear()
        try:
            t0, taps, steps = time.monotonic(), 0, []

            def note(card):
                steps.append({"stage": card["stage"], "taps": taps, "seconds": round(time.monotonic() - t0, 2),
                              "say": card.get("say"), "words": len(str(card.get("say") or "").split()),
                              **({"line": card["lines"][0]} if card.get("lines") else {}),
                              **({"combined": card["combined"]} if card.get("combined") else {})})
            card = json.loads(server.start())
            note(card)
            both = next(x for x in card["actions"] if x["kind"] == "choose" and "+" in x["label"])
            card = json.loads(server.start(**both["arguments"]))
            taps += 1
            note(card)
            while card["stage"] != "dry_run":
                tap = next((x for x in card["actions"] if x.get("decision") == "accepted"
                            and str(x.get("item", "")).startswith("match:")), None) \
                    if card["stage"] == "decide" and card.get("open_decisions") else None
                card = json.loads(server.start(**(tap or card["after"])["arguments"]))
                taps += 1
                note(card)
            everything = next(x for x in card["actions"] if x["kind"] == "dry_run_all")
            answers = {r["tool"]: json.loads(getattr(server, r["tool"])(**r["arguments"])) for r in everything["runs"]}
            taps += 1
            model = answers["create_semantic_model"].get("combined") or {}
            runs.append({"layout": "b", "taps": taps, "seconds": round(time.monotonic() - t0, 2), "steps": steps,
                         "errors": [t for t, x in answers.items() if x.get("error")],
                         "model": {"line": model.get("line"), "facts": len(model.get("facts") or []),
                                   "relationships": len(model.get("relationships") or []),
                                   "fact_to_fact": len(model.get("fact_to_fact") or [])},
                         "writes": len(mlh.WRITES)})
        finally:
            mp.undo()
            flow_state.clear()
    text = json.dumps(runs, indent=1, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    for r in runs:
        print(f"layout (b): {r['taps']} taps, {r['seconds']} s, errors={r['errors']}, writes={r['writes']} | {r['model']['line']}")
    return 0


def main() -> int:
    if "--combine" in sys.argv[1:]:                          # SM7: SAP + CRM on the fixture, layout (b)
        return combine([x for x in sys.argv[1:] if x != "--combine"])
    if "--tools" in sys.argv[1:]:                            # SM4: tools/smooth_measure_tools.py
        sys.path.insert(0, str(ROOT / "tools"))
        import smooth_measure_tools
        return smooth_measure_tools.main([a for a in sys.argv[1:] if a != "--tools"])
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
