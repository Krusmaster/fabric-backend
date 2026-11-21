"""DOCV1: the hand-drawn sketch on the docs page "Where Krusgraph is heading" (Gustav, 21 November 2026).

The sketch is a static inline SVG checked into `static/heading-sketch.svg`. This module draws it once: slightly
wobbly double strokes and hachure fills, in the manner of a whiteboard sketch, from a fixed seed so the file is the same
every time. Nothing is drawn at request time and nothing loads from elsewhere; colours are the site's CSS variables
(classes `hs-*` in site.css), so the sketch follows light and dark mode, and the text is the site's own font.

    python -m fabric_backend.heading_sketch      # writes static/heading-sketch.svg again

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


def svg() -> str:
    """The checked-in sketch (never drawn at request time)."""
    return SVG_PATH.read_text(encoding="utf-8")


def figure(inner: str) -> str:
    """The docs figure: the sketch in its own box, which scrolls sideways on a narrow screen while the page does not,
    and the same content in words under it (the Markdown between the figure markers, also what /docs.md shows)."""
    return (f'<figure class="hs-figure">\n<div class="hs-scroll" tabindex="0" role="group" aria-label="{html.escape(TITLE)}">\n'
            f'{svg().replace(f' xmlns="{XMLNS}"', "")}</div>\n<figcaption class="hs-cap"><details><summary>The sketch in words</summary>\n{inner}\n'
            f'</details></figcaption>\n</figure>')


if __name__ == "__main__":
    SVG_PATH.write_text(build_svg(), encoding="utf-8")
    print(f"wrote {SVG_PATH}")
