"""Fair-use limits per signed-in user (Entra `oid`) and per organisation (`tid`) on the hosted server.

A limit is "N calls per window"; each one is a token bucket that holds N calls and refills at N per window, so a burst
up to N is fine and the steady rate is N per window. A call goes through only when every bucket of the user and of the
organisation has a call left; it then takes one from each. A refused call costs nothing and says when the first bucket
that refused it has a call again.

Only tool calls count (the server checks inside the tool wrapper, after the 401 guard has accepted the token):
`initialize`, `tools/list`, the site and the sign-in flow are never limited, and a request without a valid token still
gets the 401 Claude starts sign-in on. In memory per replica: with `maxReplicas` 2 a user can reach up to twice the
limit for a moment. The keys are SHA-256 hashes of the ids with a salt drawn when the process starts, so the table
holds no ids in clear and nothing about it is written anywhere; a user's buckets are dropped once they have refilled,
which is at most the longest window after the user's last call (checked every minute).

Configuration (environment):
  KRUSGRAPH_RATE_LIMITS   "0" (or off/false/no) turns the limits off; on by default in Entra mode
  KRUSGRAPH_RATE_USER     per user, default "30/minute,600/hour"
  KRUSGRAPH_RATE_ORG      per organisation, default "120/minute,3000/hour"
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import math
import os
import re
import secrets
import threading
import time

DEFAULT_USER = "30/minute,600/hour"
DEFAULT_ORG = "120/minute,3000/hour"
MAX_KEYS = 20000                                     # buckets kept before full (idle) ones are dropped

_UNITS = {"s": 1, "sec": 1, "second": 1, "m": 60, "min": 60, "minute": 60, "h": 3600, "hour": 3600, "d": 86400, "day": 86400}
_SPEC = re.compile(r"^\s*(\d+)\s*/\s*(\d*)\s*([a-z]+?)s?\s*$")


def parse(spec: str) -> list[tuple[int, int]]:
    """'30/minute,600/hour' -> [(30, 60), (600, 3600)]; '5/10s' -> [(5, 10)]. A bad entry raises ValueError, so a
    typo in the configuration stops the server at startup instead of silently allowing everything."""
    out = []
    for part in (spec or "").split(","):
        if not part.strip():
            continue
        m = _SPEC.match(part.lower())
        if not m or m.group(3) not in _UNITS or int(m.group(1)) < 1 or (m.group(2) and int(m.group(2)) < 1):
            raise ValueError(f"rate limit {part.strip()!r}: write it as <calls>/<unit>, e.g. 30/minute or 600/hour")
        out.append((int(m.group(1)), int(m.group(2) or 1) * _UNITS[m.group(3)]))
    return out


def _words(calls: int, seconds: int) -> str:
    for unit, n in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds % n == 0:
            k = seconds // n
            return f"{calls} calls per {unit}" if k == 1 else f"{calls} calls per {k} {unit}s"
    return f"{calls} calls per {seconds} seconds"


class Limiter:
    def __init__(self, user: list[tuple[int, int]], org: list[tuple[int, int]], clock=time.monotonic) -> None:
        self.rules = {"user": user, "organisation": org}
        self.clock = clock
        self._salt = secrets.token_bytes(16)
        self._buckets: dict[tuple[str, str, int], tuple[float, float]] = {}    # (scope, hashed id, rule) -> (calls left, at)
        self._lock = threading.Lock()
        self._pruned = clock()

    @classmethod
    def from_env(cls) -> "Limiter | None":
        if os.environ.get("KRUSGRAPH_RATE_LIMITS", "1").strip().lower() in {"0", "off", "false", "no"}:
            return None
        return cls(parse(os.environ.get("KRUSGRAPH_RATE_USER") or DEFAULT_USER),
                   parse(os.environ.get("KRUSGRAPH_RATE_ORG") or DEFAULT_ORG))

    def _key(self, value: str) -> str:
        return hashlib.sha256(self._salt + str(value).lower().encode()).hexdigest()[:32]

    def check(self, oid: str | None, tid: str | None) -> dict | None:
        """None when the call may go ahead (and it is counted); otherwise {scope, limit, retry_after} for the first
        bucket that is empty. Ids that are missing are not limited on that scope."""
        now = self.clock()
        wanted = [(scope, self._key(ident), i, calls, window)
                  for scope, ident in (("user", oid), ("organisation", tid)) if ident
                  for i, (calls, window) in enumerate(self.rules[scope])]
        with self._lock:
            if now - self._pruned >= 60 or len(self._buckets) > MAX_KEYS:
                self._prune(now)
                self._pruned = now
            levels, refused = [], None
            for scope, key, i, calls, window in wanted:
                left, at = self._buckets.get((scope, key, i), (float(calls), now))
                left = min(float(calls), left + (now - at) * calls / window)
                if left < 1.0:
                    wait = max(1, math.ceil((1.0 - left) * window / calls))
                    if refused is None or wait > refused["retry_after"]:      # the slowest empty bucket decides when to come back
                        refused = {"scope": scope, "limit": _words(calls, window), "retry_after": wait}
                levels.append(((scope, key, i), left))
            if refused:
                return refused
            for k, left in levels:
                self._buckets[k] = (left - 1.0, now)
        return None

    def _prune(self, now: float) -> None:
        """Drop the buckets that have refilled completely (an idle user); those carry no information."""
        full = [k for k, (left, at) in self._buckets.items()
                if left + (now - at) * self.rules[k[0]][k[2]][0] / self.rules[k[0]][k[2]][1] >= self.rules[k[0]][k[2]][0]]
        for k in full:
            del self._buckets[k]


def answer(hit: dict) -> dict:
    """The tool answer for a refused call, in the error/kind/hint format of every other tool error."""
    who = "your account" if hit["scope"] == "user" else "your organisation"
    seconds = hit["retry_after"]
    when = f"{seconds} seconds" if seconds < 120 else f"{math.ceil(seconds / 60)} minutes"
    return {"error": f"Too many calls from {who} in a short time: the limit is {hit['limit']} for {who} on this server.",
            "kind": "rate_limited", "retry_after": seconds,
            "hint": f"Try again in {when}. Nothing was run for this call. If your work needs more, ask the operator about higher limits."}


# ------------------------------------------------------------------ item definitions: part checks and Fabric's limits --
# Checked before a definition is sent to Fabric (deploy.write_and_wait's callers), so a definition Fabric would refuse
# is stopped here with the reason, and nothing is written.
#
# The ontology limits are Fabric's own, as Microsoft documents them in "Payload limits" of
# tools/Fabric.Mcp.Tools.Docs/src/Resources/item-definitions/ontology-definition.md in microsoft/mcp at commit
# 7257a94355dd63ba4f1ba43fc5ae5dfcd1a7203d (MIT, Copyright (c) Microsoft Corporation; see THIRD_PARTY_NOTICES.md).
# Only the limits that can be counted from our TMDL parts without a full parser are checked. The local budgets of that
# project's tools (1024 parts, 16/32 MiB per definition) are its own and not Fabric's, so they are not here.

ONTOLOGY_LIMITS = {
    "tables": 15_998, "columns_per_table": 15_997, "model_budget": 16_000,   # 2 + tables + columns <= 16,000
    "expressions": 10_000, "relationships": 10_000, "entities": 10_000, "entity_relationships": 10_000,
    "namespaces": 10_000, "metrics": 10_000, "rules": 1_000,
    "measures_per_table": 10_000, "partitions_per_table": 1_000, "properties_per_entity": 1_000,
    "name_chars": 512, "description_chars": 4_000, "annotation_chars": 4_000,
}


class DefinitionError(ValueError):
    """A definition that would not be sent: the parts or a limit are wrong. Nothing was written to Fabric."""


def part_problems(parts) -> list[str]:
    """Problems with a definition's parts, as sentences; empty when it may be sent. `parts` is a definition's
    `parts` list ({path, payload, payloadType}) or {path: text}. Checks: every path is a relative path with no empty,
    '.' or '..' segment; paths are unique ignoring case; no path is both a file and a folder (`a` and `a/b`); an
    InlineBase64 payload is valid base64."""
    if isinstance(parts, dict):
        items = [(path, None, None) for path in parts]
    else:
        items = [(p.get("path"), p.get("payload"), p.get("payloadType")) for p in parts or []]
    problems: list[str] = []
    seen: dict[str, str] = {}
    for path, payload, kind in items:
        if not isinstance(path, str) or not path:
            problems.append("a part has no path")
            continue
        segments = path.split("/")
        if path.startswith("/") or "\\" in path or any(s in ("", ".", "..") for s in segments):
            problems.append(f"part {path!r}: the path must be relative, with '/' between non-empty names and no '.' or '..'")
        low = path.lower()
        if low in seen:
            problems.append(f"parts {seen[low]!r} and {path!r} have the same path when case is ignored")
        else:
            seen[low] = path
        if kind == "InlineBase64" or (kind is None and payload is not None):
            try:
                base64.b64decode(payload if isinstance(payload, (str, bytes)) else "\0", validate=True)
            except (binascii.Error, ValueError):
                problems.append(f"part {path!r}: the payload is not valid base64")
    folders = {"/".join(p.split("/")[:i]) for p in seen for i in range(1, p.count("/") + 1)}
    for low, path in seen.items():
        if low in folders:
            problems.append(f"part {path!r} is a file, and also a folder of another part")
    return problems


def _name(rest: str) -> str:
    """The object name of a TMDL declaration's rest ("x", "'a b'", "x = entity", "DatabaseQuery ="), unquoted."""
    return re.split(r"\s+=(?:\s|$)", rest.strip(), maxsplit=1)[0].strip().strip("'")


def _blocks(text: str, keyword: str, indent: int = 0) -> list[str]:
    """Names of the TMDL objects declared with `keyword` at this many tabs ('table x', '\\tcolumn y = ...')."""
    head = "\t" * indent + keyword + " "
    out = []
    for line in text.splitlines():
        if line.startswith(head):                    # exactly `indent` tabs: a deeper line has a tab where the keyword is
            out.append(_name(line[len(head):]))
    return out


def ontology_problems(parts: dict[str, str]) -> list[str]:
    """Fabric's payload limits for an ontology definition (generation 2, TMDL), counted from {path: text}."""
    L = ONTOLOGY_LIMITS
    problems: list[str] = []

    def over(what: str, n: int, limit: int) -> None:
        if n > limit:
            problems.append(f"{what}: {n:,}, Fabric's limit is {limit:,}")

    tables = {p: t for p, t in parts.items() if p.startswith("tables/")}
    entities = {p: t for p, t in parts.items() if p.startswith("entities/")}
    over("tables", len(tables), L["tables"])
    columns = 0
    for path, text in tables.items():
        cols = _blocks(text, "column", 1)
        columns += len(cols)
        over(f"columns in {path}", len(cols), L["columns_per_table"])
        over(f"measures in {path}", len(_blocks(text, "measure", 1)), L["measures_per_table"])
        over(f"partitions in {path}", len(_blocks(text, "partition", 1)), L["partitions_per_table"])
    if 2 + len(tables) + columns > L["model_budget"]:
        problems.append(f"2 + tables + columns: {2 + len(tables) + columns:,}, Fabric's limit is {L['model_budget']:,}")
    over("entities", len(entities), L["entities"])
    for path, text in entities.items():
        over(f"properties in {path}", len(_blocks(text, "property", 1)), L["properties_per_entity"])
    over("namespaces", sum(p.startswith("namespaces/") for p in parts), L["namespaces"])
    over("rules", sum(p.startswith("rules/") for p in parts), L["rules"])
    over("metrics", sum(p.startswith("metrics/") for p in parts), L["metrics"])
    over("expressions", len(_blocks(parts.get("expressions.tmdl", ""), "expression")), L["expressions"])
    over("relationships", len(_blocks(parts.get("relationships.tmdl", ""), "relationship")), L["relationships"])
    over("entity relationships", len(_blocks(parts.get("entityRelationships.tmdl", ""), "entityRelationship")), L["entity_relationships"])
    for path, text in parts.items():
        if not path.endswith(".tmdl"):
            continue
        for line in text.splitlines():
            bare = line.lstrip("\t")
            if bare.startswith("///"):
                over(f"a description in {path}", len(bare[3:].strip()), L["description_chars"])
                continue
            word, _, rest = bare.partition(" ")
            if word == "annotation":
                over(f"an annotation value in {path}", len(rest.partition(" = ")[2]), L["annotation_chars"])
            elif word in ("database", "model", "table", "column", "measure", "partition", "entity", "property", "relationship",
                          "entityRelationship", "namespace", "rule", "metric", "expression") and rest:
                name = _name(rest)
                over(f"the name of a {word} in {path}", len(name), L["name_chars"])
    return problems


def check_definition(definition: dict, item_type: str = "") -> None:
    """Raise DefinitionError, before anything is sent, when the parts are wrong or (for an ontology) over Fabric's limits."""
    parts = (definition or {}).get("parts") or []
    problems = part_problems(parts)
    if not problems and item_type == "Ontology":
        texts = {p["path"]: base64.b64decode(p["payload"]).decode("utf-8", "replace") for p in parts if p.get("payloadType") == "InlineBase64"}
        problems = ontology_problems(texts)
    if problems:
        shown = "; ".join(problems[:5]) + (f"; and {len(problems) - 5} more" if len(problems) > 5 else "")
        raise DefinitionError(f"the definition was not sent to Fabric: {shown}")
