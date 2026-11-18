"""WB10 (Gustav's live test in Fabric, 18 Nov 2026, issue #57): downloads from the Model editor inside Fabric's frame.

Fabric hosts a workload's editor in an iframe whose default sandbox is `allow-same-origin allow-scripts` (Microsoft
Learn, "How to relax the iFrame", learn.microsoft.com/fabric/extensibility-toolkit/how-to-relax-iframe, ms.date
12/15/2025): no `allow-downloads` and no `allow-popups`, so a `data:` link with `download`, a blob URL and window.open
do nothing. Relaxing it needs `EnableSandboxRelaxation` in the workload manifest and a consent from every user, and the
manifest is not changed here. What remains documented is the host's own `workloadClient.navigation.openBrowserTab`
(@ms-fabric/workload-client 3.1.1, "Opens a new browser tab"): the tab is opened by Fabric, outside the sandbox.

So the editor sends the file it would have offered to POST /workload/v1/file and opens the answer's URL with
openBrowserTab. The URL serves the file once with Content-Disposition: attachment:

- short-lived: the record expires after TTL seconds (10 minutes); the URL's expiry is signed with it;
- single-use: the first GET takes the record (a read and a delete in one step in the shared store, so this holds across
  the service's replicas, registration_store.py) and a second GET answers 410;
- signed: /workload/v1/file/<id>.<expiry>.<signature>, the id random (144 bits), the signature an HMAC of id and expiry
  with the server's key; nothing of the file is in the URL;
- nothing personal in logs: the routes log sizes and outcomes only, never the file name or content.

The record lives in the operations store (operations.store(): Table Storage on the hosted service, memory in tests) as
kind "op" with the key prefix "file-", compressed and cut into parts that fit a Table Storage property."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
import zlib

KIND = "op"                      # the operations store's record kind; the "file-" key prefix keeps these apart
TTL = 600                        # seconds: the link works for ten minutes
CHUNK = 24_000                   # characters per part, under Table Storage's 64 KiB (UTF-16) per property
MAX_BYTES = 6 * 1024 * 1024      # the largest file offered this way (the App package is the largest, well under it)
MIMES = {"application/json", "application/yaml", "application/zip", "application/x-ipynb+json", "application/xml",
         "application/vnd.jgraph.mxfile",
         "text/markdown", "text/plain", "text/csv", "text/x-python"}
_TOKEN = re.compile(r"^([A-Za-z0-9_-]{24})\.(\d{1,12})\.([A-Za-z0-9_-]{22})$")
_NAME_BAD = re.compile(r"[^A-Za-z0-9._ -]+")


class FileError(ValueError):
    """A file the route does not offer (too big, an unknown type, an empty name)."""


def _key() -> bytes:
    return (os.environ.get("KRUSGRAPH_SERVER_KEY", "") or "krusgraph-file-links").encode()


def _sign(file_id: str, exp: int) -> str:
    mac = hmac.new(_key(), f"file|{file_id}|{exp}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")[:22]


def safe_name(name: str) -> str:
    """A file name for Content-Disposition: letters, digits, dot, dash, underscore and space; the folder dropped."""
    base = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    clean = _NAME_BAD.sub("-", base).strip(" .-")[:120]
    return clean or "krusgraph-file"


def _store():
    from . import operations
    return operations.store()


def offer(content: bytes, filename: str, mime: str, now: float | None = None) -> dict:
    """Keeps the file for TTL seconds and answers the path that serves it once: {"path", "expires_at", "expires_in",
    "filename", "bytes"}."""
    if mime not in MIMES:
        raise FileError(f"files of type {mime!r} are not offered")
    if not content:
        raise FileError("the file is empty")
    if len(content) > MAX_BYTES:
        raise FileError(f"the file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    name = safe_name(filename)
    now = time.time() if now is None else now
    exp = int(now) + TTL
    file_id = secrets.token_urlsafe(18)
    text = base64.urlsafe_b64encode(zlib.compress(content, 6)).decode()
    parts = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)]
    s = _store()
    for n, part in enumerate(parts):
        s.put(KIND, f"file-{file_id}-p{n}", {"part": part}, ttl=TTL)
    s.put(KIND, f"file-{file_id}", {"filename": name, "mime": mime, "parts": len(parts), "exp": exp}, ttl=TTL)
    return {"path": f"/workload/v1/file/{file_id}.{exp}.{_sign(file_id, exp)}",
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(exp)), "expires_in": TTL,
            "filename": name, "bytes": len(content)}


def take(token: str, now: float | None = None) -> tuple[bytes, str, str] | str:
    """The file for a token, once: (content, filename, mime); else why not: "bad", "expired" or "gone"."""
    m = _TOKEN.match(str(token or ""))
    if not m:
        return "bad"
    file_id, exp, sig = m.group(1), int(m.group(2)), m.group(3)
    if not hmac.compare_digest(sig, _sign(file_id, exp)):
        return "bad"
    if (time.time() if now is None else now) > exp:
        return "expired"
    s = _store()
    head = s.take(KIND, f"file-{file_id}")
    if head is None:
        return "gone"
    parts = []
    for n in range(int(head.get("parts") or 0)):
        got = s.take(KIND, f"file-{file_id}-p{n}")
        if got is None:
            return "gone"
        parts.append(got["part"])
    return zlib.decompress(base64.urlsafe_b64decode("".join(parts).encode())), head["filename"], head["mime"]


def disposition(filename: str) -> str:
    """Content-Disposition: attachment, with the name as ASCII and as RFC 5987 UTF-8."""
    from urllib.parse import quote
    name = safe_name(filename)
    return f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
