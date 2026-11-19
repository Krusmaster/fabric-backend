"""MCP Apps: how every Krusgraph card reports its height (round WB13, issue #89).

Gustav's phone test in claude.ai on 19 November 2026 (Android, about 390 px wide, dark mode): under the check, review,
ontology and semantic model cards there was a tall empty area, often a full phone screen, before the next content.
Round WB12 (#68) had fixed the start card only. The check card (mcp_apps.py), the review card (mcp_apps_review.py) and
the build card (mcp_apps_build.py, which draws ontology_draft and semantic_model_draft) still sent
`document.documentElement.scrollHeight`. That value is never less than the frame's own height, so a frame the host had
made tall never shrank.

Every card now uses SIZE_JS. It measures where `main` ends (its bottom edge plus the page's scroll offset; `html` and
`body` have no margin and no height of their own), and sends that with `ui/notifications/size-changed` ({width,
height}). It reports when the card starts, whenever a ResizeObserver on `main` fires (an answer drawn, a section
opened or closed, the width changed), on every `toggle` of a details element and when the page has loaded. Sources:
the MCP Apps specification, modelcontextprotocol/ext-apps specification/2026-01-26/apps.mdx,
"ui/notifications/size-changed" (the view reports its size; the host may resize the frame), as cited in mcp_apps.py.

SIZE_JS goes inside each card's script, after `notify` is defined, and defines `reportSize()` and `watchSize(onResize)`.
"""
from __future__ import annotations

SIZE_JS = r"""
  // WB13 (#89): the height of the content (where main ends), never the frame's: documentElement.scrollHeight is at
  // least the frame's own height, so a frame the host made tall once never shrank
  var kgSizeLast = 0, kgSizeWidth = 0;
  function contentHeight() {
    var m = document.querySelector("main");
    if (!m) return 0;
    return Math.ceil(m.getBoundingClientRect().bottom + (window.scrollY || 0));
  }
  function reportSize() {
    var m = document.querySelector("main"), h = contentHeight();
    var w = Math.ceil(m ? m.getBoundingClientRect().width : document.documentElement.clientWidth);
    if (h > 0 && (h !== kgSizeLast || w !== kgSizeWidth)) {
      kgSizeLast = h; kgSizeWidth = w;
      notify("ui/notifications/size-changed", { width: w, height: h });
    }
  }
  function watchSize(onResize) {
    reportSize();
    var m = document.querySelector("main");
    if (window.ResizeObserver && m) new ResizeObserver(function () { if (onResize) onResize(); reportSize(); }).observe(m);
    document.addEventListener("toggle", function () { reportSize(); }, true);
    window.addEventListener("load", function () { reportSize(); });
  }
"""
