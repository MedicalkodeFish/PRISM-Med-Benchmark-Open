"""Parse reasoning-judge LLM output into audit JSON (tolerates minor formatting errors)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

VALID_RATINGS = frozenset(
    {
        "Logically Sound",
        "Minor Reasoning Issues",
        "Significant Reasoning Hallucinations",
    }
)


def _json_candidates(text: str) -> List[str]:
    out: List[str] = []
    if not text:
        return out
    t = text.strip()
    if t:
        out.append(t)
    m = re.search(r"```json\s*([\s\S]*?)\s*```", t, re.IGNORECASE)
    if m:
        out.append(m.group(1).strip())
    m = re.search(r"```\s*([\s\S]*?)\s*```", t)
    if m:
        out.append(m.group(1).strip())
    m = re.search(r"\{[\s\S]*\}", t)
    if m:
        out.append(m.group(0))
    # De-duplicate while preserving order
    seen = set()
    uniq: List[str] = []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _salvage_minimal(text: str) -> Optional[Dict[str, Any]]:
    rating_m = re.search(
        r'"rating"\s*:\s*"(Logically Sound|Minor Reasoning Issues|Significant Reasoning Hallucinations)"',
        text,
    )
    if not rating_m:
        return None
    summary_m = re.search(r'"audit_summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    audit_summary = ""
    if summary_m:
        try:
            audit_summary = json.loads(f'"{summary_m.group(1)}"')
        except json.JSONDecodeError:
            audit_summary = summary_m.group(1).replace("\\n", "\n")
    return {
        "audit_summary": audit_summary,
        "rating": rating_m.group(1),
        "identified_hallucinations": [],
    }


def parse_reasoning_audit_response(text: str) -> Optional[Dict[str, Any]]:
    """Return audit dict or None if nothing usable could be extracted."""
    for cand in _json_candidates(text):
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("rating") in VALID_RATINGS:
            obj.setdefault("identified_hallucinations", [])
            obj.setdefault("audit_summary", "")
            return obj
    return _salvage_minimal(text)


def parse_reasoning_audit_from_full_record(full_path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    texts: List[str] = []
    rt = payload.get("response_text")
    if isinstance(rt, str) and rt.strip():
        texts.append(rt)
    raw = payload.get("raw_result")
    if isinstance(raw, dict):
        for ch in raw.get("choices") or []:
            msg = ch.get("message") or {}
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                texts.append(content)
    for t in texts:
        parsed = parse_reasoning_audit_response(t)
        if parsed:
            return parsed
    return None
