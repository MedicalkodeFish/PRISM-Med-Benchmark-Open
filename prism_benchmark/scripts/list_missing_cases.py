#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Print missing benchmark cases and base_ask failure markers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    legacy_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default="", help="Comma-separated model names")
    parser.add_argument("--json-out", default="", help="Optional output JSON path")
    args = parser.parse_args()

    if str(legacy_root) not in sys.path:
        sys.path.insert(0, str(legacy_root))
    import prism_bootstrap

    prism_bootstrap.install_import_paths(legacy_root)

    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    cfg_dir = str(legacy_root / "config")
    if cfg_dir not in sys.path:
        sys.path.insert(0, cfg_dir)
    from legacy_script_config import DEFAULT_MODEL_LIST

    from benchmark_coverage import ROUND_NUM_LIST, load_coverage_expectations
    from benchmark_run_report import collect_base_ask_failures, enrich_checks_with_missing_cases
    from count_stage_health import collect_missing_count_outputs, format_count_health_message
    from benchmark_verify import resolve_model_ids, verify_artifacts

    models = [m.strip() for m in args.models.split(",") if m.strip()] or list(DEFAULT_MODEL_LIST)
    query = legacy_root / "dataset" / "question" / "query_question.xlsx"
    exp = load_coverage_expectations(legacy_root, query)
    model_ids = resolve_model_ids(legacy_root, models)
    cases = set(exp.case_basenames)

    ver = verify_artifacts(
        legacy_root, model_ids, expected_cases=exp.total_cases, case_basenames_set=cases
    )
    checks = enrich_checks_with_missing_cases(legacy_root, model_ids, cases, ver.get("checks", []))
    failures = collect_base_ask_failures(legacy_root, model_ids)

    count_missing = collect_missing_count_outputs(legacy_root, model_ids, ROUND_NUM_LIST)

    res = legacy_root / "benchmark" / "result"

    def missing_in(directory: Path, basenames: set[str], leaf: str) -> list[str]:
        if not directory.is_dir():
            return sorted(basenames)
        return sorted(b for b in basenames if not (directory / f"{b}{leaf}").exists())

    per_round: dict[str, dict[str, list[str]]] = {}
    for mid in model_ids:
        mdir = res / mid
        for rnd in ROUND_NUM_LIST:
            key = f"{mid}/{rnd}"
            per_round[key] = {
                "base_ask": missing_in(mdir / f"{rnd}_output_json", cases, ".json"),
                "classification": missing_in(
                    mdir / f"{rnd}_llm_responses_1", cases, "_classification.json"
                ),
                "classification_summary": missing_in(
                    mdir / f"{rnd}_llm_responses_summary", cases, "_classification.json"
                ),
            }

    payload = {
        "models": models,
        "model_ids": model_ids,
        "expected_cases": exp.total_cases,
        "base_ask_failures": failures,
        "failed_checks": [c for c in checks if not c.get("ok")],
        "count_missing_outputs": count_missing,
        "per_round_missing": per_round,
    }

    print("Models:", ", ".join(f"{a} -> {b}" for a, b in zip(models, model_ids)))
    print()
    print("=== base_ask failure markers (*.failed.json) ===")
    if not failures:
        print("(none)")
    for rec in failures:
        print(
            f"  {rec['model_id']}/{rec['round']}/{rec['case_stem']}: "
            f"{rec.get('reason')} @ {rec.get('marked_at', '')}"
        )

    print()
    print("=== Missing case stems per round ===")
    for key, stages in per_round.items():
        any_miss = any(stages[k] for k in stages)
        if not any_miss:
            continue
        print(f"--- {key} ---")
        for stage, stems in stages.items():
            if stems:
                print(f"  {stage}: {', '.join(stems)}")

    print()
    print("=== base_count / bias_count missing outputs ===")
    count_msg = format_count_health_message(missing_outputs=count_missing)
    if count_msg.strip():
        print(count_msg)
    else:
        print("(none)")

    print()
    print("=== Other failed checks ===")
    for c in checks:
        if c.get("ok"):
            continue
        if c.get("stage") in (
            "base_ask",
            "classification",
            "classification_summary",
        ) and c.get("missing_cases"):
            continue
        print(f"  [{c.get('stage')}] {c.get('key')}: {c.get('detail')}")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print("Written:", out.resolve())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
