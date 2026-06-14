#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Expected artifact counts and per-stage completion for PRISM benchmark runs."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROUND_NUM_LIST = ["1_5answer", "1_5answer_1", "1_5answer_2"]

STAGE_LABELS: dict[str, str] = {
    "base_ask": "Base generation (base_ask)",
    "classification": "Per-round classification adjudication",
    "classification_summary": "Classification summary",
    "reasoning_flaws": "Reasoning flaws (dual judges)",
    "reasoning_flaws_summary": "Reasoning flaws summary",
    "reasoning_round_xlsx": "Reasoning summary xlsx",
    "bias_ask": "SDoH branch generation (bias_ask)",
    "bias_classification": "SDoH scenario classification",
    "base_count": "Original-branch bias count",
    "bias_count": "SDoH-branch bias count",
    "bias_metrics": "Bias_Analysis_Summary",
    "classification_vote": "Classification vote table",
    "composite_score": "Composite score output",
}


def _case_stem(name: str) -> str:
    base = str(name).strip()
    for suffix in (".jsonl", ".json", ".txt"):
        if base.lower().endswith(suffix):
            return base[: -len(suffix)]
    return base


def _ensure_legacy_imports(legacy_root: Path) -> None:
    root = str(legacy_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    import prism_bootstrap

    prism_bootstrap.install_import_paths(legacy_root)


@dataclass(frozen=True)
class CoverageExpectations:
    total_cases: int
    case_basenames: frozenset[str]
    bias_case_count: int
    bias_case_basenames: frozenset[str]
    bias_json_per_round: int  # scenario prompts = bias_case_count * 2 (typically 289*2=578)

    @property
    def bias_classification_per_scenario(self) -> int:
        return self.bias_case_count


def load_coverage_expectations(legacy_root: Path, query_xlsx: Path) -> CoverageExpectations:
    _ensure_legacy_imports(legacy_root)
    from benchmark_sdoh_utils import get_case_record, normalize_case_filename
    from legacy_script_config import MERGED_DATASET_WITH_ROLE_ROOT

    df = pd.read_excel(query_xlsx)
    if "File Name" not in df.columns:
        raise ValueError(f"{query_xlsx} missing column File Name")

    all_basenames: set[str] = set()
    bias_basenames: set[str] = set()
    bias_prompts = 0

    for raw in df["File Name"].dropna():
        rel = normalize_case_filename(str(raw).replace("/", "a"))
        stem = _case_stem(rel)
        all_basenames.add(stem)
        record = get_case_record(MERGED_DATASET_WITH_ROLE_ROOT, rel)
        if not record or not isinstance(record, dict):
            continue
        scenario_keys = [
            k for k in record if k.startswith("scenario1") or k.startswith("scenario2")
        ]
        if scenario_keys:
            bias_basenames.add(stem)
            bias_prompts += len(scenario_keys)

    # Per round: one JSON per scenario prompt (typically 2 per bias case).
    bias_json_per_round = bias_prompts if bias_basenames else 0

    return CoverageExpectations(
        total_cases=len(all_basenames),
        case_basenames=frozenset(all_basenames),
        bias_case_count=len(bias_basenames),
        bias_case_basenames=frozenset(bias_basenames),
        bias_json_per_round=bias_json_per_round,
    )


def _case_artifact_count(directory: Path, basenames: set[str], leaf: str) -> int:
    if not directory.exists():
        return 0
    return sum(1 for b in basenames if (directory / f"{b}{leaf}").exists())


def _glob_count(directory: Path, pattern: str) -> int:
    if not directory.exists():
        return 0
    return len(list(directory.glob(pattern)))


def _row(
    *,
    stage_id: str,
    model_id: str,
    round_id: str,
    done: int,
    expected: int,
    unit: str,
    note: str = "",
) -> dict[str, Any]:
    expected = max(int(expected), 0)
    done = int(done)
    pct = round(100.0 * done / expected, 2) if expected else (100.0 if done else 0.0)
    complete = expected > 0 and done >= expected
    return {
        "stage_id": stage_id,
        "stage": STAGE_LABELS.get(stage_id, stage_id),
        "model_id": model_id,
        "round": round_id,
        "done": done,
        "expected": expected,
        "unit": unit,
        "pct": pct,
        "complete": complete,
        "note": note,
    }


def _count_stage_done_expected(legacy_root: Path, model_id: str, round_id: str, mode: str) -> tuple[int, int, str]:
    """base_count / bias_count run on bias_analysis ∩ output_json only, not all 942 challenge cases."""
    from count_stage_health import count_round_stats

    done, expected, _missing, note = count_round_stats(legacy_root, model_id, round_id, mode)
    return done, expected, note


def bias_analysis_subdir_count(legacy_root: Path) -> int:
    _ensure_legacy_imports(legacy_root)
    from count_stage_runner import ensure_bias_analysis_root

    root = Path(ensure_bias_analysis_root())
    if not root.is_dir():
        return 0
    return sum(1 for d in root.iterdir() if d.is_dir())


def compute_completion_table(
    legacy_root: Path,
    model_ids: list[str],
    expectations: CoverageExpectations,
) -> list[dict[str, Any]]:
    bench = legacy_root / "benchmark"
    res = bench / "result"
    cases = set(expectations.case_basenames)
    bias_cases = set(expectations.bias_case_basenames)
    n_cases = expectations.total_cases
    n_bias_json = expectations.bias_json_per_round
    n_bias_cls = expectations.bias_classification_per_scenario

    rows: list[dict[str, Any]] = []

    for mid in model_ids:
        mdir = res / mid
        for rnd in ROUND_NUM_LIST:
            n = _case_artifact_count(mdir / f"{rnd}_output_json", cases, ".json")
            rows.append(
                _row(
                    stage_id="base_ask",
                    model_id=mid,
                    round_id=rnd,
                    done=n,
                    expected=n_cases,
                    unit="cases",
                )
            )

            n = _case_artifact_count(mdir / f"{rnd}_llm_responses_1", cases, "_classification.json")
            rows.append(
                _row(
                    stage_id="classification",
                    model_id=mid,
                    round_id=rnd,
                    done=n,
                    expected=n_cases,
                    unit="cases",
                )
            )

            n = _case_artifact_count(
                mdir / f"{rnd}_llm_responses_summary", cases, "_classification.json"
            )
            rows.append(
                _row(
                    stage_id="classification_summary",
                    model_id=mid,
                    round_id=rnd,
                    done=n,
                    expected=n_cases,
                    unit="cases",
                )
            )

            d0 = _case_artifact_count(mdir / f"{rnd}_flaws", cases, "_flaws.json")
            d1 = _case_artifact_count(mdir / f"{rnd}_flaws1", cases, "_flaws.json")
            rows.append(
                _row(
                    stage_id="reasoning_flaws",
                    model_id=mid,
                    round_id=rnd,
                    done=min(d0, d1),
                    expected=n_cases,
                    unit="cases",
                    note=f"flaws {d0}/{n_cases}, flaws1 {d1}/{n_cases}",
                )
            )

            n_sum = _case_artifact_count(
                mdir / f"{rnd}_flaws_summary", cases, "_flaws_summary.json"
            )
            rows.append(
                _row(
                    stage_id="reasoning_flaws_summary",
                    model_id=mid,
                    round_id=rnd,
                    done=n_sum,
                    expected=n_cases,
                    unit="cases",
                )
            )

            bj = mdir / "bias" / rnd / "output_json"
            n_b = _glob_count(bj, "*.json") if bj.exists() else 0
            rows.append(
                _row(
                    stage_id="bias_ask",
                    model_id=mid,
                    round_id=rnd,
                    done=n_b,
                    expected=n_bias_json,
                    unit="prompts",
                    note=f"{expectations.bias_case_count} cases × 2 scenarios",
                )
            )

            for sc in ("scenario1", "scenario2"):
                d = mdir / "bias" / f"{rnd}_llm_responses_1_{sc}"
                n_c = _glob_count(d, "*_classification.json")
                rows.append(
                    _row(
                        stage_id="bias_classification",
                        model_id=mid,
                        round_id=f"{rnd}/{sc}",
                        done=n_c,
                        expected=n_bias_cls,
                        unit="cases",
                    )
                )

            bc_done, bc_exp, bc_note = _count_stage_done_expected(legacy_root, mid, rnd, "base")
            rows.append(
                _row(
                    stage_id="base_count",
                    model_id=mid,
                    round_id=rnd,
                    done=bc_done,
                    expected=bc_exp,
                    unit="count_cases",
                    note=bc_note,
                )
            )

            bbc_done, bbc_exp, bbc_note = _count_stage_done_expected(legacy_root, mid, rnd, "bias")
            rows.append(
                _row(
                    stage_id="bias_count",
                    model_id=mid,
                    round_id=rnd,
                    done=bbc_done,
                    expected=bbc_exp,
                    unit="count_cases",
                    note=bbc_note,
                )
            )

    for rnd in ROUND_NUM_LIST:
        fp = bench / f"{rnd}_flaws_summary.xlsx"
        rows.append(
            _row(
                stage_id="reasoning_round_xlsx",
                model_id="(shared)",
                round_id=rnd,
                done=1 if fp.is_file() else 0,
                expected=1,
                unit="file",
            )
        )

    rows.append(
        _row(
            stage_id="bias_metrics",
            model_id="(shared)",
            round_id="-",
            done=1 if (legacy_root / "Bias_Analysis_Summary.xlsx").is_file() else 0,
            expected=1,
            unit="file",
        )
    )
    vote_path = bench / "classification_voted_caselevel.xlsx"
    rows.append(
        _row(
            stage_id="classification_vote",
            model_id="(shared)",
            round_id="-",
            done=1 if vote_path.is_file() else 0,
            expected=1,
            unit="file",
            note=str(vote_path) if vote_path.is_file() else "missing",
        )
    )
    score_path = bench / "benchmark_scores_output.xlsx"
    rows.append(
        _row(
            stage_id="composite_score",
            model_id="(shared)",
            round_id="-",
            done=1 if score_path.is_file() else 0,
            expected=1,
            unit="file",
        )
    )

    return rows


def completion_summary_from_table(rows: list[dict[str, Any]]) -> dict[str, Any]:
    incomplete = [r for r in rows if not r.get("complete")]
    by_stage: dict[str, dict[str, Any]] = {}
    for r in rows:
        sid = str(r.get("stage_id", ""))
        bucket = by_stage.setdefault(
            sid,
            {"stage_id": sid, "stage": r.get("stage"), "lines": 0, "incomplete_lines": 0},
        )
        bucket["lines"] += 1
        if not r.get("complete"):
            bucket["incomplete_lines"] += 1
    return {
        "all_complete": len(incomplete) == 0,
        "total_lines": len(rows),
        "incomplete_lines": len(incomplete),
        "by_stage": list(by_stage.values()),
    }


def print_completion_table(
    rows: list[dict[str, Any]],
    *,
    expectations: CoverageExpectations,
    legacy_root: Path | None = None,
    title: str = "Stage completion",
    max_rows: int = 80,
) -> None:
    summary = completion_summary_from_table(rows)
    print(f"\n=== {title} ===")
    print(
        f"Challenge cases: {expectations.total_cases}; "
        f"SDoH/bias_ask cases: {expectations.bias_case_count} (expected JSON per round "
        f"{expectations.bias_json_per_round} = {expectations.bias_case_count}×2)"
    )
    if legacy_root is not None:
        n_ba = bias_analysis_subdir_count(legacy_root)
        if n_ba < expectations.bias_case_count:
            print(
                f"Note: results/bias_analysis… has only {n_ba} subdirs (full SDoH needs ~"
                f"{expectations.bias_case_count}). base_count/bias_count and IR/SSR cover that subset only."
            )
    if summary["all_complete"]:
        print("Check: all rows meet expected completion.")
    else:
        print(
            f"Check: {summary['incomplete_lines']}/{summary['total_lines']} rows incomplete. "
            "Composite score and SDoH metrics may be wrong until artifacts are filled."
        )

    header = f"{'Stage':<28} {'Model':<12} {'Round':<22} {'Done':>8} {'Expect':>8} {'%':>7} {'OK':>3}"
    print(header)
    print("-" * 95)
    shown = 0
    for r in rows:
        if r.get("complete"):
            continue
        mark = "Y" if r.get("complete") else "N"
        line = (
            f"{str(r.get('stage', ''))[:28]:<28} "
            f"{str(r.get('model_id', ''))[:12]:<12} "
            f"{str(r.get('round', ''))[:22]:<22} "
            f"{r.get('done', 0):>8} "
            f"{r.get('expected', 0):>8} "
            f"{r.get('pct', 0):>6.1f} "
            f"{mark:>3}"
        )
        note = r.get("note")
        print(line + (f"  ({note})" if note else ""))
        shown += 1
        if shown >= max_rows:
            rest = summary["incomplete_lines"] - max_rows
            if rest > 0:
                print(f"… {rest} more incomplete rows; see completion JSON / xlsx")
            break

    if summary["incomplete_lines"] == 0:
        print("(All rows complete; nothing incomplete)")


def write_completion_artifacts(
    *,
    legacy_root: Path,
    rows: list[dict[str, Any]],
    expectations: CoverageExpectations,
    output_dir: Path,
    prefix: str,
) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "expectations": {
            "total_cases": expectations.total_cases,
            "bias_case_count": expectations.bias_case_count,
            "bias_json_per_round": expectations.bias_json_per_round,
            "bias_note": "bias_ask JSON per round = cases with scenario1/2 × 2 (full ~289×2=578)",
        },
        "summary": completion_summary_from_table(rows),
        "rows": rows,
    }
    json_path = output_dir / f"{prefix}.json"
    json_path.write_text(
        __import__("json").dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    xlsx_path: Path | None = None
    try:
        xlsx_path = output_dir / f"{prefix}.xlsx"
        pd.DataFrame(rows).to_excel(xlsx_path, index=False)
    except Exception:
        xlsx_path = None
    latest = output_dir / "latest_completion_table.json"
    latest.write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    return json_path, xlsx_path
