"""v2 json_utils — stack-based JSON extraction utilities.

依據 §3.15 (JsonUtils) 定義：
- 全局設施（原則 24），所有模組可直接呼叫
- 純文本處理，不涉及 I/O，不包 Result
"""

from __future__ import annotations

import json
from typing import Any, List


def _is_string_boundary(text: str, pos: int) -> bool:
    """Check whether *pos* points to a ``"`` that is a string delimiter,
    not just a character inside text.
    """
    if text[pos] != '"':
        return False

    i = pos - 1
    while i >= 0 and text[i] == '\\':
        i -= 1
    if i >= 0 and text[i] == '"':
        i -= 1
    backslash_count = 0
    while i >= 0 and text[i] == '\\':
        backslash_count += 1
        i -= 1
    return backslash_count % 2 == 0


def _skip_string(text: str, pos: int) -> int:
    """Skip past a JSON string starting at *pos* (which points to the opening ``"``).

    Returns the index of the closing ``"``.
    """
    i = pos + 1
    while i < len(text):
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if c == '"':
            return i
        i += 1
    return len(text)


def parse_first_json(text: str) -> Any | None:
    """Parse and return the first JSON value found in *text*.

    Convenience wrapper around extract_first_json.
    Returns ``None`` on extraction or parsing failure.
    """
    raw = _extract_first_json(text)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_all_jsons(text: str) -> List[Any]:
    """Parse **all** top-level JSON values found in *text*.

    Convenience wrapper around _extract_all_jsons.
    Returns an empty list on any failure.
    """
    raws = _extract_all_jsons(text)
    results: List[Any] = []
    for raw in raws:
        try:
            results.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return results


def dump_json_str(obj: Any, indent: int | None = None) -> str:
    """Dump *obj* to a JSON string.

    Convenience wrapper around :func:`json.dumps`.
    """
    return json.dumps(obj, indent=indent, ensure_ascii=False)


# ── 私有函式 ──

def _extract_first_json(text: str) -> str | None:
    """Extract the **first** complete JSON value (object or array) from *text*.

    Returns the JSON string on success, ``None`` otherwise.
    """
    if not text:
        return None

    for i, ch in enumerate(text):
        if ch == '{' or ch == '[':
            start_char = ch
            depth = 0
            start = i
            j = i
            while j < len(text):
                c = text[j]
                if c == '"':
                    if _is_string_boundary(text, j):
                        j = _skip_string(text, j) + 1
                        continue
                    j += 1
                    continue
                if c == start_char:
                    depth += 1
                elif c == ('}' if start_char == '{' else ']'):
                    depth -= 1
                    if depth == 0:
                        return text[start:j + 1]
                j += 1
    return None


def _extract_all_jsons(text: str) -> List[str]:
    """Extract **all** top-level JSON values (objects / arrays) from *text*.

    Useful when LLM returns multiple JSON objects side-by-side.
    Returns an empty list if nothing is found.
    """
    if not text:
        return []

    results: List[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '{' or ch == '[':
            start_char = ch
            depth = 0
            start = i
            j = i
            while j < len(text):
                c = text[j]
                if c == '"' and _is_string_boundary(text, j):
                    j += 1
                    while j < len(text):
                        if text[j] == '\\' and j + 1 < len(text):
                            j += 1
                        elif text[j] == '"':
                            break
                        else:
                            j += 1
                    j += 1
                    continue
                if c == start_char:
                    depth += 1
                elif c == ('}' if start_char == '{' else ']'):
                    depth -= 1
                    if depth == 0:
                        results.append(text[start:j + 1])
                        i = j + 1
                        break
                j += 1
            else:
                i += 1
                continue
            i = j + 1
        else:
            i += 1
    return results
