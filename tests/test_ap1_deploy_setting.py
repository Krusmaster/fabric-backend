"""AP1 (24 November 2026): a deploy keeps KRUSGRAPH_APP_TENANTS, the tenant ids that may open the guided chat at /app
(fabric_backend/guided_app.py). It is set by hand on the container app, so the full run's manifest (which replaces the
whole environment) carries it over like KRUSGRAPH_CATALOG_WRITE_WORKSPACES (W3), deploy/krusgraph.json's "app_tenants"
sets it when filled in, and --update keeps it. `az` is faked; the tenant ids here are invented."""
import json

from deploy import azure_containerapp as d
from fabric_backend import guided_app
from tests import test_deploy_from_azure as fa
from tests.test_n159_operator_flags import LEGACY, Cloud, existing_app, manifest_env

VAR = "KRUSGRAPH_APP_TENANTS"
ONE = "0a0a0a0a-1111-2222-3333-444444444444"


def test_the_variable_is_the_one_the_page_reads():
    assert d.OPERATOR_VALUES["app_tenants"] == VAR == guided_app.ENV


def test_a_full_run_carries_the_hand_set_list(capsys):
    assert manifest_env(LEGACY, existing_app(**{VAR: ONE}))[VAR] == ONE
    assert f'Behåller {VAR}={ONE} som sattes för hand i appen; lägg till "app_tenants"' in capsys.readouterr().out


def test_without_a_value_nothing_is_set_and_the_key_sets_it():
    assert VAR not in manifest_env(LEGACY, existing_app())
    assert manifest_env(LEGACY | {"app_tenants": ONE})[VAR] == ONE


def test_update_keeps_the_hand_set_list(monkeypatch, tmp_path):
    cloud = Cloud(**{VAR: ONE})
    (tmp_path / "krusgraph.json").write_text(json.dumps(fa.EXPECTED), encoding="utf-8")
    fa.run_main(monkeypatch, tmp_path, cloud, "--update")
    assert cloud.env()[VAR] == ONE
