#!/usr/bin/env python3
"""Krusgraph (n175): the workload's own images in Fabric, drawn from Krusgraph's sources instead of the starter kit's
purple samples (microsoft/fabric-extensibility-toolkit dacab1b, MIT; the file names and sizes are the kit's).

    python workload/scripts/build_manifest_images.py           # writes workload/Workload/Manifest/assets/images/*.png
    python workload/scripts/build_manifest_images.py --list    # the images and their sizes, nothing written

Run it from the repository root after the logo, the mascots or the cards' map change. It needs Node's
Playwright and Chromium (as tests/test_browser.py; CHROMIUM=<path> picks the browser) and draws each image as a small HTML page at its exact size:

- the logo mark: fabric_backend/static/favicon.svg (three dots: coral #F2735C top, green #9DB8A0 left, violet
  #A99AD8 right, grey links), as the workload icon (64 px) and favicon (32 px) on the site's cream tile, and as the Krusgraph Model
  item icon on a transparent ground with mid-grey links that read on Fabric's light and dark themes alike. Fabric's
  manifests have one icon per field and no dark variant (manifest-product, manifest-item, frontend-manifests on
  Microsoft Learn, read 9 November 2026), so one image has to work on both;
- the workload page's banner and getting-started picture: the site's colours and fonts (fabric_backend/static/site.css,
  fonts/), the logo and the three mascots (fabric_backend/mcp_apps_mascots.py). No Microsoft logos;
- the editor's loading view: app/assets/krusgraph-icon.png, a copy of the workload icon, in place of the kit's
  Fabric logo;
- n183: the Krusgraph Model item's icons are Fluent-style (`fluent_item`): a rounded container with a soft gradient and a
  slight depth, and Krusgraph's own interior, the three connected nodes, in Krusgraph's own colours (coral, green,
  violet on cream); no Microsoft colour sequence and no Microsoft product shape. Sized by Microsoft's item icon guideline
  (publishing-requirements-item, 1.2 "Item has a clear icon", Learn, ms.date 24 February 2026, read 9 November 2026):
  "Filetype icons are comprised of a container and an interior Fluent system icon", sizes 20/24/32/40/48/64, the
  interior "28px in 48px container" and "14px in 24px container", centred, strokes 1px or 1.5px "if an icon is composed
  of only/mostly strokes"; 1.2.1 asks for a distinct active icon (ModelItem_Icon_Active.png, the warmer container). The
  editor shows the same 48 px file as its logo at the top left (app/assets/krusgraph-item-icon.png). The workload icon
  and favicon stay the brand's logo mark;
- n183: the banner carries no text and no logo, only the site's shapes and the mascots on the right: Fabric's workload
  page writes the workload's name and description over the banner's left side, where our text overlapped it;
- the quick look: the editor's map, drawn by the same code the editor imports (cardMap.generated.ts comes from
  fabric_backend/mcp_apps_pictures.py), on seed.py's synthetic shop with every check passed.

Fabric's package rules (manifest-product): at most 15 asset files, .png/.jpg/.jpeg only, each at most 1.5 MB, each
referenced from Product.json or an item file. tests/test_workload_manifest.py checks all four and the sizes below.
"""
from __future__ import annotations

import html
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMAGES = ROOT / "workload" / "Workload" / "Manifest" / "assets" / "images"
STATIC = ROOT / "fabric_backend" / "static"
EDITOR_ICON = ROOT / "workload" / "Workload" / "app" / "assets" / "krusgraph-icon.png"   # the editor's loading view
EDITOR_LOGO = ROOT / "workload" / "Workload" / "app" / "assets" / "krusgraph-item-icon.png"   # n183: the editor's top-left logo

# file -> (width, height, what it is). Icons: one of the sizes Microsoft's validator approves (16, 20, 24, 32, 40, 48 or 64
# px square; microsoft/fabric-extensibility-toolkit-validator 78e17c3, ImageValidator, as tools/hub_readiness.py reads
# it); the banner 1920x240 (its test 3.1.5); the other two the starter kit's sizes.
SIZES = {
    "Workload_Icon.png": (64, 64, "workload icon: the logo mark on the cream tile"),
    "Workload_Favicon.png": (32, 32, "the workload's favicon: the same mark"),
    "ModelItem_Icon.png": (48, 48, "Krusgraph Model item, Fluent-style: New item card, workspace list, editor tab"),
    "ModelItem_Icon_Small.png": (24, 24, "the New item card's small icon, Fluent-style"),
    "ModelItem_Icon_Active.png": (48, 48, "the item's active icon (its open tab): the Fluent-style icon, warmer container"),
    "Workload_Hub_Banner.png": (1920, 240, "the workload page's banner"),
    "Workload_Hub_GetStarted_1.png": (320, 180, "the getting-started card"),
    "Workload_Hub_SlideMedia_1.png": (985, 552, "the quick look: the editor's map"),
}

CORAL, GREEN, VIOLET = "#F2735C", "#9DB8A0", "#A99AD8"


def mark(size: int, tile: bool, link: str = "#8C8792", width: float = 2.4) -> str:
    """The logo mark (favicon.svg) at `size` px; tile=False leaves the ground transparent."""
    ground = '<rect width="64" height="64" rx="14" fill="#FBF8F5"/>' if tile else ""
    opacity = ' opacity=".5"' if tile else ""
    stroke = "#1B1B1F" if tile else link
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{size}" height="{size}">{ground}'
            f'<path d="M32 16 L16 46 M32 16 L48 46 M16 46 H48" stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linecap="round"{opacity}/>'
            f'<circle cx="32" cy="16" r="8" fill="{CORAL}"/><circle cx="16" cy="46" r="8" fill="{GREEN}"/>'
            f'<circle cx="48" cy="46" r="8" fill="{VIOLET}"/></svg>')


# n183: the Fluent-style item icon, drawn in a 48 x 48 box. The interior (the three connected nodes) fills 28 px of it,
# centred (10..38), as Microsoft's item icon guideline sizes it; at 24 px the same drawing gives the 14 px interior.
NODES = ((24, 14.6, CORAL, "#FFB29A", "#D9604B"), (14.6, 32.4, GREEN, "#CDDFCD", "#84A188"),
         (33.4, 32.4, VIOLET, "#D4CBF0", "#9282C6"))


def fluent_item(size: int, active: bool = False) -> str:
    """The Krusgraph Model item icon: a rounded container with a soft top-to-bottom gradient and a slight depth (a soft
    shadow line under it and a light rim), and the three connected nodes, each a soft sphere, in Krusgraph's colours."""
    top, bottom, rim = (("#FFF4EF", "#F9D9CF", "#E9A894") if active else ("#FFFFFF", "#F3ECE6", "#D8CEC5"))
    nodes = "".join(
        f'<radialGradient id="n{i}" cx="35%" cy="30%" r="75%"><stop offset="0" stop-color="{light}"/>'
        f'<stop offset=".55" stop-color="{base}"/><stop offset="1" stop-color="{dark}"/></radialGradient>'
        for i, (_x, _y, base, light, dark) in enumerate(NODES))
    dots = "".join(f'<circle cx="{x}" cy="{y}" r="5.1" fill="url(#n{i})"/>'
                   f'<ellipse cx="{x - 1.5}" cy="{y - 1.9}" rx="1.7" ry="1.1" fill="#fff" opacity=".55"/>'
                   for i, (x, y, *_rest) in enumerate(NODES))
    (ax, ay, *_a), (bx, by, *_b), (cx, cy, *_c) = NODES
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="{size}" height="{size}"><defs>'
            f'<linearGradient id="ct" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/>'
            f'<stop offset="1" stop-color="{bottom}"/></linearGradient>'
            '<linearGradient id="ln" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8C8792"/>'
            f'<stop offset="1" stop-color="#6E6874"/></linearGradient>{nodes}</defs>'
            f'<rect x="3" y="4.4" width="42" height="42" rx="10" fill="#5B4A3A" opacity=".16"/>'
            f'<rect x="3" y="3" width="42" height="42" rx="10" fill="url(#ct)" stroke="{rim}" stroke-width="1"/>'
            f'<rect x="4" y="4" width="40" height="20" rx="9" fill="#fff" opacity=".35"/>'
            f'<path d="M{ax} {ay} L{bx} {by} M{ax} {ay} L{cx} {cy} M{bx} {by} H{cx}" stroke="url(#ln)" stroke-width="1.5" '
            f'stroke-linecap="round"/>{dots}</svg>')


def _page(body: str, w: int, h: int, css: str = "", transparent: bool = False) -> str:
    fonts = (f'@font-face{{font-family:"Fredoka";src:url("{(STATIC / "fonts" / "fredoka-var.woff2").as_uri()}") format("woff2");font-weight:400 700}}'
             f'@font-face{{font-family:"Nunito";src:url("{(STATIC / "fonts" / "nunito-var.woff2").as_uri()}") format("woff2");font-weight:400 800}}')
    bg = "transparent" if transparent else "#FBF8F5"
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>{fonts}'
            f'html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{bg};color:#1B1B1F;'
            f'font-family:"Nunito",sans-serif}}*{{box-sizing:border-box}}{css}</style></head><body>{body}</body></html>')


def _mascots(height: int, poses=("rest", "rest", "rest")) -> str:
    sys.path.insert(0, str(ROOT))
    from fabric_backend import mcp_apps_mascots as M
    figs = "".join(f'<span class="fig" style="height:{height}px;width:{height}px">{M.svg(k, p)}</span>'
                   for k, p in zip(("onto", "thinker", "builder"), poses))
    return f'<style>{M.CSS} .fig{{display:inline-block}} .fig svg{{width:100%;height:100%}}</style>{figs}'


def banner() -> str:
    css = ("""
      .wrap{display:flex;align-items:center;height:240px;padding:0 96px;gap:40px;position:relative}
      .arc{position:absolute;right:-60px;top:-140px;width:520px;height:520px;border-radius:50%;background:#FCE3DC}
      .arc2{position:absolute;right:420px;bottom:-200px;width:300px;height:300px;border-radius:50%;background:#E6EFE7}
      .word{font-family:"Fredoka";font-weight:600;font-size:76px;letter-spacing:-.01em;line-height:1}
      .say{font-size:28px;color:#5B5660;margin-top:14px;max-width:980px}
      .mascots{position:absolute;right:120px;bottom:6px;display:flex;align-items:flex-end;gap:6px}
    """)
    # n183: no text and no logo: Fabric's workload page writes the name and description over the left side
    body = (f'<div class="arc"></div><div class="arc2"></div>'
            f'<div class="mascots">{_mascots(168, ("rest", "rest", "rest"))}</div>')
    return _page(body, 1920, 240, css)


def getting_started() -> str:
    css = ("""
      .g{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:14px 12px 0}
      .s{background:#fff;border:1.5px solid #E9E1DA;border-radius:12px;height:118px;padding:8px 6px;text-align:center}
      .n{font-family:"Fredoka";font-weight:600;font-size:13px;width:22px;height:22px;border-radius:11px;color:#fff;
         display:inline-flex;align-items:center;justify-content:center}
      .t{font-weight:800;font-size:12.5px;margin-top:6px;line-height:1.2}
      .fig{display:block;margin:2px auto 0}
      .foot{font-family:"Fredoka";font-weight:600;font-size:15px;text-align:center;margin-top:9px;color:#5B5660}
    """)
    sys.path.insert(0, str(ROOT))
    from fabric_backend import mcp_apps_mascots as M
    steps = [("1", "#9DB8A0", "Choose a lakehouse", "onto"), ("2", "#A99AD8", "Review and check", "thinker"),
             ("3", "#F2735C", "Dry run, then Create", "builder")]
    cells = "".join(f'<div class="s"><span class="n" style="background:{c}">{n}</span><div class="t">{html.escape(t)}</div>'
                    f'<span class="fig" style="width:52px;height:52px">{M.svg(k, "rest")}</span></div>'
                    for n, c, t, k in steps)
    return _page(f'<style>{M.CSS} .fig svg{{width:100%;height:100%}}</style><div class="g">{cells}</div>'
                 f'<div class="foot">New item → Krusgraph Model</div>', 320, 180, css)


def _shop_map() -> dict:
    """seed.py's synthetic shop, planned with R5 and checked against its own rows (fabric_backend/demo.py's database)."""
    sys.path.insert(0, str(ROOT))
    from fabric_backend import demo, evidence, infer, mcp_apps_pictures as P, seed
    execute = demo._demo_db()
    p = infer.plan(seed.schema("shop"), execute=execute)
    return P.map_from_plan(p, evidence.validate(p, execute))


def quick_look_page() -> str:
    sys.path.insert(0, str(ROOT))
    from fabric_backend import mcp_apps_pictures as P
    helpers = (ROOT / "workload" / "scripts" / "build_card_map.py").read_text(encoding="utf-8")
    start = helpers.index('HELPERS = r"""') + len('HELPERS = r"""')
    js = helpers[start:helpers.index('"""', start)] + P.picture_js() + P.DRAW_JS
    css = ("""
      .top{height:46px;display:flex;align-items:center;gap:10px;padding:0 18px;border-bottom:1px solid #E9E1DA;background:#fff}
      .top b{font-family:"Fredoka";font-weight:600;font-size:18px}
      .rib{display:flex;gap:8px;margin-left:auto}
      .rib span{font-size:13px;font-weight:700;border:1.5px solid #D8CEC5;border-radius:8px;padding:4px 10px;background:#FFF9F4}
      .rib span.go{background:#F2735C;border-color:#E2604A;color:#fff}
      .body{display:flex;height:506px}
      .side{width:260px;padding:16px;border-right:1px solid #E9E1DA;background:#FFF9F4;font-size:14px}
      .side h3{font-family:"Fredoka";font-weight:600;font-size:17px;margin:0 0 8px}
      .side .row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed #E9E1DA}
      .side .ok{color:#2F6B3A;font-weight:800}
      .main{flex:1;padding:8px 12px;overflow:hidden;background:#fff}
      #map{transform-origin:0 0}
      /* the editor's ModelItem.scss maps these to Fluent's light-theme tokens; their values in Fabric's light theme */
      .main{--kg-font:"Segoe UI","Nunito",sans-serif;--kg-bg:#ffffff;--kg-card:#fafafa;--kg-ink:#242424;--kg-muted:#616161;
            --kg-line:#d1d1d1;--kg-ok:#0e700e;--kg-bad:#b10e1c;--kg-warn:#8a6100;--kg-radius:4px;--kg-pic-edge:#424242;
            --kg-pic-accent:#5B4BA8;--kg-pic-grp-a:#fdf6f6;--kg-pic-grp-b:#f1faf1}
    """)
    m = _shop_map()
    data = json.dumps(m)
    keyed = [t for t in m["tables"] if t.get("key")]
    passed = sum(1 for r in m["relationships"] if r.get("state") == "passed")
    keyless = len(m["tables"]) - len(keyed)
    body = (f'<div class="top">{mark(26, True)}<b>Krusgraph Model</b><span style="color:#5B5660;font-size:14px">· shop · Review</span>'
            f'<div class="rib"><span>Check against the rows</span><span>Accept all</span><span class="go">Next</span></div></div>'
            f'<div class="body"><div class="side"><h3>Review</h3>'
            f'<div class="row"><span>Tables</span><span>{len(m["tables"])}</span></div>'
            f'<div class="row"><span>Keys</span><span class="ok">{len(keyed)} found</span></div>'
            f'<div class="row"><span>Relationships</span><span class="ok">{passed} of {len(m["relationships"])} passed</span></div>'
            f'<div class="row"><span>Tables without a key</span><span>{keyless}</span></div>'
            f'<p style="color:#5B5660;font-size:13px;margin-top:14px">Every key and link shows the rule that found it. '
            f'Accept or reject each one; nothing is created before the dry run.</p>{_mascots(64)}</div>'
            f'<div class="main"><div id="map" class="kg-map"></div></div></div>'
            f'<style>{P.CSS}</style><script>{js}\nvar box=document.getElementById("map");drawMap(box,{data});'
            f'var r=box.getBoundingClientRect(),k=Math.min(700/r.width,490/r.height,1.4);box.style.transform="scale("+k+")";'
            f'document.title="ready";</script>')
    return _page(body, 985, 552, css)


def pages() -> dict[str, tuple[str, bool]]:
    tile = lambda n: _page(mark(n, True), n, n, "svg{display:block}", transparent=True)   # noqa: E731
    item = lambda n, active=False: _page(fluent_item(n, active), n, n, "svg{display:block}", transparent=True)   # noqa: E731
    return {"Workload_Icon.png": (tile(64), True), "Workload_Favicon.png": (tile(32), True), "ModelItem_Icon.png": (item(48), True),
            "ModelItem_Icon_Small.png": (item(24), True), "ModelItem_Icon_Active.png": (item(48, True), True),
            "Workload_Hub_Banner.png": (banner(), False),
            "Workload_Hub_GetStarted_1.png": (getting_started(), False),
            "Workload_Hub_SlideMedia_1.png": (quick_look_page(), False)}


RENDER_JS = r"""
const { chromium } = require("playwright");
(async () => {
  const jobs = JSON.parse(process.argv[2]);
  const opts = process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {};
  const browser = await chromium.launch(opts);
  for (const j of jobs) {
    const page = await browser.newPage({ viewport: { width: j.w, height: j.h }, deviceScaleFactor: 1 });
    await page.goto(j.url);
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(150);
    await page.screenshot({ path: j.out, omitBackground: j.transparent, clip: { x: 0, y: 0, width: j.w, height: j.h } });
    await page.close();
  }
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


def main(argv: list[str]) -> int:
    if "--list" in argv:
        for f, (w, h, what) in SIZES.items():
            print(f"{f:34} {w}x{h}  {what}")
        return 0
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        for name, (doc, transparent) in pages().items():
            w, h, _ = SIZES[name]
            path = Path(tmp) / (name + ".html")
            path.write_text(doc, encoding="utf-8")
            jobs.append({"url": path.as_uri(), "out": str(IMAGES / name), "w": w, "h": h, "transparent": transparent})
        script = Path(tmp) / "render.js"
        script.write_text(RENDER_JS, encoding="utf-8")
        subprocess.run(["node", str(script), json.dumps(jobs)], check=True)
    for j in jobs:
        print(f"wrote {Path(j['out']).name} ({j['w']}x{j['h']})")
    EDITOR_ICON.write_bytes((IMAGES / "Workload_Icon.png").read_bytes())
    print(f"wrote {EDITOR_ICON.relative_to(ROOT)} (a copy of Workload_Icon.png)")
    EDITOR_LOGO.write_bytes((IMAGES / "ModelItem_Icon.png").read_bytes())
    print(f"wrote {EDITOR_LOGO.relative_to(ROOT)} (a copy of ModelItem_Icon.png)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
