#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Artifact verification helpers for full PRISM benchmark runs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Set

ROUND_NUM_LIST = ["1_5answer", "1_5answer_1", "1_5answer_2"]


def resolve_model_ids(legacy_root: Path, models: List[str]) -> List[str]:
    legacy_root_str = str(legacy_root)
    if legacy_root_str not in sys.path:
        sys.path.insert(0, legacy_root_str)
    import prism_bootstrap

    prism_bootstrap.install_import_paths(legacy_root)
    from model_config import resolve_model

    ids: List[str] = []
    for m in models:
        conf = resolve_model(m)
        if not conf:
            raise KeyError(f"model not found in model_config: {m}")
        ids.append(str(conf["id"]))
    return ids


def _glob_count(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def _case_artifact_count(directory: Path, basenames: Set[str], leaf: str) -> int:
    if not directory.exists():
        return 0
    return sum(1 for b in basenames if (directory / f"{b}{leaf}").exists())


def _load_bias_expectations(legacy_root: Path):
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from benchmark_coverage import load_coverage_expectations
    from legacy_script_config import QUERY_EXCEL_PATH

    return load_coverage_expectations(legacy_root, Path(QUERY_EXCEL_PATH))


def classification_vote_outputs_valid(
    legacy_root: Path,
    model_ids: List[str],
    *,
    expected_cases: int,
) -> bool:
    import pandas as pd

    from legacy_script_config import resolve_reference_table_path

    bench = legacy_root / "benchmark"
    ref_path = resolve_reference_table_path(bench)
    caselevel_path = bench / "classification_voted_caselevel.xlsx"
    score_in = bench / "benchmark_score_inputs.xlsx"
    if not all(p.exists() for p in (ref_path, caselevel_path, score_in)):
        return False
    ref_df = pd.read_excel(ref_path)
    if len(ref_df) != expected_cases:
        return False
    caselevel = pd.read_excel(caselevel_path)
    if caselevel.empty:
        return False
    expected_dois = set(ref_df["DOI"].dropna().astype(str))
    for mid in model_ids:
        orig = caselevel[
            (caselevel["Model"].astype(str) == mid) & (caselevel["Source"].astype(str) == "original")
        ]
        got = set(orig["DOI"].astype(str))
        if not expected_dois.issubset(got):
            return False
    return True


def verify_artifacts(
    legacy_root: Path,
    model_ids: List[str],
    *,
    expected_cases: int,
    case_basenames_set: set[str],
) -> Dict[str, Any]:
    bench = legacy_root / "benchmark"
    res = bench / "result"
    rows: List[Dict[str, Any]] = []
    bias_exp = _load_bias_expectations(legacy_root)
    bias_json_exp = bias_exp.bias_json_per_round
    bias_cls_exp = bias_exp.bias_classification_per_scenario

    def add(stage: str, key: str, ok: bool, detail: str) -> None:
        rows.append({"stage": stage, "key": key, "ok": ok, "detail": detail})

    for mid in model_ids:
        mdir = res / mid
        for r in ROUND_NUM_LIST:
            jdir = mdir / f"{r}_output_json"
            n = _case_artifact_count(jdir, case_basenames_set, ".json")
            extra = _glob_count(jdir, "*.json") - n if jdir.exists() else 0
            ok = n >= expected_cases and extra == 0
            detail = f"json {n}/{expected_cases}" + (f" (+{extra} extra)" if extra else "")
            add("base_ask", f"{mid}/{r}", ok, detail)

        for r in ROUND_NUM_LIST:
            cdir = mdir / f"{r}_llm_responses_1"
            n = _case_artifact_count(cdir, case_basenames_set, "_classification.json")
            extra = _glob_count(cdir, "*_classification.json") - n if cdir.exists() else 0
            ok = n >= expected_cases and extra == 0
            detail = f"class_json {n}/{expected_cases}" + (f" (+{extra} extra)" if extra else "")
            add("classification", f"{mid}/{r}", ok, detail)

        for r in ROUND_NUM_LIST:
            sdir = mdir / f"{r}_llm_responses_summary"
            n = _case_artifact_count(sdir, case_basenames_set, "_classification.json")
            extra = _glob_count(sdir, "*_classification.json") - n if sdir.exists() else 0
            ok = n >= expected_cases and extra == 0
            detail = f"class_json {n}/{expected_cases}" + (f" (+{extra} extra)" if extra else "")
            add("classification_summary", f"{mid}/{r}", ok, detail)

        for r in ROUND_NUM_LIST:
            fp = bench / f"{r}_flaws_summary.xlsx"
            add("reasoning_summary", r, fp.exists(), str(fp))
            d0 = _case_artifact_count(mdir / f"{r}_flaws", case_basenames_set, "_flaws.json")
            d1 = _case_artifact_count(mdir / f"{r}_flaws1", case_basenames_set, "_flaws.json")
            ok = d0 >= expected_cases and d1 >= expected_cases
            add(
                "reasoning_flaws",
                f"{mid}/{r}",
                ok,
                f"flaws {d0}/{expected_cases}, flaws1 {d1}/{expected_cases}",
            )
            n_sum = _case_artifact_count(
                mdir / f"{r}_flaws_summary", case_basenames_set, "_flaws_summary.json"
            )
            add(
                "reasoning_flaws_summary",
                f"{mid}/{r}",
                n_sum >= expected_cases,
                f"flaws_summary_json {n_sum}/{expected_cases}",
            )

        for r in ROUND_NUM_LIST:
            bj = mdir / "bias" / r / "output_json"
            n = len(list(bj.glob("*.json"))) if bj.exists() else 0
            add(
                "bias_ask",
                f"{mid}/{r}",
                n >= bias_json_exp,
                f"json {n}/{bias_json_exp} ({bias_exp.bias_case_count} cases × 2)",
            )

        for r in ROUND_NUM_LIST:
            for sc in ("scenario1", "scenario2"):
                d = mdir / "bias" / f"{r}_llm_responses_1_{sc}"
                n = len(list(d.glob("*_classification.json"))) if d.exists() else 0
                add(
                    "bias_classification",
                    f"{mid}/{r}/{sc}",
                    n >= bias_cls_exp,
                    f"class_json {n}/{bias_cls_exp}",
                )

        for r in ROUND_NUM_LIST:
            bc = mdir / f"{r}_output_json_bias_count"
            n = sum(1 for _ in bc.rglob("*.json")) if bc.exists() else 0
            add("base_count", f"{mid}/{r}", n > 0, f"count_json {n}")
            bbc = mdir / "bias" / r / "output_json_bias_count"
            n2 = sum(1 for _ in bbc.rglob("*.json")) if bbc.exists() else 0
            add("bias_count", f"{mid}/{r}", n2 > 0, f"count_json {n2}")

    for name, rel in [
        ("Bias_Analysis_Summary.xlsx", legacy_root / "Bias_Analysis_Summary.xlsx"),
        ("benchmark_score_inputs.xlsx", bench / "benchmark_score_inputs.xlsx"),
        ("benchmark_scores_output.xlsx", bench / "benchmark_scores_output.xlsx"),
        ("classification_voted_metrics.xlsx", bench / "classification_voted_metrics.xlsx"),
    ]:
        add("final", name, rel.exists(), str(rel))

    vote_ok = classification_vote_outputs_valid(
        legacy_root, model_ids, expected_cases=expected_cases
    )
    add(
        "classification_vote",
        "original_rows",
        vote_ok,
        "caselevel has original Source for each ref DOI"
        if vote_ok
        else "stale or missing original votes — re-run classification_vote",
    )

    all_ok = all(r["ok"] for r in rows)
    return {"all_ok": all_ok, "checks": rows}
