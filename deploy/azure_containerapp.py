#!/usr/bin/env python3
"""Deploy the existing Entra app from Cloud Shell. Uses Python's standard library.

Hosting incurs charges. --plan is offline; --check reads Azure without mutations.
--update builds a new image from this checkout and points the existing container app at it; it touches no Entra
settings, secrets, domains or certificates and never asks for the client secret.
No Entra registration, permission, DNS or billing-account changes are made here.

deploy/krusgraph.json (see krusgraph.example.json): tenant_id, subscription_id, client_id, domain, location,
resource_group, environment, app, registry, identity, product_name, contact_email, include_www and the optional
company_orgnr (shown on the privacy page and in the footer when set; leave "" to hide the line), key_vault (the name of
a Key Vault for the client secret, read only by --key-vault; leave "" to keep the secret in the container app) and
log_retention_days (0 while console logs go nowhere; the number of days once they go to Log Analytics, which also
turns off the access line with IP addresses; docs/OPERATIONS.md).

--key-vault moves the client secret into Azure Key Vault: it creates the vault (RBAC, tagged like everything else) if
it does not exist, asks for the secret's value once (hidden), stores it there, gives the container app's identity
"Key Vault Secrets User" on that vault, and points the app at it (ENTRA_CLIENT_SECRET_KEYVAULT_URI, AZURE_CLIENT_ID).
The old secret stays in the container app until you remove it yourself after checking; docs/OPERATIONS.md has the
two commands. Nothing is deleted.

--client-redirects prints the az commands that add Claude Code's, VS Code's and Cursor's redirect addresses to the app as
a public client, and how to try each client (docs/OPERATIONS.md, section 5). It runs nothing and calls nothing.

--client-registration prints the commands that switch on client registration for VS Code, Cursor, Glama and other MCP
clients (fabric_backend/registration.py): the one web redirect address the server's /oauth needs on the Entra app, a
storage account with one table, the server's key, the environment variables, and how to check and to switch it off. It
runs nothing and calls nothing (docs/OPERATIONS.md, section 6).

--from-azure builds that configuration from the container app that already runs, for a Cloud Shell without storage
where deploy/krusgraph.json is missing: the tenant and subscription from `az account show`, the app whose name contains
"krusgraph" (or --app / --resource-group), and the rest from the app's plain environment variables, scale, registry,
environment, identity, custom domains and resource group. It shows the result and writes deploy/krusgraph.json only
when the file is missing (--overwrite-config replaces one). No secret is read, written or shown. With --update the
image and its build tag are all that change: not min_replicas, not another environment variable. When the app is not
in the selected subscription, the others are searched and the run stops with the `az account set` command to use.
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
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import uuid

ROOT = Path(__file__).resolve().parents[1]
OWNER_TAG = {"managed-by": "krusgraph-deploy"}
REQUIRED_SCOPES = {
    "00000003-0000-0000-c000-000000000000": {"User.Read"},
    "00000009-0000-0000-c000-000000000000": {
        "Workspace.Read.All", "Item.Read.All", "GraphQLApi.ReadWrite.All", "GraphQLApi.Execute.All",
        "Notebook.ReadWrite.All", "DataPipeline.ReadWrite.All", "Item.ReadWrite.All"},
    "022907d3-0f1b-48f7-badc-1ba6abab6d66": {"user_impersonation"},
}


class DeploymentError(Exception):
    pass


class Azure:
    def __init__(self, config):
        self.config = config
        self.secret = ""

    def run(self, *args, missing_ok=False, raw=False, subscription=None):
        command = ["az", *args, "--only-show-errors", "--output", "none" if raw else "json"]
        if args[0] not in {"ad", "account", "extension"}:
            command += ["--subscription", subscription or self.config["subscription_id"]]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            if self.secret:
                detail = detail.replace(self.secret, "[hemlighet dold]")
            if missing_ok and any(code in detail for code in (
                    "ResourceNotFound", "ResourceGroupNotFound", "could not be found", "was not found", "not found within")):
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
    print("Katalog, prenumeration och de nio API-behörigheterna är kontrollerade.", flush=True)


def assert_owned(resource, name):
    if resource and (resource.get("tags") or {}).get("managed-by") != OWNER_TAG["managed-by"]:
        raise DeploymentError(f"{name} finns redan men tillhör inte denna driftsättning. Avbryter utan att ändra resursen.")


def source_tag(root=ROOT):
    files = [root / name for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "README.md", "deploy/constraints.txt")]
    files += sorted(p for p in (root / "fabric_backend").rglob("*")
                    if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts)   # css, js, fonts too
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    return "src-" + digest.hexdigest()[:16]


KEY_VAULT_SECRET = "entra-client-secret"


def key_vault_uri(config):
    """The versionless secret URI the server reads (fabric_backend/keyvault.py), or "" without a key_vault."""
    name = (config.get("key_vault") or "").strip()
    return f"https://{name}.vault.azure.net/secrets/{KEY_VAULT_SECRET}" if name else ""


KEY_VAULT_ENV = ("ENTRA_CLIENT_SECRET_KEYVAULT_URI", "AZURE_CLIENT_ID")
# Client registration (--client-registration) is switched on by hand in the app; a full run keeps these plain settings.
# KRUSGRAPH_REGISTRATION_KEY as a container app secret is not kept (the manifest replaces the secrets): the layer then
# stays off, says so on stderr, and Claude's sign-in is unaffected.
REGISTRATION_ENV = ("KRUSGRAPH_CLIENT_REGISTRATION", "KRUSGRAPH_CLIENT_REGISTRATION_DCR", "KRUSGRAPH_REGISTRATION_STORE",
                    "KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI", "KRUSGRAPH_REGISTRATION_CLIENT_DOMAINS",
                    "KRUSGRAPH_REGISTRATION_RATE_IP", "KRUSGRAPH_REGISTRATION_RATE_CLIENT", "KRUSGRAPH_REGISTRATION_RATE_REGISTER")


def plain_env(config, build=None):
    """The non-secret environment of the container, from the config. Both the full run and --update set these.
    `build` is the source tag of the image being deployed; the server reports it on /healthz so the check below
    can tell the new revision from the old one. The Key Vault settings are not here: only --key-vault sets them, after
    the secret is stored, and the other runs keep what the app has (a key_vault in the config alone changes nothing)."""
    env = {
        "MCP_PUBLIC_URL": f"https://{config['domain']}/mcp", "ENTRA_CLIENT_ID": config["client_id"],
        "ENTRA_REQUIRED": "true", "PRODUCT_NAME": config["product_name"],
        "CONTACT_EMAIL": config["contact_email"], "COMPANY_ORGNR": (config.get("company_orgnr") or "").strip(),
    }
    if build:
        env["KRUSGRAPH_BUILD"] = build
    if config.get("ontology_write"):          # offers create_ontology; only useful once the Entra app holds Item.ReadWrite.All
        env["KRUSGRAPH_ONTOLOGY_WRITE"] = "1"
    days = int(config.get("log_retention_days") or 0)
    if days:                                  # console logs are kept in Log Analytics: say so on /privacy, keep no IP addresses
        env["KRUSGRAPH_LOG_RETENTION_DAYS"] = str(days)
        env["KRUSGRAPH_ACCESS_LOG"] = "0"
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
    if existing:                              # keep the Key Vault and registration settings; the manifest replaces the whole list
        old_env = ((existing.get("properties") or {}).get("template") or {}).get("containers", [{}])[0].get("env") or []
        env += [e for e in old_env if e.get("name") in KEY_VAULT_ENV + REGISTRATION_ENV and e.get("value")]
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
                                "probes": probes()}],
                "scale": {"minReplicas": min_replicas(config), "maxReplicas": 2,
                          "rules": [{"name": "http", "http": {"metadata": {"concurrentRequests": "10"}}}]},
            },
        },
    }


def min_replicas(config) -> int:
    """0 = scale to zero when idle (cheapest; the first request after a quiet spell waits for a cold start).
    1 = always one warm instance, so MCP clients that give up after ~30 s never see a cold start."""
    value = int(config.get("min_replicas", 0))
    if value not in (0, 1, 2):
        raise DeploymentError("min_replicas ska vara 0, 1 eller 2.")
    return value


def probes():
    """Probe /healthz quickly after start so a scaled-from-zero instance takes traffic in seconds, not after 10–20 s."""
    timing = {"Startup": (1, 2, 60), "Readiness": (1, 5, 3), "Liveness": (10, 10, 3)}
    return [{"type": kind, "httpGet": {"path": "/healthz", "port": 8000}, "initialDelaySeconds": delay,
             "periodSeconds": period, "timeoutSeconds": 3, "failureThreshold": failures}
            for kind, (delay, period, failures) in timing.items()]


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


def update(az, config, keep_settings=False):
    """New image from this checkout → the existing container app. Nothing else: no Entra, no secrets, no domains,
    no certificates, and the client secret is never requested (the app keeps its secret reference).
    With keep_settings (--from-azure: the configuration was read from this app) the image and KRUSGRAPH_BUILD are all
    that change; min_replicas and the other environment variables are not sent, so they stay as the app has them."""
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
    # --set-env-vars adds and replaces only these; the Key Vault settings --key-vault made stay as they are
    env_args = [f"{key}={value}" for key, value in plain_env(config, tag).items()]     # KEY= sets an empty value; the server treats it as unset
    scale = ["--min-replicas", str(min_replicas(config))]
    if keep_settings:
        env_args, scale = [f"KRUSGRAPH_BUILD={tag}"], []
    az.run("containerapp", "update", "--name", config["app"], "--resource-group", rg, "--image", image_uri,
           "--revision-suffix", "r" + uuid.uuid4().hex[:12], *scale, "--set-env-vars", *env_args, raw=True)
    report(az, config, first_run=False, build=tag)


def move_secret_to_key_vault(az, config):
    """--key-vault: the client secret in Azure Key Vault, read by the container app's own identity. Creates the vault
    when it is missing (never touches one that is not ours), stores the secret, grants the roles, sets the two
    environment variables. Rerunnable; deletes nothing; the old container-app secret stays until removed by hand."""
    name = (config.get("key_vault") or "").strip()
    if not name:
        raise DeploymentError("Ange key_vault (namnet på ett Key Vault) i deploy/krusgraph.json först.")
    rg = config["resource_group"]
    app = az.run("containerapp", "show", "--name", config["app"], "--resource-group", rg, missing_ok=True)
    if not app:
        raise DeploymentError("Container-appen finns inte ännu. Kör en full körning (utan flagga) först.")
    assert_owned(app, config["app"])
    identity = az.run("identity", "show", "--name", config["identity"], "--resource-group", rg)
    state = az.run("provider", "show", "--namespace", "Microsoft.KeyVault")
    if state.get("registrationState") != "Registered":
        print("Aktiverar Microsoft.KeyVault…", flush=True)
        az.run("provider", "register", "--namespace", "Microsoft.KeyVault", "--wait", raw=True)
    vault = az.run("keyvault", "show", "--name", name, "--resource-group", rg, missing_ok=True)
    assert_owned(vault, name)
    if not vault:
        print(f"Skapar Key Vault {name} (RBAC-behörigheter)…", flush=True)
        vault = az.run("keyvault", "create", "--name", name, "--resource-group", rg, "--location", config["location"],
                       "--enable-rbac-authorization", "true", "--tags", *[f"{k}={v}" for k, v in OWNER_TAG.items()])
    if not (vault.get("properties") or {}).get("enableRbacAuthorization", True):
        raise DeploymentError("Key Vault använder åtkomstprinciper i stället för RBAC. Använd ett annat namn eller slå på RBAC.")
    me = az.run("ad", "signed-in-user", "show")
    grant(az, vault["id"], me["id"], "User", "Key Vault Secrets Officer")              # so this run may write the secret
    grant(az, vault["id"], identity["principalId"], "ServicePrincipal", "Key Vault Secrets User")   # so the app may read it
    if not sys.stdin.isatty() and not os.environ.get("ENTRA_CLIENT_SECRET"):
        raise DeploymentError("Kör i en interaktiv Cloud Shell-terminal så att hemligheten kan anges dolt.")
    secret = os.environ.get("ENTRA_CLIENT_SECRET") or getpass.getpass("Klistra in klienthemlighetens VÄRDE och tryck Enter (texten döljs): ")
    if not secret.strip():
        raise DeploymentError("Ingen klienthemlighet angavs.")
    az.secret = secret
    fd, filename = tempfile.mkstemp(prefix="krusgraph-", suffix=".txt")       # the value never appears in a process argument
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(secret)
        for attempt in range(12):                                           # a new role assignment takes a minute or two to apply
            try:
                az.run("keyvault", "secret", "set", "--vault-name", name, "--name", KEY_VAULT_SECRET, "--file", filename,
                       "--encoding", "utf-8", raw=True)
                break
            except DeploymentError as exc:
                if attempt == 11 or "Forbidden" not in str(exc):
                    raise
                print("Väntar på att rollen Key Vault Secrets Officer ska gälla…", flush=True)
                time.sleep(15)
    finally:
        Path(filename).unlink(missing_ok=True)
    print("Hemligheten är sparad i Key Vault. Pekar appen dit…", flush=True)
    az.run("containerapp", "update", "--name", config["app"], "--resource-group", rg, "--revision-suffix", "r" + uuid.uuid4().hex[:12],
           "--set-env-vars", f"ENTRA_CLIENT_SECRET_KEYVAULT_URI={key_vault_uri(config)}", f"AZURE_CLIENT_ID={identity['clientId']}", raw=True)
    report(az, config, first_run=False)
    print("Appen läser nu klienthemligheten från Key Vault. När inloggningen fungerar: ta bort den gamla hemligheten ur "
          "container-appen med de två kommandona i docs/OPERATIONS.md (avsnittet Key Vault).", flush=True)


def grant(az, scope, principal_id, principal_type, role):
    """A role assignment at `scope`, once (a deterministic name makes a rerun a no-op)."""
    roles = az.run("role", "assignment", "list", "--scope", scope, "--assignee", principal_id) or []
    if any(r.get("roleDefinitionName") == role for r in roles):
        return
    az.run("role", "assignment", "create", "--name", str(uuid.uuid5(uuid.NAMESPACE_URL, scope + principal_id + role)),
           "--assignee-object-id", principal_id, "--assignee-principal-type", principal_type, "--role", role, "--scope", scope, raw=True)


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


# Redirect addresses for MCP clients that sign in to a remote server themselves (round n12; sources in
# docs/OPERATIONS.md, "More MCP clients"). On Entra the port of an http://localhost redirect address is ignored
# (entra-docs reply-url.md), so one address covers a client's random or fixed port; they are public clients (PKCE, no
# secret), so they belong under publicClient, never under web next to claude.ai's callback.
CLIENT_REDIRECTS = {
    "Claude Code": ["http://localhost/callback"],          # http://localhost:<port>/callback; --callback-port fixes the port
    "VS Code (GitHub Copilot agent mode)": ["http://localhost"],   # MSAL's loopback, http://localhost:<random port>
    "Cursor": ["http://localhost/callback"],               # http://localhost:8787/callback (desktop)
}
CLIENT_REDIRECTS_OPTIONAL = {
    "Cursor, äldre versioner": "cursor://anysphere.cursor-mcp/oauth/callback",
    "VS Code på Windows med kontomäklaren (WAM)": "ms-appx-web://Microsoft.AAD.BrokerPlugin/{client_id}",
}


def client_redirects(config) -> str:
    """The az commands that add the MCP clients' redirect addresses to the existing app, and how to try each client.
    Printed only: nothing is run, nothing is read from Azure."""
    app_id, mcp = config["client_id"], f"https://{config['domain']}/mcp"
    needed = sorted({u for us in CLIENT_REDIRECTS.values() for u in us})
    lines = [
        "# Kör själv i Cloud Shell (bash). Inget av detta körs av skriptet.",
        f'APP_ID="{app_id}"',
        "",
        "# 1. Läs vad appen har i dag (ändrar inget).",
        'az ad app show --id "$APP_ID" --query "{web:web.redirectUris, publicClient:publicClient.redirectUris, fallback:isFallbackPublicClient}"',
        "",
        "# 2. Lägg till klienternas adresser som offentlig klient. --public-client-redirect-uris ersätter hela listan, så den",
        "#    befintliga listan läses först och slås ihop; går läsningen fel ändras ingenting. Rör inte --web-redirect-uris",
        "#    (där ligger claude.ai:s adress).",
        "NEW=(" + " ".join(f'"{u}"' for u in needed) + ")",
        "# Valfritt: " + "; ".join(f"{k}: {v.format(client_id=app_id)}" for k, v in CLIENT_REDIRECTS_OPTIONAL.items()),
        'if CUR=$(az ad app show --id "$APP_ID" --query "publicClient.redirectUris[]" -o tsv); then',
        '  mapfile -t ALL < <({ printf \'%s\\n\' "$CUR"; printf \'%s\\n\' "${NEW[@]}"; } | grep -v \'^$\' | sort -u)',
        '  az ad app update --id "$APP_ID" --public-client-redirect-uris "${ALL[@]}"',
        "else",
        '  echo "Kunde inte läsa appens lista; inget ändrades."',
        "fi",
        "",
        "# 3. Kontrollera: webblistan oförändrad, de nya adresserna under publicClient, fallback fortfarande false/null.",
        'az ad app show --id "$APP_ID" --query "{web:web.redirectUris, publicClient:publicClient.redirectUris, fallback:isFallbackPublicClient}"',
        "",
        "# 4. Prova varje klient (offentlig klient: ingen hemlighet ges ut).",
        f"#    Claude Code:  claude mcp add --transport http --client-id $APP_ID --callback-port 8080 krusgraph {mcp}",
        "#                  claude mcp login krusgraph   (eller /mcp i en session), sedan: Which Fabric workspaces can I see?",
        "#    VS Code:      .vscode/mcp.json eller MCP: Open User Configuration:",
        f'#                  {{"servers": {{"krusgraph": {{"type": "http", "url": "{mcp}", "oauth": {{"clientId": "{app_id}"}}}}}}}}',
        "#                  MCP: List Servers -> krusgraph -> Start, logga in; i Copilot agent mode: Which Fabric workspaces can I see?",
        "#    Cursor:       ~/.cursor/mcp.json:",
        f'#                  {{"mcpServers": {{"krusgraph": {{"url": "{mcp}", "auth": {{"CLIENT_ID": "{app_id}"}}}}}}}}',
        "#                  logga in från Cursors MCP-inställningar och kontrollera redirect_uri i adressen som öppnas.",
        "#    Skriv resultatet i docs/LIVE-TEST.md (avsnittet om klienter). Sajten fortsätter säga Claude tills dess.",
    ]
    return "\n".join(lines) + "\n"


REGISTRATION_TABLE = "krusgraphoauth"
REGISTRATION_KEY_SECRET = "krusgraph-registration-key"


def registration_storage_account(config) -> str:
    """registration_storage_account from the config, else st + the app's name + 6 hex of the subscription and group
    (storage account names are global, 3 to 24 lower-case letters and digits)."""
    name = (config.get("registration_storage_account") or "").strip().lower()
    if name:
        return name
    stem = "".join(c for c in config["app"].lower() if c.isalnum())[:14]
    return "st" + stem + hashlib.sha256(f"{config['subscription_id']}/{config['resource_group']}".encode()).hexdigest()[:6]


def client_registration(config) -> str:
    """The commands that switch on client registration (fabric_backend/registration.py) for the app in the config.
    Printed only: nothing is run, nothing is read from Azure. Entra: one web redirect address is added, merged into the
    list that holds claude.ai's; scopes, publicClient and everything else on the app are left alone."""
    domain, vault = config["domain"], (config.get("key_vault") or "").strip()
    callback = f"https://{domain}/oauth/callback"
    if vault:
        key_lines = [
            f'az keyvault secret set --vault-name "{vault}" --name {REGISTRATION_KEY_SECRET} --value "$(openssl rand -base64 32)" --output none',
            f'KEYENV="KRUSGRAPH_REGISTRATION_KEY_KEYVAULT_URI=https://{vault}.vault.azure.net/secrets/{REGISTRATION_KEY_SECRET}"',
            "#    (appens identitet har redan rollen Key Vault Secrets User på valvet sedan --key-vault)",
        ]
    else:
        key_lines = [
            'az containerapp secret set -n "$APP" -g "$RG" --secrets registration-key="$(openssl rand -base64 32)" --output none',
            'KEYENV="KRUSGRAPH_REGISTRATION_KEY=secretref:registration-key"',
            "#    (en full körning av skriptet, inte --update, tar bort den hemligheten; lagret stängs då av tills steg 3-4 körs igen.",
            "#    Med key_vault i deploy/krusgraph.json läggs nyckeln i valvet i stället och följer med.)",
        ]
    lines = [
        "# Kör själv i Cloud Shell (bash). Inget av detta körs av skriptet. Claudes inloggning ändras inte av något steg.",
        f'APP_ID="{config["client_id"]}"; RG="{config["resource_group"]}"; APP="{config["app"]}"; LOC="{config["location"]}"',
        f'IDENTITY="{config["identity"]}"; ST="{registration_storage_account(config)}"; TABLE="{REGISTRATION_TABLE}"',
        "",
        "# 1. Entra: serverns egen svarsadress under Web, där claude.ai:s adress redan ligger. --web-redirect-uris ersätter",
        "#    hela listan, så den befintliga läses först och slås ihop; går läsningen fel ändras ingenting. Rör inte scopes",
        "#    eller --public-client-redirect-uris.",
        'az ad app show --id "$APP_ID" --query "{web:web.redirectUris, publicClient:publicClient.redirectUris}"',
        f'NEW="{callback}"',
        'if CUR=$(az ad app show --id "$APP_ID" --query "web.redirectUris[]" -o tsv); then',
        '  mapfile -t ALL < <({ printf \'%s\\n\' "$CUR"; printf \'%s\\n\' "$NEW"; } | grep -v \'^$\' | sort -u)',
        '  az ad app update --id "$APP_ID" --web-redirect-uris "${ALL[@]}"',
        "else",
        '  echo "Kunde inte läsa appens lista; inget ändrades."',
        "fi",
        'az ad app show --id "$APP_ID" --query "web.redirectUris"     # claude.ai:s adress ska stå kvar, och den nya',
        "",
        "# 2. Lagring: ett lagringskonto (Standard_LRS, inga delade nycklar, ingen publik åtkomst) med en tabell, och rätten",
        "#    för appens identitet att läsa och skriva just den tabellen. Kostnad: per användning, öre i månaden vid väntad volym.",
        'az storage account create -n "$ST" -g "$RG" -l "$LOC" --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \\',
        '  --allow-blob-public-access false --allow-shared-key-access false --tags managed-by=krusgraph-deploy --output none',
        'STID=$(az storage account show -n "$ST" -g "$RG" --query id -o tsv)',
        'az rest --method put --url "https://management.azure.com$STID/tableServices/default/tables/$TABLE?api-version=2023-05-01" --body "{}" --output none',
        'PRINCIPAL=$(az identity show -n "$IDENTITY" -g "$RG" --query principalId -o tsv)',
        'az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal \\',
        '  --role "Storage Table Data Contributor" --scope "$STID/tableServices/default/tables/$TABLE" --output none',
        "",
        "# 3. Serverns nyckel: 32 slumpade byte som bara servern känner. Värdet visas aldrig.",
        *key_lines,
        "",
        "# 4. Slå på (en ny revision). En ofullständig inställning lämnar lagret avstängt och säger varför i loggen.",
        'CLIENT=$(az identity show -n "$IDENTITY" -g "$RG" --query clientId -o tsv)',
        'az containerapp update -n "$APP" -g "$RG" --set-env-vars KRUSGRAPH_CLIENT_REGISTRATION=1 KRUSGRAPH_CLIENT_REGISTRATION_DCR=1 \\',
        '  "KRUSGRAPH_REGISTRATION_STORE=https://$ST.table.core.windows.net/$TABLE" "$KEYENV" "AZURE_CLIENT_ID=$CLIENT" --output none',
        "",
        "# 5. Kontrollera.",
        f"curl -s https://{domain}/.well-known/oauth-authorization-server/oauth      # issuer https://{domain}/oauth",
        f"curl -s https://{domain}/.well-known/oauth-protected-resource             # oförändrad: Entra, som i dag (Claude)",
        f"curl -si https://{domain}/mcp/connect | grep -i www-authenticate          # .../oauth-protected-resource/mcp/connect",
        "",
        "# 6. Prova med testkontot (docs/OPERATIONS.md, avsnitt 6). Adressen för alla klienter utom Claude:",
        f"#    https://{domain}/mcp/connect",
        "",
        "# Stänga av igen (Claude påverkas inte):",
        'az containerapp update -n "$APP" -g "$RG" --set-env-vars KRUSGRAPH_CLIENT_REGISTRATION=0 --output none',
    ]
    return "\n".join(lines) + "\n"


CONTAINER_APPS = "Microsoft.App/containerApps"
REQUIRED_APP_ENV = ("ENTRA_CLIENT_ID", "MCP_PUBLIC_URL", "PRODUCT_NAME", "CONTACT_EMAIL")


def _last(resource_id):
    return (resource_id or "").rstrip("/").split("/")[-1]


def _group_of(resource_id):
    parts = (resource_id or "").split("/")
    lowered = [p.lower() for p in parts]
    return parts[lowered.index("resourcegroups") + 1] if "resourcegroups" in lowered[:-1] else ""


def find_app(az, account, app=None, resource_group=None):
    """--from-azure: the container app to read, in the selected subscription: the one named --app, or the one whose
    name contains "krusgraph". Not there: the user's other subscriptions are listed one by one, and the run stops with
    the `az account set` command to use. The subscription is never changed here."""
    def matches(resource):
        name = resource.get("name", "").lower()
        if (app and name != app.lower()) or (not app and "krusgraph" not in name):
            return False
        return not resource_group or resource.get("resourceGroup", "").lower() == resource_group.lower()

    here = [r for r in az.run("resource", "list", "--resource-type", CONTAINER_APPS) or [] if matches(r)]
    if len(here) == 1:
        return here[0]
    if here:
        raise DeploymentError("Flera container-appar passar: " + ", ".join(f"{r['name']} ({r['resourceGroup']})" for r in here)
                              + ". Ange vilken med --app och --resource-group.")
    elsewhere = []
    for sub in az.run("account", "list") or []:
        if sub.get("id", "").lower() == account["id"].lower():
            continue
        try:
            found = az.run("resource", "list", "--resource-type", CONTAINER_APPS, subscription=sub["id"]) or []
        except DeploymentError:          # a subscription this account may not list is not where the app runs
            continue
        elsewhere += [(sub, r) for r in found if matches(r)]
    wanted = f"container-appen {app}" if app else "någon container-app med krusgraph i namnet"
    if not elsewhere:
        raise DeploymentError(f"Hittade inte {wanted} i någon av dina prenumerationer. Heter den något annat: ange --app och --resource-group.")
    lines = [f"Hittade inte {wanted} i den valda prenumerationen {account.get('name', '')} ({account['id']}). Den finns här:"]
    for sub, r in elsewhere:
        lines += [f"  {r['name']} i {r['resourceGroup']}, prenumerationen {sub.get('name', '')} ({sub['id']}). Byt till den med:",
                  f"  az account set --subscription {sub['id']}"]
    lines.append("Kör sedan samma kommando igen. Skriptet byter inte prenumeration själv.")
    raise DeploymentError("\n".join(lines))


def config_from_azure(az, app=None, resource_group=None):
    """--from-azure: the fields of deploy/krusgraph.json, read from the container app that already runs. Only names, ids
    and plain environment variables are read: `az containerapp show` lists the secrets' names, never their values, and a
    variable that refers to a secret is skipped."""
    account = az.run("account", "show")
    az.config = {"subscription_id": account["id"]}
    found = find_app(az, account, app, resource_group)
    rg = found["resourceGroup"]
    live = az.run("containerapp", "show", "--name", found["name"], "--resource-group", rg)
    name = live.get("name") or found["name"]
    props = live.get("properties") or {}
    configuration, template = props.get("configuration") or {}, props.get("template") or {}
    containers = template.get("containers") or [{}]
    container = next((c for c in containers if c.get("name") == name), containers[0])
    env = {e["name"]: e.get("value") or "" for e in container.get("env") or [] if not e.get("secretRef")}
    missing = [key for key in REQUIRED_APP_ENV if not env.get(key)]
    if missing:
        raise DeploymentError(f"Container-appen {name} saknar {', '.join(missing)}, så konfigurationen kan inte läsas ur den. "
                              "Utgå från deploy/krusgraph.example.json.")
    image_host = (container.get("image") or "").split("/")[0]
    registries = configuration.get("registries") or [{}]
    registry = next((r for r in registries if r.get("server") == image_host), registries[0])
    identities = list((live.get("identity") or {}).get("userAssignedIdentities") or {})
    identity = next((i for i in identities if i.lower() == (registry.get("identity") or "").lower()), identities[0] if identities else "")
    environment = props.get("environmentId") or props.get("managedEnvironmentId") or ""
    if not (registry.get("server") and identity and environment):
        raise DeploymentError(f"Container-appen {name} saknar bildregister, användartilldelad identitet eller miljö; den är inte gjord av denna driftsättning.")
    for what, resource_id in (("Container Apps-miljön", environment), ("Identiteten", identity)):
        if _group_of(resource_id).lower() != rg.lower():
            raise DeploymentError(f"{what} {_last(resource_id)} ligger i en annan resursgrupp än appen; denna driftsättning förutsätter en enda.")
    domain = urlparse(env["MCP_PUBLIC_URL"]).hostname or ""
    domains = {d.get("name", "").lower() for d in (configuration.get("ingress") or {}).get("customDomains") or []}
    vault = urlparse(env.get("ENTRA_CLIENT_SECRET_KEYVAULT_URI", "")).hostname or ""
    days = env.get("KRUSGRAPH_LOG_RETENTION_DAYS", "").strip()
    return {
        "tenant_id": account["tenantId"], "subscription_id": account["id"], "client_id": env["ENTRA_CLIENT_ID"],
        "domain": domain, "location": az.run("group", "show", "--name", rg)["location"], "resource_group": rg,
        "environment": _last(environment), "app": name, "registry": registry["server"].split(".")[0],
        "identity": _last(identity), "product_name": env["PRODUCT_NAME"], "contact_email": env["CONTACT_EMAIL"],
        "company_orgnr": env.get("COMPANY_ORGNR", ""), "include_www": "www." + domain.lower() in domains,
        "min_replicas": int((template.get("scale") or {}).get("minReplicas") or 0),
        "ontology_write": env.get("KRUSGRAPH_ONTOLOGY_WRITE", "").lower() in {"1", "true", "yes"},
        "key_vault": vault.split(".")[0], "log_retention_days": int(days) if days.isdigit() else 0,
    }


def save_config(path, config, overwrite=False):
    """deploy/krusgraph.json from --from-azure: written when it is missing, or with --overwrite-config. An existing file
    is left byte for byte as it is, and the fields where it differs from the app are named."""
    print(f"\nKonfiguration läst ur container-appen {config['app']} ({config['resource_group']}):")
    print(json.dumps(config, indent=2, ensure_ascii=False), flush=True)
    if path.exists() and not overwrite:
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            old = {}
        differs = [key for key in config if old.get(key) != config[key]]
        print(f"{path} finns redan och skrevs inte över"
              + (f"; den skiljer sig från appen i {', '.join(differs)}." if differs else "; den stämmer med appen.")
              + " Denna körning använder appens värden; --overwrite-config ersätter filen.", flush=True)
        return False
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Sparade {path} (ignoreras av git).", flush=True)
    return True


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
    mode.add_argument("--key-vault", action="store_true", help="Flytta klienthemligheten till Azure Key Vault (valfritt; tar inte bort något)")
    mode.add_argument("--client-redirects", action="store_true",
                      help="Skriv ut az-kommandona som lägger till Claude Code, VS Code och Cursor som klienter (kör inget, inga Azure-anrop)")
    mode.add_argument("--client-registration", action="store_true",
                      help="Skriv ut kommandona som slår på klientregistrering för VS Code, Cursor och Glama (kör inget, inga Azure-anrop)")
    parser.add_argument("--from-azure", action="store_true",
                        help="Bygg konfigurationen ur den container-app som redan kör, när deploy/krusgraph.json saknas; "
                             "ensam sparar den filen, med --update (eller --check, --status) körs det steget sedan med den")
    parser.add_argument("--app", help="Med --from-azure: container-appens namn (annars den vars namn innehåller krusgraph)")
    parser.add_argument("--resource-group", help="Med --from-azure: appens resursgrupp")
    parser.add_argument("--overwrite-config", action="store_true", help="Med --from-azure: ersätt en befintlig deploy/krusgraph.json")
    args = parser.parse_args()
    if args.from_azure and (args.plan or args.client_redirects or args.client_registration):
        parser.error("--from-azure läser Azure; --plan, --client-redirects och --client-registration gör inga Azure-anrop.")
    if not args.from_azure and (args.app or args.resource_group or args.overwrite_config):
        parser.error("--app, --resource-group och --overwrite-config hör till --from-azure.")
    if not args.from_azure and not args.config.exists():
        print(f"STOPP: {args.config} saknas. Kör med --from-azure för att bygga den ur den körande appen "
              "(bash deploy/krusgraph.sh --from-azure --update), eller utgå från deploy/krusgraph.example.json.", file=sys.stderr)
        sys.exit(1)
    config = {} if args.from_azure else json.loads(args.config.read_text(encoding="utf-8"))
    if args.plan:
        show_plan(config)
        return
    if args.client_redirects:
        print(client_redirects(config), end="")
        return
    if args.client_registration:
        print(client_registration(config), end="")
        return
    az = Azure(config)
    try:
        if args.from_azure:
            config = config_from_azure(az, args.app, args.resource_group)
            save_config(args.config, config, args.overwrite_config)
            az.config = config
            if not (args.check or args.status or args.bind_domain or args.update or args.key_vault):
                return
        az.check_context()
        if args.check:
            check_entra(az, config)
        elif args.status:
            report(az, config, first_run=False)
        elif args.bind_domain:
            bind_domains(az, config)
        elif args.update:
            update(az, config, keep_settings=args.from_azure)
        elif args.key_vault:
            move_secret_to_key_vault(az, config)
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
