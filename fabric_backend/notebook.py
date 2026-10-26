"""Fabric notebooks as item definitions: the `fabricGitSource` text format (notebook-content.py) and the REST envelope.

A notebook here is a list of cells, each (kind, text) with kind "markdown", "parameters" or "code". `fabric_source()`
writes them in the layout Fabric uses for a PySpark notebook in Git and in the item definition: a "# Fabric notebook
source" header, the notebook's metadata (kernel, default lakehouse) as "# META" lines, then each cell after its marker
("# MARKDOWN", "# PARAMETERS CELL", "# CELL") with its own metadata. `parse()` reads that text back into cells (the
tests run the code cells). `envelope()` is the body for POST /workspaces/{id}/notebooks and its updateDefinition.

Sources (read 26 October 2026): microsoft/fabric-rest-api-specs a96c37a, notebook/swagger.json (Items_CreateNotebook,
Items_UpdateNotebookDefinition: long-running, delegated scope Notebook.ReadWrite.All or Item.ReadWrite.All, Contributor
on the workspace, a Fabric capacity) and notebook/definitions.json (NotebookDefinition.format "ipynb" or
"fabricGitSource", parts with `.py` content for fabricGitSource); MicrosoftDocs/fabric-docs 0b9f0f8,
fundamentals/understand-best-practices-fabric-cicd.md (the "# Fabric notebook source" header and the default-lakehouse
metadata) and data-engineering/author-execute-notebook.md (the parameters cell a pipeline overrides).
"""
from __future__ import annotations

import base64
import json
import uuid

HEADER = "# Fabric notebook source"
_MARKERS = {"markdown": "# MARKDOWN ********************", "parameters": "# PARAMETERS CELL ********************",
            "code": "# CELL ********************"}
_META = "# METADATA ********************"
_CELL_META = {"language": "python", "language_group": "synapse_pyspark"}


def _meta_lines(obj: dict) -> list[str]:
    return ["# META " + line if line else "# META" for line in json.dumps(obj, indent=2).splitlines()]


def notebook_metadata(workspace_id: str = "", lakehouse_id: str = "", lakehouse_name: str = "") -> dict:
    meta: dict = {"kernel_info": {"name": "synapse_pyspark"}}
    if lakehouse_id:
        meta["dependencies"] = {"lakehouse": {"default_lakehouse": lakehouse_id, "default_lakehouse_name": lakehouse_name,
                                              "default_lakehouse_workspace_id": workspace_id}}
    return meta


def fabric_source(cells: list[tuple[str, str]], metadata: dict) -> str:
    out = [HEADER, "", _META, "", *_meta_lines(metadata), ""]
    for kind, text in cells:
        out.append(_MARKERS[kind])
        out.append("")
        if kind == "markdown":
            out += [("# " + line).rstrip() for line in text.strip("\n").splitlines()]
            out.append("")
        else:
            out += text.strip("\n").splitlines()
            out += ["", _META, "", *_meta_lines(_CELL_META), ""]
    return "\n".join(out).rstrip("\n") + "\n"


def parse(text: str) -> list[tuple[str, str]]:
    """The cells of a notebook-content.py written by fabric_source() (or by Fabric), without the metadata blocks."""
    kinds = {v: k for k, v in _MARKERS.items()}
    cells: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line in kinds:
            cells.append((kinds[line], []))
            current = cells[-1][1]
        elif line == _META:
            current = None
        elif current is not None:
            current.append(line)
    out = []
    for kind, lines in cells:
        if kind == "markdown":
            lines = [x[2:] if x.startswith("# ") else x.lstrip("#") for x in lines]
        out.append((kind, "\n".join(lines).strip("\n")))
    return out


def _platform(item_type: str, name: str) -> str:
    return json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                       "metadata": {"type": item_type, "displayName": name},
                       "config": {"version": "2.0", "logicalId": str(uuid.uuid5(uuid.NAMESPACE_URL, item_type.lower() + "|" + name))}}, indent=2)


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode()


def envelope(name: str, source: str, description: str = "") -> dict:
    """POST /workspaces/{id}/notebooks body: the notebook-content.py part and a .platform part (type Notebook)."""
    body = {"displayName": name, "definition": {"format": "fabricGitSource", "parts": [
        {"path": "notebook-content.py", "payload": b64(source), "payloadType": "InlineBase64"},
        {"path": ".platform", "payload": b64(_platform("Notebook", name)), "payloadType": "InlineBase64"}]}}
    if description:
        body["description"] = description[:256]
    return body


def pipeline_envelope(name: str, content: dict, description: str = "") -> dict:
    """POST /workspaces/{id}/dataPipelines body: pipeline-content.json and .platform (type DataPipeline); the layout of
    dataPipeline/examples/CreateDataPipeline.json in fabric-rest-api-specs."""
    body = {"displayName": name, "definition": {"parts": [
        {"path": "pipeline-content.json", "payload": b64(json.dumps(content, indent=2)), "payloadType": "InlineBase64"},
        {"path": ".platform", "payload": b64(_platform("DataPipeline", name)), "payloadType": "InlineBase64"}]}}
    if description:
        body["description"] = description[:256]
    return body
