from __future__ import annotations

import sys
from pathlib import Path

from prism_benchmark.legacy_registry import ROUND_NUM_LIST
from prism_benchmark.pathing import resolve_benchmark_dir_from_legacy
from prism_benchmark.stages._invoke import invoke_legacy_main


def _ensure_legacy_path(legacy_root: Path) -> None:
    root = str(legacy_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def _verify_count_stage(legacy_root: Path, *, mode: str) -> None:
    _ensure_legacy_path(legacy_root)
    from legacy_script_config import COUNT_TARGET_MODEL_LIST
    from count_stage_health import assert_count_stages_complete
    from prism_benchmark.stages._model_scope import model_ids_for_env_list

    model_ids = model_ids_for_env_list(legacy_root, COUNT_TARGET_MODEL_LIST)
    assert_count_stages_complete(legacy_root, model_ids, ROUND_NUM_LIST, modes=(mode,))


def run_base_count(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "base_count")
    _verify_count_stage(legacy_root, mode="base")
    print("base_count stage completed and outputs verified.")


def run_bias_metrics(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "bias_metrics")
    p = legacy_root / "Bias_Analysis_Summary.xlsx"
    if not p.exists():
        raise RuntimeError(f"Missing bias metrics output: {p}")
    print("bias_metrics stage completed and outputs verified.")


def run_classification_vote(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "classification_vote")
    cands = [legacy_root / "benchmark", legacy_root.parent / "benchmark"]
    required_names = [
        "classification_voted_caselevel.xlsx",
        "classification_voted_metrics.xlsx",
        "benchmark_score_inputs.xlsx",
    ]
    missing = []
    for name in required_names:
        if not any((c / name).exists() for c in cands):
            # Report preferred resolved path for easier troubleshooting.
            missing.append(str(resolve_benchmark_dir_from_legacy(legacy_root) / name))
    if missing:
        raise RuntimeError("Missing classification_vote outputs:\n" + "\n".join(missing))
    print("classification_vote stage completed and outputs verified.")


def run_composite_score(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "composite_score")
    b = resolve_benchmark_dir_from_legacy(legacy_root)
    p = b / "benchmark_scores_output.xlsx"
    if not p.exists():
        raise RuntimeError(f"Missing composite score output: {p}")
    print("composite_score stage completed and outputs verified.")
