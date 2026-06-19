# -*- coding: utf-8 -*-
"""Resolve base_ask answer files (supports re-ask filenames like case_ask1.txt)."""
from __future__ import annotations

import json
import os
import re
from typing import Iterable, Optional

from benchmark_sdoh_utils import load_json as load_json_file
from llm_connection_utils import strip_llm_timing_footer


def base_file_txt_from_stem(case_stem: str) -> str:
    return f"{case_stem}.txt"


def meta_json_path(result_dir: str, case_stem: str) -> str:
    return os.path.join(result_dir, f"{case_stem}.meta.json")


def load_case_meta(result_dir: str, case_stem: str) -> Optional[dict]:
    return load_json_file(meta_json_path(result_dir, case_stem))


def _reask_answer_filenames(result_dir: str, case_stem: str) -> list[str]:
    prefix = f"{case_stem}_ask"
    names: list[str] = []
    try:
        for name in os.listdir(result_dir):
            if name.startswith(prefix) and name.endswith(".txt"):
                names.append(name)
    except OSError:
        return []
    def _attempt_idx(filename: str) -> int:
        m = re.match(rf"^{re.escape(case_stem)}_ask(\d+)\.txt$", filename)
        return int(m.group(1)) if m else 0
    return sorted(names, key=_attempt_idx, reverse=True)


def resolve_latest_answer_filename(result_dir: str, case_stem: str) -> Optional[str]:
    """
    Return the answer .txt basename under result_dir for this case, or None if missing.
    Uses meta.json latest_answer_file when present (re-ask attempts).
    """
    base_file = base_file_txt_from_stem(case_stem)
    meta = load_case_meta(result_dir, case_stem) or {}
    candidates = []
    latest = meta.get("latest_answer_file")
    if latest:
        candidates.append(latest)
    candidates.append(base_file)
    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        if os.path.isfile(os.path.join(result_dir, name)):
            return name
    for name in _reask_answer_filenames(result_dir, case_stem):
        if os.path.isfile(os.path.join(result_dir, name)):
            return name
    return None


def resolve_latest_answer_path(result_dir: str, case_stem: str) -> Optional[str]:
    name = resolve_latest_answer_filename(result_dir, case_stem)
    if not name:
        return None
    return os.path.join(result_dir, name)


def iter_case_stems_with_answer(result_dir: str, case_stems: Iterable[str]) -> list[str]:
    """Case stems that have a readable answer file in result_dir."""
    if not os.path.isdir(result_dir):
        return []
    out: list[str] = []
    for stem in case_stems:
        if resolve_latest_answer_filename(result_dir, stem):
            out.append(stem)
    return out


def read_answer_analysis(result_dir: str, case_stem: str) -> Optional[str]:
    path = resolve_latest_answer_path(result_dir, case_stem)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return strip_llm_timing_footer(f.read())
    except OSError:
        return None
