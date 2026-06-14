from __future__ import annotations

import sys
from pathlib import Path

from prism_benchmark.legacy_registry import ROUND_NUM_LIST, get_legacy_script_path
from prism_benchmark.stages._invoke import invoke_legacy_main


def _ensure_required_files(legacy_root: Path) -> None:
    required = [
        get_legacy_script_path(legacy_root, "base_ask"),
        legacy_root / "lib" / "extract_json_from_txt.py",
        legacy_root / "dataset" / "question" / "query_question.xlsx",
        legacy_root / "prompt" / "benchmark.txt",
        legacy_root / "prompt" / "formatChecker_noprompt_5answer.txt",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required files for base_ask stage:\n" + "\n".join(missing))


def _verify_round_outputs(legacy_root: Path) -> None:
    legacy_root_str = str(legacy_root.resolve())
    if legacy_root_str not in sys.path:
        sys.path.insert(0, legacy_root_str)
    from legacy_script_config import BASE_ASK_MODEL_LIST
    from prism_benchmark.stages._model_scope import iter_scoped_model_dirs, model_ids_for_env_list

    result_root = legacy_root / "benchmark" / "result"
    if not result_root.exists():
        raise RuntimeError("benchmark/result not found after base_ask stage.")
    model_ids = model_ids_for_env_list(legacy_root, BASE_ASK_MODEL_LIST)
    if not model_ids:
        raise RuntimeError("No configured base_ask models resolved from model_config.")
    missing = []
    for model_dir in iter_scoped_model_dirs(legacy_root, model_ids):
        for r in ROUND_NUM_LIST:
            p = model_dir / f"{r}_output_json"
            if not p.exists() or not any(p.glob("*.json")):
                missing.append(f"{model_dir.name}/{r}_output_json (no *.json)")
    if missing:
        raise RuntimeError("Missing base_ask outputs for configured models:\n" + "\n".join(missing))


def run(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    _ensure_required_files(legacy_root)
    invoke_legacy_main(legacy_root, "base_ask")
    _verify_round_outputs(legacy_root)
    print("base_ask stage completed and outputs verified.")
