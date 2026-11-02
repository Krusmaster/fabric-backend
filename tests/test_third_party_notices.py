"""THIRD_PARTY_NOTICES.md is generated from deploy/constraints.txt by tools/third_party_notices.py. These checks need no
network: every pin has a row with its exact version, no dependency is under a licence the repository refuses, the
script parses the pins the same way, and CONTRIBUTING.md carries the rules for copying code (round n76)."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTICES = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
CONSTRAINTS = (ROOT / "deploy" / "constraints.txt").read_text(encoding="utf-8")
sys.path.insert(0, str(ROOT / "tools"))
import third_party_notices as tpn  # noqa: E402


def _rows(section: str, until: str) -> list[list[str]]:
    body = NOTICES[NOTICES.index(section):NOTICES.index(until)]
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in body.splitlines()
            if line.startswith("| [")]


def test_every_pin_has_a_row_with_its_exact_version():
    pins = tpn.pins(CONSTRAINTS)
    assert pins, "no pins read"
    rows = {(r[0].split("]")[0].lstrip("["), r[1]) for r in _rows("## The server image", "## Extras that are not in the image")}
    assert rows == set(pins), {"missing": set(pins) - rows, "stale": rows - set(pins)}


def test_no_dependency_is_under_a_refused_licence():
    for r in _rows("## The server image", "## Vendored into the repository"):
        assert not any(bad in r[2].upper() for bad in tpn.REFUSED), r
        assert r[2] and r[2] != "not stated in metadata", r      # a package without a licence in its metadata is a decision, not a row


def test_the_extras_that_are_not_pinned_are_listed_without_a_version():
    import tomllib
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]
    names = {re.split(r"[\[<>=!~ ;]", r, maxsplit=1)[0].lower().replace("_", "-") for reqs in extras.values() for r in reqs}
    pinned = {n for n, _ in tpn.pins(CONSTRAINTS)}
    listed = {r[0].split("]")[0].lstrip("[") for r in _rows("## Extras that are not in the image", "## Vendored into the repository")}
    assert listed == names - pinned, (listed, names - pinned)


def test_the_vendored_assets_are_listed_with_their_licence_files():
    for asset, licence in (("fabric_backend/static/pyodide/README.txt", "Mozilla Public License 2.0"),
                           ("fabric_backend/static/fonts/OFL-Fredoka.txt", "SIL Open Font License 1.1"),
                           ("fabric_backend/static/fonts/OFL-Nunito.txt", "SIL Open Font License 1.1")):
        assert (ROOT / asset).exists(), asset
        assert asset in NOTICES and licence in NOTICES, (asset, licence)


def test_pins_parser_refuses_a_line_that_is_not_an_exact_pin():
    import pytest
    assert tpn.pins("# comment\nfoo==1.0  # trailing\nBar_Baz==2.0\n") == [("foo", "1.0"), ("bar-baz", "2.0")]
    with pytest.raises(SystemExit):
        tpn.pins("foo>=1.0\n")


def test_the_script_runs_from_the_command_line_without_network_for_help():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "third_party_notices.py"), "--help"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "--check" in r.stdout and "--from-installed" in r.stdout, r


def test_contributing_carries_the_rules_for_reusing_external_code():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    section = text[text.index("## Reusing external code"):text.index("## Issues, pull requests and conduct")]
    for phrase in ("pinned commit", "AGPL", "SSPL", "cannot be verified", "THIRD_PARTY_NOTICES.md", "tools/third_party_notices.py"):
        assert phrase in section, phrase
