"""WB14 (issue #108): "Save to lakehouse Files" in the Model editor, behind a switch that is off by default.

The switch lives on the hosting server (KRUSGRAPH_ONELAKE_SAVE -> the meta tag krusgraph-onelake-save in the editor's
index.html), so turning it on or off needs no workload package and no manifest change. The save itself runs in the
editor (workload/Workload/app/items/ModelItem/onelakeSave.ts; its OneLake answers are mocked in onelakeSave.test.tsx).
These checks need no browser and no network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fabric_backend import workload_host

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "workload" / "Workload" / "app" / "items" / "ModelItem"
PAGE = "<html><head><title>x</title></head><body></body></html>"


def _page(tmp_path: Path) -> str:
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    return workload_host.Editor(tmp_path).index().decode()


def test_the_switch_is_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("KRUSGRAPH_ONELAKE_SAVE", raising=False)
    assert workload_host.onelake_save_on() is False
    assert "krusgraph-onelake-save" not in _page(tmp_path)


@pytest.mark.parametrize("value", ["1", "on", "true", "YES", " On "])
def test_the_switch_on_adds_the_meta_tag(monkeypatch, tmp_path, value):
    monkeypatch.setenv("KRUSGRAPH_ONELAKE_SAVE", value)
    assert '<meta name="krusgraph-onelake-save" content="on">' in _page(tmp_path)


@pytest.mark.parametrize("value", ["", "0", "off", "false", "no", "maybe"])
def test_anything_else_keeps_it_off(monkeypatch, tmp_path, value):
    monkeypatch.setenv("KRUSGRAPH_ONELAKE_SAVE", value)
    assert "krusgraph-onelake-save" not in _page(tmp_path)


def test_the_manifest_is_not_changed_for_it():
    # Microsoft Learn, "Workload Manifest" (fabric/extensibility-toolkit/manifest-workload, ms.date 12/15/2025): the
    # manifest names the frontend app (AADFEApp > AppId) and has no element for scopes; the scope is an API permission
    # of that Entra app. So the manifest keeps no storage scope and its sandbox stays as it was.
    text = (ROOT / "workload" / "Workload" / "Manifest" / "WorkloadManifest.xml").read_text(encoding="utf-8")
    assert "storage.azure.com" not in text
    assert "<EnableSandboxRelaxation>false</EnableSandboxRelaxation>" in text


def test_the_editor_writes_only_through_the_documented_onelake_endpoint_as_the_user():
    src = (MODEL / "onelakeSave.ts").read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    hosts = set(re.findall(r"https://([a-z0-9.-]+)", code))
    assert hosts == {"onelake.dfs.fabric.microsoft.com", "storage.azure.com"}
    assert 'STORAGE_SCOPE = "https://storage.azure.com/user_impersonation"' in code
    # delegated only: no client secret, no client-credentials grant
    assert "client_secret" not in code and "client_credentials" not in code
    # a create never overwrites unless the person chose Replace
    assert '"If-None-Match": "*"' in code
    # the log carries the status and OneLake's request id only
    logged = re.findall(r"log\(\{([^}]*)\}\)", code)
    assert logged and all(set(re.findall(r"(\w+):", f)) <= {"status", "activity_id"} for f in logged)


def test_the_editor_asks_for_the_storage_scope_only_when_the_switch_is_on():
    editor = (MODEL / "ModelItemEditor.tsx").read_text(encoding="utf-8")
    assert "saveEnabled(" in editor and "scopes: [STORAGE_SCOPE]" in editor
    assert re.search(r"saveOn && lakehouse && saveItemName \?", editor)


def test_the_docs_give_the_click_list_and_the_way_back():
    setup = (ROOT / "docs" / "ONELAKE-SAVE-SETUP.md").read_text(encoding="utf-8")
    for words in ("Azure Storage", "user_impersonation", "Delegated", "Grant admin consent", "KRUSGRAPH_ONELAKE_SAVE",
                  "demo_lh", "Files/krusgraph/", "Turn it off", "learn.microsoft.com"):
        assert words in setup, words
    dev = (ROOT / "docs" / "WORKLOAD-DEV.md").read_text(encoding="utf-8")
    assert "## Save to lakehouse Files" in dev and "ONELAKE-SAVE-SETUP.md" in dev
