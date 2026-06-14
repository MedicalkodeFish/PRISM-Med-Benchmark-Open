from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Iterable, Sequence

from .steps import Step, run_step


def run_pipeline(
    *,
    steps: Iterable[Step],
    python_executable: str,
    legacy_root: Path,
    selected_step_ids: Sequence[str] | None = None,
    continue_on_error: bool = False,
    run_manifest_path: Path | None = None,
) -> dict:
    selected = set(selected_step_ids or [])
    report = {
        "started_at": datetime.utcnow().isoformat() + "Z",
        "legacy_root": str(legacy_root),
        "python_executable": python_executable,
        "selected_steps": list(selected_step_ids or []),
        "continue_on_error": continue_on_error,
        "steps": [],
        "status": "running",
    }
    failed = False
    for step in steps:
        if not step.enabled:
            continue
        if selected and step.id not in selected:
            continue
        start = perf_counter()
        entry = {
            "id": step.id,
            "description": step.description,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "status": "running",
        }
        try:
            run_step(step, python_executable=python_executable, legacy_root=legacy_root)
            entry["status"] = "success"
        except Exception as e:
            failed = True
            entry["status"] = "failed"
            entry["error"] = str(e)
            entry["traceback"] = traceback.format_exc()
            report["steps"].append(entry)
            entry["elapsed_seconds"] = round(perf_counter() - start, 3)
            entry["finished_at"] = datetime.utcnow().isoformat() + "Z"
            if not continue_on_error:
                report["status"] = "failed"
                report["finished_at"] = datetime.utcnow().isoformat() + "Z"
                if run_manifest_path:
                    run_manifest_path.parent.mkdir(parents=True, exist_ok=True)
                    with run_manifest_path.open("w", encoding="utf-8") as f:
                        json.dump(report, f, ensure_ascii=False, indent=2)
                raise
        entry["elapsed_seconds"] = round(perf_counter() - start, 3)
        entry["finished_at"] = datetime.utcnow().isoformat() + "Z"
        report["steps"].append(entry)

    report["status"] = "failed" if failed else "success"
    report["finished_at"] = datetime.utcnow().isoformat() + "Z"
    if run_manifest_path:
        run_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with run_manifest_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report

