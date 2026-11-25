"""AP2: the doubles behind the writing half of /app (tests/test_ap2_*.py). Invented names and ids only.

The read side is AP1's (tests/ap1_support.py: the hosted app in Entra mode with a test Entra app, the synthetic SAP demo
of tests/wb15_fake.py behind the tools). On top of it, `Workspaces` answers Fabric's and Power BI's REST in memory for
two workspaces: `demo` (w-demo, the source lakehouse demo_lh) and `build` (the founder's way of working: a separate build
workspace with the lakehouse build_lh). It creates the items a Create sends (notebooks, pipelines, semantic models,
reports, data agents, lakehouses), keeps each one's definition, lists them as Fabric does, answers their definitions,
updates them in place, and records every call. A DELETE fails the test: nothing on this path deletes.
"""
from __future__ import annotations

import base64
import json
import uuid
from urllib.parse import parse_qs, urlsplit

import ap1_support as s1

SOURCE_WS = "w-demo"                                            # wb15_fake's source workspace id
BUILD_WS = "6b6b6b6b-1111-2222-3333-444444444444"                # invented: the build workspace
BUILD_LH = "7c7c7c7c-1111-2222-3333-444444444444"                # invented: the build workspace's lakehouse
ROUTE_TYPES = {"notebooks": "Notebook", "dataPipelines": "DataPipeline", "semanticModels": "SemanticModel",
               "reports": "Report", "dataAgents": "DataAgent", "lakehouses": "Lakehouse", "ontologies": "Ontology",
               "graphQLApis": "GraphQLApi"}


class Response:
    def __init__(self, status: int = 200, body=None, headers: dict | None = None):
        self.status_code, self._body = status, body
        self.headers = headers or {"content-type": "application/json"}
        self.text = json.dumps(body) if body is not None else ""
        self.content = self.text.encode()
        self.ok = status < 400

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"{self.status_code} for url", response=self)


class Workspaces:
    """Fabric REST for the two workspaces, in memory. `calls` holds (method, path); `writes` the non-GET calls."""

    def __init__(self, lakehouse_get):
        self.lakehouse_get = lakehouse_get                      # wb15_fake's answer for the source lakehouse
        import wb15_fake
        self.items = {SOURCE_WS: [{"id": wb15_fake.ITEM["id"], "displayName": "demo_lh", "type": "Lakehouse"}],
                      BUILD_WS: [{"id": BUILD_LH, "displayName": "build_lh", "type": "Lakehouse"}]}
        self.definitions: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.unknown: list[tuple[str, str]] = []

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if c[0] != "GET" and not c[1].endswith("/getDefinition")]

    def created(self) -> list[dict]:
        return [it for ws in self.items.values() for it in ws if it.get("made")]

    def _find(self, iid: str) -> dict | None:
        return next((it for ws in self.items.values() for it in ws if it["id"] == iid), None)

    def route(self, method: str, url: str, body=None) -> Response:
        parts = urlsplit(str(url))
        path, query = parts.path, parse_qs(parts.query)
        self.calls.append((method, path))
        if method == "DELETE":
            raise AssertionError(f"AP2: a delete was attempted: {path}")
        if parts.netloc == "api.powerbi.com":                  # the one refresh of a new semantic model
            if method == "POST" and path.endswith("/refreshes"):
                return Response(202, None, {"x-ms-request-id": "r-1", "location": "x"})
            if method == "GET" and path.endswith("/refreshes"):
                return Response(200, {"value": [{"status": "Completed", "refreshType": "ViaApi"}]})
            return Response(200, {"value": []})
        if parts.netloc != "api.fabric.microsoft.com":
            return Response(404, {"errorCode": "NotFound", "message": "no route"})
        seg = [x for x in path.split("/") if x][1:]             # drop v1
        if seg[:1] == ["operations"]:
            return Response(200, {"status": "Succeeded"})
        if method == "GET" and seg == ["workspaces"]:
            return Response(200, {"value": [{"id": SOURCE_WS, "displayName": "demo"}, {"id": BUILD_WS, "displayName": "build"}]})
        if len(seg) < 2 or seg[0] != "workspaces" or seg[1] not in self.items:
            return Response(404, {"errorCode": "WorkspaceNotFound", "message": "The requested workspace was not found"})
        ws, rest = seg[1], seg[2:]
        if method == "GET" and rest == ["items"]:
            want = (query.get("type") or [None])[0]
            return Response(200, {"value": [dict(i) for i in self.items[ws] if want in (None, i["type"])]})
        if method == "GET" and len(rest) == 2 and rest[0] == "lakehouses":
            if ws == SOURCE_WS:
                got = self.lakehouse_get(url).json()
                got.setdefault("properties", {})["oneLakeTablesPath"] = "https://onelake.example/demo/Tables"
                return Response(200, got)
            lh = self._find(rest[1]) or {}
            return Response(200, {"id": rest[1], "displayName": lh.get("displayName", "build_lh"), "type": "Lakehouse",
                                  "properties": {"defaultSchema": "dbo", "oneLakeTablesPath": "https://onelake.example/Tables",
                                                 "sqlEndpointProperties": {"id": "ep-build", "connectionString": "build.example",
                                                                           "provisioningStatus": "Success"}}})
        if method == "GET" and len(rest) == 2 and rest[0] in ("items",) + tuple(ROUTE_TYPES):
            it = self._find(rest[1])
            return Response(200, dict(it)) if it else Response(404, {"errorCode": "ItemNotFound"})
        if method == "GET" and rest[-1:] == ["tables"]:
            return Response(200, {"data": []})
        if method == "GET":
            return Response(200, {"value": []})
        if method == "POST" and len(rest) == 1 and rest[0] in ROUTE_TYPES:
            iid = str(uuid.uuid4())
            it = {"id": iid, "displayName": (body or {}).get("displayName"), "type": ROUTE_TYPES[rest[0]],
                  "description": (body or {}).get("description", ""), "made": True, "workspace": ws}
            self.items[ws].append(it)
            if isinstance((body or {}).get("definition"), dict):
                self.definitions[iid] = body["definition"]
            return Response(201, {"id": iid, "displayName": it["displayName"]})
        if method == "POST" and rest[-1:] == ["getDefinition"]:
            d = self.definitions.get(rest[-2])
            return Response(200, {"definition": d}) if d else Response(404, {"errorCode": "ItemNotFound"})
        if method == "POST" and rest[-1:] == ["updateDefinition"]:
            if isinstance((body or {}).get("definition"), dict):
                self.definitions[rest[-2]] = body["definition"]
            return Response(200, None)
        if method == "PATCH" and len(rest) == 2:
            it = self._find(rest[1])
            if it is None:
                return Response(404, {"errorCode": "ItemNotFound"})
            it.update({k: v for k, v in (body or {}).items() if k in ("description", "displayName")})
            return Response(200, dict(it))
        if method in ("PATCH", "PUT"):                         # a data agent's staging settings and the like
            return Response(200, {})
        if method == "POST":
            return Response(202, None, {"location": "x"}) if "jobs" in rest else Response(200, {})
        self.unknown.append((method, path))
        return Response(404, {"errorCode": "EntityNotFound", "message": f"no route {method} /{'/'.join(rest)}"})

    def get(self, url, headers=None, params=None, timeout=None, **kw):
        return self.route("GET", url)

    def post(self, url, headers=None, json=None, data=None, timeout=None, **kw):
        return self.route("POST", url, json)

    def patch(self, url, headers=None, json=None, params=None, timeout=None, **kw):
        return self.route("PATCH", url, json)

    def put(self, url, headers=None, json=None, **kw):
        return self.route("PUT", url, json)

    def delete(self, url, headers=None, **kw):
        return self.route("DELETE", url)


def data(monkeypatch) -> Workspaces:
    """AP1's synthetic SAP demo behind the tools, with Fabric's REST answered by Workspaces (writes allowed, deletes not),
    both workspaces listed, and no waiting between Fabric's polls."""
    import requests
    import wb15_fake
    from fabric_backend import server
    s1.data(monkeypatch)
    fake = Workspaces(wb15_fake._get)
    for verb in ("get", "post", "patch", "put", "delete"):
        monkeypatch.setattr(requests, verb, getattr(fake, verb))
    monkeypatch.setattr(server, "_workspaces", lambda headers: [{"id": SOURCE_WS, "name": "demo", "capacity_id": "cap-1"},
                                                                {"id": BUILD_WS, "name": "build", "capacity_id": "cap-1"}])
    monkeypatch.setattr(server, "_workspace_id", lambda workspace, headers: BUILD_WS if workspace in ("build", BUILD_WS) else SOURCE_WS)
    monkeypatch.setattr(server, "MODEL_DEFINITION_PAUSES", (0, 0, 0))
    monkeypatch.setattr(server, "MODEL_DEFINITION_PAUSES_LONG", (0, 0, 0))
    from fabric_backend import workload_api
    monkeypatch.setattr(workload_api, "REFRESH_POLL_SECONDS", 0)
    monkeypatch.setattr(server, "_resolve_source", lambda workspace, source, headers: _source(workspace, source))
    return fake


def _source(workspace: str, source: str) -> dict:
    """wb15_fake's demo_lh, with the OneLake path Fabric gives a lakehouse; build_lh in the build workspace."""
    import wb15_fake
    if workspace in ("build", BUILD_WS) or source in ("build_lh", BUILD_LH):
        return {"id": BUILD_LH, "displayName": "build_lh", "type": "Lakehouse", "schemas_enabled": True}
    return {**wb15_fake.ITEM, "onelake_tables_path": f"https://onelake.dfs.fabric.microsoft.com/{SOURCE_WS}/{wb15_fake.ITEM['id']}/Tables"}


def parts_text(definition: dict) -> dict[str, str]:
    return {p["path"]: base64.b64decode(p["payload"]).decode("utf-8", "replace") for p in (definition or {}).get("parts", [])}
