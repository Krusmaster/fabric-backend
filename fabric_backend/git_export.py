"""What the creating tools would create, as files in the layout Fabric's Git integration reads: one folder per item,
named `<display name>.<item type>`, holding a `.platform` file and the item's definition files. The user commits them to
the repository connected to their workspace and lets Fabric's Git integration (Source control -> Update) or a
deployment pipeline make the change. Nothing here calls GitHub, Azure DevOps or Fabric.

The layout, from MicrosoftDocs/fabric-docs a2de7f9 (read 26 October 2026; learn.microsoft.com/fabric/cicd/...):
- cicd/git-integration/source-code-format.md (ms.date 12/15/2025): the folder is `{display name}.{public facing type}`,
  characters a folder name cannot hold are written as their HTML number; `.platform` carries `metadata.type`,
  `metadata.displayName` and `config.version` / `config.logicalId` (schema
  .../gitIntegration/platformProperties/2.0.0/schema.json, as in data-warehouse/upgrade-warehouse.md and
  fabric-rest-api-specs a96c37a lakehouse/examples/GetLakehouseDefinition.json). When copying an item folder by hand,
  "you do need to change the logicalId and the display name to something unique in the repository": every export
  derives the logicalId from the item type and display name (a UUID, never all zeros), so a re-export keeps it.
- cicd/includes/git-limitations.md: during a commit "the Fabric service deletes files inside the item folder that
  aren't part of the item definition", so the notes go next to the folders, not inside them.
- cicd/git-integration/intro-to-git-integration.md and cicd/deployment-pipelines/intro-to-deployment-pipelines.md
  (ms.date 09/01/2026, 09/24/2026): API for GraphQL, notebooks and data pipelines are supported in both; semantic
  models in both as preview.
- The definition files are the parts the REST APIs take (fabric-rest-api-specs a96c37a): graphql-definition.json;
  definition.pbism and definition/*.tmdl; notebook-content.py (fabricGitSource); pipeline-content.json.
- data-warehouse/git-integration.md (08/13/2026): "Version control support for SQL analytics endpoints isn't currently
  available", and deployment pipelines don't support the SQL analytics endpoint item: the T-SQL views of create_views
  are exported as a .sql file outside any item folder, to run with create_views or in the SQL editor.
"""
from __future__ import annotations

import base64
import json
import uuid

_UNSAFE = '\\/:*?"<>|'


def folder(display_name: str, item_type: str) -> str:
    """`<display name>.<item type>`, with the characters a folder name cannot hold written as HTML numbers."""
    name = "".join(f"&#{ord(c)};" if c in _UNSAFE or ord(c) < 32 else c for c in display_name)
    return f"{name}.{item_type}"


def _text(path: str, raw: bytes) -> str:
    text = raw.decode("utf-8")
    if path.endswith(".json") or path == ".platform":
        try:
            return json.dumps(json.loads(text), indent=2) + "\n"            # readable diffs; the content is the same JSON
        except ValueError:
            return text
    return text


def files_of(body: dict, item_type: str) -> dict[str, str]:
    """A REST create body ({displayName, definition: {parts}}) -> {path in the repository: text}."""
    root = folder(body["displayName"], item_type)
    out = {}
    for part in body["definition"]["parts"]:
        out[f"{root}/{part['path']}"] = _text(part["path"], base64.b64decode(part["payload"]))
    if f"{root}/.platform" not in out:
        out[f"{root}/.platform"] = platform(item_type, body["displayName"], body.get("description", ""))
    return out


def platform(item_type: str, display_name: str, description: str = "") -> str:
    meta = {"type": item_type, "displayName": display_name}
    if description:
        meta["description"] = description
    return json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                       "metadata": meta,
                       "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, item_type.lower() + "|" + display_name))}},
                      indent=2) + "\n"


HOW = [
    "Copy the folders as they are into the folder of your repository that is connected to the workspace (Workspace settings -> "
    "Git integration shows the branch and the Git folder).",
    "Review and commit them in your own tool, then push.",
    "In Fabric: Source control -> Updates -> Update all. Fabric creates the items that are new and updates the ones that exist; "
    "or let a deployment pipeline carry them from a development workspace to the next stage.",
    "After the update: refresh the semantic model once (framing) and run the notebooks in order (silver, then gold); the drift "
    "monitor's pipeline needs its notebook reference set (below).",
]

SOURCES = ("MicrosoftDocs/fabric-docs a2de7f9: cicd/git-integration/source-code-format.md, cicd/git-integration/intro-to-git-integration.md, "
           "cicd/deployment-pipelines/intro-to-deployment-pipelines.md, cicd/includes/git-limitations.md, data-warehouse/git-integration.md; "
           "microsoft/fabric-rest-api-specs a96c37a for the definition parts")


def readme(entries: list[dict], notes: list[str]) -> str:
    lines = ["# Krusgraph export in Fabric's Git format", "",
             "Generated from the plan. Each folder is one Fabric item (`<name>.<type>` with `.platform` and its definition files). "
             "Nothing was created in Fabric and nothing was sent to a Git provider.", "", "## Items", ""]
    lines += [f"- `{e['folder']}/` ({e['type']}; what `{e['tool']}` would create): {e['what']}" for e in entries]
    lines += ["", "## How to apply", ""] + [f"{i}. {h}" for i, h in enumerate(HOW, 1)]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    lines += ["", f"Sources: {SOURCES}.", ""]
    return "\n".join(lines)
