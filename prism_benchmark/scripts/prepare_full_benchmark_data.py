#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Restore full benchmark case list + SDoH reference table."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def _ensure_legacy_imports(legacy_root: Path) -> None:
    config_dir = str(legacy_root / "config")
    if config_dir not in sys.path:
        sys.path.insert(0, config_dir)


def _case_stem(name: str) -> str:
    base = str(name).strip()
    for suffix in (".jsonl", ".json"):
        if base.lower().endswith(suffix):
            return base[: -len(suffix)]
    return base


def _legacy_root() -> Path:
    return Path(__file__).resolve().parents[2]


def restore_full_query(legacy_root: Path, *, dry_run: bool) -> tuple[Path, int]:
    q_dir = legacy_root / "dataset" / "question"
    full_path = q_dir / "query_question.full.xlsx"
    active_path = q_dir / "query_question.xlsx"
    if not full_path.exists():
        raise FileNotFoundError(f"Missing full query backup: {full_path}")
    n = len(pd.read_excel(full_path))
    if dry_run:
        print(f"[dry-run] would copy {full_path.name} -> query_question.xlsx ({n} rows)")
        return active_path, n
    if active_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = q_dir / f"query_question.before_restore_{stamp}.xlsx"
        shutil.copy2(active_path, backup)
        print(f"Backed up current query to {backup.name}")
    shutil.copy2(full_path, active_path)
    print(f"Restored query_question.xlsx from full backup ({n} rows)")
    return active_path, n


def rebuild_reference_table(legacy_root: Path, full_query: Path, *, dry_run: bool) -> tuple[Path, int]:
    from legacy_script_config import resolve_reference_table_path

    bench = legacy_root / "benchmark"
    bench.mkdir(parents=True, exist_ok=True)
    ref_path = resolve_reference_table_path(bench)
    df = pd.read_excel(full_query)
    if "File Name" not in df.columns or "DOI" not in df.columns:
        raise ValueError("query excel must contain columns: File Name, DOI")
    ref_df = df[["File Name", "DOI"]].copy()
    ref_df = ref_df.rename(columns={"File Name": "base"})
    ref_df["base"] = ref_df["base"].astype(str).map(_case_stem)
    if "fits_scenario1" not in ref_df.columns:
        ref_df["fits_scenario1"] = True
    if "fits_scenario2" not in ref_df.columns:
        ref_df["fits_scenario2"] = True
    n = len(ref_df)
    if dry_run:
        print(f"[dry-run] would write {ref_path} ({n} rows)")
        return ref_path, n
    if ref_path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = bench / f"reference_table_bias_with_doi.before_restore_{stamp}.xlsx"
        shutil.copy2(ref_path, backup)
        print(f"Backed up current reference table to {backup.name}")
    ref_df.to_excel(ref_path, index=False)
    print(f"Wrote {ref_path.name} ({n} rows)")
    return ref_path, n


def restore_full_bias_analysis(legacy_root: Path, *, dry_run: bool) -> tuple[Path, int, Path]:
    """Use upstream 289-case formatted.json tree for base_count/bias_count (via env or copy)."""
    from legacy_script_config import DEFAULT_BIAS_ANALYSIS_DIRNAME, resolve_parent_bias_analysis_source

    source = resolve_parent_bias_analysis_source(legacy_root.parent)
    dest = legacy_root / "results" / DEFAULT_BIAS_ANALYSIS_DIRNAME
    n_src = sum(1 for d in source.iterdir() if d.is_dir()) if source and source.is_dir() else 0
    if source is None or not source.is_dir() or n_src < 200:
        raise FileNotFoundError(
            f"Missing full bias_analysis source ({n_src} dirs under parent results/)\n"
            "Expected e.g. ../results/bias_analysis_second_gpt5_bias_diagnosis\n"
            "Set PRISM_BIAS_ANALYSIS_ROOT to your 289-case tree manually."
        )
    if dry_run:
        print(f"[dry-run] would set PRISM_BIAS_ANALYSIS_ROOT={source} ({n_src} dirs)")
        print(f"[dry-run] optional copy -> {dest} (slow; prefer env pointer only)")
        return dest, n_src, source
    os.environ["PRISM_BIAS_ANALYSIS_ROOT"] = str(source.resolve())
    print(f"PRISM_BIAS_ANALYSIS_ROOT={source} ({n_src} case dirs)")
    print("Tip: no copy needed; count stages read from this path.")
    return dest, n_src, source


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore full PRISM benchmark query + reference table")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    parser.add_argument(
        "--restore-bias-analysis",
        action="store_true",
        help="Point PRISM_BIAS_ANALYSIS_ROOT at parent repo 289-case bias_analysis (for base_count/bias_count)",
    )
    args = parser.parse_args()

    legacy_root = _legacy_root()
    _ensure_legacy_imports(legacy_root)
    print("Legacy root:", legacy_root)
    _, n_q = restore_full_query(legacy_root, dry_run=args.dry_run)
    full_q = legacy_root / "dataset" / "question" / "query_question.full.xlsx"
    _, n_r = rebuild_reference_table(legacy_root, full_q, dry_run=args.dry_run)
    if args.restore_bias_analysis:
        restore_full_bias_analysis(legacy_root, dry_run=args.dry_run)
    if n_q != n_r:
        print(f"Warning: query rows ({n_q}) != reference rows ({n_r})")
    if not args.dry_run:
        print("\nNext: python run_prism_benchmark.py --check-only  (three-pillar data check)")
        print("       docs/BENCHMARK.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
