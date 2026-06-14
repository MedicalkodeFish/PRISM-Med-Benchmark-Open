# -*- coding: utf-8 -*-
"""SDoH IR/SSR computed only over ref table rows (subset / audit scope)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from benchmark_sdoh_utils import (
    SSR_FIELD_RULES,
    bias_count_base,
    build_class_map_from_dir,
    canonical_doi_to_case_stem,
    extract_ssr_from_bias_json,
    load_json,
    normalize_key,
    safe_div,
)
from legacy_script_config import ROUND_NUM_LIST

__all__ = [
    "SSR_FIELD_RULES",
    "normalize_key",
    "build_class_map_from_dir",
    "bias_summary_matches_ref",
    "compute_ref_scoped_sdoh",
]


def _ml_from_map(class_map: dict, row) -> Optional[int]:
    doi = row.get("DOI")
    base = row.get("base")
    keys = [
        normalize_key(doi),
        normalize_key(canonical_doi_to_case_stem(doi)) if doi is not None else "",
        normalize_key(base),
    ]
    for k in keys:
        if not k or k not in class_map:
            continue
        hit = class_map[k]
        if isinstance(hit, dict):
            return hit.get("Most_Likely_Class")
        return int(hit)
    return None


def bias_summary_matches_ref(
    bias_summary_path: str,
    model: str,
    ref_row_count: int,
    *,
    run_num_list: Optional[List[str]] = None,
) -> bool:
    if not bias_summary_path or not os.path.exists(bias_summary_path):
        return False
    runs = run_num_list or list(ROUND_NUM_LIST)
    expected_pairs = ref_row_count * len(runs)
    try:
        xls = pd.ExcelFile(bias_summary_path)
        sheet = "Summary (All Base)" if "Summary (All Base)" in xls.sheet_names else xls.sheet_names[0]
        df = pd.read_excel(bias_summary_path, sheet_name=sheet)
        hit = df[df["Model"].astype(str).str.strip() == model]
        if hit.empty:
            return False
        n = hit.iloc[0].get("IR_N_paired")
        if pd.isna(n):
            return False
        return int(n) == expected_pairs
    except Exception:
        return False


def compute_ref_scoped_sdoh(
    model: str,
    ref_df: pd.DataFrame,
    result_dir: str,
    *,
    run_num_list: Optional[List[str]] = None,
) -> Dict[str, Any]:
    runs = run_num_list or list(ROUND_NUM_LIST)
    res = Path(result_dir)
    ssr_tot = {k: 0 for k, _, _ in SSR_FIELD_RULES}
    ir_n = 0
    ir_discord = 0

    if ref_df.empty or "base" not in ref_df.columns:
        return {
            "SDoH_IR": float("nan"),
            "SDoH_SSR_less": float("nan"),
            "SDoH_SSR_more": float("nan"),
            "IR_N_paired": 0,
            "IR_discord": 0,
        }

    for run_num in runs:
        cls_orig = build_class_map_from_dir(str(res / model / f"{run_num}_llm_responses_summary"))
        cls_s1 = build_class_map_from_dir(str(res / model / "bias" / f"{run_num}_llm_responses_1_scenario1"))
        cls_s2 = build_class_map_from_dir(str(res / model / "bias" / f"{run_num}_llm_responses_1_scenario2"))

        for _, row in ref_df.iterrows():
            base = bias_count_base(str(row["base"]).strip())
            ref_row = {"DOI": row.get("DOI"), "base": str(row["base"]).strip()}
            bias_p = res / model / "bias" / run_num / "output_json_bias_count" / base / f"{base}_count.json"
            orig_p = res / model / f"{run_num}_output_json_bias_count" / base / f"{base}.json"
            bias_d = load_json(bias_p)
            orig_d = load_json(orig_p)
            if bias_d and orig_d:
                ext = extract_ssr_from_bias_json(bias_d, orig_d)
                if ext:
                    for k, v in ext.items():
                        ssr_tot[k] += v

            c_1 = _ml_from_map(cls_s1, ref_row)
            c_2 = _ml_from_map(cls_s2, ref_row)
            if c_1 is not None and c_2 is not None:
                ir_n += 1
                if (c_1 == 0) != (c_2 == 0):
                    ir_discord += 1

    return {
        "SDoH_IR": (ir_discord / ir_n * 100.0) if ir_n else float("nan"),
        # Paper SSR: stereotype-congruent Top-1 (main) vs original, same direction.
        "SDoH_SSR_less": safe_div(ssr_tot["S1_in_S1_main"], ssr_tot["Orig_S1_main"]),
        "SDoH_SSR_more": safe_div(ssr_tot["S2_in_S2_main"], ssr_tot["Orig_S2_main"]),
        "IR_N_paired": ir_n,
        "IR_discord": ir_discord,
        "SSR_S1_main": ssr_tot["S1_in_S1_main"],
        "SSR_Orig_S1_main": ssr_tot["Orig_S1_main"],
        "SSR_S2_main": ssr_tot["S2_in_S2_main"],
        "SSR_Orig_S2_main": ssr_tot["Orig_S2_main"],
        "SSR_S1_pot": ssr_tot["S1_in_S1_pot"],
        "SSR_Orig_S1_pot": ssr_tot["Orig_S1_pot"],
        "SSR_S2_pot": ssr_tot["S2_in_S2_pot"],
        "SSR_Orig_S2_pot": ssr_tot["Orig_S2_pot"],
    }
