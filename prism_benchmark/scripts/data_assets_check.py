#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check PRISM dataset assets for the three benchmark pillars (diagnostic / reasoning / SDoH)."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


def _legacy_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_requirements(prism_root: Path) -> dict[str, Any]:
    path = prism_root / "configs" / "data_requirements.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _bias_subdir_count(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for d in path.iterdir() if d.is_dir())


def _ensure_config_import(legacy_root: Path) -> None:
    cfg = str(legacy_root / "config")
    if cfg not in sys.path:
        sys.path.insert(0, cfg)


@dataclass
class PillarStatus:
    name: str
    label: str
    ok: bool
    detail: str


@dataclass
class DataAssetsReport:
    query_rows: int
    expected_query_rows: int
    challenge_dir_ok: bool
    sdoh_dir_ok: bool
    bias_analysis_root: str
    bias_analysis_dirs: int
    bias_analysis_min_full: int
    bias_case_count: int | None
    pillars: list[PillarStatus]
    sdoh_assets_ok: bool
    allow_partial_sdoh: bool

    def exit_code_full_run(self) -> int:
        if self.query_rows < self.expected_query_rows:
            return 2
        if not self.challenge_dir_ok:
            return 4
        if not self.sdoh_dir_ok:
            return 5
        if not self.sdoh_assets_ok and not self.allow_partial_sdoh:
            return 6
        return 0


def resolve_bias_analysis_root(legacy_root: Path, req: dict[str, Any] | None = None) -> tuple[Path | None, int, str]:
    """Return (path, subdir_count, how_selected). Honors PRISM_BIAS_ANALYSIS_ROOT."""
    explicit = os.environ.get("PRISM_BIAS_ANALYSIS_ROOT", "").strip()
    if explicit:
        p = Path(explicit)
        return p, _bias_subdir_count(p), "env:PRISM_BIAS_ANALYSIS_ROOT"

    prism_root = legacy_root / "prism_benchmark"
    if req is None:
        req = _load_requirements(prism_root)

    best: tuple[Path | None, int, str] = (None, 0, "")
    for rel in req.get("bias_analysis_candidates", []):
        rel_s = str(rel).replace("/", os.sep)
        if rel_s.startswith(".."):
            candidate = (legacy_root / rel_s).resolve()
            label = f"parent:{rel}"
        else:
            candidate = legacy_root / rel_s
            label = f"local:{rel}"
        n = _bias_subdir_count(candidate)
        if n > best[1]:
            best = (candidate, n, label)

    return best


def apply_bias_analysis_root_env(legacy_root: Path) -> tuple[Path | None, int, str]:
    """Set PRISM_BIAS_ANALYSIS_ROOT when unset and a candidate meets min threshold."""
    if os.environ.get("PRISM_BIAS_ANALYSIS_ROOT"):
        p = Path(os.environ["PRISM_BIAS_ANALYSIS_ROOT"])
        return p, _bias_subdir_count(p), "env:PRISM_BIAS_ANALYSIS_ROOT"

    req = _load_requirements(legacy_root / "prism_benchmark")
    path, n, how = resolve_bias_analysis_root(legacy_root, req)
    min_full = int(req.get("bias_analysis_min_dirs_full", 200))
    if path is not None and n >= min_full:
        os.environ["PRISM_BIAS_ANALYSIS_ROOT"] = str(path.resolve())
        return path, n, how
    if path is not None and n > 0:
        os.environ.setdefault("PRISM_BIAS_ANALYSIS_ROOT", str(path.resolve()))
    return path, n, how


def _allow_partial_sdoh() -> bool:
    return os.getenv("PRISM_ALLOW_PARTIAL_SDOH", "").strip().lower() in ("1", "true", "yes")


def build_report(legacy_root: Path) -> DataAssetsReport:
    legacy_root = legacy_root.resolve()
    prism_root = legacy_root / "prism_benchmark"
    req = _load_requirements(prism_root)

    expected_rows = int(req["expected_query_rows"])
    min_bias = int(req.get("bias_analysis_min_dirs_full", 200))
    query_active = legacy_root / req["dataset_dirs"]["query_active"]
    query_rows = len(pd.read_excel(query_active)) if query_active.is_file() else 0

    challenge = legacy_root / req["dataset_dirs"]["challenge"]
    sdoh = legacy_root / req["dataset_dirs"]["sdoh"]
    challenge_ok = challenge.is_dir()
    sdoh_ok = sdoh.is_dir()

    bias_path, bias_n, bias_how = resolve_bias_analysis_root(legacy_root, req)
    if os.environ.get("PRISM_BIAS_ANALYSIS_ROOT"):
        bias_path = Path(os.environ["PRISM_BIAS_ANALYSIS_ROOT"])
        bias_n = _bias_subdir_count(bias_path)
        bias_how = "env:PRISM_BIAS_ANALYSIS_ROOT"

    bias_case_count: int | None = None
    if query_active.is_file() and challenge_ok and sdoh_ok:
        try:
            scripts = str(prism_root / "scripts")
            if scripts not in sys.path:
                sys.path.insert(0, scripts)
            from benchmark_coverage import load_coverage_expectations

            exp = load_coverage_expectations(legacy_root, query_active)
            bias_case_count = exp.bias_case_count
        except Exception:
            bias_case_count = None

    allow_partial = _allow_partial_sdoh()
    sdoh_assets_ok = bias_path is not None and bias_n >= min_bias

    p1_ok = query_rows >= expected_rows and challenge_ok
    p2_ok = p1_ok  # reasoning uses the same challenge case list
    p3_ok = sdoh_ok and (sdoh_assets_ok or allow_partial)

    pillars = [
        PillarStatus(
            "diagnostic",
            "Pillar 1 — Challenge diagnostic performance",
            p1_ok,
            f"query rows {query_rows}/{expected_rows}; Challenge_Dataset "
            f"{'present' if challenge_ok else 'missing'}",
        ),
        PillarStatus(
            "reasoning",
            "Pillar 2 — Challenge reasoning reliability",
            p2_ok,
            "Same query list and base_ask outputs (classification / reasoning steps)",
        ),
        PillarStatus(
            "sdoh",
            "Pillar 3 — SDoH bias metrics",
            p3_ok,
            (
                f"SDoH_Dataset {'present' if sdoh_ok else 'missing'}; "
                f"bias_analysis {bias_n} subdirs (full run needs ≥{min_bias}, "
                f"~{bias_case_count if bias_case_count is not None else '?'} SDoH cases in list); "
                f"root: {bias_path or 'not found'} ({bias_how})"
            ),
        ),
    ]

    return DataAssetsReport(
        query_rows=query_rows,
        expected_query_rows=expected_rows,
        challenge_dir_ok=challenge_ok,
        sdoh_dir_ok=sdoh_ok,
        bias_analysis_root=str(bias_path) if bias_path else "",
        bias_analysis_dirs=bias_n,
        bias_analysis_min_full=min_bias,
        bias_case_count=bias_case_count,
        pillars=pillars,
        sdoh_assets_ok=sdoh_assets_ok,
        allow_partial_sdoh=allow_partial,
    )


def print_report(report: DataAssetsReport) -> None:
    print("\n=== PRISM data assets (three pillars) ===")
    if report.allow_partial_sdoh:
        print("Mode: full case list (PRISM_ALLOW_PARTIAL_SDOH=1 — pillar 3 may be incomplete)")
    else:
        print("Mode: full case list")
    for p in report.pillars:
        mark = "OK" if p.ok else "INCOMPLETE"
        print(f"  [{mark}] {p.label}")
        print(f"       {p.detail}")
    if not report.sdoh_assets_ok and not report.allow_partial_sdoh:
        print(
            "\nFull pillar 3 needs sufficient bias_analysis (base_count/bias_count read formatted.json). "
            "Junction or copy ../results/bias_analysis_second_gpt5_bias_diagnosis locally, "
            "or set PRISM_BIAS_ANALYSIS_ROOT; for pillars 1–2 only set PRISM_ALLOW_PARTIAL_SDOH=1.",
            file=sys.stderr,
        )
    print()


def report_to_dict(report: DataAssetsReport) -> dict[str, Any]:
    d = asdict(report)
    d["pillars"] = [asdict(p) for p in report.pillars]
    return d


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check PRISM dataset assets for three benchmark pillars")
    parser.add_argument("--legacy-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument("--apply-bias-env", action="store_true", help="Set PRISM_BIAS_ANALYSIS_ROOT if suitable")
    args = parser.parse_args()

    legacy = args.legacy_root or _legacy_root_from_here()
    if args.apply_bias_env:
        apply_bias_analysis_root_env(legacy)

    report = build_report(legacy)
    if args.json:
        print(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    else:
        print_report(report)

    return report.exit_code_full_run()


if __name__ == "__main__":
    raise SystemExit(main())
