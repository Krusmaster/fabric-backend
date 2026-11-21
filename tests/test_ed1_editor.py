"""Round ED1: Gustav's test of the Krusgraph Model item in the Fabric editor, 21 November 2026 (shop_lh / shop).

1. Every output card on the Choose step showed a broken image beside its title. The icons are Microsoft's files from the
   pinned npm package (fabricIcons.json); since ED1 the production build carries each one, byte for byte, as a data: URL,
   so a card's icon needs no second request, and the served copies under /assets/fabric-icons/ stay. With a built
   editor (KRUSGRAPH_WORKLOAD_DIST: `npx webpack --output-path <dir>`, outside the repository), every /assets/ path the bundle
   references and every icon file is fetched through the workload host (workload_host.wrap) and must answer 200 with
   the package's exact bytes; and every data: URL in the bundle must decode to one of those files.
2. "...a lakehouse of this workspace.Silver and gold go to...": the rendered help text is checked for a sentence run
   into the next (ed1Words.JOINED, ed1Editor.test.tsx renders every Choose state); here the words are checked at source.
The rest (one default line on Choose, the report built on the model, Plan ?, Keys and links) is in
workload/Workload/app/items/ModelItem/ed1Editor.test.tsx (`npm test`).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from fabric_backend import workload_host

ROOT = Path(__file__).resolve().parent.parent
WL = ROOT / "workload" / "Workload"
MODEL = WL / "app" / "items" / "ModelItem"
ICONS = json.loads((MODEL / "fabricIcons.json").read_text(encoding="utf-8"))
HOST = "workload.krusgraph.com"


def _dist() -> Path | None:
    d = os.environ.get("KRUSGRAPH_WORKLOAD_DIST")             # a build outside the repository (no icon file is kept in it)
    return Path(d) if d and (Path(d) / "index.html").is_file() else None


def _get(dist: Path, path: str) -> tuple[int, dict, bytes]:
    async def app(scope, receive, send):                       # the site: never reached for the workload host
        await send({"type": "http.response.start", "status": 599, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    wrapped = workload_host.wrap(app, host=HOST, dist=dist)
    out: dict = {"body": b""}

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(m):
        if m["type"] == "http.response.start":
            out["status"], out["headers"] = m["status"], {k.decode(): v.decode() for k, v in m["headers"]}
        else:
            out["body"] += m.get("body", b"")

    asyncio.run(wrapped({"type": "http", "method": "GET", "path": path, "headers": [(b"host", HOST.encode())]}, receive, send))
    return out["status"], out["headers"], out["body"]


def test_every_icon_is_copied_and_inlined_by_the_build():
    web = (WL / "webpack.config.js").read_text(encoding="utf-8")
    assert "Object.keys(FABRIC_ICONS.files).map((file) => ({" in web                       # copied (served)
    assert '"process.env.KRUSGRAPH_FABRIC_ICONS"' in web and "data:image/svg+xml;base64," in web   # and inlined
    ts = (MODEL / "fabricIcons.ts").read_text(encoding="utf-8")
    assert "process.env.KRUSGRAPH_FABRIC_ICONS" in ts and "INLINE[file] ??" in ts
    used = {v["file"] for v in [*ICONS["kinds"].values(), *ICONS["types"].values()]}
    assert used == set(ICONS["files"])
    # the workload host lets an <img> load a data: URL and an https: one
    assert "img-src 'self' data:" in workload_host.EDITOR_CSP


@pytest.mark.skipif(_dist() is None, reason="no built editor: set KRUSGRAPH_WORKLOAD_DIST to a webpack --output-path outside the repository")
def test_every_icon_the_built_editor_references_resolves_200():
    dist = _dist()
    bundles = "".join(p.read_text(encoding="utf-8", errors="replace") for p in dist.glob("*.js"))
    referenced = set(re.findall(r'["\'`](/assets/[A-Za-z0-9_./-]+\.(?:svg|png))["\'`]', bundles))
    referenced |= {f"{ICONS['servedAt']}/{f}" for f in ICONS["files"]}
    assert len(referenced) >= len(ICONS["files"])
    bad = []
    for path in sorted(referenced):
        status, headers, body = _get(dist, path)
        if status != 200 or not body:
            bad.append(f"{path}: {status}")
            continue
        name = path.rsplit("/", 1)[-1]
        if path.startswith(ICONS["servedAt"] + "/"):
            assert headers["content-type"] == "image/svg+xml", path
            assert hashlib.sha256(body).hexdigest() == ICONS["files"][name], path
    assert not bad, bad
    # the data: URLs the output cards use are exactly the package's files
    inline = re.findall(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)", bundles)
    assert {hashlib.sha256(base64.b64decode(b)).hexdigest() for b in inline} == set(ICONS["files"].values())


def test_no_sentence_runs_into_the_next_in_the_words_of_the_choose_step():
    joined = re.compile(r"(?:^|[\s(])[a-z]+[a-z)]\.[A-Z][a-z]+[\s,:;]")
    for f in ("buildPlace.ts", "ed1Words.ts", "buildWords.ts", "sourceWords.ts"):
        text = (MODEL / f).read_text(encoding="utf-8")
        for s in re.findall(r'"((?:[^"\\]|\\.)*)"|`((?:[^`\\]|\\.)*)`', text):
            words = s[0] or s[1]
            assert not joined.search(words), f"{f}: {words[:120]}"
    ed1 = (MODEL / "ed1Words.ts").read_text(encoding="utf-8")
    assert "export const JOINED = /(?:^|[\\s(])[a-z]+[a-z)]\\.[A-Z][a-z]+[\\s,:;]/;" in ed1
    assert "Silver and gold go to the first lakehouse of this workspace by name; if it has none, tick Make a lakehouse." not in (
        MODEL / "buildPlace.ts").read_text(encoding="utf-8")
