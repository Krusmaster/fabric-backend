"""n217: the data flow in the home page's replay, drawn as the Krusgraph Model editor draws it (FlowView.tsx).

The founder, 11 November 2026: walking through the chat demo, the data flow is not shown as a flow; in the Model editor
it is (bronze tables -> silver -> gold views -> what is built on the source, as connected boxes). The replay's fourth
question ("Build a Power BI model from my lakehouse.") is the step where the chat creates something: the flow of that
build sits in the replay's card under the turns, its source tables shown throughout and its other stages drawn in as
that answer appears.

Nothing here is drawn by hand: the nodes and edges are data_flow.flow()'s, the function the workload's build calls
(workload_api._flow), on seed.py's synthetic shop schema with the same lakehouse description as the editor's fixture
(workload/scripts/build_flow_fixture.py). The build is the replay's: one semantic model, shop_model_live, made on the
source tables; the silver tables and the gold views are not part of it and are drawn dashed, as the editor draws them.
data_flow.py draws the pipeline only when a build has one, so this flow has none. tests/test_n217_replay_flow.py checks
that what the page shows equals data_flow.py's output.

This module only places the boxes: one wide picture (left to right, as the editor) and one tall picture for phones (the
source and silver tables side by side, the gold views and the model under them), both inline SVG with classes only
(no script, no style attribute, no external request), and the same flow as a list for screen readers.
"""
from __future__ import annotations

import functools
import html

# The lakehouse the replay's build reads: synthetic, as in workload/scripts/build_flow_fixture.py
INFO = {"workspace_id": "00000000-0000-0000-0000-000000000000", "item_id": "00000000-0000-0000-0000-000000000001",
        "item_name": "demo_lh", "item_kind": "Lakehouse", "schema": "shop", "sql_endpoint": "", "sql_db": "demo_lh",
        "schemas_enabled": True}
MODEL = "shop_model_live"                                  # the replay's fourth answer
CHOSEN = {"semantic_model": MODEL}
# the card workload_api._flow makes for a semantic model in a build without gold views
ITEMS = [{"output": "semantic_model", "label": "Semantic model", "name": MODEL,
          "reads": f"reads the source tables in {INFO['schema']} (bronze) directly"}]

BOX_W, BOX_H, ITEM_H, GAP_Y, TOP = 150, 22, 36, 6, 26


@functools.lru_cache(maxsize=1)
def replay_flow() -> dict:
    """data_flow.flow() for the replay's build on the synthetic shop schema."""
    from . import data_flow, seed
    from .infer import plan
    return data_flow.flow(plan(seed.schema("shop")), INFO, CHOSEN, items=ITEMS)


def _h(n: dict) -> int:
    return ITEM_H if n.get("kind_label") else BOX_H


def _place(flow: dict, spots: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float, int]]:
    """Each node's top-left corner and height: a column's nodes stacked from its spot, in the engine's order."""
    out = {}
    for col, (x, y) in spots.items():
        for n in (m for m in flow["nodes"] if m["column"] == col):
            out[n["id"]] = (x, y, _h(n))
            y += _h(n) + GAP_Y
    return out


def _paths(flow: dict, at: dict, tall: bool) -> list[tuple[dict, str]]:
    out = []
    bronze = [at[n["id"]] for n in flow["nodes"] if n["column"] == "bronze"]
    for e in flow["edges"]:
        if e["to"] not in at:
            continue
        tx, ty, th = at[e["to"]]
        if e["from"] == "bronze":                          # the items read the source: one line from the bronze column
            if tall:                                       # down the left side, under the last source table
                bx, by, bh = bronze[-1]
                d = f"M{bx + 12},{by + bh} V{ty}"
            else:                                          # along the top, as the editor draws it
                sx = bronze[0][0] + BOX_W / 2
                bend = tx - 26
                d = (f"M{sx},{TOP - 4} V{TOP - 12} H{bend} C{bend + 16},{TOP - 12} {bend},{ty + th / 2} "
                     f"{tx},{ty + th / 2}")
            out.append((e, d))
            continue
        if e["from"] not in at:
            continue
        sx, sy, sh = at[e["from"]]
        a, b = sy + sh / 2, ty + th / 2
        if tall and sx == tx:                              # silver above gold in the same column: a bracket on the right
            r = sx + BOX_W
            d = f"M{r},{a} C{r + 14},{a} {r + 14},{b} {r},{b}"
        else:
            s, m = sx + BOX_W, (sx + BOX_W + tx) / 2
            d = f"M{s},{a} C{m},{a} {m},{b} {tx},{b}"
        out.append((e, d))
    return out


def _clip(s: str, n: int = 24) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def _svg(flow: dict, tall: bool) -> str:
    titles = {c["id"]: c["title"] for c in flow["columns"]}
    present = [c["id"] for c in flow["columns"] if any(n["column"] == c["id"] for n in flow["nodes"])]
    if tall:
        gap = 20
        x0, x1 = 0, BOX_W + gap
        upper = {c: (x, TOP) for c, x in (("bronze", x0), ("silver", x1)) if c in present}
        at = _place(flow, upper)
        y2 = max(y + h for (x, y, h) in at.values()) + 34 + TOP - 14
        lower = {c: (x, y2) for c, x in (("built", x0), ("gold", x1)) if c in present}
        at.update(_place(flow, lower))
        heads = [(c, x, y - 12) for c, (x, y) in {**upper, **lower}.items()]
        width = 2 * BOX_W + gap + 16
    else:
        gap = 46
        spots = {c: (i * (BOX_W + gap), TOP) for i, c in enumerate(present)}
        at = _place(flow, spots)
        heads = [(c, x, 10) for c, (x, y) in spots.items()]
        width = len(present) * BOX_W + (len(present) - 1) * gap + 2
    height = max(y + h for (x, y, h) in at.values()) + 2
    stage = {n["id"]: n["column"] for n in flow["nodes"]}
    parts = [f'<svg class="kgr kgr-{"tall" if tall else "wide"}" viewBox="0 0 {width:g} {height:g}" '
             f'width="{width:g}" height="{height:g}" aria-hidden="true" focusable="false">']
    for c, x, y in heads:
        parts.append(f'<text class="kgr-col kgr-at-{c}" x="{x:g}" y="{y:g}">{html.escape(titles[c].split(":")[0])}</text>')
    for e, d in _paths(flow, at, tall):
        cls = "kgr-e" + ("" if e["built"] else " off")
        parts.append(f'<path class="{cls} kgr-at-{stage.get(e["to"], "built")}" d="{d}" '
                     f'data-from="{html.escape(e["from"])}" data-to="{html.escape(e["to"])}"/>')
    for n in flow["nodes"]:
        x, y, h = at[n["id"]]
        cls = f"kgr-n kgr-{n['column']} kgr-at-{n['column']}" + ("" if n["built"] else " off")
        inner = f'<rect width="{BOX_W}" height="{h}" rx="6"/>'
        if n.get("kind_label"):
            inner += (f'<text class="kgr-kind" x="8" y="14">{html.escape(n["kind_label"])}</text>'
                      f'<text x="8" y="29">{html.escape(_clip(n["label"]))}</text>')
        else:
            inner += f'<text x="8" y="15">{html.escape(_clip(n["label"]))}</text>'
        parts.append(f'<g class="{cls}" data-id="{html.escape(n["id"])}" transform="translate({x:g},{y:g})">{inner}</g>')
    parts.append("</svg>")
    return "".join(parts)


def _words(flow: dict) -> str:
    """The flow as a list, for screen readers: each stage, whether this build makes it, its boxes and their lines."""
    items = []
    for c in flow["columns"]:
        nodes = [n for n in flow["nodes"] if n["column"] == c["id"]]
        if not nodes:
            continue
        if c["id"] == "bronze":
            state = "the source"
        else:
            state = "part of this build" if all(n["built"] for n in nodes) else "not part of this build"
        rows = []
        for n in nodes:
            what = f'{n["kind_label"]} {n["label"]}' if n.get("kind_label") else n["label"]
            lines = "; ".join(x for x in n["lines"] if x)
            rows.append(f"<li>{html.escape(what)}{': ' + html.escape(lines) if lines else ''}</li>")
        items.append(f"<li>{html.escape(c['title'])} ({state}):<ul>{''.join(rows)}</ul></li>")
    return "<ol>" + "".join(items) + "</ol>"


@functools.lru_cache(maxsize=1)
def replay_flow_html() -> str:
    """The flow in the replay's card, under the turns: the wide picture, the tall one, a legend and the list. It sits
    under the turns rather than in the fourth answer so the card keeps the height of its longest turn (n203: no empty
    band while a question is typed); the source tables show throughout, and the other stages are drawn in step with the
    fourth answer (site.css)."""
    f = replay_flow()
    return ('      <div class="session-flow">'
            '<p class="kgr-sr">The data flow of the build in answer 4, as a list:</p>'
            f'<div class="kgr-sr kgr-words">{_words(f)}</div>'
            f'{_svg(f, tall=False)}{_svg(f, tall=True)}'
            '<p class="kgr-legend" aria-hidden="true"><span class="kgr-lg">Solid: part of this build</span>'
            '<span class="kgr-lg off">Dashed: not part of this build</span><span>Synthetic shop data</span></p>'
            '</div>')
