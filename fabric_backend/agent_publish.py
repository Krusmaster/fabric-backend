"""Publishing the data agent Krusgraph made (round n185), as two separate choices, both off by default:

  Publish the agent in Fabric        Items_PublishDataAgent, POST /v1/workspaces/{ws}/dataAgents/{id}/staging/publish
                                     {publishedDescription}: "Promotes the current staging state to the published
                                     environment, making it live." Delegated scope Item.ReadWrite.All or
                                     DataAgent.ReadWrite.All; the caller needs read and write on the agent. Marked
                                     "Data Agent configuration management is currently in Preview"
                                     (microsoft/fabric-rest-api-specs 6f817cb, dataAgent/swagger.json, read 9 November 2026).
  Also make it available in          Learn "Consume a data agent from Microsoft Copilot" (data-agent-microsoft-365-copilot,
  Microsoft 365 Copilot              ms.date 2026-10-26): done in the portal's Publish dialog by ticking "Publish to Agent
                                     Store". No REST call for it is documented (the publish request has only
                                     publishedDescription), so Krusgraph never does it: when ticked, the card runs the
                                     preflight below and lists the portal step; it is never retried.

Fabric publishing only when (1) the person ticked it, (2) the agent reads one layer (data_agent.select_layer's
one_layer) and (3), when Run once was ticked, that run succeeded. Otherwise the agent stays a draft and the card says
which condition held it back.

The Microsoft 365 Copilot preflight, each requirement from Learn with its link; what cannot be read is "Unverified":
  - "A paid F2 or higher Fabric capacity, or a Power BI Premium per capacity (P1 or higher) capacity with Microsoft
    Fabric enabled" (data-agent-microsoft-365-copilot). Read: Get Workspace (capacityId, capacityRegion;
    Workspace.Read.All) and List Capacities (sku; Capacity.Read.All or Capacity.ReadWrite.All, which the workload app
    may not carry). A trial capacity's SKU is taken to start with "FT" (Unverified: Learn's capacity examples show only
    F4, F8, F16; the founder's trial tenant is what showed it). F2 and up, or P1 and up, pass.
  - Tenant settings (data-agent-tenant-settings, ms.date 2026-04-20): "Users can use Copilot and other features powered
    by Azure OpenAI", "Capacities can be designated as Fabric Copilot capacities", and outside the EU data boundary and
    the US also "Data sent to Azure OpenAI can be processed outside ..." and "... stored outside ...". Read with List
    Tenant Settings (GET /v1/admin/tenantsettings; Tenant.Read.All, a Fabric administrator only), matched by title as
    rayfin_app does; otherwise Unverified.
  - "Microsoft Copilot license or Office 365 commercial subscription" and user licences, and Copilot extensibility in
    the Microsoft 365 admin center: not readable through Fabric's API, always Unverified with the link.
"""
from __future__ import annotations

import re

FABRIC = "https://api.fabric.microsoft.com"
LEARN = "https://learn.microsoft.com/fabric/data-science/"
COPILOT_DOC = LEARN + "data-agent-microsoft-365-copilot"
SETTINGS_DOC = LEARN + "data-agent-tenant-settings"
PUBLISH_SCOPE = "Item.ReadWrite.All (or DataAgent.ReadWrite.All)"
CAPACITY_SCOPES = ("Capacity.Read.All", "Capacity.ReadWrite.All")
TENANT_SCOPES = ("Tenant.Read.All", "Tenant.ReadWrite.All")
DESCRIPTION = ("Answers questions about {source} from the tables Krusgraph checked (keys and links held). Deliver the "
               "agent's output as it is, without summarizing or rephrasing.")   # Learn: the description becomes description_for_model
COPILOT_STEP = ("In Fabric, open the agent → Publish → tick Publish to Agent Store → Publish. Krusgraph cannot do this step: "
                "Microsoft documents no API for it.")
FABRIC_STEP = "In Fabric, open the agent → Publish, so people with access to the workspace can use it (Krusgraph left it a draft)."
SETTINGS = (
    ("Users can use Copilot and other features powered by Azure OpenAI", "always"),
    ("Capacities can be designated as Fabric Copilot capacities", "always"),
    ("Data sent to Azure OpenAI can be processed outside your capacity's geographic region, compliance boundary, or national cloud instance", "outside"),
    ("Data sent to Azure OpenAI can be stored outside your capacity's geographic region, compliance boundary, or national cloud instance", "outside"),
)
# Regions inside the EU data boundary or the US, where Learn says the two cross-geo settings are not required. A region
# not listed here counts as outside (the settings are then listed as needed).
INSIDE = re.compile(r"(US|Europe|France|Germany|Italy|Spain|Poland|Sweden|Norway|Switzerland|North Europe|West Europe)", re.I)


def publish_words(name: str) -> str:
    return f"Create publishes {name}: people with access to the workspace can use it"


def copilot_words(name: str) -> str:
    return (f"Create cannot make {name} available in Microsoft 365 Copilot (no documented API); the card lists the portal step "
            "and what the preflight found")


def decide(ticked: bool, one_layer: bool | None, run_once: bool, run_status: str | None) -> dict:
    """Whether Create publishes the agent in Fabric now, waits for the run, or leaves it a draft, and why."""
    if not ticked:
        return {"publish": False, "state": "draft", "why": "Publish was not ticked: the agent stays a draft only you see."}
    if one_layer is False:
        return {"publish": False, "state": "draft",
                "why": "The agent's data source is not one layer (source and silver tables are both selected), so it was not published."}
    if run_once and run_status in (None, "Running", "NotStarted", "Unknown"):
        return {"publish": False, "state": "waiting",
                "why": "Publish waits for the pipeline run: the agent is published when the run has succeeded."}
    if run_once and run_status != "Succeeded":
        return {"publish": False, "state": "draft",
                "why": f"The pipeline run {str(run_status).lower()}, so the agent was not published; it stays a draft."}
    return {"publish": True, "state": "publish", "why": ""}


def _req(name: str, status: str, detail: str, doc: str) -> dict:
    return {"requirement": name, "status": status, "detail": detail, "doc": doc}


def _sku_ok(sku: str) -> tuple[str, str]:
    s = (sku or "").upper()
    if s.startswith("FT") or "TRIAL" in s:
        return "missing", f"the workspace is on a trial capacity ({sku}); Microsoft 365 Copilot needs a paid F2 or higher (Unverified: how a trial SKU is named)"
    m = re.fullmatch(r"([FP])(\d+)", s)
    if m and ((m.group(1) == "F" and int(m.group(2)) >= 2) or (m.group(1) == "P" and int(m.group(2)) >= 1)):
        return "ok", f"capacity {sku}"
    return "missing", f"capacity SKU {sku}: Microsoft 365 Copilot needs F2 or higher, or P1 or higher with Fabric enabled"


def copilot_preflight(http, workspace: str, scopes: set[str] | None) -> dict:
    """Each documented requirement for Microsoft 365 Copilot: ok, missing (with what is missing) or unverified (could
    not be read), with Microsoft's link. One read each, never retried."""
    out = []
    region = sku = None
    try:
        r = http("get", f"{FABRIC}/v1/workspaces/{workspace}")
        w = r.json() if getattr(r, "status_code", 0) < 400 else {}
    except Exception:  # noqa: BLE001
        w = {}
    cap_id, region = w.get("capacityId"), w.get("capacityRegion")
    if not cap_id:
        out.append(_req("Paid capacity, F2 or higher (or P1 or higher)", "missing" if w else "unverified",
                        "the workspace has no capacity" if w else "the workspace could not be read", COPILOT_DOC))
    elif scopes is not None and not set(CAPACITY_SCOPES) & scopes:
        out.append(_req("Paid capacity, F2 or higher (or P1 or higher)", "unverified",
                        "Unverified: reading the capacity's SKU needs Capacity.Read.All, which this sign-in does not carry", COPILOT_DOC))
    else:
        try:
            r = http("get", f"{FABRIC}/v1/capacities")
            caps = (r.json() or {}).get("value", []) if getattr(r, "status_code", 0) < 400 else None
        except Exception:  # noqa: BLE001
            caps = None
        cap = next((c for c in caps or [] if c.get("id") == cap_id), None)
        if cap is None:
            out.append(_req("Paid capacity, F2 or higher (or P1 or higher)", "unverified", "Unverified: the capacity could not be read", COPILOT_DOC))
        else:
            sku = cap.get("sku")
            st, detail = _sku_ok(sku or "")
            out.append(_req("Paid capacity, F2 or higher (or P1 or higher)", st, detail, COPILOT_DOC))
    outside = bool(region) and not INSIDE.search(region)
    titles = None
    if scopes is None or set(TENANT_SCOPES) & scopes:
        try:
            r = http("get", f"{FABRIC}/v1/admin/tenantsettings")
            if getattr(r, "status_code", 0) < 400:
                titles = {str(s.get("title", "")).strip().lower(): bool(s.get("enabled")) for s in (r.json() or {}).get("tenantSettings", [])}
        except Exception:  # noqa: BLE001
            titles = None
    for title, when in SETTINGS:
        if when == "outside" and not outside:
            if region:
                continue                                           # inside the EU data boundary or the US: not required
        name = f"Tenant setting \"{title}\""
        if titles is None:
            out.append(_req(name, "unverified", "Unverified: only a Fabric administrator can read tenant settings (Tenant.Read.All)", SETTINGS_DOC))
        elif title.lower() not in titles:
            out.append(_req(name, "unverified", "Unverified: the setting was not in the list Fabric returned", SETTINGS_DOC))
        else:
            out.append(_req(name, "ok" if titles[title.lower()] else "missing", "on" if titles[title.lower()] else "off: a Fabric administrator turns it on", SETTINGS_DOC))
    out.append(_req("Microsoft Copilot licence (or Office 365 commercial subscription) and a user licence per person", "unverified",
                    "Unverified: licences are not readable through Fabric's API", COPILOT_DOC))
    out.append(_req("Copilot extensibility allowed in the Microsoft 365 admin center", "unverified",
                    "Unverified: a Microsoft 365 admin checks Manage Copilot agents", COPILOT_DOC))
    missing = [x for x in out if x["status"] == "missing"]
    return {"requirements": out, "missing": len(missing), "unverified": sum(1 for x in out if x["status"] == "unverified"),
            "sku": sku, "region": region, "step": COPILOT_STEP,
            "words": ("Missing for Microsoft 365 Copilot: " + "; ".join(f"{x['requirement']} ({x['detail']})" for x in missing)) if missing
                     else "Nothing missing that Krusgraph could read; the rest is Unverified (see each line)."}
