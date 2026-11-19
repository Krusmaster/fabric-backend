"""FA1: app_readiness for a semantic model, before an app is built from it in Power BI Desktop for Apps (model_readiness.py)."""
import json

from fabric_backend import model_readiness as mr, seed, semantic_model as sm, server
from fabric_backend.infer import plan

WS = "11111111-1111-1111-1111-111111111111"


def _shop_parts() -> dict[str, str]:
    return sm.draft(plan(seed.schema("shop")), {"endpoint": "x", "database": "lh"}, "shop_model")["parts"]


def _by(out: dict) -> dict:
    return {c["check"]: c for c in out["checks"]}


def test_a_krusgraph_model_passes_what_microsoft_learn_states():
    out = mr.assess(_shop_parts(), "shop_model")
    by = _by(out)
    for name in ("hosted", "tables", "measures", "format_strings", "relationships", "keys", "date_table"):
        assert by[name]["status"] == "ok", (name, by[name])
    assert by["date_table"]["detail"] == "marked: Calendar"
    assert out["missing"] == []
    assert out["unknown"] == ["permissions", "tenant_settings", "workspace_capacity"]
    assert out["verdict"].startswith("7 check(s) pass; 3 cannot be read")
    assert out["next_step"]["title"] == "Build an app in Power BI Desktop for Apps"
    assert out["next_step"]["url"] == "https://learn.microsoft.com/power-bi/create-reports/desktop-for-apps/overview"


def test_every_check_says_its_basis_and_cites_learn_when_it_is_microsofts():
    for c in mr.assess(_shop_parts(), "shop_model")["checks"]:
        assert c["basis"] in ("microsoft_learn", "krusgraph", "not_documented")
        assert c["reason"] and "\n" not in c["reason"]
        if c["basis"] == "microsoft_learn":
            assert c["source"].startswith("https://learn.microsoft.com/")
        if c["basis"] == "krusgraph":
            assert c["source"] == ""
    by = _by(mr.assess(_shop_parts(), "shop_model"))
    assert by["prep_data_for_ai"]["status"] == "info" and "do not say" in by["prep_data_for_ai"]["reason"]
    assert by["descriptions"]["status"] == "info"


def test_a_bare_model_names_what_is_missing():
    parts = {
        "definition/tables/Sales.tmdl": "table Sales\n\tcolumn Amount\n\t\tdataType: decimal\n\tcolumn OrderDate\n\t\tdataType: dateTime\n"
                                         "\tmeasure Total = SUM(Sales[Amount])\n",
        "definition/tables/Customer.tmdl": "/// People who buy\ntable Customer\n\tcolumn Name\n\t\tdataType: string\n",
        "definition/roles/North.tmdl": "role North\n\tmodelPermission: read\n",
    }
    out = mr.assess(parts, "bare", hosted=False)
    by = _by(out)
    assert by["hosted"]["status"] == "info" and "Publish the model" in by["hosted"]["next_step"]
    assert by["format_strings"]["status"] == "missing" and by["format_strings"]["detail"] == "no format string: Sales[Total]"
    assert by["relationships"]["status"] == "missing" and "Customer, Sales" in by["relationships"]["detail"]
    assert by["keys"]["status"] == "info"
    assert by["date_table"]["status"] == "info" and "Sales[OrderDate]" in by["date_table"]["detail"]
    assert by["descriptions"]["detail"] == "1 of 2 table(s) and 0 of 1 measure(s) have a description"
    assert by["row_level_security"]["detail"] == "1 role(s): North"
    assert out["missing"] == ["format_strings", "relationships"]


def test_an_empty_definition_misses_tables_and_measures():
    out = mr.assess({}, "empty", hosted=False)
    assert out["missing"] == ["tables", "measures"]


def test_the_tool_reads_the_model_with_getdefinition(monkeypatch):
    monkeypatch.setattr(server, "_headers", lambda ctx: {"Authorization": "Bearer test-only"})
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: WS)
    monkeypatch.setattr(server, "find_item_by_name", lambda ws, name, headers, types=None:
                        {"id": "model-1"} if name == "shop_model" and types == ("SemanticModel",) else None)
    asked = {}

    def parts(ws, kind, item_id, headers, fmt=None):
        asked.update(ws=ws, kind=kind, item=item_id, fmt=fmt)
        return _shop_parts()
    monkeypatch.setattr(server, "_item_definition_parts", parts)
    out = json.loads(server.app_readiness("Sales", semantic_model="shop_model"))
    assert asked == {"ws": WS, "kind": "semanticModels", "item": "model-1", "fmt": "TMDL"}
    assert out["read_with"] == "Fabric getDefinition (TMDL)" and out["missing"] == []
    assert json.loads(server.app_readiness("Sales", semantic_model="nope"))["kind"] == "not_found"


def test_the_tool_asks_for_an_api_or_a_model():
    out = json.loads(server.app_readiness("Sales"))
    assert out["kind"] == "bad_input" and "semantic_model" in out["error"]
