"""A 401/403 from a creating call, told apart by Fabric's own errorCode (round n33).

The bodies are written in Fabric's error shape ({"errorCode", "message"}, Fabric REST "ErrorResponse"). The codes are
the documented ones: InsufficientScopes (learn.microsoft.com/rest/api/fabric/articles/scopes), InsufficientPrivileges
(the item APIs' error responses, learn.microsoft.com/rest/api/fabric/core/items), WorkspaceNotOnCapacity /
CapacityNotActive (already read by errors.py). A feature turned off in the tenant: FeatureNotAvailable, the code Fabric
answered create_ontology with on 28 October 2026, or another code matched by its words; the last body carries a code
nobody here knows.
"""
import json

import pytest

from fabric_backend import server

WHERE = "creating the ontology 'shop_ontology'"
SCOPE = "Item.ReadWrite.All"


def answer(http, body):
    return json.loads(server._finish_create({}, {"status": "Failed", "mode": "created", "http": http, "body": json.dumps(body)},
                                            SCOPE, WHERE))


def test_a_missing_scope_is_consent_with_fabrics_code_and_message():
    out = answer(403, {"errorCode": "InsufficientScopes", "message": "The caller does not have sufficient scopes to perform this operation"})
    assert out["kind"] == "consent" and out["scope"] == SCOPE and SCOPE in out["hint"]
    assert out["fabric_error_code"] == "InsufficientScopes" and "sufficient scopes" in out["fabric_message"]


def test_a_workspace_role_is_no_access_not_consent():
    out = answer(403, {"errorCode": "InsufficientPrivileges", "message": "The caller does not have sufficient permissions to perform this operation"})
    assert out["kind"] == "no_access" and "consent" not in json.dumps(out).lower() and "Contributor" in out["hint"]
    assert out["fabric_error_code"] == "InsufficientPrivileges"


@pytest.mark.parametrize("body", [{"errorCode": "WorkspaceNotOnCapacity", "message": "The workspace is not assigned to a capacity"},
                                  {"errorCode": "CapacityNotActive", "message": "The capacity is paused"}])
def test_no_capacity_is_capacity(body):
    out = answer(403, body)
    assert out["kind"] == "capacity" and out["fabric_error_code"] == body["errorCode"]


def test_a_feature_off_in_the_tenant_is_feature_disabled_and_quotes_fabric():
    out = answer(403, {"errorCode": "FeatureNotAvailable", "message": "The feature is disabled in the tenant settings"})
    assert out["kind"] == "feature_disabled" and "tenant settings" in out["hint"] and "consent" not in out["kind"]
    assert "FeatureNotAvailable" in out["error"] and out["fabric_message"] == "The feature is disabled in the tenant settings"


def test_feature_not_available_is_feature_disabled_by_its_code_alone():
    out = answer(403, {"errorCode": "FeatureNotAvailable", "message": "Forbidden"})
    assert out["kind"] == "feature_disabled" and out["fabric_error_code"] == "FeatureNotAvailable"


def test_an_unknown_code_says_so_and_shows_it():
    out = answer(403, {"errorCode": "SomethingNew", "message": "Forbidden"})
    assert out["kind"] == "fabric_refused" and "does not know: SomethingNew" in out["error"] and "unknown" in out["hint"]
    assert out["fabric_error_code"] == "SomethingNew" and out["fabric_message"] == "Forbidden"


def test_a_401_without_a_code_is_sign_in():
    out = answer(401, {"error": {"code": "TokenExpired", "message": "Access token has expired"}})
    assert out["kind"] == "sign_in" and out["fabric_error_code"] == "TokenExpired"


def test_a_body_that_is_not_json_is_unknown_not_consent():
    out = json.loads(server._finish_create({}, {"status": "Failed", "http": 403, "body": "Forbidden"}, SCOPE, WHERE))
    assert out["kind"] == "fabric_refused" and out["fabric_error_code"] is None and out["fabric_message"] == "Forbidden"
