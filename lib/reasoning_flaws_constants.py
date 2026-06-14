# -*- coding: utf-8 -*-
"""Shared constants and small helpers for reasoning flaw judges."""
from __future__ import annotations

from typing import Any

from async_runtime import apply_windows_proactor_event_loop_policy

HALLUCINATION_TYPES = [
    "Factual Inconsistency",
    "Unsupported Inference",
    "Missing Key Premise",
    "Over-certainty",
    "Logical Contradiction",
]


def make_json_serializable(obj: Any) -> Any:
    """Recursively convert object to a JSON-serializable structure."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [make_json_serializable(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return make_json_serializable(vars(obj))
    return str(obj)
