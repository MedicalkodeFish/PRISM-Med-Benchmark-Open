#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Post-run coverage / failure report for full PRISM benchmark runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROUND_NUM_LIST = ["1_5answer", "1_5answer_1", "1_5answer_2"]


def _case_stem(name: str) -> str:
    base = str(name).strip()
    for suffix in (".jsonl", ".json", ".txt"):
        if base.lower().endswith(suffix):
            return base[: -len(suffix)]
    return base


def load_case_basenames_from_query(query_xlsx: Path) -> set[str]:
    df = pd.read_excel(query_xlsx)
    if "File Name" not in df.columns:
        raise ValueError(f"{query_xlsx} missing column File Name")
    return {_case_stem(str(v)) for v in df["File Name"].dropna()}


def collect_base_ask_failures(legacy_root: Path, model_ids: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    res = legacy_root / "benchmark" / "result"
    for mid in model_ids:
        for rnd in ROUND_NUM_LIST:
            out_dir = res / mid / rnd
            if not out_dir.is_dir():
                continue
            for failed_path in sorted(out_dir.glob("*.failed.json")):
                stem = failed_path.name.replace(".failed.json", "")
                try:
                    data = json.loads(failed_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    data = {"raw": failed_path.read_text(encoding="utf-8", errors="replace")[:500]}
                records.append(
                    {
                        "model_id": mid,
                        "round": rnd,
                        "case_stem": stem,
                        "reason": data.get("reason"),
                        "marked_at": data.get("marked_at"),
                        "base_file": data.get("base_file"),
                        "extra": data.get("extra"),
                    }
                )
    return records


def _missing_in_dir(directory: Path, basenames: set[str], leaf: str) -> list[str]:
    if not directory.exists():
        return sorted(basenames)
    missing = [b for b in basenames if not (directory / f"{b}{leaf}").exists()]
    return sorted(missing)


def enrich_checks_with_missing_cases(
    legacy_root: Path,
    model_ids: list[str],
    case_basenames: set[str],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach `missing_cases` (and counts) to artifact checks that are not OK."""
    bench = legacy_root / "benchmark"
    res = bench / "result"
    out: list[dict[str, Any]] = []
    for row in checks:
        enriched = dict(row)
        if row.get("ok"):
            out.append(enriched)
            continue
        stage = row.get("stage", "")
        key = str(row.get("key", ""))
        missing: list[str] = []
        if stage == "base_ask" and "/" in key:
            mid, rnd = key.split("/", 1)
            missing = _missing_in_dir(res / mid / f"{rnd}_output_json", case_basenames, ".json")
        elif stage == "classification" and "/" in key:
            mid, rnd = key.split("/", 1)
            missing = _missing_in_dir(
                res / mid / f"{rnd}_llm_responses_1", case_basenames, "_classification.json"
            )
        elif stage == "classification_summary" and "/" in key:
            mid, rnd = key.split("/", 1)
            missing = _missing_in_dir(
                res / mid / f"{rnd}_llm_responses_summary", case_basenames, "_classification.json"
            )
        elif stage == "reasoning_flaws" and "/" in key:
            mid, rnd = key.split("/", 1)
            m0 = _missing_in_dir(res / mid / f"{rnd}_flaws", case_basenames, "_flaws.json")
            m1 = _missing_in_dir(res / mid / f"{rnd}_flaws1", case_basenames, "_flaws.json")
            missing = sorted(set(m0) | set(m1))
        elif stage == "reasoning_flaws_summary" and "/" in key:
            mid, rnd = key.split("/", 1)
            missing = _missing_in_dir(
                res / mid / f"{rnd}_flaws_summary", case_basenames, "_flaws_summary.json"
            )
        if missing:
            enriched["missing_count"] = len(missing)
            enriched["missing_cases"] = missing
        out.append(enriched)
    return out


def build_run_verification_payload(
    *,
    legacy_root: Path,
    models: list[str],
    query_xlsx: Path,
    pipeline_report: dict[str, Any],
    manifest_path: Path | None,
) -> dict[str, Any]:
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from benchmark_coverage import (
        compute_completion_table,
        completion_summary_from_table,
        load_coverage_expectations,
    )
    from benchmark_verify import resolve_model_ids, verify_artifacts

    expectations = load_coverage_expectations(legacy_root, query_xlsx)
    case_basenames = set(expectations.case_basenames)
    expected_cases = expectations.total_cases
    model_ids = resolve_model_ids(legacy_root, models)
    completion_rows = compute_completion_table(legacy_root, model_ids, expectations)

    verification = verify_artifacts(
        legacy_root,
        model_ids,
        expected_cases=expected_cases,
        case_basenames_set=case_basenames,
    )
    checks = enrich_checks_with_missing_cases(
        legacy_root, model_ids, case_basenames, verification.get("checks", [])
    )
    verification["checks"] = checks
    failures = collect_base_ask_failures(legacy_root, model_ids)

    failed_checks = [c for c in checks if not c.get("ok")]
    summary_by_stage: dict[str, dict[str, int]] = {}
    for c in failed_checks:
        st = str(c.get("stage", ""))
        summary_by_stage.setdefault(st, {"failed_checks": 0, "missing_cases_total": 0})
        summary_by_stage[st]["failed_checks"] += 1
        summary_by_stage[st]["missing_cases_total"] += int(c.get("missing_count") or 0)

    return {
        "expected_cases": expected_cases,
        "bias_case_count": expectations.bias_case_count,
        "bias_json_per_round": expectations.bias_json_per_round,
        "models": models,
        "model_ids": model_ids,
        "query_table": str(query_xlsx.resolve()),
        "manifest": str(manifest_path.resolve()) if manifest_path else None,
        "pipeline_status": pipeline_report.get("status"),
        "completion": {
            "summary": completion_summary_from_table(completion_rows),
            "rows": completion_rows,
        },
        "verification": {
            "all_ok": verification.get("all_ok"),
            "failed_check_count": len(failed_checks),
            "checks": checks,
        },
        "base_ask_failures": failures,
        "base_ask_failure_count": len(failures),
        "summary_by_stage": summary_by_stage,
    }


def write_run_verification_report(
    *,
    legacy_root: Path,
    models: list[str],
    query_xlsx: Path,
    pipeline_report: dict[str, Any],
    manifest_path: Path | None,
    output_path: Path,
) -> dict[str, Any]:
    payload = build_run_verification_payload(
        legacy_root=legacy_root,
        models=models,
        query_xlsx=query_xlsx,
        pipeline_report=pipeline_report,
        manifest_path=manifest_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def print_run_verification_summary(payload: dict[str, Any], output_path: Path) -> None:
    exp = payload.get("expected_cases", 0)
    bias_n = payload.get("bias_case_count", 0)
    bias_j = payload.get("bias_json_per_round", 0)
    ver = payload.get("verification") or {}
    all_ok = ver.get("all_ok")
    n_fail = ver.get("failed_check_count", 0)
    n_mark = payload.get("base_ask_failure_count", 0)
    comp = payload.get("completion") or {}
    comp_summary = comp.get("summary") or {}

    print("\n=== Post-run verification (coverage / failures) ===")
    print(f"Expected cases: {exp}; bias_ask scope: {bias_n} cases ×2 = {bias_j} JSON per round")
    if comp_summary and not comp_summary.get("all_complete"):
        print(
            f"Completion table: {comp_summary.get('incomplete_lines', '?')}/"
            f"{comp_summary.get('total_lines', '?')} rows incomplete (see completion.rows in report)"
        )
    print(f"All step checks passed: {'yes' if all_ok else 'no'} ({n_fail} failed check(s))")
    print(f"base_ask failure markers (*.failed.json): {n_mark}")
    if payload.get("summary_by_stage"):
        print("Failed checks by stage:")
        for stage, agg in sorted(payload["summary_by_stage"].items()):
            print(
                f"  - {stage}: {agg.get('failed_checks', 0)} failed check(s), "
                f"~{agg.get('missing_cases_total', 0)} missing case slots (may double-count across rounds)"
            )

    shown = 0
    for row in ver.get("checks") or []:
        if row.get("ok"):
            continue
        mark = "MISS"
        miss = row.get("missing_count")
        miss_hint = f", missing {miss} case(s)" if miss else ""
        print(f"  [{mark}] {row.get('stage', ''):22} {row.get('key', ''):36} {row.get('detail', '')}{miss_hint}")
        shown += 1
        if shown >= 40 and n_fail > 40:
            print(f"  … {n_fail - 40} more failures; see report JSON")
            break

    if n_mark:
        print("base_ask failure marker samples (up to 15):")
        for rec in (payload.get("base_ask_failures") or [])[:15]:
            print(
                f"  - {rec.get('model_id')}/{rec.get('round')}/{rec.get('case_stem')}: "
                f"{rec.get('reason')} @ {rec.get('marked_at', '')}"
            )
        if n_mark > 15:
            print(f"  … {n_mark - 15} more; see base_ask_failures in report JSON")

    print(f"Full report: {output_path}")


def main() -> int:
    import argparse

    legacy_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Generate PRISM full-run verification report (no pipeline)")
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated model names (default: legacy_script_config DEFAULT_MODEL_LIST)",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional run manifest JSON to reference in the report",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output path (default: prism_benchmark/runs/run_verification_<timestamp>.json)",
    )
    args = parser.parse_args()

    cfg_dir = str(legacy_root / "config")
    if cfg_dir not in sys.path:
        sys.path.insert(0, cfg_dir)
    from legacy_script_config import DEFAULT_MODEL_LIST

    models = [m.strip() for m in args.models.split(",") if m.strip()] or list(DEFAULT_MODEL_LIST)
    query_xlsx = legacy_root / "dataset" / "question" / "query_question.xlsx"
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    if args.output:
        out = Path(args.output).resolve()
    else:
        from datetime import datetime

        out = (
            legacy_root
            / "prism_benchmark"
            / "runs"
            / f"run_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

    pipeline_report = {"status": "unknown", "note": "verify-only, pipeline not executed"}
    if manifest_path and manifest_path.is_file():
        try:
            pipeline_report = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pipeline_report["manifest_read_error"] = str(manifest_path)

    payload = write_run_verification_report(
        legacy_root=legacy_root,
        models=models,
        query_xlsx=query_xlsx,
        pipeline_report=pipeline_report,
        manifest_path=manifest_path,
        output_path=out,
    )
    from benchmark_coverage import compute_completion_table, load_coverage_expectations, print_completion_table

    expectations = load_coverage_expectations(legacy_root, query_xlsx)
    rows = compute_completion_table(legacy_root, payload["model_ids"], expectations)
    print_completion_table(
        rows, expectations=expectations, legacy_root=legacy_root, title="Current — stage completion"
    )
    print_run_verification_summary(payload, out)
    return 0 if (payload.get("verification") or {}).get("all_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
