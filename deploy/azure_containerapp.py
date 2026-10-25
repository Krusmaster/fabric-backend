#!/usr/bin/env python3
"""Deploy the existing Entra app from Cloud Shell. Uses Python's standard library.

Hosting incurs charges. --plan is offline; --check reads Azure without mutations.
--update builds a new image from this checkout and points the existing container app at it; it touches no Entra
settings, secrets, domains or certificates and never asks for the client secret.
No Entra registration, permission, DNS or billing-account changes are made here.

deploy/krusgraph.json (see krusgraph.example.json): tenant_id, subscription_id, client_id, domain, location,
resource_group, environment, app, registry, identity, product_name, contact_email, include_www and the optional
company_orgnr (shown on the privacy page and in the footer when set; leave "" to hide the line).
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
OWNER_TAG = {"managed-by": "krusgraph-deploy"}
REQUIRED_SCOPES = {
    "00000003-0000-0000-c000-000000000000": {"User.Read"},
    "00000009-0000-0000-c000-000000000000": {
        "Workspace.Read.All", "Item.Read.All", "GraphQLApi.ReadWrite.All", "GraphQLApi.Execute.All"},
    "022907d3-0f1b-48f7-badc-1ba6abab6d66": {"user_impersonation"},
}


class DeploymentError(Exception):
    pass


class Azure:
    def __init__(self, config):
        self.config = config
        self.secret = ""

    def run(self, *args, missing_ok=False, raw=False):
        command = ["az", *args, "--only-show-errors", "--output", "none" if raw else "json"]
        if args[0] not in {"ad", "account", "extension"}:
            command += ["--subscription", self.config["subscription_id"]]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            if self.secret:
                detail = detail.replace(self.secret, "[hemlighet dold]")
            if missing_ok and any(code in detail for code in (
                    "ResourceNotFound", "ResourceGroupNotFound", "could not be found", "was not found")):
                return None
            raise DeploymentError(detail[-8000:] or f"Azure-kommandot {args[0]} misslyckades.")
        if raw or not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise DeploymentError(f"Oväntat svar från Azure ({args[0]}).") from exc

    def check_context(self):
        account = self.run("account", "show")
        if account.get("tenantId", "").lower() != self.config["tenant_id"].lower():
            raise DeploymentError("Fel Entra-katalog är vald. Byt till Krusgraphs katalog i Azure och öppna Cloud Shell där.")
        if account.get("id", "").lower() != self.config["subscription_id"].lower():
            raise DeploymentError("Fel prenumeration är vald. Kör: az account set --subscription " + self.config["subscription_id"])
        if account.get("state") != "Enabled":
            raise DeploymentError("Azure-prenumerationen är inte aktiv.")


def check_entra(az, config):
    """Read the registration and grants before creating billable resources."""
    app = az.run("ad", "app", "show", "--id", config["client_id"])
    api = app.get("api") or {}
    if app.get("signInAudience") != "AzureADMultipleOrgs" or api.get("requestedAccessTokenVersion") != 2:
        raise DeploymentError("Appen behöver flera Entra-klientorganisationer och tokenversion 2.")
    if f"https://{config['domain']}/mcp" not in app.get("identifierUris", []):
        raise DeploymentError("Appens program-ID-URI stämmer inte med MCP-adressen.")
    if not any(s.get("value") == "user_impersonation" and s.get("isEnabled")
               for s in api.get("oauth2PermissionScopes", [])):
        raise DeploymentError("Appens user_impersonation-omfång behöver vara aktiverat.")
    grants = az.run("ad", "app", "permission", "list-grants", "--id", config["client_id"])
    requested = {r["resourceAppId"]: r["resourceAccess"] for r in app.get("requiredResourceAccess", [])}
    for resource, scopes in REQUIRED_SCOPES.items():
        sp = az.run("ad", "sp", "show", "--id", resource)
        if not sp.get("accountEnabled"):
            raise DeploymentError(f"Tjänsteappen {sp.get('displayName', resource)} är inaktiverad.")
        scope_ids = {s["value"]: s["id"] for s in sp.get("oauth2PermissionScopes", []) if s.get("isEnabled")}
        configured_ids = {s["id"] for s in requested.get(resource, []) if s.get("type") == "Scope"}
        if not all(scope_ids.get(scope) in configured_ids for scope in scopes):
            raise DeploymentError(f"Behörigheter saknas under {sp['displayName']} i appregistreringen.")
        granted = set()
        for grant in grants:
            if grant.get("resourceId") == sp["id"] and grant.get("consentType") == "AllPrincipals":
                granted.update(grant.get("scope", "").split())
        if not scopes <= granted:
            raise DeploymentError(f"Administratörsmedgivande saknas för {sp['displayName']}: {', '.join(sorted(scopes - granted))}")
    print("Katalog, prenumeration och de sex API-behörigheterna är kontrollerade.", flush=True)


def assert_owned(resource, name):
    if resource and (resource.get("tags") or {}).get("managed-by") != OWNER_TAG["managed-by"]:
        raise DeploymentError(f"{name} finns redan men tillhör inte denna driftsättning. Avbryter utan att ändra resursen.")


def source_tag(root=ROOT):
    files = [root / name for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "README.md")]
    files += sorted(p for p in (root / "fabric_backend").rglob("*")
                    if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts)   # css, js, fonts too
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    return "src-" + digest.hexdigest()[:16]


def plain_env(config, build=None):
    """The non-secret environment of the container, from the config. Both the full run and --update set these.
    `build` is the source tag of the image being deployed; the server reports it on /healthz so the check below
    can tell the new revision from the old one."""
    env = {
        "MCP_PUBLIC_URL": f"https://{config['domain']}/mcp", "ENTRA_CLIENT_ID": config["client_id"],
        "ENTRA_REQUIRED": "true", "PRODUCT_NAME": config["product_name"],
        "CONTACT_EMAIL": config["contact_email"], "COMPANY_ORGNR": (config.get("company_orgnr") or "").strip(),
    }
    if build:
        env["KRUSGRAPH_BUILD"] = build
    return env


def make_manifest(config, env_id, identity_id, login_server, image, secret, existing=None, build=None):
    ingress = {"external": True, "targetPort": 8000, "transport": "http", "allowInsecure": False}
    if existing:
        old_ingress = existing["properties"]["configuration"].get("ingress") or {}
        for name in ("customDomains", "ipSecurityRestrictions", "corsPolicy"):
            if name in old_ingress:
                ingress[name] = old_ingress[name]
    env = [{"name": key, "value": value} for key, value in plain_env(config, build).items()]
    env.append({"name": "ENTRA_CLIENT_SECRET", "secretRef": "entra-secret"})
    return {
        "name": config["app"], "location": config["location"], "tags": OWNER_TAG,
        "identity": {"type": "UserAssigned", "userAssignedIdentities": {identity_id: {}}},
        "properties": {
            "environmentId": env_id, "workloadProfileName": "Consumption",
            "configuration": {"activeRevisionsMode": "Single", "ingress": ingress,
                              "secrets": [{"name": "entra-secret", "value": secret}],
                              "registries": [{"server": login_server, "identity": identity_id}]},
            "template": {
                "revisionSuffix": "r" + uuid.uuid4().hex[:12],
                "containers": [{"name": config["app"], "image": image, "env": env,
                                "resources": {"cpu": 0.25, "memory": "0.5Gi"},
                                "probes": [{"type": kind, "httpGet": {"path": "/healthz", "port": 8000},
                                            "initialDelaySeconds": 10, "periodSeconds": 10,
                                            "timeoutSeconds": 3, "failureThreshold": 12 if kind == "Startup" else 3}
                                           for kind in ("Startup", "Readiness", "Liveness")]}],
                "scale": {"minReplicas": 0, "maxReplicas": 2,
                          "rules": [{"name": "http", "http": {"metadata": {"concurrentRequests": "10"}}}]},
            },
        },
    }


def apply_manifest(az, config, manifest, exists):
    # JSON is valid YAML. Keep the secret out of history, process arguments and the build context.
    fd, filename = tempfile.mkstemp(prefix="krusgraph-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(manifest, out)
        az.run("containerapp", "update" if exists else "create", "--name", config["app"],
               "--resource-group", config["resource_group"], "--yaml", filename, raw=True)
    finally:
        Path(filename).unlink(missing_ok=True)


def http_response(url, method="GET"):
    request = Request(url, data=b"{}" if method == "POST" else None, method=method)
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, response.headers, response.read().decode("utf-8")


def verify_server(base_url, config, build=None):
    """The deployed server answers as the Entra-protected Krusgraph. With `build` (the source tag just deployed),
    the check also waits until /healthz reports that build, so an old revision still answering cannot pass."""
    served = None
    for attempt in range(18):
        try:
            status, _, body = http_response(base_url + "/healthz")
            if status == 200:
                health = json.loads(body)
                if not isinstance(health, dict) or health.get("ok") is not True or health.get("auth") != "entra":
                    raise DeploymentError("Servern svarar men Microsoft-inloggningen är inte aktiverad.")
                served = health.get("build")
                if not build or served == build:
                    break
        except (URLError, TimeoutError, ValueError):
            pass
        if attempt == 17:
            if build and served is not None and served != build:
                raise DeploymentError(f"Servern svarar fortfarande med den gamla bilden ({served or 'utan byggmärke'}, väntade {build}). "
                                      "Kontrollera att den nya revisionen startade i Azure Container Apps.")
            raise DeploymentError("Servern blev inte klar. Kontrollera revisionen i Azure Container Apps och kör om efter rättning.")
        time.sleep(10)
    # Right after an update the old revision can still answer /healthz for a while; wait until the new pages
    # are served instead of failing on the first 404.
    paths = ("/", "/explore", "/start", "/docs", "/privacy", "/demo/plan.json", "/static/site.css",
             "/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp")
    for attempt in range(18):
        failing = None
        for path in paths:
            try:
                status, _, body = http_response(base_url + path)
            except (URLError, TimeoutError):
                status = 0
            if status != 200:
                failing = (path, status)
                break
        if failing is None:
            break
        if attempt == 17:
            raise DeploymentError(f"Kontrollen av {failing[0]} gav HTTP {failing[1]}.")
        time.sleep(10)
    for path in paths:
        status, _, body = http_response(base_url + path)
        if "oauth-protected-resource" in path and json.loads(body).get("resource") != f"https://{config['domain']}/mcp":
            raise DeploymentError("Serverns OAuth-adress stämmer inte med domänen.")
    status, headers, _ = http_response(base_url + "/mcp", "POST")
    if status != 401 or f"https://{config['domain']}/.well-known/oauth-protected-resource" not in headers.get("WWW-Authenticate", ""):
        raise DeploymentError("MCP-kontrollen fick inte det förväntade inloggningskravet.")
    print("Hemsida, dokumentation, sekretessida och MCP-inloggningskrav svarar korrekt.", flush=True)


def dns_records(config, app, environment):
    ip = environment["properties"]["staticIp"]
    props = app["properties"]
    verification = props["customDomainVerificationId"]
    fqdn = props["configuration"]["ingress"]["fqdn"]
    records = [{"type": "A", "host": "@", "value": ip}, {"type": "TXT", "host": "asuid", "value": verification}]
    if config.get("include_www"):
        records += [{"type": "CNAME", "host": "www", "value": fqdn},
                    {"type": "TXT", "host": "asuid.www", "value": verification}]
    return records


def report(az, config, verify=True, first_run=True, build=None):
    app = az.run("containerapp", "show", "-n", config["app"], "-g", config["resource_group"])
    env = az.run("containerapp", "env", "show", "-n", config["environment"], "-g", config["resource_group"])
    url = "https://" + app["properties"]["configuration"]["ingress"]["fqdn"]
    if verify:
        verify_server(url, config, build)
    result = {"preview_url": url, "domain": config["domain"], "dns": dns_records(config, app, env)}
    if build:
        result["build"] = build
    (ROOT / "azure-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")   # git-ignored
    if first_run:
        print("\nSTART KLART – kopiera följande offentliga värden till chatten:")
        print(json.dumps(result, indent=2))
        print("\nNästa steg: lägg in DNS-posterna i Namecheap. Därefter kör du scriptet med --bind-domain.")
    else:
        served = f" med bygget {build}" if build else ""
        print(f"\nKLART: {url} svarar{served}; domänen {config['domain']} är oförändrad. DNS-värdena finns i azure-result.json.")
        if not build:
            print(build_status(url))
    return result


def build_status(url):
    """--status: is the live server built from this checkout? One line, from /healthz and the local source tag."""
    try:
        status, _, body = http_response(url + "/healthz")
        live = json.loads(body).get("build") if status == 200 else None
    except (URLError, TimeoutError, ValueError):
        live = None
    local = source_tag()
    if not live:
        return f"Servern rapporterar inget byggmärke (äldre bild). Denna utcheckning är {local}; kör --update för att driftsätta den."
    if live == local:
        return f"Servern kör bygget {live}, samma som denna utcheckning."
    return f"Servern kör bygget {live}; denna utcheckning är {local}. Kör --update för att driftsätta den."


def deploy(az, config):
    check_entra(az, config)
    show_plan(config)
    if not sys.stdin.isatty() and not os.environ.get("ENTRA_CLIENT_SECRET"):
        raise DeploymentError("Kör i en interaktiv Cloud Shell-terminal så att hemligheten kan anges dolt.")
    secret = os.environ.get("ENTRA_CLIENT_SECRET") or getpass.getpass("Klistra in klienthemlighetens VÄRDE och tryck Enter (texten döljs): ")
    if not secret.strip():
        raise DeploymentError("Ingen klienthemlighet angavs.")
    try:
        uuid.UUID(secret)
    except ValueError:
        pass
    else:
        raise DeploymentError("Det ser ut som ett hemlighets-ID. Använd kolumnen Värde från Entra.")
    az.secret = secret
    print("Förbereder Azure Container Apps…", flush=True)
    az.run("extension", "add", "--name", "containerapp", "--upgrade", "--yes", raw=True)
    for provider in ("Microsoft.CloudShell", "Microsoft.App", "Microsoft.ContainerRegistry", "Microsoft.ManagedIdentity"):
        state = az.run("provider", "show", "--namespace", provider)
        if state.get("registrationState") != "Registered":
            print(f"Aktiverar {provider}…", flush=True)
            az.run("provider", "register", "--namespace", provider, "--wait", raw=True)
    rg = config["resource_group"]
    tags = [f"{key}={value}" for key, value in OWNER_TAG.items()]
    if az.run("group", "exists", "--name", rg):
        assert_owned(az.run("group", "show", "--name", rg), rg)
    else:
        az.run("group", "create", "--name", rg, "--location", config["location"], "--tags", *tags, raw=True)
    registry = az.run("acr", "show", "--name", config["registry"], "--resource-group", rg, missing_ok=True)
    assert_owned(registry, config["registry"])
    if not registry:
        print("Skapar bildregistret (Basic)…", flush=True)
        registry = az.run("acr", "create", "--name", config["registry"], "--resource-group", rg,
                          "--location", config["location"], "--sku", "Basic", "--admin-enabled", "false",
                          "--role-assignment-mode", "rbac", "--tags", *tags)
    if registry.get("roleAssignmentMode") not in (None, "LegacyRegistryPermissions"):
        raise DeploymentError("Registret har en annan behörighetsmodell än denna driftsättning. Kontrollera dess rollinställningar.")
    az.run("acr", "config", "authentication-as-arm", "update", "--registry", config["registry"], "--status", "enabled", raw=True)
    identity = az.run("identity", "show", "--name", config["identity"], "--resource-group", rg, missing_ok=True)
    assert_owned(identity, config["identity"])
    if not identity:
        identity = az.run("identity", "create", "--name", config["identity"], "--resource-group", rg,
                          "--location", config["location"], "--tags", *tags)
    roles = az.run("role", "assignment", "list", "--scope", registry["id"])
    if not any(r.get("principalId") == identity["principalId"] and r.get("roleDefinitionName") == "AcrPull" for r in roles):
        az.run("role", "assignment", "create", "--name", str(uuid.uuid5(uuid.NAMESPACE_URL, registry["id"] + identity["principalId"] + "AcrPull")),
               "--assignee-object-id", identity["principalId"], "--assignee-principal-type", "ServicePrincipal",
               "--role", "AcrPull", "--scope", registry["id"], raw=True)
    tag = source_tag()
    image_uri = build_image(az, config, registry, tag)
    environment = az.run("containerapp", "env", "show", "--name", config["environment"], "--resource-group", rg, missing_ok=True)
    assert_owned(environment, config["environment"])
    if not environment:
        print("Skapar servermiljön i Sweden Central…", flush=True)
        environment = az.run("containerapp", "env", "create", "--name", config["environment"], "--resource-group", rg,
                             "--location", config["location"], "--logs-destination", "none", "--enable-workload-profiles", "true", "--tags", *tags)
    existing = az.run("containerapp", "show", "--name", config["app"], "--resource-group", rg, missing_ok=True)
    assert_owned(existing, config["app"])
    print("Startar hemsidan och MCP-servern…", flush=True)
    manifest = make_manifest(config, environment["id"], identity["id"], registry["loginServer"], image_uri, secret, existing, tag)
    apply_manifest(az, config, manifest, bool(existing))
    manifest["properties"]["configuration"]["secrets"][0].pop("value")
    report(az, config, build=tag)


def build_image(az, config, registry, tag):
    """`az acr build` of this checkout as krusgraph:<tag>; returns the immutable image reference (by digest)."""
    print(f"Bygger servern i Azure ({tag}). Detta kan ta flera minuter…", flush=True)
    az.run("acr", "build", "--registry", config["registry"], "--image", f"krusgraph:{tag}",
           "--file", str(ROOT / "Dockerfile"), "--platform", "linux/amd64", str(ROOT), raw=True)
    image = az.run("acr", "repository", "show", "--name", config["registry"], "--image", f"krusgraph:{tag}")
    return f"{registry['loginServer']}/krusgraph@{image['digest']}"


def update(az, config):
    """New image from this checkout → the existing container app. Nothing else: no Entra, no secrets, no domains,
    no certificates, and the client secret is never requested (the app keeps its secret reference)."""
    rg = config["resource_group"]
    existing = az.run("containerapp", "show", "--name", config["app"], "--resource-group", rg, missing_ok=True)
    if not existing:
        raise DeploymentError("Container-appen finns inte ännu. Kör en full körning (utan flagga) först.")
    assert_owned(existing, config["app"])
    registry = az.run("acr", "show", "--name", config["registry"], "--resource-group", rg, missing_ok=True)
    if not registry:
        raise DeploymentError("Bildregistret finns inte. Kör en full körning (utan flagga) först.")
    assert_owned(registry, config["registry"])
    az.run("extension", "add", "--name", "containerapp", "--upgrade", "--yes", raw=True)     # no interactive install prompt later
    tag = source_tag()
    image_uri = build_image(az, config, registry, tag)
    print("Uppdaterar container-appen till den nya bilden…", flush=True)
    env_args = [f"{key}={value}" for key, value in plain_env(config, tag).items()]     # KEY= sets an empty value; the server treats it as unset
    az.run("containerapp", "update", "--name", config["app"], "--resource-group", rg, "--image", image_uri,
           "--revision-suffix", "r" + uuid.uuid4().hex[:12], "--set-env-vars", *env_args, raw=True)
    report(az, config, first_run=False, build=tag)


def bind_domains(az, config):
    rg = config["resource_group"]
    app = az.run("containerapp", "show", "--name", config["app"], "--resource-group", rg)
    assert_owned(app, config["app"])
    existing = {d["name"]: d for d in app["properties"]["configuration"]["ingress"].get("customDomains") or []}
    domains = [(config["domain"], "HTTP")]
    if config.get("include_www"):
        domains.append(("www." + config["domain"], "CNAME"))
    for domain, method in domains:
        if domain not in existing:
            az.run("containerapp", "hostname", "add", "--hostname", domain, "--name", config["app"], "--resource-group", rg, raw=True)
        if existing.get(domain, {}).get("bindingType") != "SniEnabled":
            print(f"Verifierar {domain} och beställer HTTPS-certifikat…", flush=True)
            az.run("containerapp", "hostname", "bind", "--hostname", domain, "--name", config["app"], "--resource-group", rg,
                   "--environment", config["environment"], "--validation-method", method, raw=True)
        verify_server("https://" + domain, config)
    print(f"\nDomänen är ansluten: https://{config['domain']}\nMCP: https://{config['domain']}/mcp")


def show_plan(config):
    print(f"\nKrusgraph i {config['location']}: {config['resource_group']}")
    print("Container Apps Consumption, 0–2 instanser, 0,25 CPU och 0,5 GiB per instans.")
    print("Bildregister Basic: cirka 5 USD/månad. Byggen, trafik och serveranvändning kan tillkomma.")
    print("Beloppen beror på ditt Azure-avtal och eventuell skatt. Ingen Fabric-kapacitet eller databas skapas.")
    print(f"Befintlig Entra-app: {config['client_id']}\nPlanerad adress: https://{config['domain']}\n", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("krusgraph.json"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Visa resurser och kostnadsbild utan Azure-anrop")
    mode.add_argument("--check", action="store_true", help="Kontrollera katalog och Entra-behörigheter utan att skapa resurser")
    mode.add_argument("--status", action="store_true", help="Visa serveradress och DNS-poster igen")
    mode.add_argument("--bind-domain", action="store_true", help="Anslut domänen efter att DNS-posterna har lagts in")
    mode.add_argument("--update", action="store_true", help="Bygg en ny bild av denna utcheckning och uppdatera den befintliga appen (rör inte Entra, hemligheter eller domäner)")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.plan:
        show_plan(config)
        return
    az = Azure(config)
    try:
        az.check_context()
        if args.check:
            check_entra(az, config)
        elif args.status:
            report(az, config, first_run=False)
        elif args.bind_domain:
            bind_domains(az, config)
        elif args.update:
            update(az, config)
        else:
            deploy(az, config)
    except (DeploymentError, FileNotFoundError) as exc:
        message = str(exc).replace(az.secret, "[hemlighet dold]") if az.secret else str(exc)
        print("\nSTOPP: " + message, file=sys.stderr)
        print("Resurser som redan skapats finns kvar. Spara felmeddelandet; samma paket kan köras igen.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAvbrutet. Redan skapade Azure-resurser finns kvar.", file=sys.stderr)
        sys.exit(130)
    finally:
        az.secret = ""


if __name__ == "__main__":
    main()
