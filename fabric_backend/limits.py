"""Fair-use limits per signed-in user (Entra `oid`) and per organisation (`tid`) on the hosted server.

A limit is "N calls per window"; each one is a token bucket that holds N calls and refills at N per window, so a burst
up to N is fine and the steady rate is N per window. A call goes through only when every bucket of the user and of the
organisation has a call left; it then takes one from each. A refused call costs nothing and says when the first bucket
that refused it has a call again.

Only tool calls count (the server checks inside the tool wrapper, after the 401 guard has accepted the token):
`initialize`, `tools/list`, the site and the sign-in flow are never limited, and a request without a valid token still
gets the 401 Claude starts sign-in on. In memory per replica: with `maxReplicas` 2 a user can reach up to twice the
limit for a moment. The keys are SHA-256 hashes of the ids with a salt drawn when the process starts, so the table
holds no ids in clear and nothing about it is written anywhere.

Configuration (environment):
  KRUSGRAPH_RATE_LIMITS   "0" (or off/false/no) turns the limits off; on by default in Entra mode
  KRUSGRAPH_RATE_USER     per user, default "30/minute,600/hour"
  KRUSGRAPH_RATE_ORG      per organisation, default "120/minute,3000/hour"
"""
from __future__ import annotations

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
        if not m or m.group(3) not in _UNITS or int(m.group(1)) < 1:
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
            levels = []
            for scope, key, i, calls, window in wanted:
                left, at = self._buckets.get((scope, key, i), (float(calls), now))
                left = min(float(calls), left + (now - at) * calls / window)
                if left < 1.0:
                    wait = (1.0 - left) * window / calls
                    return {"scope": scope, "limit": _words(calls, window), "retry_after": max(1, math.ceil(wait))}
                levels.append(((scope, key, i), left))
            for k, left in levels:
                self._buckets[k] = (left - 1.0, now)
            if len(self._buckets) > MAX_KEYS:
                self._prune(now)
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
