# -*- coding: utf-8 -*-
"""Bounded helpers to detect bad LLM answer files (no infinite retry loops)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

# Substrings that indicate a failed API / gateway response saved as .txt
FAILURE_KEYWORDS = (
    "失败",
    "错误",
    "通讯失败",
    "请求失败",
    "rate limit",
    "timeout",
    "timed out",
    "connection error",
    "internal server error",
)

DEFAULT_MIN_ANSWER_CHARS = 50
# Extra full sweeps over *only incomplete* cases at end of a stage (hard-capped).
TAIL_PASS_HARD_MAX = 2


def tail_pass_limit(env_key: str, *, default: int = 1) -> int:
    """Read PRISM_* tail pass count; 0 disables, never above TAIL_PASS_HARD_MAX."""
    raw = os.environ.get(env_key, str(default))
    try:
        n = int(raw)
    except ValueError:
        n = default
    return max(0, min(n, TAIL_PASS_HARD_MAX))


def read_answer_text(path: str | Path) -> Optional[str]:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def text_indicates_llm_failure(text: str) -> bool:
    if not text or not str(text).strip():
        return True
    lower = text.lower()
    for kw in FAILURE_KEYWORDS:
        if kw in text or kw in lower:
            return True
    return False


def answer_txt_is_usable(
    txt_path: str | Path,
    *,
    min_chars: int = DEFAULT_MIN_ANSWER_CHARS,
) -> bool:
    content = read_answer_text(txt_path)
    if content is None:
        return False
    if len(content.strip()) < min_chars:
        return False
    return not text_indicates_llm_failure(content)


def remove_file_quiet(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def should_regenerate_answer_txt(
    txt_path: str | Path,
    *,
    json_path: str | Path | None = None,
    json_is_valid: Optional[Callable[[str | Path], bool]] = None,
    min_chars: int = DEFAULT_MIN_ANSWER_CHARS,
) -> bool:
    """
    True => caller should call the LLM again for this artifact.

    If json_path is given and validates, never regenerate (stage is complete).
    If txt is usable but json is missing/invalid, do not regenerate txt (checker pass only).
    """
    if json_path is not None and json_is_valid is not None and json_is_valid(json_path):
        return False
    if not Path(txt_path).is_file():
        return True
    if not answer_txt_is_usable(txt_path, min_chars=min_chars):
        return True
    return False
