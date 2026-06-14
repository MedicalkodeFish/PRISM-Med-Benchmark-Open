from __future__ import annotations

import sys
from pathlib import Path

from prism_benchmark.legacy_registry import ROUND_NUM_LIST
from prism_benchmark.stages._invoke import invoke_legacy_main


def _verify_classification_outputs(legacy_root: Path, *, expect_summary: bool) -> None:
    legacy_root_str = str(legacy_root.resolve())
    if legacy_root_str not in sys.path:
        sys.path.insert(0, legacy_root_str)
    from legacy_script_config import CLASSIFICATION_MODEL_LIST
    from prism_benchmark.stages._model_scope import iter_scoped_model_dirs, model_ids_for_env_list

    result_root = legacy_root / "benchmark" / "result"
    if not result_root.exists():
        raise RuntimeError("benchmark/result not found after classification run.")
    model_ids = model_ids_for_env_list(legacy_root, CLASSIFICATION_MODEL_LIST)
    missing = []
    for model_dir in iter_scoped_model_dirs(legacy_root, model_ids):
        for r in ROUND_NUM_LIST:
            sub = "llm_responses_summary" if expect_summary else "llm_responses_1"
            out_dir = model_dir / f"{r}_{sub}"
            if not out_dir.exists():
                missing.append(str(out_dir))
                continue
            n_json = len(list(out_dir.glob("*_classification.json")))
            if n_json < 1:
                missing.append(f"{out_dir} (no *_classification.json)")
    if missing:
        raise RuntimeError("Missing classification output paths:\n" + "\n".join(missing[:30]))


def run_round_classification(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "classification_round")
    _verify_classification_outputs(legacy_root, expect_summary=False)
    print("classification (round-level) completed and outputs verified.")


def run_summary_classification(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "classification_summary")
    _verify_classification_outputs(legacy_root, expect_summary=True)
    print("classification (summary-level) completed and outputs verified.")
