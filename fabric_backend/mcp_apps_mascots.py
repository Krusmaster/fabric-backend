"""The site's mascots in the MCP Apps cards (round n136): Onto, the Thinker and the Builder as inline SVG.

The shapes are the site's own: they are read from `fabric_backend/static/mascots.js` (its `KINDS`), a file inside the
package and so inside the Docker image; nothing outside `fabric_backend/` is read. The card draws them as flat SVG: the
site's gradients and blurs are references (`url(#…)`), which the cards do not use, so a figure here is the same body,
arms, cheeks, highlight and eyes in flat colours.

How the cards use them (`mcp_apps.py`, `mcp_apps_review.py`), in the way the site's chat demo does:

- Onto says the counts, the Thinker what needs attention, the Builder the next steps. Each says one sentence taken
  word for word from the tool's text answer, and that sentence is also on the card outside the figures; a figure with
  nothing from the answer to say is not shown. Mascots are decoration, never the only carrier of information (docs/SITE.md).
- A figure is glad (`celebrate`, `heart`) only when the check passed; on a failed check, an error or a cancelled call
  nobody celebrates (`GLAD`, `poses()` in the card script).
- A visible button on the card, "Mascots: on" / "Mascots: off", hides them, like the site's footer switch. The choice
  lasts as long as the card: the cards use no storage.
- No animation: the poses are still positions (the site's `site.css` pose rules without its keyframes).
"""
from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "static" / "mascots.js"
KINDS = ("onto", "thinker", "builder")
NAMES = {"onto": "Onto", "thinker": "Thinker", "builder": "Builder"}
GLAD = ("celebrate", "heart")                     # the poses that show joy; only for a check that passed
POSES = ("rest", "point", "explain", "think", "notice", "calm") + GLAD


@lru_cache(maxsize=1)
def kinds() -> dict:
    """mascots.js's KINDS object as data. The object is a plain literal (numbers, strings, arrays); this turns it into
    JSON: comments out, keys and single-quoted strings in double quotes."""
    js = SOURCE.read_text(encoding="utf-8")
    m = re.search(r"var KINDS = (\{.*?\n  \});", js, re.S)
    if not m:
        raise ValueError(f"no KINDS object in {SOURCE.name}")
    body = re.sub(r"//[^\n]*", "", m.group(1))
    body = re.sub(r"'([^'\\]*)'", lambda q: json.dumps(q.group(1)), body)
    body = re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', body)
    data = json.loads(body)
    missing = [k for k in KINDS if k not in data]
    if missing:
        raise ValueError(f"{SOURCE.name} has no {', '.join(missing)}")
    return data


def _n(x) -> str:
    return f"{x:g}" if isinstance(x, (int, float)) else str(x)


def _arm(side: str, a: list, k: dict) -> str:
    x, y, angle = a
    rx, ry = k["armRX"], k["armRY"]
    tool = (f'<g class="m-tool"><rect x="{_n(x + 2)}" y="{_n(y + 16)}" width="15" height="6.5" rx="2.5" fill="#5B4A3A"/>'
            f'<rect x="{_n(x + 7)}" y="{_n(y + 20)}" width="4" height="10" rx="2" fill="#8A6B4F"/></g>') if side == "r" else ""
    return (f'<g class="m-arm m-arm-{side}" style="transform-origin:{_n(x)}px {_n(y)}px">'
            f'<g transform="rotate({_n(angle)} {_n(x)} {_n(y)})">'
            f'<ellipse cx="{_n(x)}" cy="{_n(y + ry - 3)}" rx="{_n(rx)}" ry="{_n(ry)}" fill="{k["fill"]}" '
            f'stroke="{k["dark"]}" stroke-width="1.1" stroke-opacity=".7"/>'
            f'<ellipse cx="{_n(x - 1.5)}" cy="{_n(y + 2)}" rx="2.4" ry="4" fill="#fff" opacity=".22"/></g>{tool}</g>')


def svg(kind: str, pose: str = "rest") -> str:
    """One figure as inline SVG, decorative (aria-hidden): what it says is in the bubble's text beside it."""
    k = kinds()[kind]
    eyes = "".join(f'<circle class="m-eye" cx="{_n(x)}" cy="{_n(y)}" r="{_n(k["eyeR"])}"/>'
                   f'<circle class="m-glint" cx="{_n(x + 1.2)}" cy="{_n(y - 1.3)}" r="1.15"/>' for x, y in k["eyes"])
    blush = "".join(f'<ellipse cx="{_n(x)}" cy="{_n(y)}" rx="5" ry="2.8" fill="{k["cheek"]}" opacity=".6"/>'
                    for x, y in k["blush"])
    hx, hy, hrx, hry, hrot = k["hl"]
    sx, sy, srx, sry = k["shadow"]
    return (f'<svg class="mascot {kind}" data-kind="{kind}" data-pose="{html.escape(pose)}" viewBox="0 0 120 120" '
            f'aria-hidden="true" focusable="false" style="--tilt:{_n(k["tilt"])}deg">'
            f'<ellipse class="m-shadow" cx="{_n(sx)}" cy="{_n(sy)}" rx="{_n(srx)}" ry="{_n(sry)}" fill="{k["dark"]}"/>'
            '<g class="m-figure">'
            '<g class="m-confetti"><circle cx="28" cy="26" r="3" fill="#F2735C"/><circle cx="60" cy="8" r="3" fill="#9DB8A0"/>'
            '<circle cx="94" cy="22" r="3" fill="#A99AD8"/><circle cx="42" cy="10" r="2" fill="#E3A93B"/>'
            '<circle cx="80" cy="6" r="2" fill="#F2735C"/></g>'
            f'<g class="m-body"><path d="{k["body"]}" fill="{k["fill"]}" stroke="{k["dark"]}" stroke-width="1.2" stroke-opacity=".6"/>'
            f'<ellipse cx="{_n(hx)}" cy="{_n(hy)}" rx="{_n(hrx)}" ry="{_n(hry)}" fill="{k["light"]}" opacity=".85" '
            f'transform="rotate({_n(hrot)} {_n(hx)} {_n(hy)})"/>{blush}</g>'
            + _arm("l", k["armL"], k) + _arm("r", k["armR"], k) +
            '<g class="m-heart"><path d="M60 98 C53 91 46 88 46 81 C46 76 51 73 55 76 C57.5 77.8 60 81 60 81 C60 81 62.5 '
            '77.8 65 76 C69 73 74 76 74 81 C74 88 67 91 60 98 Z" fill="#F2735C" stroke="#fff" stroke-width="2.5"/></g>'
            f'<g class="m-eyes">{eyes}</g></g></svg>')


# The site's pose rules (static/site.css, "mascots"), without animation; colours stay readable on dark cards.
CSS = """
.kg-mascots { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none }
.kg-mascots[hidden], .kg-say[hidden] { display: none }
.kg-say { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 2px 8px; align-items: start; margin: 0 }
.kg-say .kg-fig { width: 44px; height: 44px }
.kg-say .kg-fig svg { display: block; width: 100%; height: 100%; overflow: visible }
.kg-bub { min-width: 0; background: var(--kg-card); border: 1px solid var(--kg-line); border-radius: 4px 14px 14px 14px;
  padding: 6px 10px; display: grid; gap: 2px }
.kg-bub p { margin: 0; overflow-wrap: anywhere }
.kg-say.glad .kg-bub { border-color: var(--kg-ok); border-width: 2px }
.kg-who { font-size: 12.5px; font-weight: 650; color: var(--kg-muted) }
.kg-toggle { font: inherit; font-size: 13px; font-weight: 650; justify-self: start; color: var(--kg-ink);
  background: var(--kg-card); border: 1px solid var(--kg-line); border-radius: 999px; padding: 2px 12px; cursor: pointer }
.kg-toggle:focus-visible, button:focus-visible { outline: 2px solid var(--kg-ink); outline-offset: 2px }
.kg-head { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: center; justify-content: space-between }
.mascot .m-figure { transform-box: view-box; transform-origin: 60px 108px; transform: rotate(var(--tilt)) }
.mascot .m-eyes { transform: translate(1.2px, -.6px) }
.mascot .m-arm { transform-box: view-box }
.mascot .m-heart, .mascot .m-confetti, .mascot .m-tool { opacity: 0 }
.mascot .m-eye { fill: #1B1B1F }
.mascot .m-glint { fill: #fff }
.mascot .m-shadow { opacity: .45 }
.mascot[data-pose=point] .m-arm-r { transform: rotate(-125deg) }
.mascot[data-pose=point] .m-figure { transform: rotate(calc(var(--tilt) + 4deg)) }
.mascot[data-pose=celebrate] .m-arm-l { transform: rotate(140deg) }
.mascot[data-pose=celebrate] .m-arm-r { transform: rotate(-140deg) }
.mascot[data-pose=celebrate] .m-confetti { opacity: 1 }
.mascot[data-pose=celebrate] .m-eyes { transform: translate(0, -2px) }
.mascot[data-pose=heart] .m-arm-l { transform: rotate(-38deg) }
.mascot[data-pose=heart] .m-arm-r { transform: rotate(38deg) }
.mascot[data-pose=heart] .m-heart { opacity: 1 }
.mascot[data-pose=notice] .m-figure { transform: rotate(calc(var(--tilt) - 3deg)) translateY(-4px) }
.mascot[data-pose=think] .m-arm-r { transform: rotate(135deg) }
.mascot[data-pose=think] .m-eyes { transform: translate(-2.5px, -3px) }
.mascot[data-pose=explain] .m-arm-l { transform: rotate(38deg) }
.mascot[data-pose=explain] .m-arm-r { transform: rotate(-38deg) }
.mascot[data-pose=calm] .m-figure { transform: rotate(0deg) }
@media (prefers-color-scheme: dark) { .mascot .m-shadow { opacity: .7 } }
"""


def section() -> str:
    """The toggle and the three figures, hidden until an answer arrives. The card script fills the bubbles with
    `textContent` and sets the poses."""
    rows = "".join(
        f'<li class="kg-say {k}" data-mascot="{k}" hidden><span class="kg-fig">{svg(k, "rest")}</span>'
        f'<div class="kg-bub"><p class="kg-who">{NAMES[k]}</p><p class="kg-line"></p></div></li>' for k in KINDS)
    return (f'<ul id="kg-mascots" class="kg-mascots" aria-label="Mascots: the same sentences as on the card" hidden>{rows}</ul>')


TOGGLE = ('<button id="kg-toggle" class="kg-toggle" type="button" aria-pressed="true" aria-controls="kg-mascots">'
          'Mascots: on</button>')

# The card script's part: show(sayings, glad) puts each figure's sentence in its bubble, or hides it when it has none;
# a figure is glad only when `glad` is true (the check passed), never otherwise.
JS = r"""
  var mascotsOn = true, GLAD = __GLAD__;
  function mascots(say, passed) {
    // say: {onto: [text, pose], thinker: [...], builder: [...]}; passed: true only when the check passed.
    var box = document.getElementById("kg-mascots"), any = false;
    ["onto", "thinker", "builder"].forEach(function (k) {
      var row = box.querySelector('[data-mascot="' + k + '"]'), s = say[k];
      var pose = s ? s[1] : "rest";
      if (!passed && GLAD.indexOf(pose) >= 0) pose = "explain";      // never glad about a check that did not pass
      row.querySelector("svg").setAttribute("data-pose", pose);
      row.className = "kg-say " + k + (passed && GLAD.indexOf(pose) >= 0 ? " glad" : "");
      row.querySelector(".kg-line").textContent = s && s[0] ? s[0] : "";
      row.hidden = !(s && s[0]);
      any = any || !row.hidden;
    });
    box.setAttribute("data-filled", any ? "1" : "");
    box.hidden = !any || !mascotsOn;
  }
  function mascotsQuiet() { var box = document.getElementById("kg-mascots"); box.setAttribute("data-filled", ""); box.hidden = true; }
  (function () {
    var b = document.getElementById("kg-toggle");
    b.addEventListener("click", function () {
      mascotsOn = !mascotsOn;
      b.setAttribute("aria-pressed", mascotsOn ? "true" : "false");
      b.textContent = mascotsOn ? "Mascots: on" : "Mascots: off";
      var box = document.getElementById("kg-mascots");
      box.hidden = !mascotsOn || !box.getAttribute("data-filled");
    });
  })();
""".replace("__GLAD__", json.dumps(list(GLAD)))
