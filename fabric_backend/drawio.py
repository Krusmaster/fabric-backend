"""Krusgraph's diagrams as draw.io files (round n228). The founder, 12 November 2026, looking at the semantic model draft
card in claude.ai: "can I see this as a draw.io file/flow if I want?"

Three diagrams, each from what Krusgraph already computes, by rules, with no AI and nothing but the standard library:

- the map (`map_data`, `map_file`): tables as boxes with their key, links as arrows labelled with the column and the rule
  (R1, R5, SAP pack). A table without a key is marked "no key"; a composite key shows every column. The data has the
  shape of the chat cards' map (mcp_apps_pictures.map_from_plan) and of the Model editor's MapData, so either can be
  exported as it is; `map_data` makes it from a plan without the cards' 60-table limit.
- the semantic model draft (`model_data`, `model_file`): what semantic_model.draft() wrote. Fact and dimension tables in
  two colours, relationships with cardinality (many to one), inactive ones dashed, the ones a tabular model cannot
  express dotted red with the reason, the date table, and each table's measures listed in its box. The relationships
  are read from the draft's own relationships.tmdl and summary, so the picture is the file, not a second opinion.
- the data flow (`flow_file`): data_flow.flow()'s nodes and edges: bronze -> silver -> gold -> the items built on the
  source, and what is built on those (a report on the model, an app on the API).

The format is draw.io's uncompressed mxfile XML (an <mxfile> with one <diagram> holding an <mxGraphModel>), which
app.diagrams.net and the desktop app open as they are. Nothing in a file depends on the time or on the order of a
dict: ids are made from the names, coordinates are whole numbers, and every cell is one line, so two exports of the
same plan are byte for byte the same and a changed plan shows as a small diff.

The layout is left to right in columns. An edge runs only in the gutters between columns: it leaves a box on its side,
turns in a channel of its own and enters the next column's box on its side; an edge that passes a column does so in a
row reserved for it between the boxes, so no edge is drawn through a box and no two boxes overlap, at any size
(`problems()` checks a file for both and for a well-formed structure; tests/test_n228_drawio.py runs it on 200 tables).
Names are cleaned of characters XML does not allow and escaped by the XML writer; labels are HTML, so a name is
HTML-escaped first.

Read-only: these functions read a plan, a draft or a flow that is already in memory and return text.
"""
from __future__ import annotations

import hashlib
import html
import math
import re
import xml.etree.ElementTree as ET

MIME = "application/vnd.jgraph.mxfile"
EXTENSION = ".drawio"
DIAGRAMS = ("map", "semantic_model", "data_flow")
FORMATS = ("json", "drawio")
HOW = ("Save `content` as a file with the name in `filename` and open it in draw.io (app.diagrams.net: File, Open from, "
       "Device; or the desktop app). Nothing was written to Fabric.")

# sizes, in draw.io's units (pixels at 100 %)
CHAR, LABEL_CHAR, LINE = 6.8, 5.8, 17           # the width of a character of a box's text and of an edge's label; a line's height
MIN_W, MAX_W = 150, 400
ROW_GAP, PASS_GAP = 26, 12                      # between two boxes of a column; around a row an edge passes a column in
PORT, CHANNEL, PAD = 16, 8, 28                  # between two edges on a box's side; between two channels; a gutter's margin
MAX_ROWS = 12                                   # boxes per column before a layer is split into two columns
MAX_NOTES = 12                                  # reasons written under the semantic model before "and n more"
MAX_MEASURES = 12                               # measures listed in one table's box before "and n more"

_INVALID = re.compile("[^\u0009\u000a\u000d -퟿-�\U00010000-\U0010ffff]")
COLOURS = {                                     # fill, stroke
    "table": ("#DAE8FC", "#6C8EBF"), "no_key": ("#FFF2CC", "#D6B656"),
    "fact": ("#FFE6CC", "#D79B00"), "dimension": ("#DAE8FC", "#6C8EBF"), "date": ("#D5E8D4", "#82B366"),
    "other": ("#F5F5F5", "#666666"),
    "bronze": ("#F8CECC", "#B85450"), "silver": ("#F5F5F5", "#666666"), "gold": ("#FFF2CC", "#D6B656"),
    "built": ("#DAE8FC", "#6C8EBF"), "pipeline": ("#E1D5E7", "#9673A6"),
}
RED, GREY = "#B85450", "#888888"


def clean(text) -> str:
    """The text without the characters XML 1.0 does not allow (a control character in a name becomes U+FFFD)."""
    return _INVALID.sub("�", str(text))


def _esc(text) -> str:
    return html.escape(clean(text), quote=False)


def cell_id(kind: str, *parts) -> str:
    """A cell's id from what it stands for: readable when the names are plain, with a short hash of the exact names
    when they are not (or are long), so two different names never share an id and the same name always gets the same."""
    raw = "|".join(clean(p) for p in parts)
    slug = re.sub(r"[^A-Za-z0-9_]+", "-", raw).strip("-")
    if slug != raw.replace("|", "-") or len(slug) > 60:
        slug = (slug[:48] + "-" if slug else "") + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{kind}-{slug}"


def filename(name: str, diagram: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", clean(name or "")).strip("-.") or "krusgraph"
    return f"{stem[:80]}-{diagram.replace('_', '-')}{EXTENSION}"


def _short(text: str, n: int) -> str:
    text = " ".join(clean(text).split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


# ------------------------------------------------------------------------------------------------ the layout ----

def _size(lines: list[str], bold_first: bool = True) -> tuple[int, int]:
    """A box for these lines of text: wide enough for the longest up to MAX_W, and as high as the lines need when the
    longer ones wrap."""
    longest = max((len(x) * (CHAR * 1.08 if i == 0 and bold_first else CHAR) for i, x in enumerate(lines)), default=0)
    w = int(min(MAX_W, max(MIN_W, math.ceil(longest + 24))))
    rows = sum(max(1, math.ceil(len(x) * CHAR * 1.08 / (w - 20))) for x in lines) or 1
    return w, int(rows * LINE + 14)


def _columns(ids: list[str], pairs: list[tuple[str, str]]) -> dict[str, int]:
    """A column for every node: an arrow goes from a column to one further right. Cycles are broken where a depth-first
    walk in the given order closes them (that one arrow then points left); a node nothing points at stands just left of
    what it points at; nodes without any arrow come last. A layer of more than MAX_ROWS is split into several columns."""
    succ: dict[str, list[str]] = {i: [] for i in ids}
    for a, b in pairs:
        if a != b and b not in succ[a]:
            succ[a].append(b)
    state: dict[str, int] = {}
    back: set[tuple[str, str]] = set()
    for root in ids:                                              # iterative depth-first walk: an arrow onto the walk's own path closes a cycle
        if root in state:
            continue
        stack = [(root, iter(succ[root]))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
            elif state.get(nxt) == 1:
                back.add((node, nxt))
            elif nxt not in state:
                state[nxt] = 1
                stack.append((nxt, iter(succ[nxt])))
    out: dict[str, list[str]] = {i: [] for i in ids}
    into: dict[str, list[str]] = {i: [] for i in ids}
    for a in ids:
        for b in succ[a]:
            x, y = (b, a) if (a, b) in back else (a, b)
            if y not in out[x]:
                out[x].append(y)
                into[y].append(x)
    rank: dict[str, int] = {}
    left = {i: len(into[i]) for i in ids}
    ready = [i for i in ids if not left[i]]
    while ready:                                                  # longest path from the left
        n = ready.pop(0)
        rank[n] = max((rank[p] + 1 for p in into[n]), default=0)
        for m in out[n]:
            left[m] -= 1
            if not left[m]:
                ready.append(m)
    for n in ids:
        if not into[n] and out[n]:
            rank[n] = min(rank[m] for m in out[n]) - 1
    linked = [i for i in ids if into[i] or out[i]]
    alone = [i for i in ids if not into[i] and not out[i]]
    col: dict[str, int] = {}
    at = 0
    for r in sorted({rank[i] for i in linked}):
        layer = [i for i in linked if rank[i] == r]
        for k, i in enumerate(layer):
            col[i] = at + k // MAX_ROWS
        at += (len(layer) - 1) // MAX_ROWS + 1
    for k, i in enumerate(alone):
        col[i] = at + k // MAX_ROWS
    return col


def layout(nodes: list[dict], edges: list[dict], columns: dict[str, int] | None = None) -> dict:
    """Places `nodes` ({id, w, h, pin?: "top" | "bottom"}) in columns and routes `edges` ({id, source, target, label?}).
    `columns` fixes each node's column (the data flow); without it the columns come from the arrows. Returns {"nodes":
    {id: (x, y, w, h)}, "edges": {id: {"points", "exit", "entry", "label_at"}}, "width", "height"}; an edge whose ends
    are not both nodes is left out."""
    ids = [n["id"] for n in nodes]
    by_id = {n["id"]: n for n in nodes}
    edges = [e for e in edges if e["source"] in by_id and e["target"] in by_id]
    if columns is None:
        col = _columns(ids, [(e["source"], e["target"]) for e in edges])
    else:
        col = {i: int(columns.get(i, 0)) for i in ids}
        for _ in ids:                                             # two ends in one column: the target moves one to the right
            same = [e for e in edges if e["source"] != e["target"] and col[e["source"]] == col[e["target"]]]
            if not same:
                break
            for e in same:
                if col[e["source"]] == col[e["target"]]:
                    col[e["target"]] += 1
    n_cols = max(col.values(), default=-1) + 1
    order: list[list[str]] = [[] for _ in range(n_cols)]
    for i in ids:
        order[col[i]].append(i)
    # an edge as a chain from its left end to its right end, with one passing row in every column between them
    chains: dict[str, list[str]] = {}
    passes: set[str] = set()
    for e in edges:
        if e["source"] == e["target"]:
            continue
        a, b = sorted((e["source"], e["target"]), key=lambda i: col[i])
        chain = [a]
        for c in range(col[a] + 1, col[b]):
            p = f"\x00{e['id']}\x00{c}"
            passes.add(p)
            order[c].append(p)
            chain.append(p)
        chains[e["id"]] = chain + [b]
    near: dict[str, tuple[list[str], list[str]]] = {i: ([], []) for column in order for i in column}
    for chain in chains.values():
        for x, y in zip(chain, chain[1:]):
            near[x][1].append(y)
            near[y][0].append(x)
    pin = lambda i: {"top": 0, "bottom": 2}.get(by_id[i].get("pin"), 1) if i in by_id else 1

    def sweep(columns_in_order, side: int) -> None:
        for c in columns_in_order:
            place = {i: k for column in order for k, i in enumerate(column)}
            def key(i):
                ns = near[i][side]
                return (pin(i), sum(place[n] for n in ns) / len(ns) if ns else place[i], place[i])
            order[c].sort(key=key)
    for c in range(n_cols):
        order[c].sort(key=pin)
    for _ in range(4):                                            # the barycentre of the neighbours, left to right and back
        sweep(range(1, n_cols), 0)
        sweep(range(n_cols - 2, -1, -1), 1)

    # heights: a box is at least as high as the edges on its fuller side need
    sides: dict[str, tuple[list, list]] = {i: ([], []) for i in ids}          # (left, right): (edge id, the node at the other end)
    for e in edges:
        if e["source"] == e["target"]:
            sides[e["source"]][1].extend([(e["id"], None), (e["id"], None)])
            continue
        chain = chains[e["id"]]
        sides[chain[0]][1].append((e["id"], chain[1]))
        sides[chain[-1]][0].append((e["id"], chain[-2]))
    h = {i: max(int(by_id[i]["h"]), PORT * (max(len(sides[i][0]), len(sides[i][1])) + 1)) for i in ids}
    width = [max((int(by_id[i]["w"]) for i in column if i in by_id), default=0) for column in order]
    # rows: y of every box and of every passing row
    y: dict[str, int] = {}
    tall = []
    for column in order:
        at, prev = 0, None
        for i in column:
            real = i in by_id
            if prev is not None:
                at += ROW_GAP if real and prev else PASS_GAP
            y[i] = at
            at += h[i] if real else 0
            prev = real
        tall.append(at)
    height = max(tall, default=0)
    for column, t in zip(order, tall):
        shift = (height - t) // 2 if columns is None else 0      # fixed columns keep their headings on one line
        for i in column:
            y[i] += shift
    # ports: the edges on a side, top to bottom in the order of where they come from
    centre = lambda i: y[i] + (h[i] // 2 if i in by_id else 0)
    port: dict[tuple[str, str], int] = {}                           # (node, edge id) -> y; a loop has two, the second under edge id + "'"
    for i in ids:
        for side in (0, 1):
            here = sorted(sides[i][side], key=lambda s: (centre(s[1]) if s[1] else 10 ** 9, s[0]))
            for k, (eid, _) in enumerate(here):
                yy = y[i] + round(h[i] * (k + 1) / (len(here) + 1))
                port[(i, eid + "'") if (i, eid) in port else (i, eid)] = yy
    # gutters: a channel for every edge that turns in it, and room for the labels at the edges' starts
    label_w = lambda e: int(len(clean(e.get("label") or "")) * LABEL_CHAR + 12) if e.get("label") else 0
    turns: list[list[tuple]] = [[] for _ in range(max(n_cols - 1, 0))]
    pad_l, pad_r = [PAD] * n_cols, [PAD] * n_cols                    # the margin right of column c, and left of column c
    for e in edges:
        if e["source"] == e["target"]:
            pad_l[col[e["source"]]] = max(pad_l[col[e["source"]]], PAD + label_w(e))
            continue
        chain = chains[e["id"]]
        forward = chain[0] == e["source"]
        if forward:
            pad_l[col[chain[0]]] = max(pad_l[col[chain[0]]], label_w(e) + 20)
        else:
            pad_r[col[chain[-1]]] = max(pad_r[col[chain[-1]]], label_w(e) + 20)
        for k, (a, b) in enumerate(zip(chain, chain[1:])):
            ya = port[(a, e["id"])] if a in by_id else y[a]
            yb = port[(b, e["id"])] if b in by_id else y[b]
            turns[col[chain[0]] + k].append((ya, yb, e["id"], k))
    x = [0] * n_cols
    channel: dict[tuple[str, int], int] = {}
    for g in range(n_cols):
        if g:
            ts = turns[g - 1]
            up = sorted((t for t in ts if t[0] > t[1]), key=lambda t: (t[0], t[1], t[2]))
            down = sorted((t for t in ts if t[0] < t[1]), key=lambda t: (-t[0], -t[1], t[2]))
            start = x[g - 1] + width[g - 1] + pad_l[g - 1]
            for k, t in enumerate(up + down):
                channel[(t[2], t[3])] = start + k * CHANNEL
            x[g] = start + max(len(up) + len(down) - 1, 0) * CHANNEL + pad_r[g]
    placed = {i: (x[col[i]], y[i], width[col[i]], h[i]) for i in ids}
    routed = {}
    for e in edges:
        s, t = e["source"], e["target"]
        if s == t:
            bx, by, bw, bh = placed[s]
            y1, y2 = sorted((port[(s, e["id"])], port[(s, e["id"] + "'")]))
            pts = [(bx + bw + 14, y1), (bx + bw + 14, y2)]
            ends = ((bx + bw, y1), (bx + bw, y2))
            exit_, entry = (1, (y1 - by) / bh), (1, (y2 - by) / bh)
        else:
            chain = chains[e["id"]]
            pts = []
            for k, (a, b) in enumerate(zip(chain, chain[1:])):
                ya = port[(a, e["id"])] if a in by_id else y[a]
                yb = port[(b, e["id"])] if b in by_id else y[b]
                if ya != yb:
                    cx = channel[(e["id"], k)]
                    pts += [(cx, ya), (cx, yb)]
            a, b = chain[0], chain[-1]
            ax, ay, aw, ah = placed[a]
            bx, by, bw, bh = placed[b]
            pa, pb = port[(a, e["id"])], port[(b, e["id"])]
            left_end, right_end = (1, (pa - ay) / ah), (0, (pb - by) / bh)
            ends = ((ax + aw, pa), (bx, pb))
            if chain[0] == s:
                exit_, entry = left_end, right_end
            else:
                exit_, entry, pts, ends = right_end, left_end, pts[::-1], ends[::-1]
        path = [ends[0]] + pts + [ends[1]]
        length = sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(path, path[1:])) or 1
        along = 10 + label_w(e) / 2
        routed[e["id"]] = {"points": pts, "exit": exit_, "entry": entry,
                           "label_at": round(max(-1.0, min(1.0, -1 + 2 * along / length)), 3)}
    total_w = (x[-1] + width[-1] + pad_l[-1]) if n_cols else 0
    return {"nodes": placed, "edges": routed, "width": total_w, "height": height}


# ------------------------------------------------------------------------------------------------- the file ----

BOX = "rounded=1;arcSize=6;whiteSpace=wrap;html=1;align=left;verticalAlign=top;spacingLeft=8;spacingRight=6;spacingTop=4;fontSize=12;"
TEXT = "text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;strokeColor=none;fillColor=none;fontSize=12;"
EDGE = "edgeStyle=none;rounded=1;html=1;fontSize=10;labelBackgroundColor=default;exitPerimeter=0;entryPerimeter=0;"


def _box_style(kind: str, dashed: bool = False) -> str:
    fill, stroke = COLOURS[kind]
    return BOX + f"fillColor={fill};strokeColor={stroke};" + ("dashed=1;" if dashed else "")


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else f"{v:.4f}".rstrip("0").rstrip(".")


class _File:
    """One diagram's cells, written one per line in the order they were added."""

    def __init__(self, diagram: str, name: str):
        self.diagram, self.name, self.cells, self.ids = diagram, name, [], set()
        self.right = self.bottom = 0

    def _add(self, cid: str, value: str, style: str, tooltip: str | None, attrs: dict, geometry: ET.Element) -> None:
        if cid in self.ids:
            raise ValueError(f"two cells with the id {cid}")
        self.ids.add(cid)
        cell = ET.Element("mxCell", {"style": style, **attrs, "parent": "1"})
        cell.append(geometry)
        if tooltip:
            outer = ET.Element("UserObject", {"label": value, "tooltip": clean(tooltip), "id": cid})
            outer.append(cell)
        else:
            cell.attrib = {"id": cid, "value": value, **cell.attrib}
            outer = cell
        self.cells.append(outer)

    def box(self, cid: str, lines_html: list[str], style: str, at: tuple, tooltip: str | None = None) -> None:
        bx, by, bw, bh = at
        geo = ET.Element("mxGeometry", {"x": _num(bx), "y": _num(by), "width": _num(bw), "height": _num(bh), "as": "geometry"})
        self._add(cid, "<br>".join(lines_html), style, tooltip, {"vertex": "1"}, geo)
        self.right, self.bottom = max(self.right, bx + bw), max(self.bottom, by + bh)

    def edge(self, cid: str, label: str, style: str, source: str, target: str, route: dict, tooltip: str | None = None) -> None:
        style += (f"exitX={_num(route['exit'][0])};exitY={_num(route['exit'][1])};exitDx=0;exitDy=0;"
                  f"entryX={_num(route['entry'][0])};entryY={_num(route['entry'][1])};entryDx=0;entryDy=0;")
        geo = ET.Element("mxGeometry", {"x": _num(route["label_at"]), "relative": "1", "as": "geometry"})
        if route["points"]:
            pts = ET.SubElement(geo, "Array", {"as": "points"})
            for px, py in route["points"]:
                ET.SubElement(pts, "mxPoint", {"x": _num(px), "y": _num(py)})
        self._add(cid, _esc(label), style, tooltip, {"edge": "1", "source": source, "target": target}, geo)

    def text(self) -> str:
        w, hh = int(self.right + 40), int(self.bottom + 40)
        head = ('<mxfile host="Krusgraph" agent="Krusgraph draw.io export" version="24.7.17" type="device">\n'
                f'<diagram id="{self.diagram}" name={_attr(self.name)}>\n'
                f'<mxGraphModel dx="{w}" dy="{hh}" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" '
                f'page="0" pageScale="1" pageWidth="{w}" pageHeight="{hh}" math="0" shadow="0">\n<root>\n'
                '<mxCell id="0"/>\n<mxCell id="1" parent="0"/>\n')
        body = "".join(ET.tostring(c, encoding="unicode") + "\n" for c in self.cells)
        return head + body + "</root>\n</mxGraphModel>\n</diagram>\n</mxfile>\n"


def _attr(text: str) -> str:
    e = ET.Element("a", {"v": clean(text)})
    return ET.tostring(e, encoding="unicode")[5:-3]


def _text_box(f: _File, cid: str, lines: list[str], top: int, width: int, bold_first: bool = True) -> int:
    """A block of text under the picture; returns the y under it."""
    if not lines:
        return top
    w = int(max(360, min(max(width, 360), 900)))
    rows = sum(max(1, math.ceil(len(x) * CHAR / (w - 16))) for x in lines)
    hh = int(rows * LINE + 12)
    shown = [("<b>" + _esc(x) + "</b>") if i == 0 and bold_first else _esc(x) for i, x in enumerate(lines)]
    f.box(cid, shown, TEXT, (0, top, w, hh))
    return top + hh + 16


def _draw(f: _File, nodes: list[dict], edges: list[dict], columns: dict[str, int] | None, title: list[str], notes: list[str],
          legend: list[str]) -> str:
    """Places and writes the nodes ({id, lines_html, plain, style, tooltip?}) and edges ({id, source, target, label,
    style, tooltip?}); the title above, the legend and the notes below."""
    for n in nodes:
        n["w"], n["h"] = n.get("size") or _size(n["plain"])
    top = int(len(title) * LINE + 12 + 20) if title else 0
    lay = layout(nodes, edges, columns)
    if title:
        f.box(f"{f.diagram}-title", [("<b>" + _esc(x) + "</b>") if i == 0 else _esc(x) for i, x in enumerate(title)],
              TEXT + "fontSize=13;", (0, 0, int(max(lay["width"], 480)), top - 20))
    for n in nodes:
        bx, by, bw, bh = lay["nodes"][n["id"]]
        f.box(n["id"], n["lines_html"], n["style"], (bx, by + top, bw, bh), n.get("tooltip"))
    for e in edges:
        r = lay["edges"].get(e["id"])
        if r:
            r = {**r, "points": [(px, py + top) for px, py in r["points"]]}
            f.edge(e["id"], e.get("label") or "", e["style"], e["source"], e["target"], r, e.get("tooltip"))
    under = top + lay["height"] + 40
    under = _text_box(f, f"{f.diagram}-legend", legend, under, lay["width"])
    _text_box(f, f"{f.diagram}-notes", notes, under, lay["width"])
    return f.text()


# -------------------------------------------------------------------------------------------------- the map ----

def map_data(plan, tables: set[str] | list[str] | None = None) -> dict:
    """The plan as the map's data: every table with its key and the key's rule, every relationship with its rule as a
    person reads it (`rule_label`: "SAP pack"). `tables` keeps those tables only. No limit on the number of tables."""
    keep = {t.lower() for t in tables} if tables is not None else None
    keyed = {k.lower(): v for k, v in plan.keys.items()}
    out_tables = []
    for t in plan.schema:
        if keep is not None and t.name.lower() not in keep:
            continue
        cols, rule = keyed.get(t.name.lower(), ([], None))
        out_tables.append({"name": t.name, "key": list(cols), "key_rule": rule or "K3", "columns": len(t.columns),
                           **({"key_rule_label": plan.label(rule)} if rule and plan.label(rule) != rule else {})})
    names = {t["name"].lower() for t in out_tables}
    rels = [{"id": f"rel:{r.source}.{'+'.join(r.source_cols)}>{r.target}", "source": r.source, "source_cols": list(r.source_cols),
             "target": r.target, "target_cols": list(r.target_cols), "rule": r.rule, "rule_label": plan.label(r.rule)}
            for r in plan.relationships if r.source.lower() in names and r.target.lower() in names]
    return {"tables": out_tables, "relationships": rels, "schema": plan.schema.schema or ""}


def _table_names(tables: list[dict]) -> dict[str, str]:
    return {str(t["name"]).lower(): cell_id("table", t["name"]) for t in tables}


def _key_line(t: dict) -> str:
    key = [str(c) for c in t.get("key") or []]
    if not key:
        return "no key"
    rule = t.get("key_rule_label") or t.get("key_rule")
    return f"key: {' + '.join(key)}" + (f" ({rule})" if rule else "")


def _link_words(r: dict) -> str:
    return (f"{r['source']}.{'+'.join(map(str, r.get('source_cols') or []))} -> "
            f"{r['target']}.{'+'.join(map(str, r.get('target_cols') or []))}")


def map_file(data: dict, title: str = "") -> str:
    """The map as a draw.io file. `data`: {"tables": [{name, key, key_rule, columns?}], "relationships": [{source,
    source_cols, target, target_cols, rule, rule_label?, state?, proposed?}]} (map_data, or the cards' and the editor's map)."""
    tables = [t for t in data.get("tables") or [] if isinstance(t, dict) and t.get("name") is not None]
    ids = _table_names(tables)
    nodes = []
    for t in tables:
        plain = [str(t["name"]), _key_line(t)] + ([f"{t['columns']} columns"] if isinstance(t.get("columns"), int) else [])
        nodes.append({"id": ids[str(t["name"]).lower()], "plain": plain, "tooltip": None,
                      "lines_html": ["<b>" + _esc(plain[0]) + "</b>"] + [_esc(x) for x in plain[1:]],
                      "style": _box_style("table" if t.get("key") else "no_key", dashed=not t.get("key"))})
    edges, seen = [], set()
    for r in data.get("relationships") or []:
        if not isinstance(r, dict) or str(r.get("source", "")).lower() not in ids or str(r.get("target", "")).lower() not in ids:
            continue
        eid = cell_id("link", r["source"], "+".join(map(str, r.get("source_cols") or [])), r["target"])
        if eid in seen:
            continue
        seen.add(eid)
        rule = str(r.get("rule_label") or r.get("rule") or "")
        state = str(r.get("state") or "")
        label = "+".join(map(str, r.get("source_cols") or [])) + (f" · {rule}" if rule else "")
        if r.get("proposed") or state == "not_counted":
            label += " · proposed, not counted"
        elif state and state != "not_checked":
            label += f" · {state}"
        style = EDGE + "endArrow=block;endFill=1;strokeColor=#444444;"
        if r.get("proposed") or state == "not_counted":
            style = EDGE + f"endArrow=block;endFill=0;dashed=1;strokeColor={GREY};fontColor={GREY};"
        elif state == "failed":
            style = EDGE + f"endArrow=block;endFill=1;strokeColor={RED};fontColor={RED};"
        edges.append({"id": eid, "source": ids[str(r["source"]).lower()], "target": ids[str(r["target"]).lower()],
                      "label": label, "style": style, "tooltip": _link_words(r) + (f" ({rule})" if rule else "")})
    no_key = sum(1 for t in tables if not t.get("key"))
    head = [title or "Krusgraph: the map", f"{len(tables)} tables, {len(edges)} links" + (f", {no_key} without a key" if no_key else "")]
    legend = ["How to read it", "A box is a table with its key and the rule the key comes from; a dashed yellow box has no key.",
              "An arrow goes from the column that refers to the table it points at; its label is the column and the rule."]
    notes = [str(data["left_out"])] if data.get("left_out") else []
    return _draw(_File("map", "Map"), nodes, edges, None, head, (["Notes"] + notes) if notes else [], legend)


# --------------------------------------------------------------------------------------- the semantic model ----

_TMDL_REF = re.compile(r"^('(?:[^']|'')*'|[^.']+)\.('(?:[^']|'')*'|.+)$")


def _tmdl_plain(name: str) -> str:
    return name[1:-1].replace("''", "'") if len(name) >= 2 and name.startswith("'") and name.endswith("'") else name


def tmdl_relationships(text: str) -> list[dict]:
    """The relationships of a relationships.tmdl as semantic_model.draft() writes it: [{source, column, target,
    target_column, active}]."""
    out, cur = [], None
    for line in (text or "").splitlines():
        s = line.strip()
        if line.startswith("relationship "):
            cur = {"active": True}
            out.append(cur)
        elif cur is not None and s == "isActive: false":
            cur["active"] = False
        elif cur is not None and (s.startswith("fromColumn: ") or s.startswith("toColumn: ")):
            m = _TMDL_REF.match(s.split(": ", 1)[1])
            if m:
                t, c = _tmdl_plain(m.group(1)), _tmdl_plain(m.group(2))
                if s.startswith("fromColumn"):
                    cur["source"], cur["column"] = t, c
                else:
                    cur["target"], cur["target_column"] = t, c
    return [r for r in out if {"source", "column", "target", "target_column"} <= set(r)]


def _why_short(x: dict) -> str:
    if x.get("key_not_unique"):
        return "key not unique in the rows"
    if len(x.get("columns") or []) > 1 or len(x.get("target_columns") or []) > 1:
        return "composite key"
    why = str(x.get("why") or "")
    return "no key on the one side" if "has no key" in why else "composite key on the one side"


def model_data(map_: dict, draft: dict, name: str = "") -> dict:
    """What semantic_model.draft() wrote, as the diagram's data. `map_`: the plan's map (map_data), for the keys and the
    rules; `draft`: draft()'s answer ({"parts", "summary"}). Tables are the summary's, each with its role and measures;
    relationships are the ones in relationships.tmdl (active or inactive, with the summary's reason for an inactive
    one) and the summary's not expressible ones with their reasons; the date table with what relates to it."""
    summary = draft.get("summary") or {}
    parts = draft.get("parts") or {}
    by_name = {str(t["name"]).lower(): t for t in map_.get("tables") or []}
    rules = {(str(r["source"]).lower(), "+".join(map(str, r["source_cols"])).lower(), str(r["target"]).lower()):
             (r.get("rule_label") or r.get("rule") or "") for r in map_.get("relationships") or []}
    measures: dict[str, list[dict]] = {}
    for m in summary.get("measures") or []:
        measures.setdefault(m["table"], []).append({"name": m["name"], "expression": m["expression"]})
    tables = [{"name": t, "role": role or "other", "key": list((by_name.get(t.lower()) or {}).get("key") or []),
               "measures": measures.get(t, [])} for t, role in (summary.get("roles") or {}).items()]
    cal = summary.get("date_table") or None
    cal_name = cal["name"] if cal else None
    why_inactive = {(x["source"].lower(), "+".join(x["columns"]).lower(), x["target"].lower()): x["why"] for x in summary.get("inactive") or []}
    rels = []
    for r in tmdl_relationships(parts.get("definition/relationships.tmdl", "")):
        if cal_name and r["target"] == cal_name:
            continue                                                # the date table's are taken from the summary, with their reason
        k = (r["source"].lower(), r["column"].lower(), r["target"].lower())
        rels.append({"source": r["source"], "source_cols": [r["column"]], "target": r["target"], "target_cols": [r["target_column"]],
                     "state": "active" if r["active"] else "inactive", "rule": rules.get(k, ""),
                     **({"why": why_inactive.get(k, "another active path already joins the two tables")} if not r["active"] else {})})
    for x in summary.get("not_expressible") or []:
        k = (x["source"].lower(), "+".join(x["columns"]).lower(), x["target"].lower())
        rels.append({"source": x["source"], "source_cols": list(x["columns"]), "target": x["target"],
                     "target_cols": list(x.get("target_columns") or []), "state": "not_expressible",
                     "rule": rules.get(k, x.get("rule") or ""), "why": x.get("why") or "", "short": _why_short(x)})
    notes = []
    if summary.get("reads"):
        notes.append(str(summary["reads"].get("said") or ""))
    out = {"name": name, "tables": tables, "relationships": rels, "notes": [n for n in notes if n]}
    if cal:
        out["date_table"] = {"name": cal_name, "range": cal.get("range") or "",
                             "related": [dict(d) for d in cal.get("related") or []],
                             "not_related": [dict(d) for d in cal.get("not_related") or []]}
    return out


def model_file(data: dict, title: str = "") -> str:
    """The semantic model draft as a draw.io file (`data`: model_data's answer)."""
    tables = list(data.get("tables") or [])
    ids = _table_names(tables)
    nodes = []
    for t in tables:
        role = str(t.get("role") or "other")
        kind = role if role in ("fact", "dimension") else "other"
        ms = list(t.get("measures") or [])
        plain = [str(t["name"]), f"{role} · {_key_line(t)}"]
        plain += [_short(f"{m['name']} = {m['expression']}", 110) for m in ms[:MAX_MEASURES]]
        if len(ms) > MAX_MEASURES:
            plain.append(f"and {len(ms) - MAX_MEASURES} more measures")
        lines = ["<b>" + _esc(plain[0]) + "</b>", "<i>" + _esc(plain[1]) + "</i>"] + [_esc(x) for x in plain[2:]]
        nodes.append({"id": ids[str(t["name"]).lower()], "plain": plain, "lines_html": lines,
                      "style": _box_style(kind, dashed=not t.get("key"))})
    cal = data.get("date_table")
    notes = [str(n) for n in data.get("notes") or []]
    if cal:
        cid = cell_id("table", cal["name"])
        if cid in set(ids.values()):
            cid = cell_id("datetable", cal["name"])
        ids["\x00date"] = cid
        plain = [str(cal["name"]), "date table · key: Date"] + ([_short(str(cal["range"]), 110)] if cal.get("range") else [])
        nodes.append({"id": cid, "plain": plain, "style": _box_style("date"),
                      "lines_html": ["<b>" + _esc(plain[0]) + "</b>", "<i>" + _esc(plain[1]) + "</i>"] + [_esc(x) for x in plain[2:]]})
    many_one = "startArrow=ERmany;startFill=0;endArrow=ERone;endFill=0;"
    styles = {"active": EDGE + many_one + "strokeColor=#444444;",
              "inactive": EDGE + many_one + f"dashed=1;strokeColor={GREY};fontColor={GREY};",
              "not_expressible": EDGE + many_one + f"dashed=1;dashPattern=1 4;strokeColor={RED};fontColor={RED};"}
    edges, seen = [], set()
    counts = {"active": 0, "inactive": 0, "not_expressible": 0}

    def add(source: str, cols: list[str], target_id: str, target_words: str, state: str, rule: str, why: str, short: str) -> None:
        eid = cell_id("rel", source, "+".join(cols), target_words.split(".")[0])
        if eid in seen or source.lower() not in ids:
            return
        seen.add(eid)
        counts[state] += 1
        label = "+".join(cols) + " · * : 1" + (f" · {rule}" if rule else "")
        if state == "inactive":
            label += " · inactive"
        elif state == "not_expressible":
            label += f" · not in the model: {short}"
        words = f"{source}.{'+'.join(cols)} -> {target_words}"
        edges.append({"id": eid, "source": ids[source.lower()], "target": target_id, "label": label, "style": styles[state],
                      "tooltip": words + (f" ({rule})" if rule else "") + (f": {why}" if why else "")})
        if state == "inactive":
            notes.append(f"Inactive: {words}: {why}. Use USERELATIONSHIP in DAX, or pick another active one.")
        elif state == "not_expressible":
            notes.append(f"Not in the model: {words}: {why}.")

    for r in data.get("relationships") or []:
        if str(r["target"]).lower() in ids:
            add(str(r["source"]), [str(c) for c in r["source_cols"]], ids[str(r["target"]).lower()],
                f"{r['target']}.{'+'.join(map(str, r.get('target_cols') or []))}", r["state"], str(r.get("rule") or ""),
                str(r.get("why") or "").rstrip("."), str(r.get("short") or ""))
    if cal:
        for d in cal.get("related") or []:
            add(str(d["fact"]), [str(d["column"])], ids["\x00date"], f"{cal['name']}.Date", "active" if d.get("active") else "inactive",
                "", str(d.get("why") or ""), "")
        for d in cal.get("not_related") or []:
            notes.append(f"Not related to {cal['name']}: {d['fact']}.{d['column']} ({d.get('why') or 'not a date column'}).")
    if len(notes) > MAX_NOTES:                                      # a hover on an arrow has its own reason
        notes = notes[:MAX_NOTES] + [f"And {len(notes) - MAX_NOTES} more: hover over an arrow to read its reason."]
    n_measures = sum(len(t.get("measures") or []) for t in tables)
    head = [title or "Krusgraph: the semantic model draft",
            f"{len(tables)} tables" + (f" and the date table {cal['name']}" if cal else "")
            + f"; relationships: {counts['active']} active, {counts['inactive']} inactive, {counts['not_expressible']} not in the model; "
            f"{n_measures} measures"]
    legend = ["How to read it", "Orange: fact tables, with their measures. Blue: dimension tables. Green: the date table. Grey: other tables. "
              "A dashed box has no key.",
              "A line is a relationship from the many side (crow's foot) to the one side: solid is active, dashed grey is inactive, "
              "dotted red is one the plan found that a tabular model cannot express as the tables stand."]
    return _draw(_File("semantic_model", "Semantic model"), nodes, edges, None, head, (["Notes"] + notes) if notes else [], legend)


# --------------------------------------------------------------------------------------------- the data flow ----

FLOW_COLUMNS = {"bronze": 0, "silver": 1, "gold": 2, "built": 3}


def flow_file(flow: dict, title: str = "") -> str:
    """The data flow as a draw.io file (`flow`: data_flow.flow()'s answer: columns, nodes, edges, notes, said). Each of
    the flow's columns has its heading as a box at the top; an arrow the flow draws from a column as a whole (the items
    that read the source tables) starts at that heading. An item built on another item stands one column further right.
    A node that is not part of the build is dashed, as in the editor."""
    heads = {c["id"]: c["title"] for c in flow.get("columns") or [] if c.get("id") in FLOW_COLUMNS}
    used = {n.get("column") for n in flow.get("nodes") or []} | {"bronze"}
    nodes, columns, known = [], {}, {}
    for cid, at in FLOW_COLUMNS.items():
        if cid in heads and (cid in used or cid == "built" and any(n.get("column") == "pipeline" for n in flow.get("nodes") or [])):
            hid = cell_id("flow", cid)
            known[cid] = hid
            columns[hid] = at
            nodes.append({"id": hid, "plain": [heads[cid]], "lines_html": ["<b>" + _esc(heads[cid]) + "</b>"], "pin": "top",
                          "style": BOX + "fillColor=none;strokeColor=none;fontSize=13;"})
    for n in flow.get("nodes") or []:
        column = n.get("column")
        at = FLOW_COLUMNS.get(n.get("under") if column == "pipeline" else column)
        if at is None:
            continue
        nid = cell_id("flow", n["id"])
        known[n["id"]] = nid
        columns[nid] = at
        plain = [str(n.get("label") or n["id"])] + ([str(n["kind_label"])] if n.get("kind_label") else []) \
            + [_short(str(x), 120) for x in n.get("lines") or [] if x]
        lines = ["<b>" + _esc(plain[0]) + "</b>"] + [_esc(x) for x in plain[1:]]
        kind = "pipeline" if column == "pipeline" else column
        nodes.append({"id": nid, "plain": plain, "lines_html": lines, "style": _box_style(kind, dashed=not n.get("built", True)),
                      **({"pin": "bottom"} if column == "pipeline" else {})})
    edges, seen = [], []
    for e in flow.get("edges") or []:
        if e.get("from") not in known or e.get("to") not in known:
            continue
        eid = cell_id("flowedge", e["from"], e["to"], e.get("via") or "", e.get("label") or "")
        n = sum(1 for x in seen if x == eid)                         # the same arrow twice (two joins on the same columns): both drawn
        seen.append(eid)
        eid += f"-{n + 1}" if n else ""
        label = str(e.get("label") or "") + (f" · {e['rule']}" if e.get("rule") else "")
        style = EDGE + "endArrow=block;endFill=1;strokeColor=#444444;" + ("" if e.get("built", True) else f"dashed=1;strokeColor={GREY};")
        edges.append({"id": eid, "source": known[e["from"]], "target": known[e["to"]], "label": _short(label, 60), "style": style})
    head = [title or "Krusgraph: the data flow"] + ([str(flow["said"]).replace(" Click a box to see its code.", "")] if flow.get("said") else [])
    notes = [str(n) for n in flow.get("notes") or []]
    legend = ["How to read it", "Left to right: the source tables (bronze), the silver tables, the gold views, then what is built on the "
              "source and what is built on that. A dashed box is not part of this build. Purple: the pipeline's steps."]
    return _draw(_File("data_flow", "Data flow"), nodes, edges, columns, head, (["Notes"] + notes) if notes else [], legend)


# --------------------------------------------------------------------------------------- the answer, checked ----

def answer(diagram: str, name: str, content: str, limit: int | None = None) -> dict:
    """What a tool answers for a draw.io export: the file's name, type and text, and what it holds. When the text as JSON
    is over `limit` characters it is left out and the answer says how to get a part."""
    import json
    found = problems(content)
    boxes, links = counts(content)
    out = {"format": "drawio", "diagram": diagram, "filename": filename(name, diagram), "mime_type": MIME,
           "boxes": boxes, "arrows": links, "changes": "nothing: read-only, nothing written to Fabric", "how": HOW}
    if found:                                                       # never expected; said rather than hidden
        out["problems"] = found[:10]
    size = len(json.dumps(content))
    if limit is not None and size > limit:
        out["too_large"] = (f"The file is {size} characters as JSON text, over this answer's limit of {limit}. Pass "
                            "tables=[...] (names or globs) to get a part of the schema as its own file.")
        return out
    out["content"] = content
    return out


WHICH = {"map": "map", "model": "semantic_model", "semantic_model": "semantic_model", "flow": "data_flow", "data_flow": "data_flow"}
BUILT_ON_SOURCE = (("semantic_model", "Semantic model", "{item}_model"), ("graphql", "API for GraphQL", "{item}_api"),
                   ("ontology", "Ontology", "{item}_ontology"), ("data_agent", "Data agent", "{item}_agent"))


def source_flow(plan, info: dict) -> dict:
    """data_flow.flow() for a source as the creating tools would build it with their default names: the silver notebook,
    the gold views, the items that read the source (semantic model, API for GraphQL, ontology, data agent), a report
    on the model and an app on the API. Drafts only: nothing is read beyond the plan and nothing is created."""
    from . import data_flow
    item, schema = info.get("item_name") or "source", info.get("schema") or plan.schema.schema or "dbo"
    chosen = {"silver_notebook": f"silver_{schema}", "gold_views": f"gold_{schema}", "semantic_model": f"{item}_model"}
    reads = f"reads the source tables in {schema} (bronze) directly"
    items = [{"output": o, "label": label, "name": name.format(item=item), "reads": reads} for o, label, name in BUILT_ON_SOURCE]
    items.append({"output": "report", "label": "Report", "name": f"{item}_report", "on_model": "item:semantic_model",
                  "reads": f"on {item}_model"})
    flow = data_flow.flow(plan, info, chosen, items=items)
    flow["nodes"].append({"id": "item:app", "column": "built", "label": "App", "kind_label": "an app on the API (app_starter)",
                          "lines": [f"on {item}_api"], "pills": [], "built": True, "code": None})
    flow["edges"].append({"from": "item:graphql", "to": "item:app", "label": "on the API", "built": True})
    return flow


def export(which: str, plan, info: dict | None, name: str, tables: set[str] | None = None, limit: int | None = None) -> dict:
    """One diagram of a plan as a tool's answer (answer()). `which`: map, model or flow. `info`: the source as
    server._source_inputs describes it (the model and the flow need it). `tables` keeps those tables only."""
    from . import compact, semantic_model
    diagram = WHICH.get(str(which or "").strip().lower())
    if not diagram:
        from .infer import PlanInputError
        raise PlanInputError('drawio: "map", "model" or "flow"')
    schema = plan.schema.schema or ""
    data = map_data(plan, tables)
    if diagram == "map":
        text = map_file(data, f"{name}: the map")
    elif diagram == "semantic_model":
        model = f"{(info or {}).get('item_name') or 'semantic'}_model"
        draft = semantic_model.draft(plan, info or {}, model, sorted(tables, key=str.lower) if tables is not None else None)
        text = model_file(model_data(data, draft, model), f"{name}: the semantic model draft {model}")
    else:
        text = flow_file(source_flow(compact.sub_plan(plan, tables), {**(info or {}), "schema": (info or {}).get("schema") or schema}),
                         f"{name}: the data flow, as the creating tools would build it")
    return answer(diagram, name, text, limit)


def _cells(text: str):
    root = ET.fromstring(text)
    model = root.find("./diagram/mxGraphModel")
    cells = []
    for el in (model.find("root") if model is not None else []):
        cell = el if el.tag == "mxCell" else el.find("mxCell")
        if cell is not None:
            cells.append((el.get("id"), el.get("value") if el.tag == "mxCell" else el.get("label"), cell))
    return root, model, cells


def counts(text: str) -> tuple[int, int]:
    """(boxes, arrows) of a file: the vertices that are not plain text, and the edges."""
    _, _, cells = _cells(text)
    return (sum(1 for _, _, c in cells if c.get("vertex") == "1" and not (c.get("style") or "").startswith("text;")),
            sum(1 for _, _, c in cells if c.get("edge") == "1"))


def _style(cell) -> dict:
    return dict(p.split("=", 1) for p in (cell.get("style") or "").split(";") if "=" in p)


def _crosses(p, q, box, inset: float = 1.0) -> bool:
    """Whether the segment p-q passes through the inside of the box (Liang-Barsky on the box drawn `inset` smaller)."""
    x0, y0, x1, y1 = box[0] + inset, box[1] + inset, box[0] + box[2] - inset, box[1] + box[3] - inset
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for d, lo, hi, s in ((dx, x0, x1, p[0]), (dy, y0, y1, p[1])):
        if d == 0:
            if s <= lo or s >= hi:
                return False
            continue
        a, b = (lo - s) / d, (hi - s) / d
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
        if t0 >= t1:
            return False
    return True


def problems(text: str) -> list[str]:
    """What is wrong with a file, as sentences; an empty list when it is a well-formed mxfile whose ids are unique, whose
    edges join cells that exist, whose boxes do not overlap and whose edges pass through no box."""
    try:
        root, model, cells = _cells(text)
    except ET.ParseError as e:
        return [f"not XML: {e}"]
    out = []
    if root.tag != "mxfile" or model is None or model.find("root") is None:
        return ["not an mxfile: <mxfile><diagram><mxGraphModel><root> expected"]
    ids = [i for i, _, _ in cells]
    if ids[:2] != ["0", "1"] or cells[1][2].get("parent") != "0":
        out.append("the first two cells are not the root (id 0) and the layer (id 1, parent 0)")
    for i in sorted({i for i in ids if ids.count(i) > 1 or not i}):
        out.append(f"the id {i!r} is used more than once or is empty")
    boxes = {}
    for i, _, c in cells[2:]:
        if c.get("parent") != "1":
            out.append(f"{i}: its parent is not the layer")
        g = c.find("mxGeometry")
        if g is None or g.get("as") != "geometry":
            out.append(f"{i}: no geometry")
        elif c.get("vertex") == "1":
            try:
                boxes[i] = tuple(float(g.get(k)) for k in ("x", "y", "width", "height"))
            except (TypeError, ValueError):
                out.append(f"{i}: a box without x, y, width and height")
    names = sorted(boxes)
    by_x = sorted(names, key=lambda i: boxes[i][0])
    for k, a in enumerate(by_x):
        ax, ay, aw, ah = boxes[a]
        for b in by_x[k + 1:]:
            bx, by, bw, bh = boxes[b]
            if bx >= ax + aw:
                break
            if ay < by + bh and by < ay + ah:
                out.append(f"the boxes {a} and {b} overlap")
    for i, _, c in cells[2:]:
        if c.get("edge") != "1":
            continue
        s, t = c.get("source"), c.get("target")
        if s not in boxes or t not in boxes:
            out.append(f"{i}: joins a cell that is not a box in the file")
            continue
        st = _style(c)
        try:
            ends = [(boxes[n][0] + float(st[a + "X"]) * boxes[n][2], boxes[n][1] + float(st[a + "Y"]) * boxes[n][3])
                    for n, a in ((s, "exit"), (t, "entry"))]
        except (KeyError, ValueError):
            out.append(f"{i}: no exit or entry point")
            continue
        pts = [(float(p.get("x")), float(p.get("y"))) for p in c.findall("./mxGeometry/Array/mxPoint")]
        path = [ends[0]] + pts + [ends[1]]
        lo_x, hi_x = min(p[0] for p in path), max(p[0] for p in path)
        for name in names:
            b = boxes[name]
            if b[0] > hi_x or b[0] + b[2] < lo_x:
                continue
            if any(_crosses(p, q, b) for p, q in zip(path, path[1:])):
                out.append(f"the edge {i} passes through the box {name}")
    return out
