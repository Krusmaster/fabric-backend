"""n159: the operator switches KRUSGRAPH_MCP_APPS, KRUSGRAPH_READ_ONLY and KRUSGRAPH_NO_ROW_VALUES survive a deploy.
On 8 November 2026 an update dropped KRUSGRAPH_MCP_APPS=1, set by hand on the container app, because the full run's
manifest replaces the whole environment and carried over only the Key Vault and registration settings. They are now
keys of deploy/krusgraph.json (mcp_apps, read_only, no_row_values); a hand-set one whose key is missing is carried over
with a hint. `az` is faked; every id and name here is invented."""
import json

import pytest

from deploy import azure_containerapp as d
from tests import test_deploy_from_azure as fa

BASE = json.loads((d.ROOT / "deploy/krusgraph.example.json").read_text(encoding="utf-8"))
LEGACY = {k: v for k, v in BASE.items() if k not in d.OPERATOR_FLAGS}      # a krusgraph.json from before n159


def existing_app(**env):
    plain = {"PRODUCT_NAME": "Krusgraph", "KRUSGRAPH_BUILD": "src-old", **env}
    return {"properties": {"configuration": {"ingress": {}},
                           "template": {"containers": [{"name": "krusgraph", "env":
                                        [{"name": k, "value": v} for k, v in plain.items()]
                                        + [{"name": "ENTRA_CLIENT_SECRET", "secretRef": "entra-secret"}]}]}}}


def manifest_env(config, existing=None):
    manifest = d.make_manifest(config, "env", "identity", "registry", "image", "s", existing, build="src-new")
    return {e["name"]: e.get("value") for e in manifest["properties"]["template"]["containers"][0]["env"]}


HINT = 'Behåller KRUSGRAPH_MCP_APPS=1 som sattes för hand i appen; lägg till "mcp_apps": true i deploy/krusgraph.json.'


def test_full_run_keeps_a_hand_set_mcp_apps_and_says_so(capsys):
    env = manifest_env(LEGACY, existing_app(KRUSGRAPH_MCP_APPS="1"))
    assert env["KRUSGRAPH_MCP_APPS"] == "1"
    assert "KRUSGRAPH_READ_ONLY" not in env and "KRUSGRAPH_NO_ROW_VALUES" not in env
    out = capsys.readouterr().out
    assert out.count(HINT) == 1 and "KRUSGRAPH_READ_ONLY" not in out


@pytest.mark.parametrize("key,variable", list(d.OPERATOR_FLAGS.items()))
def test_config_true_sets_the_flag_without_a_hint(key, variable, capsys):
    env = manifest_env(BASE | {key: True}, existing_app())
    assert env[variable] == "1"
    assert manifest_env(BASE | {key: True})[variable] == "1"          # first run, no app yet
    assert "Behåller" not in capsys.readouterr().out


@pytest.mark.parametrize("config", [BASE, LEGACY], ids=["false", "absent"])
def test_false_or_absent_without_an_old_value_leaves_the_flags_unset(config, capsys):
    for existing in (None, existing_app(), existing_app(KRUSGRAPH_MCP_APPS="0", KRUSGRAPH_READ_ONLY="")):
        env = manifest_env(config, existing)
        assert not set(d.OPERATOR_FLAGS.values()) & set(env)
    assert "Behåller" not in capsys.readouterr().out


def test_explicit_false_in_the_config_wins_over_the_old_revision(capsys):
    env = manifest_env(BASE, existing_app(KRUSGRAPH_MCP_APPS="1"))
    assert "KRUSGRAPH_MCP_APPS" not in env and "Behåller" not in capsys.readouterr().out


def test_read_only_and_no_row_values_are_read_as_the_server_reads_them(capsys):
    env = manifest_env(LEGACY, existing_app(KRUSGRAPH_READ_ONLY="true", KRUSGRAPH_NO_ROW_VALUES="1", KRUSGRAPH_MCP_APPS="true"))
    assert env["KRUSGRAPH_READ_ONLY"] == "true" and env["KRUSGRAPH_NO_ROW_VALUES"] == "1"
    assert "KRUSGRAPH_MCP_APPS" not in env                     # the server turns the cards on only with "1"
    assert capsys.readouterr().out.count("Behåller") == 2


class Cloud(fa.FakeCloud):
    def __init__(self, **env):
        super().__init__(selected=fa.APP_SUB)
        container = self.app["properties"]["template"]["containers"][0]
        container["env"] += [{"name": k, "value": v} for k, v in env.items()]

    def env(self):
        return d.app_env(self.app)


def test_update_with_a_legacy_config_keeps_the_hand_set_flag_and_prints_the_hint(monkeypatch, tmp_path, capsys):
    cloud = Cloud(KRUSGRAPH_MCP_APPS="1")
    legacy = {k: v for k, v in fa.EXPECTED.items() if k not in d.OPERATOR_FLAGS}
    (tmp_path / "krusgraph.json").write_text(json.dumps(legacy), encoding="utf-8")
    fa.run_main(monkeypatch, tmp_path, cloud, "--update")
    assert cloud.env()["KRUSGRAPH_MCP_APPS"] == "1" and cloud.env()["KRUSGRAPH_BUILD"] == "src-new"
    update = next(a for a, _ in cloud.calls if a[:2] == ("containerapp", "update"))
    assert "KRUSGRAPH_MCP_APPS=1" in update
    assert HINT in capsys.readouterr().out


def test_update_with_mcp_apps_true_sets_it(monkeypatch, tmp_path, capsys):
    cloud = Cloud()
    (tmp_path / "krusgraph.json").write_text(json.dumps(fa.EXPECTED | {"mcp_apps": True}), encoding="utf-8")
    fa.run_main(monkeypatch, tmp_path, cloud, "--update")
    assert cloud.env()["KRUSGRAPH_MCP_APPS"] == "1"
    assert "Behåller" not in capsys.readouterr().out


def test_update_with_false_and_no_old_value_leaves_it_unset(monkeypatch, tmp_path, capsys):
    cloud = Cloud()
    (tmp_path / "krusgraph.json").write_text(json.dumps(fa.EXPECTED), encoding="utf-8")
    fa.run_main(monkeypatch, tmp_path, cloud, "--update")
    assert not set(d.OPERATOR_FLAGS.values()) & set(cloud.env())
    assert "Behåller" not in capsys.readouterr().out


def test_from_azure_update_keeps_the_flag_and_records_it_in_the_saved_config(monkeypatch, tmp_path):
    cloud = Cloud(KRUSGRAPH_MCP_APPS="1", KRUSGRAPH_NO_ROW_VALUES="yes")
    fa.run_main(monkeypatch, tmp_path, cloud, "--from-azure", "--update")
    saved = json.loads((tmp_path / "krusgraph.json").read_text(encoding="utf-8"))
    assert saved == fa.EXPECTED | {"mcp_apps": True, "no_row_values": True, "read_only": False}
    assert cloud.env()["KRUSGRAPH_MCP_APPS"] == "1" and cloud.env()["KRUSGRAPH_NO_ROW_VALUES"] == "yes"


def test_the_example_documents_the_three_keys_as_false():
    assert {k: BASE[k] for k in d.OPERATOR_FLAGS} == {"mcp_apps": False, "read_only": False, "no_row_values": False}
