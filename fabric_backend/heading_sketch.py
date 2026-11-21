"""DOCV1: the hand-drawn sketch on the docs page "Where Krusgraph is heading" (Gustav, 21 November 2026).

The sketch is a static inline SVG checked into `static/heading-sketch.svg`. This module draws it once: slightly
wobbly double strokes and hachure fills, in the manner of a whiteboard sketch, from a fixed seed so the file is the same
every time. Nothing is drawn at request time and nothing loads from elsewhere; colours are the site's CSS variables
(classes `hs-*` in site.css), so the sketch follows light and dark mode, and the text is the site's own font.

    python -m fabric_backend.heading_sketch      # writes static/heading-sketch*.svg again

DOCV2 adds two more sketches drawn by the same pen: what Krusgraph builds in your Fabric (heading-sketch-fabric.svg)
and how it keeps itself up to date (heading-sketch-loop.svg).

`tests/test_docv1_heading_page.py` checks that the file equals what this module draws.
"""
from __future__ import annotations

import html
import math
import random
from pathlib import Path

SVG_PATH = Path(__file__).parent / "static" / "heading-sketch.svg"     # static/* is package data, so the image has it
W, H = 1040, 960
XMLNS = "http://www.w3.org/2000/svg"        # in the file (so /static/heading-sketch.svg opens on its own); not inline
TITLE = "Sketch: where Krusgraph is heading"
DESC = ("A hand-drawn sketch. A dashed boundary marks your Fabric tenant, where your data stays. You sign in with Entra. "
        "The Krusgraph app has three panes. Your estate: bronze done, silver done with keys 6 of 6, gold missing, model "
        "missing, catalog missing, comparing desired with actual. The mascots suggest: “You have no gold for orders.” "
        "with the buttons Build gold + model, Add a key check and Show why; one tap is a dry run. An arrow leads to the "
        "Plan: 4 gold views, a model on gold, 12 tests, the rest defaults, and an Approve button, which leads to a pull "
        "request in Fabric Git. One sign-in and one approval; everything else is a default. Behind the scenes: Find, Ask, "
        "Build, Approve, Run, Use, Improve. Find, Build and Improve are rules; Ask, Run and Use are where a model proposes; "
        "Approve is you. Data rows are read only inside Fabric.")


class _Pen:
    def __init__(self, seed: int = 21112026):
        self.r = random.Random(seed)

    def j(self, a: float = 1.6) -> float:
        return self.r.uniform(-a, a)

    def _seg(self, x1, y1, x2, y2, wob: float) -> str:
        """One stroke from (x1, y1) to (x2, y2) that bows a little, like a line drawn by hand."""
        n = math.hypot(x2 - x1, y2 - y1) or 1
        bow = min(wob, n / 60) * self.r.choice((-1, 1)) * self.r.uniform(0.4, 1)
        nx, ny = -(y2 - y1) / n, (x2 - x1) / n
        mx = (x1 + x2) / 2 + nx * bow + self.j(0.8)
        my = (y1 + y2) / 2 + ny * bow + self.j(0.8)
        return (f"M{x1 + self.j():.1f} {y1 + self.j():.1f}Q{mx:.1f} {my:.1f} "
                f"{x2 + self.j():.1f} {y2 + self.j():.1f}")

    def line(self, x1, y1, x2, y2, cls="hs-ink", twice=True, wob=3.0, extra="") -> str:
        d = self._seg(x1, y1, x2, y2, wob) + (self._seg(x1, y1, x2, y2, wob) if twice else "")
        return f'<path class="{cls}" d="{d}"{extra}/>'

    def rect(self, x, y, w, h, cls="hs-ink", r=10.0, twice=True, extra="") -> str:
        """A rounded box drawn as one path, twice, with each corner a little off."""
        def once():
            k = [(x + r, y), (x + w - r, y), (x + w, y + r), (x + w, y + h - r), (x + w - r, y + h), (x + r, y + h),
                 (x, y + h - r), (x, y + r)]
            c = [(x + w, y), (x + w, y + h), (x, y + h), (x, y)]
            p = [(a + self.j(), b + self.j()) for a, b in k]
            d = f"M{p[0][0]:.1f} {p[0][1]:.1f}"
            for i in range(4):
                a, b = p[2 * i + 1]
                cx, cy = c[i]
                e = p[(2 * i + 2) % 8]
                d += f"L{a:.1f} {b:.1f}Q{cx + self.j(1):.1f} {cy + self.j(1):.1f} {e[0]:.1f} {e[1]:.1f}"
            return d + "Z"
        return f'<path class="{cls}" d="{once()}{once() if twice else ""}"{extra}/>'

    def hachure(self, x, y, w, h, cls, gap=9.0, pad=4.0) -> str:
        """Diagonal hatching inside a box (lines x + y = k, clipped to it), each line a little uneven."""
        x, y, w, h = x + pad, y + pad, w - 2 * pad, h - 2 * pad
        d = ""
        k = x + y + gap / 2
        while k < x + w + y + h:
            xa, xb = max(x, k - (y + h)), min(x + w, k - y)
            if xb - xa > 3:
                d += self._seg(xa, k - xa, xb, k - xb, 1.2)
            k += gap + self.j(1.2)
        return f'<path class="{cls}" d="{d}"/>'

    def arrow(self, x1, y1, x2, y2, cls="hs-ink") -> str:
        a = math.atan2(y2 - y1, x2 - x1)
        head = "".join(self._seg(x2, y2, x2 - 14 * math.cos(a + s), y2 - 14 * math.sin(a + s), 0.5) for s in (0.45, -0.45))
        return f'<path class="{cls}" d="{self._seg(x1, y1, x2, y2, 5)}{self._seg(x1, y1, x2, y2, 5)}{head}"/>'


def _t(x, y, s, cls="hs-t", anchor="start") -> str:
    a = "" if anchor == "start" else f' text-anchor="{anchor}"'
    return f'<text x="{x:.0f}" y="{y:.0f}" class="{cls}"{a}>{html.escape(s, quote=False)}</text>'


def build_svg() -> str:
    p = _Pen()
    out: list[str] = []
    add = out.append

    # the tenant: a dashed boundary, its label, and the sign-in pill
    add(p.rect(20, 20, 1000, 920, "hs-ink hs-dash", r=18, twice=False))
    add(_t(46, 62, "Your Fabric tenant · your data stays here", "hs-t hs-label"))
    add(p.hachure(790, 34, 210, 44, "hs-h-sage"))
    add(p.rect(790, 34, 210, 44, r=22))
    add(_t(895, 63, "Sign in with Entra", "hs-t hs-b", "middle"))

    # the app window
    add(p.rect(50, 100, 940, 430, r=14))
    add(p.line(50, 146, 990, 146))
    for i, cls in enumerate(("hs-dot-coral", "hs-dot-mustard", "hs-dot-sage")):
        add(f'<circle class="{cls}" cx="{74 + 22 * i}" cy="123" r="6"/>')
    add(_t(520, 131, "Krusgraph", "hs-t hs-title", "middle"))

    px, pw, py, ph = (72, 385, 698), 270, 166, 344
    for x in px:
        add(p.rect(x, py, pw, ph, r=10))

    # pane 1: your estate
    x = px[0] + 18
    add(_t(x, 198, "1  Your estate", "hs-t hs-h"))
    rows = [("bronze", "✓", "hs-ok", ""), ("silver", "✓", "hs-ok", "keys 6/6"), ("gold", "–", "hs-miss", "missing"),
            ("model", "–", "hs-miss", "missing"), ("catalog", "–", "hs-miss", "missing")]
    for i, (name, mark, cls, note) in enumerate(rows):
        y = 240 + i * 46
        add(_t(x, y, name))
        add(_t(x + 100, y, mark, f"hs-t hs-b {cls}"))
        if note:
            add(_t(x + 124, y, note, f"hs-t {'hs-miss' if cls == 'hs-miss' else 'hs-muted'}"))
        if i < len(rows) - 1:
            add(p.line(x, y + 16, x + pw - 36, y + 16, "hs-faint", twice=False, wob=2))
    add(_t(x, 492, "desired vs actual", "hs-t hs-note"))

    # pane 2: the mascots suggest
    x = px[1] + 18
    add(_t(x, 198, "2  The mascots suggest", "hs-t hs-h"))
    add(p.hachure(x, 214, pw - 36, 66, "hs-h-sage", gap=12))
    add(p.rect(x, 214, pw - 36, 66, r=16))
    add(p.line(x + 30, 280, x + 18, 298, wob=1))
    add(_t(x + 16, 242, "“You have no gold", "hs-t hs-q"))
    add(_t(x + 16, 266, "for orders.”", "hs-t hs-q"))
    for i, label in enumerate(("Build gold + model", "Add a key check", "Show why")):
        y = 316 + i * 52
        add(p.rect(x, y, pw - 36, 40, r=20))
        add(_t(x + (pw - 36) / 2, y + 26, label, "hs-t hs-b", "middle"))
    add(_t(x, 492, "one tap = a dry run", "hs-t hs-note"))
    add(p.arrow(px[1] + pw + 4, 338, px[2] - 6, 338))

    # pane 3: plan
    x = px[2] + 18
    add(_t(x, 198, "3  Plan", "hs-t hs-h"))
    for i, s in enumerate(("+ 4 gold views", "+ model on gold", "+ 12 tests")):
        add(_t(x, 240 + i * 40, s))
    add(_t(x, 362, "the rest: defaults", "hs-t hs-muted"))
    add(p.hachure(x, 400, pw - 36, 48, "hs-h-mustard", gap=8))
    add(p.rect(x, 400, pw - 36, 48, "hs-ink hs-strong", r=24))
    add(_t(x + (pw - 36) / 2, 431, "Approve", "hs-t hs-b hs-big", "middle"))

    # the pull request, under the window
    bx = px[2] + 18
    add(p.arrow(bx + (pw - 36) / 2, 452, bx + (pw - 36) / 2, 574))
    add(p.rect(bx - 6, 580, pw - 24, 50, r=8))
    add(_t(bx - 6 + (pw - 24) / 2, 612, "PR in Fabric Git", "hs-t hs-b", "middle"))

    add(_t(72, 606, "One sign-in + one approval.", "hs-t hs-big"))
    add(_t(72, 638, "Everything else is a default.", "hs-t hs-big"))
    add(p.line(72, 650, 400, 652, "hs-under", twice=False, wob=3))

    # behind the scenes
    add(p.line(40, 690, 1000, 690, "hs-faint", twice=False, wob=2))
    add(_t(46, 726, "Behind the scenes", "hs-t hs-h"))
    steps = [("Find", "rules"), ("Ask", "model"), ("Build", "rules"), ("Approve", "you"), ("Run", "model"),
             ("Use", "model"), ("Improve", "rules")]
    fill = {"rules": "hs-h-gray", "model": "hs-h-lav", "you": "hs-h-mustard"}
    bw, gap, y0 = 112, 28, 750
    for i, (name, kind) in enumerate(steps):
        x = 46 + i * (bw + gap)
        add(p.hachure(x, y0, bw, 52, fill[kind], gap=8))
        add(p.rect(x, y0, bw, 52, r=10))
        add(_t(x + bw / 2, y0 + 33, name, "hs-t hs-b", "middle"))
        if i < len(steps) - 1:
            add(p.arrow(x + bw + 3, y0 + 26, x + bw + gap - 3, y0 + 26))

    # the legend
    lx = 46
    for kind, label in (("rules", "gray = rules"), ("model", "purple = a model proposes"), ("you", "amber = you approve")):
        add(p.hachure(lx, 836, 30, 22, fill[kind], gap=6, pad=2))
        add(p.rect(lx, 836, 30, 22, r=5, twice=False))
        add(_t(lx + 40, 853, label, "hs-t hs-small"))
        lx += 40 + len(label) * 10.5 + 34
    add(_t(46, 900, "data rows are read only inside Fabric", "hs-t hs-small hs-muted"))

    body = "\n".join(out)
    return (f'<svg class="hs-svg" xmlns="{XMLNS}" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'role="img" aria-labelledby="hs-title hs-desc" focusable="false">\n'
            f'<title id="hs-title">{html.escape(TITLE)}</title>\n<desc id="hs-desc">{html.escape(DESC)}</desc>\n'
            f'{body}\n</svg>\n')


def _wrap(body: str, w: int, h: int, ids: str, title: str, desc: str) -> str:
    return (f'<svg class="hs-svg" xmlns="{XMLNS}" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-labelledby="{ids}-title {ids}-desc" focusable="false">\n'
            f'<title id="{ids}-title">{html.escape(title)}</title>\n<desc id="{ids}-desc">{html.escape(desc)}</desc>\n'
            f'{body}\n</svg>\n')


# DOCV2 (Gustav, 21 November 2026, "Gärna"): two more sketches on the same page, drawn by the same pen.
FABRIC_PATH = SVG_PATH.parent / "heading-sketch-fabric.svg"
FABRIC_W, FABRIC_H = 1040, 1030
FABRIC_TITLE = "Sketch: what Krusgraph builds in your Fabric"
FABRIC_DESC = ("A hand-drawn sketch inside a dashed boundary marked Your Fabric tenant. Sources: SAP, Salesforce, Dynamics "
               "and more sources, brought in by mirroring or shortcuts. Then bronze (a lakehouse, raw), silver (a notebook, "
               "keys checked) and gold (views, a star schema), joined by arrows. Below, a dashed box: data products in the "
               "domain Sales, with the cards Customer, Product and Order, each with a key, an owner and a contract; "
               "interface arrows lead into Product. What people use: a semantic model, an ontology, a data agent, a report "
               "and a GraphQL API. Around it: a pipeline, dbt tests, the catalog, domains, alerts and Fabric Git. Same plan, "
               "same items; every change is a pull request. Colours: coral is raw, amber is refined, purple is a data "
               "product, teal is what people use, gray is run and govern.")
LOOP_PATH = SVG_PATH.parent / "heading-sketch-loop.svg"
LOOP_W, LOOP_H = 1040, 880
LOOP_TITLE = "Sketch: how Krusgraph keeps itself up to date"
LOOP_DESC = ("A hand-drawn sketch. A box, It watches: a new column in a source, a new table, a key that is no longer "
             "unique, data that is not fresh, a broken relationship, unused items, cost running away. Then a loop: Watch, "
             "every night and on change; Compare, desired with actual, which is the plan; Classify, where rules decide the "
             "risk. Two branches: Safe, done on its own (the catalog, tests, a new column), and Risky, a draft pull request "
             "that a mascot explains and you approve. Both lead to Rebuild and test (dbt tests, the rows prove it), then "
             "Learn from the decision (the same choice becomes the default), and an arrow back to Watch, round after "
             "round. Today: watching and dry runs. Next: fixing on its own.")


def _box(p: _Pen, add, x, y, w, h, name, sub=(), fill=None, r=10.0, gap=9.0) -> None:
    """A labelled box: a hachure fill (optional), the outline, the name in bold and up to two small lines under it,
    each with a halo in the card colour so it reads over the hatching."""
    if fill:
        add(p.hachure(x, y, w, h, fill, gap=gap))
    add(p.rect(x, y, w, h, r=r))
    lines = [name, *sub]
    top = y + h / 2 - (len(lines) - 1) * 12 + 7
    add(_t(x + w / 2, top, name, "hs-t hs-b hs-halo", "middle"))
    for i, s in enumerate(sub):
        add(_t(x + w / 2, top + 24 * (i + 1), s, "hs-t hs-small hs-halo", "middle"))


def build_fabric_svg() -> str:
    p = _Pen(21112027)
    out: list[str] = []
    add = out.append
    add(p.rect(20, 20, 1000, 990, "hs-ink hs-dash", r=18, twice=False))
    add(_t(46, 62, "Your Fabric tenant", "hs-t hs-label"))

    # sources
    add(_t(46, 112, "Sources", "hs-t hs-h"))
    for i, name in enumerate(("SAP", "Salesforce", "Dynamics", "More sources …")):
        _box(p, add, 46 + i * 224, 126, 200, 52, name, fill="hs-h-coral", gap=11)
    add(p.arrow(146, 184, 146, 262))
    add(_t(166, 228, "mirroring · shortcuts", "hs-t hs-note"))

    # bronze, silver, gold
    layers = [("Bronze", ("lakehouse · raw",), "hs-h-coral"), ("Silver", ("notebook · keys checked",), "hs-h-mustard"),
              ("Gold", ("views · star schema",), "hs-h-mustard")]
    for i, (name, sub, fill) in enumerate(layers):
        x = 46 + i * 330
        _box(p, add, x, 268, 280, 84, name, sub, fill)
        if i < 2:
            add(p.arrow(x + 284, 310, x + 326, 310))

    # data products
    add(p.arrow(846, 356, 846, 420))
    add(p.rect(46, 426, 940, 200, "hs-ink hs-dash", r=14, twice=False))
    add(_t(70, 462, "Data products · domain: Sales", "hs-t hs-h"))
    cards = ("Customer", "Product", "Order")
    for i, name in enumerate(cards):
        x = 86 + i * 314
        _box(p, add, x, 484, 240, 112, name, ("key · owner · contract",), "hs-h-lav", gap=12)
    add(p.arrow(330, 540, 396, 540))
    add(p.arrow(696, 540, 644, 540))
    add(_t(520, 616, "interfaces lead into Product", "hs-t hs-note", "middle"))

    # what people use
    add(p.arrow(516, 630, 516, 680))
    add(_t(46, 676, "What people use", "hs-t hs-h"))
    for i, name in enumerate(("Semantic model", "Ontology", "Data agent", "Report", "GraphQL API")):
        _box(p, add, 46 + i * 192, 694, 172, 56, name, fill="hs-h-teal", gap=10)

    # around it
    add(_t(46, 800, "Around it", "hs-t hs-h"))
    for i, name in enumerate(("Pipeline", "dbt tests", "Catalog", "Domains", "Alerts", "Fabric Git")):
        _box(p, add, 46 + i * 160, 818, 140, 50, name, fill="hs-h-gray", gap=8)

    add(_t(46, 916, "Same plan, same items · every change is a PR", "hs-t hs-big"))
    add(p.line(46, 928, 520, 930, "hs-under", twice=False, wob=3))

    # the legend
    lx = 46
    for fill, label in (("hs-h-coral", "raw"), ("hs-h-mustard", "refined"), ("hs-h-lav", "data product"),
                        ("hs-h-teal", "what people use"), ("hs-h-gray", "run and govern")):
        add(p.hachure(lx, 960, 30, 22, fill, gap=6, pad=2))
        add(p.rect(lx, 960, 30, 22, r=5, twice=False))
        add(_t(lx + 40, 977, label, "hs-t hs-small"))
        lx += 40 + len(label) * 10.5 + 34
    return _wrap("\n".join(out), FABRIC_W, FABRIC_H, "hs2", FABRIC_TITLE, FABRIC_DESC)


def build_loop_svg() -> str:
    p = _Pen(21112028)
    out: list[str] = []
    add = out.append

    # what it watches
    add(p.rect(46, 30, 948, 190, r=14))
    add(_t(70, 70, "It watches", "hs-t hs-h"))
    watched = ("new column in a source", "new table", "key no longer unique", "data not fresh", "broken relationship",
               "unused items", "cost running away")
    for i, s in enumerate(watched):
        col, row = divmod(i, 4)
        add(_t(84 + col * 470, 110 + row * 30, "· " + s))

    # watch, compare, classify
    add(p.arrow(186, 224, 186, 262))
    steps = [("Watch", ("every night + on change",)), ("Compare", ("desired vs actual = plan",)),
             ("Classify", ("rules decide the risk",))]
    for i, (name, sub) in enumerate(steps):
        x = 46 + i * 334
        _box(p, add, x, 268, 280, 84, name, sub, "hs-h-gray", gap=10)
        if i < 2:
            add(p.arrow(x + 284, 310, x + 330, 310))

    # the two branches
    add(p.arrow(800, 356, 560, 424))
    add(p.arrow(860, 356, 860, 424))
    _box(p, add, 380, 430, 340, 112, "Safe: done on its own", ("catalog · tests", "a new column"), "hs-h-sage", gap=11)
    _box(p, add, 740, 430, 254, 112, "Risky: draft PR", ("a mascot explains", "you approve"), "hs-h-mustard", gap=9)

    # rebuild, learn, and round again
    add(p.arrow(560, 546, 660, 612))
    add(p.arrow(866, 546, 780, 612))
    _box(p, add, 560, 618, 300, 84, "Rebuild + test", ("dbt tests · rows prove",), "hs-h-gray", gap=10)
    add(p.arrow(556, 660, 476, 660))
    _box(p, add, 46, 618, 426, 84, "Learn from the decision", ("the same choice becomes the default",), "hs-h-lav", gap=10)
    add(p.arrow(186, 614, 186, 358))
    add(_t(206, 492, "round after round", "hs-t hs-note"))

    add(_t(46, 776, "Today: watching and dry runs.", "hs-t hs-big"))
    add(_t(46, 812, "Next: fixing on its own.", "hs-t hs-big"))
    add(p.line(46, 826, 330, 828, "hs-under", twice=False, wob=3))
    return _wrap("\n".join(out), LOOP_W, LOOP_H, "hs3", LOOP_TITLE, LOOP_DESC)


# every sketch on the page: its docs figure name, its file, how it is drawn and its accessible name
SKETCHES = {
    "heading-sketch": (SVG_PATH, build_svg, TITLE),
    "heading-sketch-fabric": (FABRIC_PATH, build_fabric_svg, FABRIC_TITLE),
    "heading-sketch-loop": (LOOP_PATH, build_loop_svg, LOOP_TITLE),
}


def svg(name: str = "heading-sketch") -> str:
    """A checked-in sketch (never drawn at request time)."""
    return SKETCHES[name][0].read_text(encoding="utf-8")


def _figure(name: str, inner: str) -> str:
    """The docs figure: the sketch in its own box, which scrolls sideways on a narrow screen while the page does not,
    and the same content in words under it (the Markdown between the figure markers, also what /docs.md shows)."""
    title = SKETCHES[name][2]
    inline = svg(name).replace(f' xmlns="{XMLNS}"', "")
    return (f'<figure class="hs-figure">\n<div class="hs-scroll" tabindex="0" role="group" aria-label="{html.escape(title)}">\n'
            f'{inline}</div>\n<figcaption class="hs-cap"><details><summary>The sketch in words</summary>\n{inner}\n'
            f'</details></figcaption>\n</figure>')


def figure(inner: str) -> str:
    return _figure("heading-sketch", inner)


def figures() -> dict:
    """The docs figures of all three sketches, by the name in DOCS.md's figure markers."""
    return {name: (lambda inner, n=name: _figure(n, inner)) for name in SKETCHES}


if __name__ == "__main__":
    for _path, _build, _title in SKETCHES.values():
        _path.write_text(_build(), encoding="utf-8")
        print(f"wrote {_path}")
