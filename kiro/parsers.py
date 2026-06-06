"""Parsing utilities for LLM output post-processing."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Brace / bracket matching
# ---------------------------------------------------------------------------

def find_matching_brace(text: str, start: int = 0) -> int:
    """Return the index of the closing ``}`` that matches the ``{`` at *start*.

    Returns ``-1`` if *start* does not point at ``{`` or the brace is
    unclosed.
    """
    if start >= len(text) or text[start] != "{":
        return -1
    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_json_objects(text: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            end = find_matching_brace(text, i)
            if end != -1:
                fragment = text[i : end + 1]
                try:
                    results.append(json.loads(fragment))
                except json.JSONDecodeError:
                    pass
                i = end + 1
                continue
        i += 1
    return results


def extract_first_json(text: str) -> Optional[Dict[str, Any]]:
    objs = extract_json_objects(text)
    return objs[0] if objs else None


# ---------------------------------------------------------------------------
# Markdown code-fence stripping
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(
    r"^```[\w]*\n?(.+?)\n?```$",
    re.DOTALL | re.MULTILINE,
)


def strip_code_fences(text: str) -> str:
    m = _CODE_FENCE_RE.search(text.strip())
    return m.group(1).strip() if m else text.strip()


def parse_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return extract_first_json(cleaned)
