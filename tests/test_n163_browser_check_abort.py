"""n163: tests/browser_check.js counts every failed request as an error, except one case: a same-origin file under
/static/media/ cancelled by navigation (net::ERR_ABORTED). The home page fetches the film's captions track, and the old
anchors (/#demo and the others) move on to /check while that fetch can still be running; CI run 721 failed on it."""
import re
from pathlib import Path

SRC = (Path(__file__).parent / "browser_check.js").read_text(encoding="utf-8")


def _handler() -> str:
    m = re.search(r"page\.on\('requestfailed', r => \{(.*?)\n    \}\);", SRC, re.S)
    assert m, "the requestfailed handler is a block"
    return m.group(1)


def test_only_aborted_media_is_skipped():
    body = _handler()
    assert body.count("return;") == 1
    skip = next(line for line in body.splitlines() if "return;" in line)
    assert "aborted" in skip and "base + '/static/media/'" in skip
    assert "=== 'net::ERR_ABORTED'" in body


def test_every_other_failure_is_still_an_error():
    body = _handler()
    assert body.rstrip().endswith("errors.push(`${label}: request failed ${r.url()}`);")
    assert SRC.count("'requestfailed'") == 1
