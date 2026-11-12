"""n224: every file the site serves from /static/ is in the installed package, not only in the repository.

On 12 Nov 2026 /static/mascots/*.webp returned 404 on krusgraph.com: the image is built with `pip install .`
(Dockerfile), and pyproject.toml's [tool.setuptools.package-data] listed static/* but not static/mascots/*. The
tests ran from the checkout, where the files exist, so nothing failed. These tests read the package-data globs the
way setuptools does (a pattern is relative to the package directory and `*` does not cross a `/`) and check that
every /static/... path a page, a template, a script or a stylesheet refers to, and every file in static/, is matched.
"""
import re
import tomllib
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from fabric_backend import server
from fabric_backend.pages import PAGES, STATIC_TYPES, static_file

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "fabric_backend"
STATIC = PKG / "static"
REF = re.compile(r"/static/([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)")
# Data files inside the package that are deliberately not installed: the facet schema is published by its GitHub URL.
NOT_PACKAGED = {"openlineage_krusgraph_facet.json"}


def packaged() -> set[str]:
    globs = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]["fabric_backend"]
    return {p.relative_to(PKG).as_posix() for g in globs for p in PKG.glob(g) if p.is_file()}


def refs_in(text: str) -> set[str]:
    return {m.rstrip(".") for m in REF.findall(text)}


@pytest.fixture(scope="module")
def client():
    with TestClient(server.build_app()) as c:
        yield c


def site_paths(client) -> list[str]:
    urls = re.findall(r"<loc>https?://[^/<]+(/[^<]*)</loc>", client.get("/sitemap.xml").text)
    return sorted(set(urls) | set(PAGES) | {"/docs", "/privacy", "/lovable", "/local"})


def test_every_static_reference_in_a_rendered_page_is_packaged(client):
    have, missing = packaged(), {}
    for path in site_paths(client):
        r = client.get(path)
        if r.status_code != 200:
            continue
        for ref in refs_in(r.text):
            if f"static/{ref}" not in have:
                missing.setdefault(f"static/{ref}", path)
    assert not missing, f"referenced by a page but not in [tool.setuptools.package-data]: {missing}"


def test_every_static_reference_in_the_sources_is_packaged():
    have, missing = packaged(), {}
    sources = [*PKG.glob("*.py"), *PKG.glob("page_templates/*"), *STATIC.glob("*.js"), *STATIC.glob("*.css")]
    for f in sources:
        for ref in refs_in(f.read_text(encoding="utf-8")):
            if (STATIC / ref).is_file() and f"static/{ref}" not in have:
                missing.setdefault(f"static/{ref}", f.name)
    assert not missing, f"not in [tool.setuptools.package-data]: {missing}"


def test_every_servable_static_file_is_packaged():
    """The mascot renders are named at run time (MASCOT_RENDERS + kind), so no literal reference finds them."""
    have = packaged()
    servable = [p.relative_to(PKG).as_posix() for p in STATIC.rglob("*") if p.is_file() and p.suffix in STATIC_TYPES]
    assert servable and not [p for p in servable if p not in have]


def test_every_data_file_in_the_package_is_packaged():
    have = packaged()
    data = [p.relative_to(PKG).as_posix() for p in PKG.rglob("*")
            if p.is_file() and p.suffix not in {".py", ".pyc"} and "__pycache__" not in p.parts]
    assert [p for p in data if p not in have and p not in NOT_PACKAGED] == []


@pytest.mark.parametrize("name", ["onto", "thinker", "builder"])
@pytest.mark.parametrize("ext", ["webp", "png"])
def test_the_mascot_renders_are_packaged_and_served(client, name, ext):
    assert f"static/mascots/{name}.{ext}" in packaged()
    assert static_file(f"mascots/{name}.{ext}") is not None
    r = client.get(f"/static/mascots/{name}.{ext}")
    assert r.status_code == 200 and r.headers["content-type"] == f"image/{ext}"


def test_the_glob_reader_would_have_caught_the_live_bug():
    globs_without = [g for g in tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]
                     ["package-data"]["fabric_backend"] if g != "static/mascots/*"]
    files = {p.relative_to(PKG).as_posix() for g in globs_without for p in PKG.glob(g) if p.is_file()}
    assert "static/mascots/onto.webp" not in files      # static/* does not reach into a subfolder
