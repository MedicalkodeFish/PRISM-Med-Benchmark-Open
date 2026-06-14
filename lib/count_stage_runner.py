# -*- coding: utf-8 -*-
"""Shared orchestration for base_count and bias_count stages."""
from __future__ import annotations

import concurrent.futures
import json
import os
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple, Union

import pandas as pd

from benchmark_paths import path_model_bias_output_json, path_model_run_output_json
from bias_count_common import transform_output_base_to_bias_key
from legacy_script_config import BIAS_ANALYSIS_ROOT, DEFAULT_COUNT_MODEL
from model_config import resolve_model

CountFileSpec = Union[str, List[str]]


def ensure_bias_analysis_root() -> str:
    if not BIAS_ANALYSIS_ROOT.exists():
        raise FileNotFoundError(
            "Bias analysis directory not found. Set PRISM_BIAS_ANALYSIS_ROOT "
            "or create default directory: " + str(BIAS_ANALYSIS_ROOT)
        )
    return str(BIAS_ANALYSIS_ROOT)


def resolve_count_llm_credentials() -> Tuple[str, str, str]:
    model_config = resolve_model(DEFAULT_COUNT_MODEL)
    if not model_config:
        raise ValueError(f"Model config for {DEFAULT_COUNT_MODEL} not found")
    return model_config["id"], model_config["api_key"], model_config["url"]


def load_count_prompt_template(template_path: str) -> str:
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def output_json_dir_for(mode: str, model: str, run_id: str) -> str:
    if mode == "base":
        return str(path_model_run_output_json(model, run_id))
    return str(path_model_bias_output_json(model, run_id))


def match_count_output_files(mode: str, bias_root: str, output_json_dir: str) -> Dict[str, CountFileSpec]:
    keys = [d for d in os.listdir(bias_root) if os.path.isdir(os.path.join(bias_root, d))]
    files = [f for f in os.listdir(output_json_dir) if f.endswith(".json")]
    transform = transform_output_base_to_bias_key
    match_dict: Dict[str, CountFileSpec] = {}

    if mode == "base":
        base_to_files = {f.replace(".json", ""): f for f in files}
        for key in keys:
            for base in list(base_to_files.keys()):
                if transform(base) == key:
                    match_dict[key] = base_to_files[base]
                    del base_to_files[base]
    else:
        base_to_files: Dict[str, List[str]] = defaultdict(list)
        for f in files:
            if "_scenario" in f:
                base, _ = f.rsplit("_scenario", 1)
                base = base.rstrip("_")
                base_to_files[base].append(f)
        for key in keys:
            for base in list(base_to_files.keys()):
                if transform(base) == key:
                    match_dict[key] = sorted(base_to_files[base])
                    del base_to_files[base]
    return match_dict


def build_roots_to_process(
    bias_root: str, match_dict: Dict[str, CountFileSpec]
) -> List[Tuple[str, str, CountFileSpec]]:
    roots: List[Tuple[str, str, CountFileSpec]] = []
    for key, spec in match_dict.items():
        root = os.path.join(bias_root, key)
        if os.path.exists(os.path.join(root, "formatted.json")):
            roots.append((root, key, spec))
    return roots


def write_processed_dois_txt(count_output_dir: str, roots_to_process) -> None:
    doi_txt_path = os.path.join(count_output_dir, "processed_dois.txt")
    with open(doi_txt_path, "w", encoding="utf-8") as f:
        for _, key, _ in roots_to_process:
            f.write(key + "\n")
    print(f"Saved processed DOIs to {doi_txt_path}")


def run_count_thread_pool(
    roots_to_process,
    worker: Callable[..., Optional[str]],
    max_workers: int,
) -> List[str]:
    processed: List[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(worker, root, key, spec): (root, key)
            for root, key, spec in roots_to_process
        }
        for future in concurrent.futures.as_completed(futures):
            root_key = futures[future]
            try:
                count_path = future.result()
                if count_path:
                    processed.append(count_path)
            except Exception as exc:
                print(f"{root_key} generated an exception: {exc}")
    return processed


def print_skipped_subdirs(match_dict: Dict[str, CountFileSpec], processed_files: List[str], run_label: str) -> None:
    all_subdirs = list(match_dict.keys())
    processed_subdirs = [os.path.basename(os.path.dirname(p)) for p in processed_files]
    skipped = [s for s in all_subdirs if s not in processed_subdirs]
    if skipped:
        print(f"Skipped subdirectories for {run_label}: {len(skipped)}")


def save_count_results_excel(rows: List[dict], excel_path: str, label: str) -> None:
    if rows:
        pd.DataFrame(rows).to_excel(excel_path, index=False)
        print(f"Saved aggregated results for {label} to {excel_path}")
    else:
        print(f"No valid data to save to Excel for {label}")
