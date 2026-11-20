"""DIR1 (20 November 2026): what the Claude connector directory's review asks of every tool answer, applied in one place.

Source: claude.com/docs/connectors/building/review-criteria (read 20 Nov 2026). Two of its rules concern the text a
tool answers with, not only its description:

- "Avoid prompt-injection patterns. Describe what the tool does, and don't tell Claude how to behave." Krusgraph's
  answers used to end in sentences addressed to the model ("Offer one next step: ...", "run create_data_agent with
  ...", "For the assistant, not for the user: please do not repeat ..."). Since DIR1 an answer describes options and
  facts for the user ("Possible next step: a dry run of the data agent (create_data_agent with name=...)"); the user
  and Claude choose. The cards' buttons still call the tools directly through the host bridge, so nothing changes for
  a person who presses a button.
- "Keep responses reasonably sized for the task." An answer whose JSON passes ANSWER_MAX characters has its longest
  texts (file contents: TMDL, SQL, notebooks) shortened to their first lines, each marked, and a `folded` note says
  which were shortened and how to get them whole (the same call narrowed with `tables`, which every drafting tool
  takes). Counts, names, keys, links and the evidence are never shortened.

The texts are written in their own modules (coach.py, start_flow.py, after_create.py, mcp_apps_next.py, ...); this
module holds the pattern the tests check them with (IMPERATIVE) and the last pass over an answer before it leaves the
server (`bounded`), so a phrase a future round writes the old way is made descriptive here too.
"""
from __future__ import annotations

import json
import re

# The hosted tools' names (mcp_apps_words.TOOLS_NAMED) plus `start`, which is a plain word elsewhere.
from .mcp_apps_words import TOOLS_NAMED

TOOLS = tuple(sorted(set(TOOLS_NAMED) | {"start"}, key=len, reverse=True))
_NAMES = "|".join(TOOLS)
# An instruction to the model to call a tool: "run validate_plan", "call start", "use the create_views tool",
# "Run requirements_draft on ...". A tool's name after "run" in the possessive ("run create_silver_notebook's notebook",
# a Fabric notebook) is not a tool call, and neither is a negation ("create_backend does not run `validate_plan`").
IMPERATIVE = re.compile(
    r"(?<!not\s)(?<!n't\s)\b(?:run|call|use|invoke|re-run|rerun)\s+(?:the\s+)?`?(?:" + _NAMES + r")\b(?!['’]s)`?"
    r"|\b(?:use|call)\s+the\s+`?\w+`?\s+tool\b",
    re.I)
# Sentences addressed to the model about how to reply. None of them may appear in an answer or a description.
DIRECTIVE = re.compile(
    r"For the assistant|Offer one next step|Say in one short sentence|follow its steps|offer that step, nothing more"
    r"|end with the one next step|Only if asked, also|please do not repeat|Please say only|please add no"
    r"|reply with one short sentence|do not send it again",
    re.I)

ANSWER_MAX = 40_000      # characters of an answer's JSON text; about 10,000 tokens
FOLD_MIN = 1_500         # a text shorter than this is never shortened
FOLD_KEEP = 600          # the characters a shortened text keeps
FOLD_MARK = "\n… [shortened by Krusgraph: {n} characters in all; the same call with fewer `tables` returns it whole]"


def neutral(text: str) -> str:
    """The text with each instruction to call a tool said as an option: "run validate_plan with x" becomes
    "validate_plan with x"; "use the X tool" becomes "the X tool". Anything else is left as it is."""
    if not isinstance(text, str) or not text:
        return text

    def one(m: re.Match) -> str:
        s = m.group(0)
        s = re.sub(r"^(?:run|call|use|invoke|re-run|rerun)\s+", "", s, flags=re.I)
        return s
    return IMPERATIVE.sub(one, text)


def _walk(value, fn):
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: _walk(v, fn) for k, v in value.items()}
    return value


def neutral_value(value):
    """neutral() on every string of a JSON value."""
    return _walk(value, neutral)


def _strings(value, path=()):
    """(path, length) of every string leaf."""
    if isinstance(value, str):
        yield path, len(value)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _strings(v, path + (i,))
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(v, path + (k,))


def _get(value, path):
    for p in path:
        value = value[p]
    return value


def _set(value, path, new):
    for p in path[:-1]:
        value = value[p]
    value[path[-1]] = new


def _size(value) -> int:
    return len(json.dumps(value, indent=2, default=str))         # as bounded() writes it (\\u escapes count)


def _lists(value, keep: int, path=()):
    """(path, items, characters) of every list of more than `keep` items."""
    if isinstance(value, list):
        if len(value) > keep:
            yield path, len(value), len(json.dumps(value, default=str))
        for i, v in enumerate(value):
            yield from _lists(v, keep, path + (i,))
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _lists(v, keep, path + (k,))


# The passes of fold(), gentlest first: (shortest text that is shortened, items a long list keeps)
STAGES = ((FOLD_MIN, 25), (800, 10), (400, 5))
LIST_KEEP = STAGES[0][1]


def fold(answer: dict, limit: int = ANSWER_MAX) -> dict:
    """The answer, fitted into `limit` characters of JSON, in passes from gentlest to firmest (STAGES): in each, the
    longest texts (file contents first) are shortened to their first lines, then the largest lists are cut to their
    first items, until the answer fits. A text is shortened only by as much as the answer is over the limit. The
    answer's `folded` says what was shortened and how long it was; the summary, the error and the counts that the
    answer states are untouched."""
    if not isinstance(answer, dict) or _size(answer) <= limit:
        return answer
    out = json.loads(json.dumps(answer, default=str))
    texts, lists = [], []
    for least, keep in STAGES:
        for path, n in sorted(((p, n) for p, n in _strings(out) if n >= least), key=lambda x: -x[1]):
            if _size(out) <= limit:
                break
            if not path or path[0] in ("summary", "error", "kind", "hint"):
                continue
            excess = _size(out) - limit + len(FOLD_MARK) + 50
            cut = max(min(FOLD_KEEP, least // 2), n - excess)      # only as much as the answer is over, at a line end
            text = _get(out, path)[:cut]
            if "\n" in text[cut // 2:]:
                text = text[:text.rindex("\n")]
            _set(out, path, text + FOLD_MARK.format(n=n))
            texts.append({"path": ".".join(str(p) for p in path), "characters": n})
        for _ in range(500):
            if _size(out) <= limit:
                break
            found = sorted(_lists(out, keep), key=lambda x: -x[2])
            if not found or not found[0][0]:
                break
            path, n, _chars = found[0]
            _set(out, path, _get(out, path)[:keep])
            lists.append({"path": ".".join(str(p) for p in path), "items": n, "kept": keep})
        if _size(out) <= limit:
            break
    if texts or lists:
        out["folded"] = {"texts": texts[:30], "lists": lists[:30],
                         "note": (f"This answer passed {limit:,} characters, so "
                                  + (f"{len(texts)} long texts are shortened to their first lines" if texts else "")
                                  + (" and " if texts and lists else "")
                                  + (f"{len(lists)} long lists keep their first items" if lists else "")
                                  + ". The summary and its counts cover everything. The same call with fewer `tables` "
                                    "returns it whole; shortening changed nothing in Fabric.")}
    return out


def bounded(text: str) -> str:
    """The last pass over a tool's text answer: instructions to call a tool said as options, and an answer longer than
    ANSWER_MAX folded. A text that is not a JSON object is only made neutral."""
    if not isinstance(text, str):
        return text
    try:
        data = json.loads(text)
    except ValueError:
        return neutral(text)
    if not isinstance(data, dict):
        return neutral(text)
    small = fold(neutral_value(data))
    if small == data:
        return text
    return json.dumps(small, indent=2, default=str)
