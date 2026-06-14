from __future__ import annotations

from pathlib import Path
from typing import Tuple


ROUND_NUM_LIST = ("1_5answer", "1_5answer_1", "1_5answer_2")


# Mapping: step_key -> root-level script filename (relative to legacy_root).
# Used when a stage still needs the script path on disk (e.g. for existence
# checks) or when something must be invoked as a subprocess as a fallback.
LEGACY_SCRIPTS = {
    "base_ask": "stages/base_ask.py",
    "classification_round": "stages/classification_json_benchmark.py",
    "classification_summary": "stages/classification_json_benchmark_summary.py",
    "reasoning_flaws": "stages/judge_reasoning_flaws.py",
    "reasoning_flaws_summary": "stages/judge_reasoning_flaws_summary.py",
    "bias_ask": "stages/bias_ask_.py",
    "bias_classification": "stages/classification_json_bias_benchmark.py",
    "base_count": "stages/base_count.py",
    "bias_count": "stages/bias_count.py",
    "bias_metrics": "stages/analyze_bias_comparison.py",
    "classification_vote": "stages/classification_majority_vote_and_score_input.py",
    "composite_score": "stages/compute_composite_benchmark_score.py",
}


# Mapping: step_key -> (module_name, function_name) for in-process invocation
# via importlib. The stage runner imports ``module_name`` from ``legacy_root``
# and calls ``function_name()``. Module names match the .py files in
# LEGACY_SCRIPTS but without the .py extension; this map exists so future
# entries can have a different callable name without changing the registry
# consumers.
LEGACY_MODULES = {
    "base_ask": ("base_ask", "main"),
    "classification_round": ("classification_json_benchmark", "main"),
    "classification_summary": ("classification_json_benchmark_summary", "main"),
    "reasoning_flaws": ("judge_reasoning_flaws", "main"),
    "reasoning_flaws_summary": ("judge_reasoning_flaws_summary", "main"),
    "bias_ask": ("bias_ask_", "main"),
    "bias_classification": ("classification_json_bias_benchmark", "main"),
    "base_count": ("base_count", "main"),
    "bias_count": ("bias_count", "main"),
    "bias_metrics": ("analyze_bias_comparison", "main"),
    "classification_vote": ("classification_majority_vote_and_score_input", "main"),
    "composite_score": ("compute_composite_benchmark_score", "main"),
}


def get_legacy_script_path(legacy_root: Path, script_key: str) -> Path:
    script_name = LEGACY_SCRIPTS.get(script_key)
    if not script_name:
        raise KeyError(f"Unknown legacy script key: {script_key}")
    return legacy_root / script_name


def get_legacy_module_target(script_key: str) -> Tuple[str, str]:
    target = LEGACY_MODULES.get(script_key)
    if not target:
        raise KeyError(f"No module mapping for legacy script key: {script_key}")
    return target
