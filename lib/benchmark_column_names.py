# -*- coding: utf-8 -*-
"""Canonical English column names for benchmark spreadsheets (legacy Chinese supported)."""
from __future__ import annotations

import pandas as pd

COL_MODEL_CANONICAL_NAME = "model_canonical_name"
COL_BASE_ACCURACY = "base_accuracy"
COL_COVERAGE = "coverage"

# Legacy Chinese headers still found in older xlsx artifacts.
_LEGACY_TO_ENGLISH = {
    "模型标准名": COL_MODEL_CANONICAL_NAME,
    "基础准确率": COL_BASE_ACCURACY,
    "覆盖率": COL_COVERAGE,
}

# Diagnosis summary sheets from base_ask / bias_ask.
COL_FILENAME = "filename"
COL_MOST_LIKELY_DIAGNOSIS = "most_likely_diagnosis"
COL_POSSIBLE_DIAGNOSES = "possible_diagnoses"

_LEGACY_DIAGNOSIS_COLUMNS = {
    "文件名": COL_FILENAME,
    "最可能的诊断": COL_MOST_LIKELY_DIAGNOSIS,
    "可能的诊断": COL_POSSIBLE_DIAGNOSES,
}

# Classification rule sheet (Excel may still use the Chinese header).
RULE_NOTES_COLUMN_CANDIDATES = ("notes", "备注说明")


def normalize_score_input_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename known legacy Chinese score-input columns to English."""
    rename = {k: v for k, v in _LEGACY_TO_ENGLISH.items() if k in df.columns}
    if not rename:
        return df
    out = df.rename(columns=rename)
    return out


def normalize_diagnosis_summary_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {k: v for k, v in _LEGACY_DIAGNOSIS_COLUMNS.items() if k in df.columns}
    if not rename:
        return df
    return df.rename(columns=rename)


def normalize_classification_rule_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "notes" in df.columns or "备注说明" not in df.columns:
        return df
    return df.rename(columns={"备注说明": "notes"})
