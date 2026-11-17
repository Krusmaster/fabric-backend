#!/usr/bin/env python3
"""CD1 (16 November 2026): the parts of the automatic deployment (.github/workflows/deploy.yml) that are not
`bash deploy/krusgraph.sh --from-azure --update` itself. Standard library only, like azure_containerapp.py, whose
functions it reuses so the health checks are the same ones --update runs.

    gate                                         are the repository variables there and the switch on? (no Azure call)
    snapshot --app A --resource-group G          the running image, build and revision, before the update
    rollback --app A --resource-group G --image I [--build B]
                                                 point the app back at that image and check it the way --update does

The workflow runs `snapshot`, then --update (which builds in Azure, updates the app and checks the home page, docs,
privacy page, the MCP login requirement and the build at /healthz), and `rollback` only when that step failed.
docs/AUTO-DEPLOY.md has the one-time setup.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import azure_containerapp as aca  # noqa: E402

# The repository variables the workflow needs; none of them is a secret (GitHub's OIDC token replaces a client secret).
REQUIRED_VARIABLES = ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID", "KRUSGRAPH_RESOURCE_GROUP",
                      "KRUSGRAPH_APP")
SWITCH = "KRUSGRAPH_AUTO_DEPLOY"


IDS = ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_SUBSCRIPTION_ID")
# The gate's outputs: the cleaned values the deploy job uses instead of the raw variables (DP1).
OUTPUTS = {"AZURE_CLIENT_ID": "client_id", "AZURE_TENANT_ID": "tenant_id", "AZURE_SUBSCRIPTION_ID": "subscription_id",
           "KRUSGRAPH_RESOURCE_GROUP": "resource_group", "KRUSGRAPH_APP": "app"}
GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class GateError(Exception):
    """A variable is set but cannot be right; the gate job fails instead of going dormant."""


def gate(env) -> tuple[bool, str]:
    """(go, reason). Dormant until every variable exists and the switch is "on"; anything else is a clean no-op.
    DP1: surrounding spaces and line breaks are removed from every value. A space or line break inside a value, or an
    id that is not a GUID, raises GateError naming the variable (never its value)."""
    missing = [name for name in REQUIRED_VARIABLES if not (env.get(name) or "").strip()]
    if missing:
        return False, ("Automatic deployment is not set up (missing repository variables: " + ", ".join(missing)
                       + "). Nothing was deployed. See docs/AUTO-DEPLOY.md.")
    switch = (env.get(SWITCH) or "").strip().lower()
    if switch != "on":
        return False, f"Automatic deployment is switched off ({SWITCH}={switch or 'unset'}). Nothing was deployed."
    values(env)
    return True, "Automatic deployment is on."


def values(env) -> dict:
    """The required variables with surrounding whitespace removed, checked as gate() describes."""
    cleaned, wrong = {}, []
    for name in REQUIRED_VARIABLES:
        text = (env.get(name) or "").strip()
        if any(ch.isspace() or not ch.isprintable() for ch in text):
            wrong.append(f"{name} contains a space, tab or line break inside the value")
        elif name in IDS and not GUID.fullmatch(text):
            wrong.append(f"{name} is not a GUID (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)")
        cleaned[name] = text
    if wrong:
        raise GateError("Automatic deployment stopped before any Azure call: " + "; ".join(wrong)
                        + ". Edit the repository variable (Settings -> Secrets and variables -> Actions -> Variables) and "
                        "paste the value again without spaces or line breaks. See docs/AUTO-DEPLOY.md, step 3.")
    return cleaned


def _container(app: dict) -> dict:
    template = (app.get("properties") or {}).get("template") or {}
    containers = template.get("containers") or [{}]
    return next((c for c in containers if c.get("name") == app.get("name")), containers[0])


def describe(app: dict) -> dict:
    """What a rollback needs from `az containerapp show`: the image (by digest), the build at /healthz, the revision,
    the address --update checks, and the domain its OAuth checks expect."""
    props = app.get("properties") or {}
    env = aca.app_env(app)
    return {
        "image": _container(app).get("image") or "",
        "build": env.get("KRUSGRAPH_BUILD", ""),
        "revision": props.get("latestReadyRevisionName") or props.get("latestRevisionName") or "",
        "fqdn": ((props.get("configuration") or {}).get("ingress") or {}).get("fqdn") or "",
        "domain": urlparse(env.get("MCP_PUBLIC_URL", "")).hostname or "",
    }


def _azure() -> aca.Azure:
    az = aca.Azure({})
    az.config = {"subscription_id": az.run("account", "show")["id"]}
    return az


def _show(az, app, rg) -> dict:
    found = az.run("containerapp", "show", "--name", app, "--resource-group", rg, missing_ok=True)
    if not found:
        raise aca.DeploymentError(f"The container app {app} was not found in {rg}.")
    aca.assert_owned(found, app)
    return found


def _output(values: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            for key, value in values.items():
                fh.write(f"{key}={value}\n")


def snapshot(az, app, rg) -> dict:
    state = describe(_show(az, app, rg))
    if not state["image"]:
        raise aca.DeploymentError("The container app has no image; there is nothing to roll back to.")
    return state


def rollback(az, app, rg, image, build="") -> str:
    """Back to `image` (and KRUSGRAPH_BUILD=`build`) unless the app already runs it, then the checks of --update. Only
    the image and KRUSGRAPH_BUILD change, as with --from-azure --update; no secret, domain or Entra setting."""
    current = _show(az, app, rg)
    now = describe(current)
    if now["image"] == image and now["build"] == build:
        message = "The app still runs the previous image; nothing was changed."
    else:
        az.run("containerapp", "update", "--name", app, "--resource-group", rg, "--image", image,
               "--revision-suffix", "rb" + uuid.uuid4().hex[:11], "--set-env-vars", f"KRUSGRAPH_BUILD={build}", raw=True)
        message = f"Rolled back to the previous image ({build or 'no build id'})."
        now = describe(_show(az, app, rg))
    aca.verify_server("https://" + now["fqdn"], {"domain": now["domain"]}, build or None)
    return message + " The previous build answers the checks of --update."


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("gate")
    for name in ("snapshot", "rollback"):
        p = sub.add_parser(name)
        p.add_argument("--app", required=True)
        p.add_argument("--resource-group", required=True)
        if name == "rollback":
            p.add_argument("--image", required=True)
            p.add_argument("--build", default="")
    args = parser.parse_args(argv)
    if args.command == "gate":
        try:
            go, reason = gate(os.environ)
        except GateError as exc:
            print("STOP: " + str(exc))
            _output({"go": "false"})
            return 1
        print(reason)
        _output({"go": "true" if go else "false",
                 **({OUTPUTS[k]: v for k, v in values(os.environ).items()} if go else {})})
        return 0
    try:
        app = aca.clean_name(args.app, "--app")
        rg = aca.clean_name(args.resource_group, "--resource-group")
        az = _azure()
        if args.command == "snapshot":
            state = snapshot(az, app, rg)
            print(json.dumps({k: state[k] for k in ("build", "revision")}))
            _output(state)
        else:
            print(rollback(az, app, rg, args.image.strip(), args.build.strip()))
    except aca.DeploymentError as exc:
        print("STOP: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
