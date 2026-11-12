"""One time budget per call (n226, SCOPE-REVIEW section 6, mechanism 2).

Every tool call that reads gets one deadline, CALL_SECONDS after it starts, set here and nowhere else. The deadline is
passed by a context variable, so the plan (infer.py's R5 counting), every counting query (evidence.validate, amounts,
the column profile) and every SQL read (platforms/fabric.py: the statement timeout is cut to what is left) see the same
clock without a new argument on each function.

What happens when it runs out:
- before a read starts: the read is not started (TimeUp); a tool that has nothing yet answers {error, kind: "time"}
  with what to narrow;
- in the check: the items counted so far are returned; every other item says NOT_CHECKED, and the answer carries the
  call that resumes (validate_plan's `resume_from`);
- in the plan's R5: the candidates not reached are proposed, "not checked (time)", never applied.

A query that fails for any other reason becomes "not counted: <reason>" for its item; the call goes on.

A creating call (dry_run=false) is not bounded: cutting an item half created is worse than a slow answer, and its own
waits (capacity, long-running operations) have their own limits in deploy.py. Its plan is still made under no deadline
then, exactly as before.

Nothing here measures or promises a speed: CALL_SECONDS is a ceiling on waiting, not a claim about how long a call
takes.
"""
from __future__ import annotations

import contextvars
import math
import os
import time
from contextlib import contextmanager

from .errors import TimeLimit

# About 45 s: below the client tool timeouts seen so far (the four-minute cancel in SCOPE-REVIEW section 2 is unverified),
# and long enough for a few dozen counting statements on a warm endpoint. One place; KRUSGRAPH_CALL_SECONDS overrides it.
CALL_SECONDS = 45.0
MIN_STATEMENT_SECONDS = 5          # a statement started with less than this left still gets this long (the driver's floor)

NOT_CHECKED = "not checked (time)"


def call_seconds() -> float:
    try:
        v = float(os.environ.get("KRUSGRAPH_CALL_SECONDS", "") or CALL_SECONDS)
    except ValueError:
        v = CALL_SECONDS
    return v if v > 0 else CALL_SECONDS


class TimeUp(TimeLimit):
    """The call's time budget ran out before a read could start (errors.explain: kind "time_limit")."""

    def __init__(self, seconds: float, what: str = ""):
        self.seconds = seconds
        self.what = what
        super().__init__(f"the time budget of {seconds:g} s for this call ran out" + (f" before {what}" if what else ""))


class Deadline:
    """`seconds` from now on `clock` (time.monotonic; the tests pass their own)."""

    def __init__(self, seconds: float | None = None, clock=None):
        self.clock = clock or time.monotonic
        self.seconds = float(seconds if seconds is not None else call_seconds())
        self.start = self.clock()

    def used(self) -> float:
        return max(0.0, self.clock() - self.start)

    def remaining(self) -> float:
        return self.seconds - self.used()

    def expired(self) -> bool:
        return self.remaining() <= 0

    def as_dict(self) -> dict:
        """For an answer: the budget, and the seconds used only once it ran out (a measured time is not a promise)."""
        return {"seconds": self.seconds, **({"used": round(self.used(), 1)} if self.expired() else {})}


_CURRENT: contextvars.ContextVar[Deadline | None] = contextvars.ContextVar("krusgraph_deadline", default=None)


def current() -> Deadline | None:
    return _CURRENT.get()


@contextmanager
def call(seconds: float | None = None, clock=None, bounded: bool = True):
    """The deadline of one call. Nested calls keep the outer deadline (a tool that calls a tool has one budget).
    bounded=False (a creating call) runs with no deadline at all, also for what it calls."""
    if _CURRENT.get() is not None and bounded:
        yield _CURRENT.get()
        return
    token = _CURRENT.set(Deadline(seconds, clock) if bounded else None)
    try:
        yield _CURRENT.get()
    finally:
        _CURRENT.reset(token)


def expired() -> bool:
    d = _CURRENT.get()
    return d is not None and d.expired()


def check(what: str = "") -> None:
    """Raise TimeUp when the call's budget is spent: before a read, never in the middle of one."""
    d = _CURRENT.get()
    if d is not None and d.expired():
        raise TimeUp(d.seconds, what)


def statement_timeout(default: int) -> int:
    """The per-statement timeout for the next SQL read: the connection's own, cut to what is left of the call."""
    d = _CURRENT.get()
    if d is None:
        return default
    return int(max(MIN_STATEMENT_SECONDS, min(default, math.ceil(d.remaining()))))


def http_timeout(default: float) -> float:
    """The timeout of the next REST read, cut the same way."""
    d = _CURRENT.get()
    if d is None:
        return default
    return float(max(MIN_STATEMENT_SECONDS, min(default, math.ceil(d.remaining()))))


def ran_out() -> dict | None:
    """For an answer: the budget and what was used, when this call has one."""
    d = _CURRENT.get()
    return None if d is None else d.as_dict()
