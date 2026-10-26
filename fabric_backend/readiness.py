"""What an app still needs before it can use a created API for GraphQL item: the checks behind app_readiness.

Everything here is computed from the API's own definition (describe_definition's output) and the result of one
introspection probe; the server does the HTTP. Where Fabric offers no way to read a setting (item permissions, the
tenant setting for service principals: no route in microsoft/fabric-rest-api-specs as read on 26 October 2026) the
check says "unknown" and names the portal path, instead of guessing.
"""
from __future__ import annotations

INTROSPECTION_QUERY = "{ __schema { queryType { name } } }"


def classify_probe(status: int, body) -> dict:
    """The introspection probe's answer as on / off / unknown with the reason."""
    if status in (401, 403):
        return {"status": "unknown", "detail": f"HTTP {status}: the signed-in account may not run queries on this API, so introspection could not be probed"}
    if status >= 400:
        return {"status": "unknown", "detail": f"HTTP {status} from the endpoint"}
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict) and data.get("__schema"):
        return {"status": "on", "detail": "an introspection query answered"}
    errors = body.get("errors") if isinstance(body, dict) else None
    first = ""
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        first = str(errors[0].get("message", ""))[:200]
    return {"status": "off", "detail": first or "the endpoint answered without __schema"}


def assess(description: dict, probe: dict, endpoint: str, api: str) -> dict:
    """Checks with status ok / missing / unknown / info and a next step each, plus a one-line verdict."""
    types = description.get("types", [])
    keyless = [t["type"] for t in types if not t.get("by_key")]
    unlinked = [t["type"] for t in types if not t.get("relationships")] if len(types) > 1 else []
    writable = [t["type"] for t in types if t.get("writable")]
    checks = [
        {"check": "api", "status": "ok" if types else "missing",
         "detail": f"{len(types)} type(s) in the definition" if types else "the API has no types",
         "next_step": "" if types else "create_backend with the tables the app needs"},
        {"check": "introspection", "status": {"on": "ok", "off": "missing"}.get(probe.get("status"), "unknown"),
         "detail": probe.get("detail", ""),
         "next_step": "" if probe.get("status") == "on" else
         f"{api} -> Settings (gear) -> Introspection -> turn on -> Confirm. A workspace admin does this in the portal; Fabric has no "
         "REST route for it (microsoft/fabric-rest-api-specs, read 26 October 2026). Schema-aware builders need it; an app that sends "
         "the queries from app_starter does not."},
        {"check": "permissions", "status": "unknown",
         "detail": "Fabric exposes no REST route to read who may run queries on an item (spec read 26 October 2026)",
         "next_step": f"{api} -> Manage permissions: the app's identity needs 'Run Queries and Mutations' (a service principal, or the users "
                      "when the app signs them in). A service principal also needs the tenant setting 'Service principals can use Fabric APIs' "
                      "(Admin portal -> Tenant settings -> Developer settings) and read access to the data source when the API uses single sign-on."},
        {"check": "keys", "status": "missing" if keyless else "ok",
         "detail": ("no key: " + ", ".join(keyless)) if keyless else "every type can be fetched by key",
         "next_step": ("these types can be listed but not fetched by key and nothing can relate to them; pass `keys` to create_backend to change that"
                       if keyless else "")},
        {"check": "relationships", "status": "info" if unlinked else "ok",
         "detail": ("in no relationship: " + ", ".join(unlinked)) if unlinked else "every type is linked to at least one other",
         "next_step": ("suggest_relationships ranks the candidates and checks them against the data; pass the one you accept as `confirmed` to create_backend"
                       if unlinked else "")},
        {"check": "write_access", "status": "info",
         "detail": ("writable: " + ", ".join(writable)) if writable else "read-only API (no create/update/delete)",
         "next_step": "" if not writable else "the app's identity needs write permission on the data source too"},
    ]
    missing = [c["check"] for c in checks if c["status"] == "missing"]
    unknown = [c["check"] for c in checks if c["status"] == "unknown"]
    ok = [c["check"] for c in checks if c["status"] == "ok"]
    verdict = (f"{len(ok)} check(s) pass; " + (f"{len(missing)} need a step ({', '.join(missing)}); " if missing else "")
               + f"{len(unknown)} cannot be read through the API ({', '.join(unknown)}): confirm in the portal")
    return {"api": api, "endpoint": endpoint, "checks": checks, "missing": missing, "unknown": unknown, "verdict": verdict,
            "note": "Computed from the API's definition and one introspection query; unit-tested, not yet run against a live workspace."}
