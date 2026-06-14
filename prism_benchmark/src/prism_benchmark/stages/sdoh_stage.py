from __future__ import annotations

import sys
from pathlib import Path

from prism_benchmark.legacy_registry import ROUND_NUM_LIST
from prism_benchmark.stages._invoke import invoke_legacy_main


def _ensure_legacy_path(legacy_root: Path) -> None:
    root = str(legacy_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def run_bias_ask(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    _ensure_legacy_path(legacy_root)
    from legacy_script_config import BIAS_ASK_MODEL_LIST
    from prism_benchmark.stages._model_scope import iter_scoped_model_dirs, model_ids_for_env_list

    invoke_legacy_main(legacy_root, "bias_ask")
    model_ids = model_ids_for_env_list(legacy_root, BIAS_ASK_MODEL_LIST)
    missing = []
    for model_dir in iter_scoped_model_dirs(legacy_root, model_ids):
        for r in ROUND_NUM_LIST:
            p = model_dir / "bias" / r / "output_json"
            if not p.exists() or not any(p.glob("*.json")):
                missing.append(str(p))
    if missing:
        raise RuntimeError("Missing bias_ask outputs:\n" + "\n".join(missing[:50]))
    print("bias_ask stage completed and outputs verified.")


def run_bias_classification(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    _ensure_legacy_path(legacy_root)
    from legacy_script_config import BIAS_ASK_MODEL_LIST
    from prism_benchmark.stages._model_scope import iter_scoped_model_dirs, model_ids_for_env_list

    invoke_legacy_main(legacy_root, "bias_classification")
    model_ids = model_ids_for_env_list(legacy_root, BIAS_ASK_MODEL_LIST)
    missing = []
    for model_dir in iter_scoped_model_dirs(legacy_root, model_ids):
        for r in ROUND_NUM_LIST:
            p1 = model_dir / "bias" / f"{r}_llm_responses_1_scenario1"
            p2 = model_dir / "bias" / f"{r}_llm_responses_1_scenario2"
            if not p1.exists():
                missing.append(str(p1))
            if not p2.exists():
                missing.append(str(p2))
    if missing:
        raise RuntimeError("Missing bias classification outputs:\n" + "\n".join(missing[:50]))
    print("bias classification stage completed and outputs verified.")


def run_bias_count(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    _ensure_legacy_path(legacy_root)
    from count_stage_health import assert_count_stages_complete
    from legacy_script_config import COUNT_TARGET_MODEL_LIST
    from prism_benchmark.stages._model_scope import model_ids_for_env_list

    invoke_legacy_main(legacy_root, "bias_count")
    model_ids = model_ids_for_env_list(legacy_root, COUNT_TARGET_MODEL_LIST)
    assert_count_stages_complete(legacy_root, model_ids, ROUND_NUM_LIST, modes=("bias",))
    print("bias_count stage completed and outputs verified.")
