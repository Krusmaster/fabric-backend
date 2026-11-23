"""W3 (23 November 2026): a deploy keeps KRUSGRAPH_CATALOG_WRITE_WORKSPACES, the list of workspaces where "Publish to
OneLake catalog" may write (fabric_backend/catalog_publish/writes.py). The full run's manifest replaces the container's
whole environment and carried only known settings, so a list set by hand on the app was wiped. It is now carried like a
hand-set operator switch (with one line asking for the key), set from deploy/krusgraph.json when the key is there, and
kept by --update. `az` is faked; every id and name here is invented."""
import json

from deploy import azure_containerapp as d
from fabric_backend.catalog_publish import writes
from tests import test_deploy_from_azure as fa
from tests.test_n159_operator_flags import LEGACY, Cloud, existing_app, manifest_env

VAR = "KRUSGRAPH_CATALOG_WRITE_WORKSPACES"
ONE = "00000000-0000-4000-8000-0000000000aa"
TWO = f"{ONE},00000000-0000-4000-8000-0000000000bb"


def test_the_variable_is_the_one_the_catalog_reads():
    assert d.OPERATOR_VALUES["catalog_write_workspaces"] == VAR == writes.ALLOW_ENV


def test_a_full_run_carries_the_hand_set_list_and_says_so(capsys):
    env = manifest_env(LEGACY, existing_app(**{VAR: TWO}))
    assert env[VAR] == TWO
    out = capsys.readouterr().out
    assert out.count(f'Behåller {VAR}={TWO} som sattes för hand i appen; lägg till "catalog_write_workspaces"') == 1


def test_without_an_old_value_nothing_is_set(capsys):
    for existing in (None, existing_app(), existing_app(**{VAR: "  "})):
        assert VAR not in manifest_env(LEGACY, existing)
    assert "Behåller" not in capsys.readouterr().out


def test_the_config_key_sets_it_and_an_empty_key_leaves_it_out(capsys):
    assert manifest_env(LEGACY | {"catalog_write_workspaces": ONE})[VAR] == ONE           # first run, no app yet
    assert manifest_env(LEGACY | {"catalog_write_workspaces": ONE}, existing_app(**{VAR: TWO}))[VAR] == ONE
    assert VAR not in manifest_env(LEGACY | {"catalog_write_workspaces": ""}, existing_app(**{VAR: TWO}))
    assert "Behåller" not in capsys.readouterr().out


def test_update_keeps_the_hand_set_list(monkeypatch, tmp_path, capsys):
    cloud = Cloud(**{VAR: ONE})
    (tmp_path / "krusgraph.json").write_text(json.dumps(fa.EXPECTED), encoding="utf-8")
    fa.run_main(monkeypatch, tmp_path, cloud, "--update")
    assert cloud.env()[VAR] == ONE and cloud.env()["KRUSGRAPH_BUILD"] == "src-new"
    assert f"Behåller {VAR}={ONE}" in capsys.readouterr().out
