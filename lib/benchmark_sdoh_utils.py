# -*- coding: utf-8 -*-
"""Shared SDoH / reference-table helpers used across benchmark scripts.

Case identifiers (do not conflate):
  canonical_doi — standard DOI string from Excel, e.g. ``10.1056/NEJMcpc1900419``
  case_stem     — filename stem for model JSON / classification artifacts,
                  e.g. ``10.1056aNEJMcpc1900419`` (``/`` → ``a``)
  bias_count_dir — directory name under ``output_json_bias_count``, from ref
                  ``base`` via :func:`bias_count_base` (e.g. ``10_1056_NEJM...``)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

# (aggregator_key, source, json_field)
SSR_FIELD_RULES = (
    ("S1_in_S1_pot", "bias_sc1", "scenario1_potential_count"),
    ("S1_in_S1_main", "bias_sc1", "scenario1_main_count"),
    ("S1_in_S2_pot", "bias_sc1", "scenario2_potential_count"),
    ("S1_in_S2_main", "bias_sc1", "scenario2_main_count"),
    ("S2_in_S1_pot", "bias_sc2", "scenario1_potential_count"),
    ("S2_in_S1_main", "bias_sc2", "scenario1_main_count"),
    ("S2_in_S2_pot", "bias_sc2", "scenario2_potential_count"),
    ("S2_in_S2_main", "bias_sc2", "scenario2_main_count"),
    ("Orig_S1_pot", "orig", "scenario1_potential_count"),
    ("Orig_S1_main", "orig", "scenario1_main_count"),
    ("Orig_S2_pot", "orig", "scenario2_potential_count"),
    ("Orig_S2_main", "orig", "scenario2_main_count"),
)


def normalize_key(x: Any, *, remove_spaces: bool = False) -> str:
    if x is None:
        return ""
    s = str(x).strip().lower()
    if remove_spaces:
        s = s.replace(" ", "")
    return s


def load_json(path: Union[str, Path]) -> Optional[dict]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def bias_count_base(raw_base: str) -> str:
    """Map case stem / filename to bias_count JSON directory name."""
    from case_dataset_io import case_stem_from_filename

    base = case_stem_from_filename(str(raw_base).strip())
    if base.startswith("10.1056a"):
        return base.replace("10.1056a", "10_1056_", 1)
    return base.replace(".", "_")


def extract_ssr_from_bias_json(
    bias_data: dict,
    orig_data: dict,
    *,
    coerce_int: bool = True,
) -> Optional[Dict[str, Union[int, float]]]:
    try:
        sources = {
            "bias_sc1": bias_data.get("scenario1", {}) or {},
            "bias_sc2": bias_data.get("scenario2", {}) or {},
            "orig": orig_data,
        }
        out: Dict[str, Union[int, float]] = {}
        for key, src, field in SSR_FIELD_RULES:
            val = sources[src].get(field, 0) or 0
            out[key] = int(val) if coerce_int else val
        return out
    except (AttributeError, TypeError):
        return None


def build_class_map_from_dir(dir_path: str, *, require_potential: bool = False) -> dict:
    out: dict = {}
    if not dir_path or not os.path.exists(dir_path):
        return out
    for fn in os.listdir(dir_path):
        if not fn.endswith("_classification.json"):
            continue
        fp = os.path.join(dir_path, fn)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        doi = data.get("DOI")
        ml = data.get("most_likely_diagnosis_class")
        pc = data.get("potential_diagnoses_class")
        if doi is None or ml is None:
            continue
        if require_potential and pc is None:
            continue
        entry: Dict[str, int] = {"Most_Likely_Class": int(ml)}
        if pc is not None:
            entry["Potential_Class"] = int(pc)
        elif require_potential:
            continue
        canonical = str(doi)
        for key in (
            normalize_key(canonical),
            normalize_key(canonical_doi_to_case_stem(canonical)),
        ):
            out[key] = entry
    return out


def classification_safe_mode(vals: List[Any]) -> Optional[int]:
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    s = pd.Series(vals)
    modes = s.mode()
    if len(modes) == 0:
        return vals[0]
    return int(modes.iloc[0])


def get_case_record(dataset_root: Union[str, Path], ref: str) -> Optional[dict]:
    from case_dataset_io import get_case_record as _get

    return _get(dataset_root, ref)


def load_case_record(path: Union[str, Path]) -> Optional[dict]:
    """Load a challenge / SDoH per-case record (``.jsonl`` or legacy ``.json``)."""
    from case_dataset_io import load_case_record as _load

    return _load(path)


def resolve_case_record_path(dataset_root: Union[str, Path], rel_or_name: str) -> Optional[str]:
    from case_dataset_io import catalog_path, case_stem_from_filename, load_catalog

    root = Path(dataset_root)
    stem = case_stem_from_filename(rel_or_name)
    if stem in load_catalog(root):
        return str(catalog_path(root))
    from case_dataset_io import case_record_path

    p = case_record_path(dataset_root, rel_or_name)
    return str(p) if p.is_file() and p.name != "cases.jsonl" else None


def case_stem_from_filename(name: str) -> str:
    from case_dataset_io import case_stem_from_filename as _stem

    return _stem(name)


def normalize_case_filename(name: str) -> str:
    from case_dataset_io import normalize_case_filename as _norm

    return _norm(name)


def canonical_doi_to_case_stem(canonical_doi: Any) -> str:
    """Map standard DOI (with ``/``) to output/classification JSON filename stem."""
    if canonical_doi is None:
        return ""
    return str(canonical_doi).strip().replace("/", "a")


# Backward-compatible alias (deprecated name; means case_stem not a DOI string).
doi_to_safe_filename = canonical_doi_to_case_stem  # noqa: F841 — kept for external forks


def first_existing_path(candidates: Sequence[Union[str, Path]]) -> Optional[str]:
    for p in candidates:
        ps = str(p)
        if os.path.exists(ps):
            return ps
    return None


def safe_div(num: float, den: float) -> float:
    """SSR / coverage style: denominator 0 → 0.0 (not inf)."""
    return ratio_or_zero(num, den)


def ratio_or_zero(num: float, den: float) -> float:
    return (num / den) if den else 0.0


def ratio_or_inf(num: float, den: float) -> float:
    """IR-style: denominator 0 and numerator non-zero → inf; both zero → 0."""
    if den == 0:
        return 0.0 if num == 0 else float("inf")
    return num / den
