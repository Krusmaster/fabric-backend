"""Round SM4: the tool listing and the cards' dead ends, measured locally (no browser, no Fabric).

    python tools/smooth_measure.py --tools [--out FILE.json]

- tools: how many tools tools/list holds by default and with KRUSGRAPH_ADVANCED_TOOLS=1;
- dead ends: every hosted tool that draws a card is run once on the synthetic SAP demo behind tools/directory_measure.py's fake Fabric
  (cards on; no write possible), and each card's last state is read from its structuredContent. A card is a dead end
  when none of its buttons (its next steps, its actions, start's own actions) goes on: a button for a tool the
  default listing holds, a hand-back to the Start Krusgraph card, or a link. A button for a tool the default listing
  leaves out is counted separately ("buttons to unlisted tools"); a model in the chat cannot call such a tool.

Deterministic: the same calls, the same fake Fabric, the same rules every run.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _buttons(sc) -> list[dict]:
    """Every button a card draws for one answer: next steps, actions, and start's own actions and next call."""
    if not isinstance(sc, dict):
        return []
    out = [s for s in sc.get("next") or [] if isinstance(s, dict)]
    out += [a for a in sc.get("actions") or [] if isinstance(a, dict)]
    if isinstance(sc.get("after"), dict) and sc["after"].get("tool"):
        out.append(sc["after"])
    return out


def _run(dm, name: str, arguments: dict) -> dict:
    """One call as the hosted server registers it: with the build card's actions where the tool has them."""
    from fabric_backend import mcp_apps, mcp_apps_build, server
    if name not in mcp_apps_build.ACTION_TOOLS:
        return dm.run(name, arguments)
    fn = mcp_apps.structured(mcp_apps_build.with_actions(name, getattr(server, name), server._item_names,
                                                         server._workspace_id_ctx), name)
    r = fn(**arguments)
    return {"structured": r.structured_content if not isinstance(r, str) else None, "kind": None}


def listing_counts() -> dict:
    from fabric_backend import server
    old = os.environ.pop("KRUSGRAPH_ADVANCED_TOOLS", None)
    try:
        default = [t.name for t in asyncio.run(server.mcp.list_tools())]
        os.environ["KRUSGRAPH_ADVANCED_TOOLS"] = "1"
        every = [t.name for t in asyncio.run(server.mcp.list_tools())]
    finally:
        os.environ.pop("KRUSGRAPH_ADVANCED_TOOLS", None)
        if old is not None:
            os.environ["KRUSGRAPH_ADVANCED_TOOLS"] = old
    return {"default": len(default), "advanced": len(every), "listed": default,
            "hidden": sorted(set(every) - set(default))}


def dead_ends(data: str = "sap") -> dict:
    import directory_measure as dm
    from fabric_backend import mcp_apps, tool_listing
    os.environ.setdefault("KRUSGRAPH_MCP_APPS", "1")
    rows = []
    with dm.fake_fabric(data) as schema:
        for name, args in dm.calls(schema, data):
            try:
                r = _run(dm, name, args)
            except Exception as e:                       # noqa: BLE001 - counted as a dead end, the run goes on
                rows.append({"tool": name, "args": sorted(args), "dead_end": True, "raised": type(e).__name__})
                continue
            if "meta" not in mcp_apps.registration(name, on=True):
                continue                                 # no card: the host draws nothing for this tool
            sc = r["structured"]
            buttons = _buttons(sc)
            unlisted = sorted({b["tool"] for b in buttons if isinstance(b.get("tool"), str)
                               and not tool_listing.listed(b["tool"])})
            rows.append({"tool": name, "args": sorted(args), "dead_end": not tool_listing.forward(buttons),
                         "buttons": [b.get("label") for b in buttons], "unlisted": unlisted,
                         "kind": r.get("kind")})
    return {"calls": len(rows), "dead_ends": sum(r["dead_end"] for r in rows),
            "buttons_to_unlisted_tools": sum(len(r["unlisted"]) for r in rows), "rows": rows}


def main(argv: list[str]) -> int:
    logging.disable(logging.CRITICAL)
    out = {"tools": listing_counts(), "cards": dead_ends()}
    if "--out" in argv:
        Path(argv[argv.index("--out") + 1]).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    t, c = out["tools"], out["cards"]
    print(f"tools listed: {t['default']} by default, {t['advanced']} with KRUSGRAPH_ADVANCED_TOOLS=1")
    print(f"cards: {c['calls']} calls, {c['dead_ends']} dead ends, {c['buttons_to_unlisted_tools']} buttons to unlisted tools")
    for r in c["rows"]:
        if r["dead_end"] or r.get("unlisted"):
            print(f"  {'DEAD END' if r['dead_end'] else 'unlisted'}  {r['tool']:<26} {','.join(r['args'])[:40]:<40} "
                  f"{r.get('unlisted') or ''} {r.get('buttons') or ''}"[:200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
