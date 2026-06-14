# -*- coding: utf-8 -*-
"""
Central path builders for benchmark artifacts.

All functions anchor on ``legacy_script_config.resolve_benchmark_dir()`` so
deployments with ``benchmark/`` under ``opensource_prism/`` or the parent repo
both work. Legacy scripts still run with ``cwd == opensource_prism``; prefer
these helpers over ``benchmark\\result\\...`` string literals.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from legacy_script_config import resolve_benchmark_dir

PathLike = Union[str, Path]


def _bench_root() -> Path:
    return resolve_benchmark_dir()


def benchmark_result_root() -> Path:
    return _bench_root() / "result"


def as_legacy_str(path: Path) -> str:
    """Relative path string matching historical ``benchmark\\result\\...`` usage."""
    return str(path)


def path_model_run_output_json(model: str, run: str) -> Path:
    return benchmark_result_root() / model / f"{run}_output_json"


def path_model_bias_output_json(model: str, run: str) -> Path:
    return benchmark_result_root() / model / "bias" / run / "output_json"


def path_model_round_output_json(model: str, round_num: str) -> Path:
    return benchmark_result_root() / model / f"{round_num}_output_json"


def path_model_classification_run_dir(
    model: str,
    round_num: str,
    run: Union[int, str],
    *,
    dataset_name: str = "benchmark",
) -> Path:
    """Adjudication run output (``{round}_llm_responses_{run}`` under dataset mirror)."""
    return Path(dataset_name) / "result" / model / f"{round_num}_llm_responses_{run}"


def path_model_classification_summary_dir(model: str, round_num: str) -> Path:
    return benchmark_result_root() / model / f"{round_num}_llm_responses_summary"


def path_bias_classification_scenario_dir(
    model: str,
    round_num: str,
    scenario: str,
    *,
    dataset_name: str = "benchmark",
) -> Path:
    """scenario is ``scenario1`` or ``scenario2``."""
    return (
        Path(dataset_name)
        / "result"
        / model
        / "bias"
        / f"{round_num}_llm_responses_1_{scenario}"
    )


def path_model_ask_result_dir(model: str, ask_num: str) -> str:
    return as_legacy_str(benchmark_result_root() / model / ask_num)


def path_model_flaws_dir(model: str, ask_num: str, run_suffix: str = "") -> str:
    return as_legacy_str(benchmark_result_root() / model / f"{ask_num}_flaws{run_suffix}")


def path_model_flaws_summary_dir(model: str, ask_num: str) -> str:
    return as_legacy_str(benchmark_result_root() / model / f"{ask_num}_flaws_summary")


def path_benchmark_flaws_round_summary_xlsx(ask_num: str, run_suffix: str = "") -> str:
    return as_legacy_str(_bench_root() / f"{ask_num}_flaws{run_suffix}_summary.xlsx")


def flaws_dirs_for_model_runs(model: str, ask_num: str, run_list) -> list[str]:
    return [path_model_flaws_dir(model, ask_num, run) for run in run_list]


def path_base_ask_round_dirs(model_id: str, round_num: str) -> dict[str, str]:
    """All base_ask output directories for one model round."""
    base = benchmark_result_root() / model_id
    return {
        "out_dir": as_legacy_str(base / round_num),
        "prompt_save_dir": as_legacy_str(base / f"{round_num}_prompt"),
        "log_save_dir": as_legacy_str(base / f"{round_num}_log"),
        "output_dir": as_legacy_str(base / f"{round_num}_output"),
        "output_prompt_dir": as_legacy_str(base / f"{round_num}_output_prompt"),
        "output_log_dir": as_legacy_str(base / f"{round_num}_output_log"),
        "json_save_dir": as_legacy_str(base / f"{round_num}_output_json"),
    }


def path_base_ask_progress_file(round_num: str) -> str:
    return as_legacy_str(benchmark_result_root() / f"progress_round{round_num}.json")


def path_base_ask_round_xlsx(model_id: str, round_num: str) -> str:
    return as_legacy_str(benchmark_result_root() / model_id / f"{round_num}.xlsx")


def path_bias_ask_round_base(model_id: str, round_num: str) -> str:
    return as_legacy_str(benchmark_result_root() / model_id / "bias" / round_num)
