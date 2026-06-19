# -*- coding: utf-8 -*-
"""Connection-error detection and path helpers for ask-stage LLM clients."""
from __future__ import annotations

import os
import re

_CONN_ERR_PATTERNS = [
    r"\bconnection\s+error\b",
    r"\bconnection\s+failed\b",
    r"\bnetwork\s+error\b",
    r"\btimeout\b",
    r"\bread\s+timed\s*out\b",
    r"\bconnect\s+timed\s*out\b",
    r"\btemporarily\s+unavailable\b",
    r"\bservice\s+unavailable\b",
    r"\b502\b",
    r"\b503\b",
    r"\b504\b",
    r"\b429\b",
    r"rate\s*limit",
    r"too_many_requests",
    r"负载已饱和",
]

RESPONSE_FAILURE_KEYWORDS = [
    "请求错误",
    "失败",
    "错误",
    "通讯失败",
    "请求失败",
]


def is_connection_error_text(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    for pat in _CONN_ERR_PATTERNS:
        if re.search(pat, t):
            return True
    return False


def ensure_parent_file(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def response_has_failure_keywords(text: str) -> bool:
    if text is None:
        return False
    lower = text.lower()
    return any(keyword in lower for keyword in RESPONSE_FAILURE_KEYWORDS)


def strip_llm_timing_footer(text: str) -> str:
    lines = (text or "").splitlines()
    if lines and (
        lines[-1].startswith("total_elapsed_sec:")
        or lines[-1].startswith("Total time:")
        or "总耗时" in lines[-1]
    ):
        lines = lines[:-1]
    return "\n".join(lines)


def is_unusable_checker_response(text: str) -> bool:
    """True when checker output cannot yield diagnosis JSON (retry-worthy)."""
    body = strip_llm_timing_footer(text or "").strip()
    if not body:
        return True
    lower = body.lower()
    if lower in ("no diagnosis", "none", "n/a"):
        return True
    if len(body) < 32 and "no diagnosis" in lower:
        return True
    if is_connection_error_text(body):
        return True
    return False
