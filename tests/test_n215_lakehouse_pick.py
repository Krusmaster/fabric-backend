"""Round n215: the routes the Krusgraph Model editor calls right after a lakehouse is picked in the OneLake catalog
answer without an error for a plain lakehouse source.

Live, 11 November 2026, the editor went white after the pick (the cause was in the editor: the host's numeric item type
reached sourceLabel(...).toLowerCase(); workload/Workload/app/items/ModelItem/sourcePick.test.tsx). Here, against the
Fabric and SQL doubles, the engine's side of the same step: /access (the trial line), /schemas (Choose a source), /review
(Find keys and relationships), /check (Check against the rows) and a dry run of /build, as the editor sends them for a
lakehouse (no target), and the request the broken editor sent (target lakehouse null, as for a read-only source)."""
import pytest

pytest.importorskip("jwt")

from test_workload_api import SRC, keys  # noqa: E402,F401
from test_workload_create import _post, make  # noqa: E402,F401


def _ok(r):
    assert r.status_code == 200, (r.status_code, r.text)
    out = r.json()
    assert "error" not in out or not out.get("kind"), out
    return out


@pytest.mark.parametrize("extra", [{}, {"target": {"lakehouse": None}}], ids=["lakehouse", "lakehouse-sent-as-read-only"])
def test_every_route_after_the_pick_answers_a_plain_lakehouse(make, extra):
    client, fake, priv = make()
    _ok(_post(client, "/access", {}, priv))
    schemas = _ok(_post(client, "/schemas", {k: SRC[k] for k in ("workspace", "source", "source_name")}, priv))
    assert [s["schema"] for s in schemas["schemas"] if s["tables"]] == ["shop"]
    review = _ok(_post(client, "/review", {**SRC, **extra}, priv))
    assert review["review"]["items"] and review.get("source_kind", "Lakehouse") == "Lakehouse"
    assert not review.get("read_only")
    check = _ok(_post(client, "/check", {**SRC, **extra, "review": review["review"]}, priv))
    assert check["check"]["failed"] == []
    dry = _ok(_post(client, "/build", {**SRC, **extra, "review": review["review"], "dry_run": True, "created": [],
                                       "outputs": [{"kind": "silver_notebook", "name": "demo_lh_silver"}]}, priv))
    assert dry["outputs"][0]["answer"]["dry_run"] is True and not dry["outputs"][0].get("refusal"), dry["outputs"][0]
