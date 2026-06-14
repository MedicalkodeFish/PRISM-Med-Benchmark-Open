# -*- coding: utf-8 -*-
"""Excel row builders for reasoning flaw JSON artifacts."""
from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Dict, Optional

from reasoning_flaws_constants import HALLUCINATION_TYPES


def _load_json_file(json_path: str) -> Optional[dict]:
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                print(f"Warning: Empty JSON file {json_path}, skipping.")
                return None
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in {json_path}: {e}")
        return None
    except Exception as e:
        print(f"Error processing {json_path}: {e}")
        return None


def _audit_data_to_row(data: dict, case_id: str, *, include_peer_review: bool) -> Dict[str, Any]:
    audit_summary = data.get("audit_summary", "")
    rating = data.get("rating", "")
    hallucinations = data.get("identified_hallucinations", [])

    severity_count = Counter(h["severity"] for h in hallucinations)
    type_count = Counter()
    severe_type_count = Counter()
    for h in hallucinations:
        types = h.get("hallucination_types", [])
        type_count.update(types)
        if h.get("severity") == "High":
            severe_type_count.update(types)

    row: Dict[str, Any] = {
        "Case ID": case_id,
        "Audit Summary": audit_summary,
        "Rating": rating,
        "Total Hallucinations": len(hallucinations),
        "High Severity Count": severity_count.get("High", 0),
        "Medium Severity Count": severity_count.get("Medium", 0),
        "Low Severity Count": severity_count.get("Low", 0),
    }
    for t in HALLUCINATION_TYPES:
        row[f"{t} Count"] = type_count.get(t, 0)
    for t in HALLUCINATION_TYPES:
        row[f"{t} High Severity Count"] = severe_type_count.get(t, 0)

    if include_peer_review:
        peer_review = data.get("peer_evaluation_review", {})
        row["Eval1 Summary"] = peer_review.get("evaluation_1_review", {}).get("summary_of_findings", "")
        row["Eval2 Summary"] = peer_review.get("evaluation_2_review", {}).get("summary_of_findings", "")

    row["Hallucinations Details"] = json.dumps(hallucinations, ensure_ascii=False)
    return row


def process_flaws_json_file(json_path: str) -> Optional[Dict[str, Any]]:
    data = _load_json_file(json_path)
    if data is None:
        return None
    case_id = os.path.basename(json_path).replace("_flaws.json", "")
    return _audit_data_to_row(data, case_id, include_peer_review=False)


def process_flaws_summary_json_file(json_path: str) -> Dict[str, Any]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    case_id = os.path.basename(json_path).replace("_flaws_summary.json", "")
    return _audit_data_to_row(data, case_id, include_peer_review=True)
