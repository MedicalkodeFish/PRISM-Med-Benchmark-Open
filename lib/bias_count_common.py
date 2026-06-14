# -*- coding: utf-8 -*-
"""Shared helpers for base_count and bias_count prompt assembly."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple


def transform_output_base_to_bias_key(base: str) -> str:
    transformed = base.replace("aNEJM", "_NEJM")
    return transformed.replace(".", "_")


from legacy_script_config import SCENARIO1_BIAS_JSON_KEY, SCENARIO2_BIAS_JSON_KEY


def load_bias_directions(formatted_json_path: str) -> Tuple[str, str]:
    with open(formatted_json_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    low_bias = data.get(SCENARIO1_BIAS_JSON_KEY) or ""
    high_bias = data.get(SCENARIO2_BIAS_JSON_KEY) or ""
    return low_bias, high_bias


def diagnosis_payload_from_model_output(output_data: List[Any]) -> Tuple[List[str], str]:
    """Parse base_ask / bias_ask JSON (split or merged single-object layouts)."""
    possible_list: List[str] = []
    most_likely = ""
    for item in output_data:
        if not isinstance(item, dict):
            continue
        pot = item.get("Potential differential diagnoses")
        if isinstance(pot, dict):
            possible_list = [
                key.split(". ", 1)[1] if ". " in key else key for key in pot.keys()
            ]
        main = item.get("Most Likely Main Diagnosis") or item.get("Most Lik Likely Main Diagnosis")
        if main:
            most_likely = str(main)
    return possible_list, most_likely


def build_bias_count_prompt(template: str, low_bias: str, high_bias: str, output_data: List[Any]) -> str:
    possible_list, most_likely = diagnosis_payload_from_model_output(output_data)
    diag_dict = {
        "Potential differential diagnoses": possible_list,
        "Most Likely Main Diagnosis": [most_likely],
    }
    diag_text = json.dumps(diag_dict, indent=4, ensure_ascii=False)
    return (
        template.replace("{scenario1_low SES bias}", low_bias)
        .replace("{scenario2_high SES bias}", high_bias)
        .replace("{DIAGNOSIS LIST}", diag_text)
    )
