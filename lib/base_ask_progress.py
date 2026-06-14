# -*- coding: utf-8 -*-
"""base_ask round progress (resume across BATCH_SIZE changes)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

LEGACY_DEFAULT_BATCH_SIZE = 2
BASE_ASK_BATCH_SIZE = 5


def load_progress(path: str | Path) -> Optional[Dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def next_case_index_from_progress(
    prog: Optional[Dict[str, Any]],
    *,
    total_cases: int,
) -> int:
    """Index in [0, total_cases) to start the next batch."""
    if not prog:
        return 0
    if "next_case_index" in prog:
        idx = int(prog["next_case_index"])
        return max(0, min(idx, total_cases))
    old_batch = int(prog.get("batch_size", LEGACY_DEFAULT_BATCH_SIZE))
    last_batch = int(prog.get("last_completed_batch", -1))
    if last_batch < 0:
        return 0
    return max(0, min((last_batch + 1) * old_batch, total_cases))


def contiguous_complete_prefix_end(
    total_cases: int,
    needs_work,
) -> int:
    """Largest `end` such that every index in [0, end) has valid outputs (no work needed)."""
    end = 0
    while end < total_cases and not needs_work(end):
        end += 1
    return end


def list_incomplete_case_indices(total_cases: int, needs_work) -> list[int]:
    return [i for i in range(total_cases) if needs_work(i)]


def plan_base_ask_resume(
    *,
    total_cases: int,
    needs_work,
    prog: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build work queue from on-disk targets (via needs_work callback).
    Progress file is a hint only; incomplete indices always come from file scan.
    """
    incomplete = list_incomplete_case_indices(total_cases, needs_work)
    prefix_end = contiguous_complete_prefix_end(total_cases, needs_work)
    prog_hint = next_case_index_from_progress(prog, total_cases=total_cases)
    return {
        "work_queue": incomplete,
        "complete_prefix_end": prefix_end,
        "incomplete_count": len(incomplete),
        "progress_hint_index": prog_hint,
    }


def build_progress_payload(
    *,
    next_case_index: int,
    batch_size: int,
    total_cases: int,
    batch_start: int,
) -> Dict[str, Any]:
    total_batches = (total_cases + batch_size - 1) // batch_size
    current_batch = batch_start // batch_size
    return {
        "next_case_index": next_case_index,
        "batch_size": batch_size,
        "total_cases": total_cases,
        "last_completed_batch": current_batch,
        "total_batches": total_batches,
    }


def rollback_progress_data(
    data: Dict[str, Any],
    *,
    current_batch_size: int,
) -> Dict[str, Any]:
    """Move checkpoint back by one batch (for retry after failures)."""
    if "next_case_index" in data:
        step = int(data.get("batch_size", current_batch_size))
        idx = int(data["next_case_index"])
        new_idx = max(0, idx - step)
        data["next_case_index"] = new_idx
        data["batch_size"] = current_batch_size
        if new_idx == 0:
            data["last_completed_batch"] = -1
        else:
            data["last_completed_batch"] = (new_idx - 1) // current_batch_size
        return data
    batch = int(data.get("last_completed_batch", 0))
    if batch <= 0:
        return data
    old_bs = int(data.get("batch_size", LEGACY_DEFAULT_BATCH_SIZE))
    new_batch = batch - 1
    data["last_completed_batch"] = new_batch
    data["next_case_index"] = max(0, (new_batch + 1) * old_bs)
    data["batch_size"] = current_batch_size
    return data


def write_progress(path: str | Path, payload: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def rollback_progress_file(
    path: str | Path,
    *,
    current_batch_size: int,
) -> bool:
    prog = load_progress(path)
    if not prog:
        return False
    updated = rollback_progress_data(prog, current_batch_size=current_batch_size)
    write_progress(path, updated)
    return True
