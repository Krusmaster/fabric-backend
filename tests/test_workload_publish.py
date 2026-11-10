"""Round n176: Krusgraph.Modeler, the permanent workload name, for up to 20 selected tenants.

The package builds as Org.Krusgraph (default) or Krusgraph.Modeler and refuses every other Krusgraph.* name; the item type
follows the name (Krusgraph.Modeler.Model) and is written once, by the build. The server accepts tokens for every URI in
KRUSGRAPH_WORKLOAD_APP_ID_URI (a comma list while both names run) and gives a tenant outside the allowed list a plain
refusal, not a sign-in loop. The pilot page renders and lists the administrator's steps in order. Docs and site only
describe; nothing here uploads, consents or calls Entra or Fabric."""
import importlib.util
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WL_ID = "99999999-8888-7777-6666-555555555555"


def _builder():
    spec = importlib.util.spec_from_file_location("build_package_n176", ROOT / "workload/scripts/build_package.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------ the package names --------------------------------

def _read(pkg: Path) -> dict[str, str]:
    with zipfile.ZipFile(pkg) as z:
        return {n: z.read(n).decode("utf-8", "replace") for n in z.namelist() if n.endswith((".xml", ".json", ".nuspec", ".rels"))}


@pytest.mark.parametrize("args, name", [
    ([], "Org.Krusgraph"),
    (["--name", "Org.Krusgraph"], "Org.Krusgraph"),
    (["--name", "Krusgraph.Modeler"], "Krusgraph.Modeler"),
])
def test_the_package_takes_its_name_from_the_build(tmp_path, args, name):
    run = subprocess.run(["bash", str(ROOT / "workload/scripts/build-package"), "--frontend-app-id", WL_ID, "--version", "1.0.9",
                          "--out", str(tmp_path), *args], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert f"item type {name}.Model" in run.stdout and "Nothing was uploaded" in run.stdout
    assert ("cannot be undone" in run.stdout) == (name == "Krusgraph.Modeler")
    files = _read(tmp_path / f"{name}.1.0.9.nupkg")
    assert f'WorkloadName="{name}"' in files["BE/WorkloadManifest.xml"]
    assert f'<Item TypeName="{name}.Model"' in files["BE/ModelItem.xml"] and f'WorkloadName="{name}"' in files["BE/ModelItem.xml"]
    assert f"<id>{name}</id>" in files[f"{name}.nuspec"]
    product = json.loads(files["FE/Product.json"])
    assert product["createExperience"]["cards"][0]["itemType"] == "Model"            # Fabric adds the workload part
    other = "Org.Krusgraph" if name == "Krusgraph.Modeler" else "Krusgraph.Modeler"
    for path, text in files.items():
        assert "{{" not in text and other not in text, path


def test_the_name_is_written_once_in_the_sources():
    """The manifests carry the placeholder only; build_package.py is the one place the two names are written."""
    for p in (ROOT / "workload/Workload/Manifest").rglob("*"):
        if p.suffix in (".xml", ".json", ".nuspec"):
            text = p.read_text(encoding="utf-8-sig")
            assert "Org.Krusgraph" not in text and "Krusgraph.Modeler" not in text, p
    item = (ROOT / "workload/Workload/Manifest/items/ModelItem/ModelItem.xml").read_text()
    assert 'TypeName="{{WORKLOAD_NAME}}.Model"' in item
    b = _builder()
    assert b.item_type("Krusgraph.Modeler") == "Krusgraph.Modeler.Model" and b.item_type("Org.Krusgraph") == "Org.Krusgraph.Model"


@pytest.mark.parametrize("name, word", [
    ("Krusgraph.Model", "reserve it in the tenant for good"),
    ("Krusgraph.Modeller", "reserve it in the tenant for good"),
    ("krusgraph.modeler", "reserve it in the tenant for good"),                     # the exact spelling only
    ("Krusgraph.Modeler.Model", "reserve it in the tenant for good"),
    ("Org.Other", "must be Org.Krusgraph or Krusgraph.Modeler"),
    ("", "must be Org.Krusgraph or Krusgraph.Modeler"),
])
def test_every_other_name_is_refused_before_anything_is_written(tmp_path, name, word):
    b = _builder()
    with pytest.raises(b.PackageError, match=word):
        b.build(WL_ID, "1.0.1", out_dir=tmp_path, name=name)
    assert not list(tmp_path.glob("*.nupkg"))
    run = subprocess.run(["bash", str(ROOT / "workload/scripts/build-package"), "--frontend-app-id", WL_ID, "--version", "1.0.1",
                          "--out", str(tmp_path), "--name", name], capture_output=True, text=True)
    assert run.returncode == 1 and "STOP" in run.stderr


def test_a_stray_workload_name_in_a_manifest_file_stops_the_build(tmp_path):
    import shutil
    b = _builder()
    for stray in ("Org.Krusgraph", "Krusgraph.Other"):
        manifest = tmp_path / stray / "Manifest"
        shutil.copytree(ROOT / "workload/Workload/Manifest", manifest)
        item = manifest / "items/ModelItem/ModelItem.json"
        item.write_text(item.read_text().replace('"name": "Model"', f'"name": "Model", "note": "{stray}.Model"'))
        with pytest.raises(b.PackageError, match="names"):
            b.build(WL_ID, "1.0.1", out_dir=tmp_path / "out", manifest=manifest, name="Krusgraph.Modeler")


def test_the_hosted_editor_reads_the_workload_from_the_item():
    """One editor build for both names: the worker and the engine scope follow the item type, not WORKLOAD_NAME alone."""
    app = ROOT / "workload/Workload/app"
    worker = (app / "index.worker.ts").read_text(encoding="utf-8")
    assert "sampleWorkloadName" not in worker and worker.count("workloadOf(createdItem.itemType)") == 3
    assert "rememberWorkloadOf(got.item.type)" in (app / "items/ModelItem/ModelItemEditor.tsx").read_text(encoding="utf-8")
    assert "getWorkloadName()" in (app / "items/ModelItem/engineClient.ts").read_text(encoding="utf-8")


# ------------------------------------------------------------------ the server: both URIs, allowed tenants -----------

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from fabric_backend import entra, server, workload_api, workload_host  # noqa: E402
from fabric_backend.entra import EntraConfig, TenantNotAllowed, TokenError, Validator, WorkloadConfig  # noqa: E402

TID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER = "12121212-3434-5656-7878-909090909090"
DEV_URI = "https://krusgraph.com/workload/workload/Org.Krusgraph"
PUB_URI = "https://krusgraph.com/workload/workload/Krusgraph.Modeler"
ENV = {"KRUSGRAPH_WORKLOAD_CLIENT_ID": WL_ID, "KRUSGRAPH_WORKLOAD_CLIENT_SECRET": "wl-secret",
       "KRUSGRAPH_WORKLOAD_APP_ID_URI": f"{DEV_URI}, {PUB_URI}/", "KRUSGRAPH_WORKLOAD_ALLOWED_TENANTS": f" {TID.upper()} "}


class FakeJWKS:
    def __init__(self, key):
        self.key = key

    def get_signing_key_from_jwt(self, token):
        return type("K", (), {"key": self.key})()


@pytest.fixture(scope="module")
def keys():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def tok(priv, tid=TID, **over):
    claims = {"aud": PUB_URI, "iss": f"https://login.microsoftonline.com/{tid}/v2.0", "tid": tid,
              "exp": int(time.time()) + 600, "scp": "user_impersonation", "oid": "user-1"}
    claims.update(over)
    return jwt.encode(claims, priv, algorithm="RS256")


@pytest.fixture
def cfg(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    return WorkloadConfig.from_env()


def test_the_app_id_uri_setting_is_a_list(cfg):
    assert cfg.app_id_uris == [DEV_URI, PUB_URI] and cfg.app_id_uri == DEV_URI         # the first stays the primary one
    assert cfg.audiences == [DEV_URI, PUB_URI, WL_ID, f"api://{WL_ID}"]
    assert cfg.allowed_tenants == {TID}
    assert entra.split_uris(f"{PUB_URI} {PUB_URI}/,,{DEV_URI}") == [PUB_URI, DEV_URI]
    one = WorkloadConfig(WL_ID, "s", DEV_URI + "/")                                    # the one-URI form is unchanged
    assert one.app_id_uris == [DEV_URI] and one.app_id_uri == DEV_URI


def test_both_audiences_are_accepted_and_no_other(keys, cfg):
    priv, pub = keys
    v = Validator(cfg, FakeJWKS(pub))
    for aud in (DEV_URI, PUB_URI, WL_ID):
        assert v.validate(tok(priv, aud=aud))["tid"] == TID
    for aud in ("https://krusgraph.com/workload/workload/Krusgraph.Other", "https://krusgraph.com/mcp", "api://someone-else"):
        with pytest.raises(TokenError) as e:
            v.validate(tok(priv, aud=aud))
        assert not isinstance(e.value, TenantNotAllowed)


def test_the_mcp_app_cannot_hide_in_the_list(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_APP_ID_URI", f"{PUB_URI},https://krusgraph.com/mcp")
    with pytest.raises(ValueError, match="own Entra app"):
        WorkloadConfig.from_env(EntraConfig("https://krusgraph.com/mcp", "11111111-2222-3333-4444-555555555555", "x"))
    monkeypatch.setenv("KRUSGRAPH_WORKLOAD_APP_ID_URI", " , ")
    with pytest.raises(ValueError, match="names no URI"):
        WorkloadConfig.from_env()


def test_a_tenant_outside_the_list_gets_a_plain_refusal(keys, cfg, monkeypatch):
    from starlette.applications import Starlette
    priv, pub = keys
    v = Validator(cfg, FakeJWKS(pub))
    with pytest.raises(TenantNotAllowed) as e:
        v.validate(tok(priv, tid=OTHER))
    assert e.value.tenant == OTHER and isinstance(e.value, TokenError)                # /mcp still treats it as before
    monkeypatch.setattr(server, "limiter", None)

    class NoOBO:
        def token(self, *a):
            raise AssertionError("no exchange for a refused tenant")

    c = TestClient(Starlette(routes=workload_api.routes(cfg, v, NoOBO())))
    r = c.post(workload_api.PREFIX + "/review", json={}, headers={"Authorization": f"Bearer {tok(priv, tid=OTHER)}",
                                                                   "Origin": "https://app.fabric.microsoft.com"})
    assert r.status_code == 403 and "www-authenticate" not in r.headers                 # not a sign-in prompt
    body = r.json()
    assert body["kind"] == "tenant_not_allowed" and body["tenant"] == OTHER
    assert body["error"] == "Krusgraph is not turned on for your organisation yet."
    assert OTHER in body["hint"] and "/pilot/fabric" in body["hint"] and "Nothing was read or changed" in body["hint"]
    assert TID not in json.dumps(body)                                                  # never names another tenant
    r = c.post(workload_api.PREFIX + "/review", json={}, headers={"Authorization": f"Bearer {tok(priv, aud='api://x')}",
                                                                   "Origin": "https://app.fabric.microsoft.com"})
    assert r.status_code == 401 and r.json()["kind"] == "sign_in"                      # a bad token is still a sign-in


def test_the_editor_page_lists_every_scope(monkeypatch, tmp_path):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    assert workload_host.engine_scopes() == [f"{DEV_URI}/user_impersonation", f"{PUB_URI}/user_impersonation"]
    assert workload_host.engine_scope() == f"{DEV_URI}/user_impersonation"
    (tmp_path / "index.html").write_text("<html><head><title>x</title></head><body></body></html>", encoding="utf-8")
    page = workload_host.Editor(tmp_path).index().decode()
    assert f'<meta name="krusgraph-engine-scope" content="{DEV_URI}/user_impersonation">' in page
    assert (f'<meta name="krusgraph-engine-scopes" content="{DEV_URI}/user_impersonation {PUB_URI}/user_impersonation">'
            in page)


# ------------------------------------------------------------------ the pilot page and the docs ----------------------

@pytest.fixture
def site(monkeypatch):
    monkeypatch.setenv("PRODUCT_NAME", "Krusgraph")
    monkeypatch.setenv("MCP_PUBLIC_URL", "https://krusgraph.test/mcp")
    monkeypatch.setenv("CONTACT_EMAIL", "hello@krusgraph.test")
    monkeypatch.setenv("ENTRA_CLIENT_ID", "cid-123")
    with TestClient(server.build_app()) as c:
        yield c


STEPS = ["tenant-id", "tenant-setting", "consent", "network", "new-item"]


def test_the_pilot_page_lists_the_steps_in_order(site):
    r = site.get("/pilot/fabric")
    assert r.status_code == 200
    page = r.text
    positions = [page.index(f'id="{s}"') for s in STEPS]
    assert positions == sorted(positions)
    for words in ("Users can see and work with additional workloads not validated by Microsoft",
                  "adminconsent?client_id=853a0cf0-7d35-42b7-b384-26178755a72a", "&lt;your tenant id&gt;",
                  "<code>krusgraph.com</code>", "<code>workload.krusgraph.com</code>", "port 443",
                  "+ New item → Krusgraph Model", "synthetic", "not affiliated with Microsoft", "hello@krusgraph.test"):
        assert words in page, words
    assert '<a href="/pilot/fabric">' in site.get("/partners").text


def test_the_pilot_page_and_docs_make_no_speed_or_compliance_claims(site):
    texts = [re.sub(r"<[^>]+>", " ", site.get("/pilot/fabric").text.split("<main", 1)[-1].split("<footer", 1)[0]),
             (ROOT / "docs/PILOT-ONBOARDING.md").read_text(encoding="utf-8")]
    banned = ("faster", "minutes to", "in seconds", "compliant", "gdpr", "iso 27001", "certified", "secure by", "seamless",
              "effortless", "guarantee", "endorsed", "partner of microsoft", "validated by microsoft.")
    for text in texts:
        low = text.lower()
        for word in banned:
            assert word not in low, word
    pilot_ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", " ".join(texts))
    assert set(pilot_ids) <= {"853a0cf0-7d35-42b7-b384-26178755a72a"}                  # the app id only, no tenant ids


def test_the_publish_doc_has_the_founders_steps_in_order():
    doc = (ROOT / "docs/WORKLOAD-PUBLISH.md").read_text(encoding="utf-8")
    # n195: the runbook's steps 0-8 first (tests/test_n195_attestation.py), n176's detail after them as A1-A4
    order = ["## Step 1. The name-registration blocker", "## Step 2. Publisher verification", "## Step 3. Upload Krusgraph.Modeler",
             "## Step 4. Microsoft's test tenant", "## Step 8. The submission form", "## A1. Entra", "## A2. The server",
             "## A3. Upload Krusgraph.Modeler", "## A4. Publish", "## Adding the next pilot", "## Withdrawing", "## Decision"]
    at = [doc.index(h) for h in order]
    assert at == sorted(at)
    for words in ("Confirm workload Name", "cannot be undone", "Selected tenants", "--name Krusgraph.Modeler",
                  "https://krusgraph.com/workload/workload/Krusgraph.Modeler", "workloadSignIn/$TENANT/Krusgraph.Modeler",
                  "msit.fabric.microsoft.com", "workload_allowed_tenants", "not turned on for your organisation yet",
                  "Recommendation: keep the existing app"):
        assert words in doc, words
    assert doc.count("**Check on first run") + doc.count("check on first run") >= 5
    # the az lines keep what is there: the current lists are read and added to, never replaced from scratch
    assert '--query "spa.redirectUris[]"' in doc and '--query "identifierUris[]"' in doc


def test_contributing_names_the_one_allowed_krusgraph_name():
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Krusgraph.Modeler" in text and "docs/WORKLOAD-PUBLISH.md" in text
