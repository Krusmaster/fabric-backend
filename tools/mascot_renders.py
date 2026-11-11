#!/usr/bin/env python3
"""n216: the three mascots as the overview film draws them (soft, glossy 3D), cut out on a transparent ground.

    python tools/mascot_renders.py            # writes fabric_backend/static/mascots/*.webp and *.png
    python tools/mascot_renders.py --check    # compares the committed files with a fresh cut, nothing written

The film (fabric_backend/static/media/krusgraph-overview-web.mp4, 1920 x 1080) is the only 3D render of the
characters in this repository: its closing frame (43 s) shows Onto, Thinker and Builder side by side, resting, about
90 px wide on a flat #F4F4F4 ground. This tool takes that frame with ffmpeg, keys out the ground, un-mixes the
anti-aliased rim from it (I = a*F + (1-a)*B, solved for a along the line to the body's colour) and replaces the film's
contact shadow, a darkening of a light ground that would glow on a dark page, with a soft shadow in a dark tint of the
figure's own colour, so the figures sit on any background, light or dark, without a grey halo.

Each figure lands on the same 112 x 112 canvas at the film's own scale and ground line, so the three stand at their
relative sizes wherever they are placed. 112 px is the most the film gives; it is crisp at 2x up to 56 CSS px.
Larger slots, other poses and props need new renders: docs/MASCOT-ART-NEEDED.md.

Needs ffmpeg on PATH and Pillow and numpy (dev-only; not a runtime dependency).
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILM = ROOT / "fabric_backend" / "static" / "media" / "krusgraph-overview-web.mp4"
OUT = ROOT / "fabric_backend" / "static" / "mascots"
WORKLOAD_OUT = ROOT / "workload" / "Workload" / "app" / "assets" / "mascots"
AT = "43"                      # seconds into the film: the closing frame, all eyes open
CROP = (780, 785, 360, 120)    # x, y, w, h of the three figures in the 1920 x 1080 frame
SPANS = {"onto": (14, 105), "thinker": (148, 216), "builder": (269, 335)}   # columns inside the crop
GROUND = (244, 244, 244)
CANVAS = 112
# channel distance from the ground above which a pixel is body, per figure: the film's coloured contact shadow stays
# below it (at most 45 for Onto and 50 for Thinker, 76 for the stronger coral of Builder; the bodies are 98-168)
BODY = {"onto": 58.0, "thinker": 62.0, "builder": 92.0}


def frame():
    from PIL import Image
    png = subprocess.run(["ffmpeg", "-v", "error", "-ss", AT, "-i", str(FILM), "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], check=True, capture_output=True).stdout
    x, y, w, h = CROP
    return Image.open(io.BytesIO(png)).convert("RGB").crop((x, y, x + w, y + h))


def _local_mean(values, weight, radius: int):
    """Mean of `values` over a (2r+1)^2 window, counting only pixels where weight is 1."""
    import numpy as np
    k = 2 * radius + 1
    def box(x):
        p = np.pad(x, [(radius, radius), (radius, radius)] + [(0, 0)] * (x.ndim - 2))
        c = p.cumsum(0).cumsum(1)
        c = np.pad(c, [(1, 0), (1, 0)] + [(0, 0)] * (x.ndim - 2))
        return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    w = box(weight.astype(float))
    v = box(values * weight[..., None])
    return v / np.maximum(w, 1e-9)[..., None], w


def cut(img):
    """RGBA of the crop: each body opaque (holes filled), the anti-aliased rim un-mixed from the ground, the film's
    contact shadow (a darkening of the ground) dropped; figures() draws a soft shadow of its own that reads on light
    and dark pages."""
    import numpy as np
    from PIL import Image, ImageDraw
    a = np.asarray(img).astype(float)
    b = np.array(GROUND, float)
    d = np.abs(a - b).max(axis=2)
    limit = np.full(d.shape, 255.0)
    for kind, (x0, x1) in SPANS.items():
        limit[:, x0:x1 + 1] = BODY[kind]
    core_img = Image.fromarray(((d > limit) * 255).astype("uint8")).copy()   # a copy: fromarray shares a read-only buffer
    # The glossy highlights come close to the ground's own grey and open onto the outline, so the shape is taken from
    # a low threshold (anything off the ground), filled, pulled in by 2 px (the rim below mattes that band), and cut
    # off under each column's lowest body pixel, which is where the film's contact shadow starts.
    from PIL import ImageFilter
    core = np.asarray(core_img) > 0
    loose = Image.fromarray(((d > 12) * 255).astype("uint8")).copy()
    ImageDraw.floodfill(loose, (0, 0), 128)
    filled = Image.fromarray(((np.asarray(loose) != 128) * 255).astype("uint8"))
    shape = np.asarray(filled.filter(ImageFilter.MinFilter(5))) > 0
    rows = np.arange(d.shape[0])[:, None]
    bottom = np.where(core.any(axis=0), d.shape[0] - 1 - np.argmax(core[::-1], axis=0), -1)
    inside = core | (shape & (rows <= bottom[None, :]))
    # the rim: within 2 px of a body, alpha is the pixel's share of the nearest body colour, projected on the line
    # from the ground to that colour (I = a*F + (1-a)*B)
    f, w = _local_mean(a, inside, 2)
    near = (w > 0) & ~inside
    fb = f - b
    alpha = np.clip(((a - b) * fb).sum(axis=2) / np.maximum((fb * fb).sum(axis=2), 1e-9), 0, 1)
    alpha = np.where(near, alpha, 0.0)
    alpha[inside] = 1.0
    fg = np.where(inside[..., None], a, f)
    rgba = np.dstack([np.clip(fg, 0, 255), alpha * 255]).round().astype("uint8")
    return Image.fromarray(rgba, "RGBA")


def shadow(width: int, colour):
    """A soft contact shadow under a figure: a blurred ellipse in a dark tint of the figure's own colour."""
    from PIL import Image, ImageDraw, ImageFilter
    layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    tint = tuple(int(c * 0.45) for c in colour[:3])
    draw = ImageDraw.Draw(layer)
    w = int(width * 0.8)
    cx, cy = CANVAS // 2, CANVAS - 9
    draw.ellipse((cx - w // 2, cy - 3, cx + w // 2, cy + 3), fill=tint + (90,))
    return layer.filter(ImageFilter.GaussianBlur(2.2))


def figures() -> dict:
    from PIL import Image
    rgba = cut(frame())
    out = {}
    for kind, (x0, x1) in SPANS.items():
        w = x1 - x0 + 1
        fig = rgba.crop((x0, 0, x1 + 1, rgba.height))
        box = fig.getbbox()
        fig = fig.crop((0, 0, fig.width, box[3]))
        canvas = shadow(w, fig.getpixel((w // 2, box[3] - 8)))
        # same ground line for all three: each body's lowest pixel sits 9 px above the canvas bottom
        canvas.alpha_composite(fig, ((CANVAS - w) // 2, CANVAS - 9 - fig.height + 1))
        out[kind] = canvas
    return out


def encode(img, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "webp":
        img.save(buf, "WEBP", lossless=True, method=6)
    else:
        img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for kind, img in figures().items():
        targets = [(OUT / f"{kind}.webp", "webp"), (OUT / f"{kind}.png", "png"), (WORKLOAD_OUT / f"{kind}.png", "png")]
        for path, fmt in targets:
            data = encode(img, fmt)
            if check:
                if not path.exists():
                    stale.append(str(path))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            print(f"{path.relative_to(ROOT)}  {img.width}x{img.height}  {len(data)} bytes")
    if stale:
        print("missing:", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
