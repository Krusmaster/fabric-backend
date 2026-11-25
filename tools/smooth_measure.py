"""Round SM1: measure the guided path (taps, seconds, words per step) on the synthetic SAP demo, locally.

Runs the real hosted tools behind tests/wb15_fake.py's seams (no Fabric, no write possible) and clicks one Start
Krusgraph card with tools/smooth_measure.js, on the careful path and the lazy path, at 390 x 800 and 1280 x 900.

    python tools/smooth_measure.py [--shots DIR] [--out FILE.json]
    python tools/smooth_measure.py --tools [--out FILE.json]     # SM4: tools listed and the cards' dead ends, no browser
    python tools/smooth_measure.py --combine [--out FILE.json]   # SM7: SAP + CRM on the fixture, layout (b), no browser
    python tools/smooth_measure.py --change [--shots DIR] [--out FILE.json]   # LFD8: the diff card, every state, 390 px

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
sys.path.insert(0, str(ROOT))                    # LFD8: this checkout's package, also when another is installed


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


# ------------------------------------------------------------------ LFD8: the diff card -------------------------------

CHANGE_LIMITS = {"words": 25, "primaries": 1, "width": 390, "contrast": 4.5}


def change_states(apply_ready: bool = False) -> tuple[list[dict], callable]:
    """The diff card's states on the synthetic shop_lfd sample (SQLite, no network), each with the taps to make, and the
    host's answer for a tools/call from the card: propose_change with the product's own code (the plan as plan_backend
    makes it from names, with the call's confirmed links), apply_change recorded and answered as round LFD6's tool
    might (the card is tested against an answer, never against a write). Needs KRUSGRAPH_CHANGES=1 in the environment
    while it runs (change_run sets it)."""
    from fabric_backend import change_diff, change_numbers, lfd_demo, mcp_apps_change, server
    from fabric_backend.infer import plan as make_plan
    info = dict(workspace_id="11111111-1111-1111-1111-111111111111", item_id="lh-1", item_name="shop_lh", item_kind="Lakehouse",
                schema="shop", schemas_enabled=True)
    schema, execute = lfd_demo.sqlite("shop_lfd")
    is_test = {"column": "is_test", "op": "is_true"}
    a2 = {"type": "filter_rows", "table": "customers", "drop_where": is_test,
          "cascade": ["orders", "order_items", "addresses", "audit_log"]}
    a4 = {"type": "add_measure", "name": "Order value per customer",
          "measure": {"form": "ratio", "numerator": {"measure": "Order amount"},
                      "denominator": {"form": "distinct_count", "table": "orders", "column": "customer_id"}}}
    ship = {"from": {"table": "orders", "columns": ["ship_to_id"]}, "to": {"table": "addresses", "columns": ["address_id"]}}
    base = {"workspace": "demo", "source": "shop_lh", "schema": "shop"}
    applied_calls: list = []

    def counter(*, before, after):                       # round LFD4's counter, as round LFD6 wires it
        return change_numbers.count(after["applied"], after["plan"], execute)

    def as_json(r) -> dict:
        if isinstance(r, str):
            return {"content": [{"type": "text", "text": r}]}
        return {"content": [{"type": "text", "text": c.text} for c in r.content], "structuredContent": r.structured_content,
                "isError": bool(getattr(r, "isError", False))}

    def propose(args: dict, numbers=None) -> dict:
        conf = args.get("confirmed")
        out = change_diff.propose(args.get("change"), make_plan(schema, None, conf), info, args.get("applied"), confirmed=conf,
                                  replan=lambda links: make_plan(schema, None, links), numbers=numbers)
        return as_json(mcp_apps_change.result(change_diff.answer(out, server.MAX_RESULT_CHARS), args))

    def host(name: str, args: dict) -> dict:
        if name == "propose_change":
            return propose(args)
        if name == "apply_change":
            applied_calls.append(args)
            text = json.dumps({"result": "applied", "summary": "The change list was applied (a test double for apply_change)."})
            return {"content": [{"type": "text", "text": text}], "structuredContent": json.loads(text), "isError": False}
        return {"content": [{"type": "text", "text": json.dumps({"error": f"{name} is not on this host"})}], "isError": True}
    host.applied = applied_calls

    ready = mcp_apps_change.apply_tool
    if apply_ready:
        mcp_apps_change.apply_tool = lambda: {"properties": None}
    try:
        ok = propose({**base, "change": a4, "applied": [a2]})
        states = [
            {"name": "ok", "kind": "ok", "result": ok, "shot": True,
             "clicks": [{"kind": "yes"}, {"kind": "no", "shot": "no"}]},
            {"name": "ok-open", "kind": "ok", "result": ok,
             "clicks": [{"kind": "fold", "text": "Plan"}, {"kind": "fold", "text": "Items", "shot": "items"}, {"kind": "fold", "text": "Numbers"}]},
            {"name": "not-counted", "kind": "ok", "result": propose({**base, "change": a2}),
             "clicks": [{"kind": "fold", "text": "Numbers", "shot": "numbers"}]},
            {"name": "counted", "kind": "ok", "result": propose({**base, "change": a2}, numbers=counter),
             "clicks": [{"kind": "fold", "text": "Numbers", "shot": "numbers"}]},
            {"name": "question", "kind": "question", "result": propose({**base, "change": {"type": "filter_rows", "table": "customers"}}),
             "shot": True, "clicks": [{"kind": "choice", "text": "is_test"}, {"kind": "choice", "text": "Yes, from all"}]},
            {"name": "denied", "kind": "denied", "shot": True, "result": propose({**base, "change": {
                "type": "add_column", "table": "orders", "from": "addresses", "columns": ["region"], "via": [
                    {"from": {"table": "orders", "columns": ["customer_id"]}, "to": {"table": "customers", "columns": ["customer_id"]}},
                    {"from": {"table": "addresses", "columns": ["customer_id"]}, "to": {"table": "customers", "columns": ["customer_id"]}}]}}),
             "clicks": [{"kind": "back"}]},
            {"name": "replan", "kind": "replan", "result": propose({**base, "change": a4, "applied": [{"type": "add_link", **ship}]}),
             "clicks": [{"kind": "choice"}]},
            {"name": "undo", "kind": "ok", "result": ok, "clicks": [{"kind": "undo"}]},
        ]
        if apply_ready:
            states = [{"name": "ok-ready", "kind": "ok", "result": ok, "clicks": [{"kind": "yes"}]},
                      {"name": "ok-ready-no", "kind": "ok", "result": ok, "clicks": [{"kind": "no"}]},
                      {"name": "ok-ready-chat", "kind": "ok", "result": ok, "caps": {}, "clicks": [{"kind": "yes"}]}]
    finally:
        mcp_apps_change.apply_tool = ready
    return states, host


def change_run(shots: str = "", schemes=("light", "dark"), apply_ready: bool = False) -> list[dict]:
    """Clicks the diff card's states in Chromium (tests/lfd8_card_click.js) at 390 px in each scheme; returns one run per
    state and scheme with a measure per state the card showed, the tools/calls and the chat messages."""
    import os
    import tempfile
    from fabric_backend import mcp_apps_change
    old = os.environ.get("KRUSGRAPH_CHANGES")
    os.environ["KRUSGRAPH_CHANGES"] = "1"
    try:
        states, host = change_states(apply_ready)
        lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):                               # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with lock:
                    out = host(body["name"], body.get("arguments") or {})
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
        runs = []
        with tempfile.TemporaryDirectory() as tmp:
            card = Path(tmp) / "change_card.html"
            card.write_text(mcp_apps_change.card_html(), encoding="utf-8")
            data = Path(tmp) / "states.json"
            data.write_text(json.dumps(states), encoding="utf-8")
            if shots:
                Path(shots).mkdir(parents=True, exist_ok=True)
            try:
                for scheme in schemes:
                    r = subprocess.run(["node", str(ROOT / "tests" / "lfd8_card_click.js"), str(card), str(httpd.server_address[1]),
                                        scheme, str(data), shots], capture_output=True, text=True, timeout=600, cwd=ROOT)
                    if r.returncode:
                        raise RuntimeError(r.stderr[-3000:])
                    for run in json.loads(r.stdout):
                        run["kind"] = next(s["kind"] for s in states if s["name"] == run["name"])
                        runs.append(run)
            finally:
                httpd.shutdown()
        for run in runs:
            run["applied"] = list(host.applied)
        return runs
    finally:
        if old is None:
            os.environ.pop("KRUSGRAPH_CHANGES", None)
        else:
            os.environ["KRUSGRAPH_CHANGES"] = old


def change_checks(runs: list[dict]) -> list[str]:
    """The SMOOTH measures of the diff card; an empty list when every one holds. Words are counted with the folds
    closed (an opened fold is the person's own choice, as SM1 counts them); everything else in every state."""
    bad, lim = [], CHANGE_LIMITS
    for run in runs:
        for s in run["steps"]:
            where = f"{run['name']} ({run['scheme']}) {s.get('key')}"
            if s.get("missing"):
                bad.append(f"{where}: the button is not there")
                continue
            if not s["key"].startswith("fold") and s["words"] > lim["words"]:
                bad.append(f"{where}: {s['words']} words outside the buttons")
            if s["primaries"] > lim["primaries"]:
                bad.append(f"{where}: {s['primaries']} primary buttons")
            if s["enabled"] < 1:
                bad.append(f"{where}: a dead end (no button to tap)")
            if s["width"] > lim["width"]:
                bad.append(f"{where}: {s['width']} px wide")
            if s["contrast"] < lim["contrast"]:
                bad.append(f"{where}: contrast {s['contrast']}")
        first = run["steps"][0]
        if run["kind"] == "ok" and first["primaries"] != 1:
            bad.append(f"{run['name']} ({run['scheme']}): an ok answer needs exactly one primary button")
    return bad


def change(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    runs = change_run(a.shots) + change_run("", apply_ready=True)
    if a.out:
        Path(a.out).write_text(json.dumps(runs, indent=1, ensure_ascii=False), encoding="utf-8")
    for run in runs:
        for s in run["steps"]:
            print(f"{run['name']:<14} {run['scheme']:<5} {s['key']:<22} words={s.get('words', '-'):<3} primary={s.get('primaries', '-')} "
                  f"enabled={s.get('enabled', '-')} width={s.get('width', '-')} contrast={s.get('contrast', '-')} | {s.get('line', '')[:60]}")
    bad = change_checks(runs)
    print("\n" + ("every measure holds" if not bad else "\n".join(bad)))
    return 1 if bad else 0


def main() -> int:
    if "--change" in sys.argv[1:]:                           # LFD8: the diff card
        return change([x for x in sys.argv[1:] if x != "--change"])
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
