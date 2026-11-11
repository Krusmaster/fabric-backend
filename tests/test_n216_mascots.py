"""Round n216: one look for the mascots, the glossy 3D figures of the overview film, on the product cards, the Fabric
workload's page and the Krusgraph Model editor; and the Claude card says exactly which MCP clients sign in today."""
from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest

from starlette.testclient import TestClient

from fabric_backend import offering, server

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "fabric_backend" / "static"
WORKLOAD = ROOT / "workload" / "Workload"
IMAGES = WORKLOAD / "Manifest" / "assets" / "images"
KINDS = ("onto", "thinker", "builder")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


def _png(path: Path) -> tuple[int, int, int]:
    b = path.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n", path
    w, h = struct.unpack(">II", b[16:24])
    return w, h, b[25]                    # colour type: 6 is RGBA


# ------------------------------------------------------------------ the renders -------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_each_figure_is_a_transparent_112_px_render_on_the_site_and_in_the_workload(kind):
    for path in (STATIC / "mascots" / f"{kind}.png", WORKLOAD / "app" / "assets" / "mascots" / f"{kind}.png"):
        assert _png(path) == (112, 112, 6), path
        assert path.stat().st_size < 20_000, path
    webp = (STATIC / "mascots" / f"{kind}.webp").read_bytes()
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP" and len(webp) < 12_000
    # the workload's copy is the site's file, byte for byte
    assert (STATIC / "mascots" / f"{kind}.png").read_bytes() == (WORKLOAD / "app" / "assets" / "mascots" / f"{kind}.png").read_bytes()


def test_the_renders_are_cut_from_the_film_by_the_tool_and_the_art_still_needed_is_listed():
    tool = (ROOT / "tools" / "mascot_renders.py").read_text(encoding="utf-8")
    assert "krusgraph-overview-web.mp4" in tool and 'AT = "43"' in tool and "CANVAS = 112" in tool
    need = (ROOT / "docs" / "MASCOT-ART-NEEDED.md").read_text(encoding="utf-8")
    for f in ("onto-table.png", "thinker-bubble.png", "builder-screen.png", "onto-code.png"):
        assert f"`{f}`" in need, f
    assert "512 x 512 px" in need and "transparent background" in need
    assert "1.5 MB" in need and "manifest-product" in need


def test_the_site_serves_the_renders(client):
    for kind in KINDS:
        r = client.get(offering.render_src(kind))
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/webp"), kind


# ------------------------------------------------------------------ the editor --------------------------------------

def test_the_editor_draws_the_3d_figures_not_the_flat_svg():
    app = WORKLOAD / "app" / "items" / "ModelItem"
    fig = (app / "mascotFigure.tsx").read_text(encoding="utf-8")
    for kind in KINDS:
        assert f'{kind}: "/assets/mascots/{kind}.png"' in fig
    assert 'alt=""' in fig and 'aria-hidden="true"' in fig and "data-pose" in fig
    for name in ("ModelItemViews.tsx", "FlowView.tsx"):
        src = (app / name).read_text(encoding="utf-8")
        assert "MASCOT_SVG" not in src and "<MascotFigure " in src, name
    scss = (app / "ModelItem.scss").read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in scss and "krusgraph-hop" in scss
    # the on/off switch is the same as before
    assert 'label={props.on ? "Mascots: on" : "Mascots: off"}' in (app / "ModelItemViews.tsx").read_text(encoding="utf-8")


# ------------------------------------------------------------------ the workload's page -----------------------------

def test_the_workload_page_images_use_the_3d_figures_within_fabrics_limits():
    script = (ROOT / "workload" / "scripts" / "build_manifest_images.py").read_text(encoding="utf-8")
    assert "M.svg(" not in script and 'RENDERS = STATIC / "mascots"' in script and "_mascots(112)" in script
    # Learn, Product Manifest (manifest-product, ms.date 15 December 2025): at most 15 files, .png/.jpg/.jpeg, 1.5 MB each
    files = [p for p in (WORKLOAD / "Manifest" / "assets" / "images").iterdir() if p.is_file()]
    assert len(files) <= 15 and all(p.suffix in (".png", ".jpg", ".jpeg") for p in files)
    assert all(p.stat().st_size <= 1.5 * 1024 * 1024 for p in files)
    sizes = {p.name: _png(p)[:2] for p in files}
    assert sizes["Workload_Hub_Banner.png"] == (1920, 240) and sizes["Workload_Hub_GetStarted_1.png"] == (320, 180)
    assert sizes["Workload_Hub_SlideMedia_1.png"] == (985, 552)
    # the icons stay the logo mark: a mascot does not read at 16-32 px
    assert sizes["ModelItem_Icon_Small.png"] == (24, 24) and sizes["Workload_Favicon.png"] == (32, 32)


# ------------------------------------------------------------------ the Claude card's clients -----------------------

@pytest.mark.parametrize("registration", ["", "1"])
def test_the_claude_card_says_exactly_which_clients_sign_in_today(monkeypatch, registration):
    monkeypatch.setenv("KRUSGRAPH_CLIENT_REGISTRATION", registration)
    from fabric_backend import pages
    w = offering.way("claude")
    texts = [offering.val(w, "who"), offering.val(w, "short"), offering.val(w, "how"), *offering.val(w, "needs")]
    joined = " ".join(texts)
    assert "another MCP client" not in joined and "any MCP client" not in joined and "other MCP clients that" not in joined
    if pages._registration_on():
        assert "VS Code or Cursor (they sign in at /mcp/connect" in offering.val(w, "who")
        assert offering.val(w, "needs")[0] == "Claude with a custom connector, or VS Code or Cursor signing in at /mcp/connect"
        assert offering.val(w, "short") == "The MCP connector, in Claude and in VS Code and Cursor"
    else:
        assert "Other MCP clients cannot sign in to the hosted service today" in offering.val(w, "who")
        assert "/mcp/connect" not in joined and "VS Code" not in joined
        assert offering.val(w, "short") == "The MCP connector, in Claude"


def test_the_choose_page_shows_the_new_claude_wording(client):
    h = client.get("/choose").text
    assert "or another MCP client (VS Code, Cursor, through /mcp/connect)" not in h
    assert re.search(r"Claude with a custom connector[ ,(]", h)
