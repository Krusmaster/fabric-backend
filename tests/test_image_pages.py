"""n135: every page renders from the files the Docker image holds, and nothing that renders a page reads a repository
file. Tonight's 500 on /docs came from a page that read deploy/ at render time; CI ran in the full repository, where
deploy/ exists. These tests rebuild the image's file set from .dockerignore and render the site from it alone."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pattern(p: str) -> re.Pattern:
    """A .dockerignore pattern as a regex over a path relative to the context; a match on a directory covers what is in it."""
    p = p.strip("/")
    out, i = "", 0
    while i < len(p):
        if p.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif p.startswith("**", i):
            out, i = out + ".*", i + 2
        elif p[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif p[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(p[i]), i + 1
    return re.compile(out + "(?:/.*)?")


def image_files() -> list[Path]:
    """The files `docker build .` sends into the image: .dockerignore's rules, the last matching one wins."""
    rules = []
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keep = line.startswith("!")
            rules.append((keep, _pattern(line.lstrip("!"))))
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT).as_posix()
        if not p.is_file() or rel.startswith(".git/"):
            continue
        included = True
        for keep, rx in rules:
            if rx.fullmatch(rel):
                included = keep
        if included:
            out.append(p)
    return out


def test_image_file_set_is_what_the_dockerfile_copies():
    rel = {p.relative_to(ROOT).as_posix() for p in image_files()}
    assert {"Dockerfile", "pyproject.toml", "README.md", "deploy/constraints.txt", "fabric_backend/server.py",
            "fabric_backend/concepts.py"} <= rel
    assert not [r for r in rel if r.split("/")[0] in ("deploy", "docs", "tests", "examples", "plugin") and r != "deploy/constraints.txt"]
    assert "CHANGELOG.md" not in rel and not [r for r in rel if "__pycache__" in r]


PROBE = r'''
import json, os, sys
img = os.getcwd()
sys.path.insert(0, img)
outside = set()
def hook(event, args):
    if event == "open" and isinstance(args[0], str):
        p = os.path.abspath(args[0])
        if os.path.isfile(p) and p.startswith(img + os.sep) and not p.startswith(os.path.join(img, "fabric_backend") + os.sep):
            outside.add(os.path.relpath(p, img))
sys.addaudithook(hook)
import re
from starlette.testclient import TestClient
from fabric_backend import server, pages
assert pages.__file__.startswith(img), pages.__file__
paths = ["/", "/docs", "/docs.md", "/llms.txt", "/llms-full.txt", "/check", "/privacy", "/it", "/sitemap.xml", "/healthz"]
paths += ["/blog"] + [f"/blog/{x['slug']}{e}" for x in pages.BLOG_POSTS for e in ("", ".md")]     # n145
menu = [p["path"] for p in pages.docs_pages()]
paths += menu + list(pages.PAGES)
bad = {}
with TestClient(server.build_app(), raise_server_exceptions=False) as c:
    sitemap = c.get("/sitemap.xml").text
    paths += [re.sub(r"^https?://[^/]+", "", u) or "/" for u in re.findall(r"<loc>([^<]+)</loc>", sitemap)]
    paths = list(dict.fromkeys(paths))
    for p in paths:
        r = c.get(p)
        if r.status_code != 200:
            bad[p] = r.status_code
print("RESULT " + json.dumps({"bad": bad, "checked": paths, "menu": menu, "outside": sorted(outside)}))
'''


def test_every_page_renders_from_the_image_files_alone(tmp_path):
    img = tmp_path / "app"
    for p in image_files():
        dst = img / p.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "ENTRA_", "MCP_", "KRUSGRAPH_"))}
    env.update(MCP_PUBLIC_URL="https://krusgraph.test/mcp", PRODUCT_NAME="Krusgraph", ENTRA_CLIENT_ID="cid-123",
               ENTRA_CLIENT_SECRET="test-secret", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-I", "-c", PROBE], cwd=img, env=env, capture_output=True, text=True, timeout=600)
    line = next((x for x in r.stdout.splitlines() if x.startswith("RESULT ")), None)
    assert line, r.stdout[-3000:] + r.stderr[-6000:]
    res = json.loads(line[len("RESULT "):])
    assert res["bad"] == {}, (res["bad"], r.stderr[-6000:])
    assert len(res["menu"]) > 5 and set(res["menu"]) <= set(res["checked"])
    for p in ("/", "/docs", "/docs.md", "/llms.txt", "/llms-full.txt", "/check", "/privacy", "/it", "/sitemap.xml", "/healthz",
              "/blog", "/blog/fabric-totals-double-after-join", "/blog/fabric-totals-double-after-join.md"):
        assert p in res["checked"]
    assert res["outside"] == [], "rendering read files outside the package: " + ", ".join(res["outside"])


def test_where_it_runs_page_still_matches_the_repository():
    """The checks that used to run while /docs rendered (n117): the scripts in pyproject.toml, deploy/krusgraph.sh,
    `location` in deploy/krusgraph.example.json and what /check's code says. Here, in the repository, never at render."""
    from fabric_backend import concepts
    assert concepts.where_code_problems(ROOT) == []


def test_where_it_runs_checks_catch_a_missing_deploy_file(tmp_path):
    (tmp_path / "pyproject.toml").write_text((ROOT / "pyproject.toml").read_text(encoding="utf-8"), encoding="utf-8")
    from fabric_backend import concepts
    assert concepts.where_code_problems(tmp_path) == ["deploy/ no longer has what the Where it runs page names"]
