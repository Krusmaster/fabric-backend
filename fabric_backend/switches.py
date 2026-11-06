"""Server-wide switches (round n123, docs/LANDSCAPE.md idea 3): two operator settings for the hosted and the local server.

Both are off by default; off, nothing changes (the listing and every answer are as before).

- KRUSGRAPH_READ_ONLY=1 (read-only Krusgraph): no tool that creates or changes anything in Fabric is registered. Which
  tools those are is read, never listed here: a tool is creating when fabric_backend/tool_status.py gives it the kind
  CREATES, or when its own annotations say read_only_hint=False (the local server's tools, the Databricks ones
  included, have annotations but no status entry).
- KRUSGRAPH_NO_ROW_VALUES=1: sample_rows is not registered, and the other answers have their row values taken out,
  keeping names and counts: the data of a GraphQL result becomes its field names with the number of rows per list,
  a list of rows anywhere in an answer becomes its count, and a value quoted after the word "value" in a message from
  the SQL endpoint or Fabric is replaced by "…". Steps that point at a tool this server does not register are dropped
  from next_steps.

A removed tool is absent from tools/list, so an MCP client calling it by name gets the SDK's "Unknown tool" error; called
directly in Python it answers kind switched_off. The settings are read at start for registration and at every call
for the answers.
"""
from __future__ import annotations

import functools
import json
import os
import re

READ_ONLY = "KRUSGRAPH_READ_ONLY"
NO_ROW_VALUES = "KRUSGRAPH_NO_ROW_VALUES"
ROW_VALUE_TOOLS = ("sample_rows",)          # the tools whose answer is row values and nothing else
REMOVED = "(value removed)"
_ON = {"1", "true", "yes", "on"}

# One neutral clause each, for both servers' instructions, /llms.txt and the docs (tests/test_n123_switches.py).
READ_ONLY_CLAUSE = (f"{READ_ONLY}=1 leaves out the tools that create or change something in Fabric")
NO_ROW_VALUES_CLAUSE = (f"{NO_ROW_VALUES}=1 leaves out sample_rows and removes row values from the other answers, "
                        "keeping names and counts")
SENTENCE = (f"Two operator settings, both off by default: {READ_ONLY_CLAUSE}, and {NO_ROW_VALUES_CLAUSE}.")


def _on(name: str, environ=None) -> bool:
    return (os.environ if environ is None else environ).get(name, "").strip().lower() in _ON


def read_only(environ=None) -> bool:
    return _on(READ_ONLY, environ)


def no_row_values(environ=None) -> bool:
    return _on(NO_ROW_VALUES, environ)


def mode(environ=None) -> str:
    """The mode as /healthz says it: default, read-only, no-row-values, or both."""
    on = [m for m, f in (("read-only", read_only), ("no-row-values", no_row_values)) if f(environ)]
    return ", ".join(on) or "default"


def creates(name: str, annotations=None) -> bool:
    """A tool that creates or changes something in Fabric: CREATES in tool_status, or read_only_hint=False."""
    from . import tool_status
    status = tool_status.STATUS.get(name)
    if status is not None and status.kind == tool_status.CREATES:
        return True
    return annotations is not None and getattr(annotations, "read_only_hint", None) is False


def removed(name: str, annotations=None, environ=None) -> str | None:
    """The setting that removes this tool, or None when it stays."""
    if read_only(environ) and creates(name, annotations):
        return READ_ONLY
    if no_row_values(environ) and name in ROW_VALUE_TOOLS:
        return NO_ROW_VALUES
    return None


KNOWN: dict = {}                            # every tool a server defined, with its annotations, kept or not


def register(name: str, annotations=None) -> bool:
    """At registration: note the tool, and say whether the server registers it under the settings at start."""
    KNOWN[name] = annotations
    return removed(name, annotations) is None


def _keep(name) -> bool:
    return not isinstance(name, str) or removed(name, KNOWN.get(name)) is None


def refusal(name: str, setting: str) -> str:
    what = ("tools that create or change something in Fabric" if setting == READ_ONLY
            else "tools that return row values")
    return json.dumps({"error": f"{name} is switched off on this server ({setting}=1: no {what}).", "kind": "switched_off",
                       "hint": "The operator of this server decides this setting; tools/list shows the tools it offers."},
                      indent=2)


# ------------------------------------------------------------------ answers -------------------------------------------

_QUOTED_VALUE = re.compile(r"(?i)(\bvalues?\b[^'\"\n]{0,24}?)(['\"])(.*?)\2")


def _shape(v):
    """A GraphQL result without its values: objects keep their field names, a list becomes its count (and, for a list
    of objects, the fields of its items), a scalar becomes REMOVED."""
    if isinstance(v, dict):
        return {k: _shape(x) for k, x in v.items()}
    if isinstance(v, list):
        out: dict = {"count": len(v)}
        items = [x for x in v if isinstance(x, dict)]
        if items:
            merged: dict = {}
            for x in items:
                for k, y in x.items():
                    merged.setdefault(k, y)
            out["fields"] = _shape(merged)
        return out
    return None if v is None else REMOVED


def _text(s: str) -> str:
    return _QUOTED_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}…{m.group(2)}", s)


def _walk(v, top: bool, keep_tool):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k == "data" and top and isinstance(x, (dict, list)):        # a GraphQL result's data (at the top or in result)
                out[k] = _shape(x)
            elif k == "rows" and isinstance(x, list):                      # rows of a table, wherever an answer carries them
                out[k] = {"count": len(x), "values": REMOVED} if x else x
            elif k == "next_steps" and isinstance(x, list):
                out[k] = [s for s in x if not (isinstance(s, dict) and not keep_tool(s.get("tool")))]
            elif k in ("error", "hint") and isinstance(x, str):
                out[k] = _text(x)
            else:
                out[k] = _walk(x, top and k == "result", keep_tool)
        return out
    if isinstance(v, list):
        return [_walk(x, False, keep_tool) for x in v]
    return v


def answer(text, keep_tool=_keep, environ=None):
    """A tool's answer under the switches: unchanged when both are off or when it is not JSON."""
    ro, nrv = read_only(environ), no_row_values(environ)
    if not (ro or nrv) or not isinstance(text, str):
        return text
    try:
        body = json.loads(text)
    except ValueError:
        return text
    if nrv:
        body = _walk(body, True, keep_tool)
    elif isinstance(body, dict) and isinstance(body.get("next_steps"), list):
        body["next_steps"] = [s for s in body["next_steps"] if not (isinstance(s, dict) and not keep_tool(s.get("tool")))]
    return json.dumps(body, indent=2, ensure_ascii=False, default=str)


def guard(fn, name: str, annotations=None, keep_tool=_keep):
    """Around a tool function: a refusal when its setting is on at call time, else the answer under the switches."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        setting = removed(name, annotations)
        if setting:
            return refusal(name, setting)
        return answer(fn(*args, **kwargs), keep_tool)
    return wrapper
