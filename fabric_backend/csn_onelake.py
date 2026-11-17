"""SAP CSN files in the lakehouse's own Files area, used without the CLI (round CSN2; docs/SAP-CSN.md section 4).

A customer exports a CSN/JSON file from SAP Datasphere (or SAP Business Data Cloud, or a CAP project) and uploads it to
the lakehouse's *Files*, by default under `Files/krusgraph/csn/`. Every hosted plan of that lakehouse (plan_backend,
validate_plan, every drafting tool, and the Fabric workload's review, check and build) then reads it and plans with its
keys, links and amounts, rule "CSN metadata", provenance "declared by metadata (CSN)"; validate_plan counts them in the
rows like any other key or link. A tool's `csn_path` (a folder or one file under Files/) reads another place.

How it reads OneLake. OneLake speaks the ADLS Gen2 (DFS) API: `https://onelake.dfs.fabric.microsoft.com/<workspace
id>/<item id>/<path>`, with a token for the Azure Storage audience (`https://storage.azure.com/.default`), per Microsoft
Learn, "How do I connect to OneLake?" (learn.microsoft.com/fabric/onelake/onelake-access-api, the page mirroring.py
cites). Two calls, both GET:

- list one folder, not recursively: `GET https://onelake.dfs.fabric.microsoft.com/<ws>?resource=filesystem
  &recursive=false&directory=<item>/<folder>` (ADLS Gen2 "Path - List"), answering `{"paths": [{name, contentLength,
  isDirectory}]}`;
- read one file: `GET https://onelake.dfs.fabric.microsoft.com/<ws>/<item>/<file>` (ADLS Gen2 "Path - Read"), read as
  a stream and stopped at MAX_FILE_BYTES.

Not run against OneLake in this round (unit tests with a fake listing only): the URL forms are the documented ones, the
token audience and the delegated permission the Entra app needs (Azure Storage `user_impersonation`, consented by an
administrator) are from the same documentation, not verified.

What it never does. It never writes, renames or deletes anything in the customer's lakehouse (no PUT, PATCH, POST or
DELETE is sent). It reads the file in the call and keeps nothing: no copy, no cache, no log of the contents (the log
lines carry counts and kinds only), and nothing is sent anywhere but back to the caller, as the plan built from it.

Validation. A file is used only when it parses as JSON and is CSN: a `definitions` object and one of `$version`,
`csnInteropEffective` or `version.csn` (CSN 0.1/0.2). Anything else is skipped and listed with why; other extensions
than .json and .csn are not opened. Limits: MAX_FILES files, MAX_FILE_BYTES each, MAX_TOTAL_BYTES together.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import quote

from . import csn as _csn

DEFAULT_DIR = "Files/krusgraph/csn"
HOST = "onelake.dfs.fabric.microsoft.com"
STORAGE_SCOPE = "https://storage.azure.com/.default"
DELEGATED = "Azure Storage: user_impersonation"
SWITCH = "KRUSGRAPH_LAKEHOUSE_CSN"                    # "0" turns the default folder off; csn_path still reads
MAX_FILES = 20
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
TIMEOUT = 15
EXTENSIONS = (".json", ".csn")
LAKEHOUSE_TYPES = ("Lakehouse",)
FROM_LAKEHOUSE = "the lakehouse's Files"


class NotRead(Exception):
    """OneLake answered, but not with what was asked for (denied, missing, too large); `kind` says which."""

    def __init__(self, kind: str, why: str) -> None:
        super().__init__(why)
        self.kind, self.why = kind, why


def enabled(environ=None) -> bool:
    return (os.environ if environ is None else environ).get(SWITCH, "1").strip().lower() not in ("0", "false", "no", "off")


def clean_path(path: str | None) -> str:
    """A path under the lakehouse's Files: 'Files/x/y', 'x/y' (Files/ added) or '/Files/x/'. Refuses what leaves Files:
    '..', a URL, Tables/, a backslash, a drive or an empty name. Returns 'Files/...' without a trailing slash."""
    p = (path or "").strip()
    if not p:
        return DEFAULT_DIR
    if "://" in p or "\\" in p or re.match(r"^[A-Za-z]:", p) or len(p) > 400:
        raise ValueError("csn_path is a folder or a file under the lakehouse's Files, such as Files/krusgraph/csn/model.json")
    parts = [x for x in p.strip("/").split("/") if x not in ("", ".")]
    if any(x == ".." for x in parts):
        raise ValueError("csn_path may not contain '..': it stays under the lakehouse's Files")
    if parts and parts[0].lower() == "tables":
        raise ValueError("csn_path reads the lakehouse's Files, not its Tables")
    if not parts or parts[0].lower() != "files":
        parts = ["Files"] + parts
    parts[0] = "Files"
    return "/".join(parts)


def is_csn(obj) -> tuple[bool, str]:
    """(True, '') for a CSN object; else (False, why). CSN here: a `definitions` object and a version marker."""
    if not isinstance(obj, dict):
        return False, "not a JSON object"
    if not isinstance(obj.get("definitions"), dict):
        return False, "no 'definitions' object: not CSN"
    ver = obj.get("version")
    if not (obj.get("$version") or obj.get("csnInteropEffective") or (isinstance(ver, dict) and ver.get("csn"))):
        return False, "no '$version' or 'csnInteropEffective': not recognised as CSN"
    return True, ""


class OneLake:
    """Read-only access to one item's folder in OneLake: list() and read(). Only GET is ever sent."""

    def __init__(self, workspace_id: str, item_id: str, token: str, get=None, timeout: int = TIMEOUT) -> None:
        self.ws, self.item, self._token, self.timeout = workspace_id, item_id, token, timeout
        self._get = get

    def _http(self, url: str, **kw):
        if self._get is not None:
            return self._get(url, **kw)
        return _http_get(url, **kw)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}", "x-ms-version": "2023-11-03"}

    @staticmethod
    def _check(r, what: str) -> None:
        code = getattr(r, "status_code", 0)
        if code in (401, 403):
            raise NotRead("denied", f"OneLake refused to {what} (HTTP {code}): the sign-in lacks read access to the "
                                    f"lakehouse's Files, or the app lacks the delegated permission {DELEGATED}")
        if code == 404:
            raise NotRead("missing", f"not found in the lakehouse ({what})")
        if code >= 400 or code == 0:
            raise NotRead("error", f"OneLake answered HTTP {code} ({what})")

    def list(self, folder: str) -> list[dict]:
        """[{name (path under the item), size, is_dir}] of one folder, not recursively."""
        url = (f"https://{HOST}/{quote(self.ws, safe='')}?resource=filesystem&recursive=false"
               f"&directory={quote(f'{self.item}/{folder}', safe='/')}")
        r = self._http(url, headers=self._headers(), timeout=self.timeout)
        self._check(r, "list the folder")
        out, prefix = [], f"{self.item}/"
        for x in (r.json() or {}).get("paths") or []:
            name = str(x.get("name") or "")
            name = name[len(prefix):] if name.startswith(prefix) else name
            out.append({"name": name, "size": int(x.get("contentLength") or 0),
                        "is_dir": str(x.get("isDirectory", "false")).lower() == "true"})
        return out

    def read(self, path: str, limit: int = MAX_FILE_BYTES) -> bytes:
        url = f"https://{HOST}/{quote(self.ws, safe='')}/{quote(self.item, safe='')}/{quote(path, safe='/')}"
        r = self._http(url, headers=self._headers(), timeout=self.timeout, stream=True)
        self._check(r, "read the file")
        got, n = [], 0
        for chunk in r.iter_content(64 * 1024):
            n += len(chunk)
            if n > limit:
                getattr(r, "close", lambda: None)()
                raise NotRead("too_large", f"larger than {limit // (1024 * 1024)} MB")
            got.append(chunk)
        return b"".join(got)


def _http_get(url: str, **kw):                         # the one network call; tests replace it (tests/conftest.py)
    import requests
    return requests.get(url, **kw)


@dataclass
class Found:
    """What was looked for and what came of it. `model` is None when no file was used."""
    path: str
    given: bool = False
    model: object = None
    used: list = field(default_factory=list)            # [{file, entities, version}]
    skipped: list = field(default_factory=list)         # [{file, why}]
    not_read: dict | None = None                        # {kind, why, hint}

    def report(self) -> dict:
        out = {"looked_in": self.path, "where": FROM_LAKEHOUSE, "used": self.used}
        if self.skipped:
            out["skipped"] = self.skipped
        if self.not_read:
            out["not_read"] = self.not_read
        if not self.used and not self.not_read:
            out["note"] = "no CSN file was used from this place"
        return out

    def worth_saying(self) -> bool:
        """The default folder that is not there, or a sign-in that cannot read it, says nothing; anything found, skipped
        or asked for (csn_path) does."""
        return bool(self.used or self.skipped or self.given)


def find(lake: OneLake, path: str | None = None) -> Found:
    """The CSN files at `path` (a folder: its .json and .csn files, not recursively; or one file), validated and read
    into one csn.Model whose file names are the paths under Files/. Never raises for what OneLake answers."""
    given = bool((path or "").strip())
    target = clean_path(path)
    found = Found(target, given)
    try:
        single = target.lower().endswith(EXTENSIONS)
        if single:
            names = [{"name": target, "size": 0, "is_dir": False}]
        else:
            names = sorted(lake.list(target), key=lambda x: x["name"].lower())
    except NotRead as e:
        if e.kind == "missing" and not given:
            return found
        found.not_read = {"kind": e.kind, "why": e.why, "hint": _hint(e.kind)}
        return found
    files = []
    for x in names:
        base = x["name"].rsplit("/", 1)[-1]
        if x["is_dir"]:
            continue
        if not base.lower().endswith(EXTENSIONS):
            found.skipped.append({"file": x["name"], "why": "not a .json or .csn file; not opened"})
        elif x["size"] > MAX_FILE_BYTES:
            found.skipped.append({"file": x["name"], "why": f"larger than {MAX_FILE_BYTES // (1024 * 1024)} MB; not opened"})
        else:
            files.append(x)
    if len(files) > MAX_FILES:
        found.skipped += [{"file": x["name"], "why": f"more than {MAX_FILES} files in the folder; not opened"} for x in files[MAX_FILES:]]
        files = files[:MAX_FILES]
    pairs, total = [], 0
    for x in files:
        try:
            raw = lake.read(x["name"], min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total))
        except NotRead as e:
            if e.kind == "denied" or (single and e.kind == "missing"):
                found.not_read = {"kind": e.kind, "why": e.why, "hint": _hint(e.kind)}
                break
            found.skipped.append({"file": x["name"], "why": e.why if e.kind != "too_large" or total == 0
                                  else f"the files together exceed {MAX_TOTAL_BYTES // (1024 * 1024)} MB; not read"})
            continue
        total += len(raw)
        try:
            obj = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            found.skipped.append({"file": x["name"], "why": "not JSON"})
            continue
        ok, why = is_csn(obj)
        if not ok:
            found.skipped.append({"file": x["name"], "why": why})
            continue
        pairs.append((x["name"], obj))
        del raw
    if pairs:
        model = _csn.read_named(pairs)
        found.model = model
        for name, _ in pairs:
            ver = next((v for v in model.versions if v["file"] == name), {})
            found.used.append({"file": name, "entities": sum(1 for e in model.entities.values() if e.file == name),
                               "version": ver.get("interop") and f"CSN Interop {ver['interop']}" or ver.get("$version") or ver.get("csn")})
    return found


def _hint(kind: str) -> str:
    if kind == "denied":
        return (f"Krusgraph reads Files with your own sign-in. You need read access to the lakehouse, and the Entra app "
                f"the delegated permission {DELEGATED} with an administrator's consent (docs/SAP-CSN.md section 4).")
    if kind == "missing":
        return f"Upload the CSN/JSON export to {DEFAULT_DIR}/ in the lakehouse, or pass csn_path with the folder or file under Files/."
    return "Try again; the plan was made without the CSN file."


def plan_with(schema, found: Found | None, make, keys=None, confirmed=None, **kwargs):
    """The plan of `schema`: with a CSN found in the lakehouse, csn.plan (its keys and links first, then `make`'s rules,
    which is infer.plan with the caller's options); else `make` alone. What was looked at in the lakehouse is kept on
    the plan (plan.csn["lakehouse"], or plan.csn_lakehouse when no file was used) for digest()."""
    if found is not None and found.model is not None:
        p, report = _csn.plan(schema, found.model, keys=keys, confirmed=confirmed, **kwargs)
        report["lakehouse"] = found.report()
        return p
    p = make(schema, keys, confirmed, **kwargs)
    if found is not None and found.worth_saying():
        try:
            p.csn_lakehouse = found.report()
        except AttributeError:
            pass
    return p


def digest(p, limit: int = 40) -> dict | None:
    """For a tool's answer: which file each CSN key and link came from, what was not applied, the amounts, and what was
    looked at in the lakehouse. None when the plan used no CSN and nothing is worth saying."""
    c = getattr(p, "csn", None)
    if not c:
        there = getattr(p, "csn_lakehouse", None)
        return {"provenance": _csn.PROVENANCE, "lakehouse": there} if there else None
    file_of = {m["table"]: m.get("file") for m in c.get("matched", {}).values()}
    keys = [{"table": t, "columns": cols, "rule": _csn.RULE, "file": file_of.get(t)} for t, cols in c.get("keys", {}).items()]
    links = [{"source": r["source"], "source_cols": r["source_cols"], "target": r["target"], "target_cols": r["target_cols"],
              "rule": _csn.RULE, "declared_in": [{"file": d["file"], "association": d["association"],
                                                  "cardinality": d["cardinality"]} for d in r["declared_in"]]}
             for r in c.get("links", [])]
    out = {"provenance": _csn.PROVENANCE, "status": c.get("status"), "files": c.get("files"),
           "keys": keys[:limit], "links": links[:limit],
           "not_applied": c.get("not_applied", [])[:limit],
           "amounts": [{k: a[k] for k in ("table", "column", "currency", "level") if k in a} for a in c.get("amounts", [])][:limit],
           "unmatched": c.get("unmatched", [])[:limit]}
    if len(keys) > limit or len(links) > limit:
        out["cut"] = f"the first {limit} keys and links are shown; plan.csn holds all"
    if c.get("lakehouse"):
        out["lakehouse"] = c["lakehouse"]
    return out
