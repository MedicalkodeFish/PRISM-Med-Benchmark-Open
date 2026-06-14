#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clear base_ask failure markers so cases can be retried on the next base_ask run.

Rolls back progress by one batch (uses next_case_index; safe across BATCH_SIZE changes).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

LEGACY_ROOT = Path(__file__).resolve().parents[2]
if str(LEGACY_ROOT / "config") not in sys.path:
    sys.path.insert(0, str(LEGACY_ROOT / "config"))
if str(LEGACY_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(LEGACY_ROOT / "lib"))

from legacy_script_config import BASE_ASK_MODEL_LIST, ROUND_NUM_LIST  # noqa: E402
from base_ask_progress import (  # noqa: E402
    BASE_ASK_BATCH_SIZE,
    load_progress,
    next_case_index_from_progress,
    rollback_progress_file,
)


def _round_dirs(model_id: str, round_num: str) -> Path:
    return LEGACY_ROOT / "benchmark" / "result" / model_id / round_num


def clear_failures(model_id: str, round_num: str, *, dry_run: bool) -> int:
    out_dir = _round_dirs(model_id, round_num)
    if not out_dir.is_dir():
        print(f"Skip missing dir: {out_dir}")
        return 0
    n = 0
    for failed in sorted(out_dir.glob("*.failed.json")):
        stem = failed.name.replace(".failed.json", "")
        meta = out_dir / f"{stem}.meta.json"
        if dry_run:
            print(f"[dry-run] would remove {failed.name}" + (f" + {meta.name}" if meta.exists() else ""))
        else:
            failed.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)
        n += 1
    return n


def rollback_progress(round_num: str, *, dry_run: bool) -> None:
    progress = LEGACY_ROOT / "benchmark" / "result" / f"progress_round{round_num}.json"
    if not progress.is_file():
        return
    before = next_case_index_from_progress(load_progress(progress), total_cases=10**9)
    if dry_run:
        print(f"[dry-run] would roll back {progress.name} from index {before}")
        return
    if rollback_progress_file(progress, current_batch_size=BASE_ASK_BATCH_SIZE):
        after = next_case_index_from_progress(load_progress(progress), total_cases=10**9)
        print(f"Rolled back {progress.name}: next_case_index {before} -> {after}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear base_ask .failed.json and roll back one batch of progress")
    parser.add_argument("--model", default="", help="Model id under benchmark/result (default: BASE_ASK_MODEL_LIST)")
    parser.add_argument("--round", default="", help="Round folder e.g. 1_5answer (default: all rounds)")
    parser.add_argument("--no-progress-rollback", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    models = [args.model] if args.model else list(BASE_ASK_MODEL_LIST)
    rounds = [args.round] if args.round else list(ROUND_NUM_LIST)
    total = 0
    rolled = False
    for mid in models:
        mc_dir = LEGACY_ROOT / "benchmark" / "result" / mid
        if not mc_dir.is_dir() and not args.model:
            continue
        for rnd in rounds:
            n = clear_failures(mid, rnd, dry_run=args.dry_run)
            total += n
            if n and not args.no_progress_rollback and not rolled:
                rollback_progress(rnd, dry_run=args.dry_run)
                rolled = True
    print(f"Cleared failure markers: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
