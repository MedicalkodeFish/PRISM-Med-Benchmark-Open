#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PRISM Benchmark one-click launcher (full 942 cases, 12-step pipeline).

Run with no arguments:
  - Double-click ``run_prism_full_benchmark.bat`` in this directory
  - Or run this file from your IDE

Sets UTF-8, restores full data when needed, prints per-stage completion tables at
start/end, preflights count inputs (base_count/bias_count), clears base_ask failure
markers, probes APIs, and runs the full pipeline.

Optional env (bounded tail sweeps on incomplete cases only; hard max 2, default 1):
  PRISM_BASE_ASK_TAIL_PASSES, PRISM_BIAS_ASK_TAIL_PASSES (set 0 to disable).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

LEGACY_ROOT = Path(__file__).resolve().parent
PRISM_ROOT = LEGACY_ROOT / "prism_benchmark"
DEFAULT_CONFIG = PRISM_ROOT / "configs" / "default.json"
FULL_QUERY_BACKUP = LEGACY_ROOT / "dataset" / "question" / "query_question.full.xlsx"
ACTIVE_QUERY = LEGACY_ROOT / "dataset" / "question" / "query_question.xlsx"
def _data_requirements() -> dict:
    path = PRISM_ROOT / "configs" / "data_requirements.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _expected_full_rows() -> int:
    return int(_data_requirements().get("expected_query_rows", 942))


def _config_imports():
    if str(LEGACY_ROOT) not in sys.path:
        sys.path.insert(0, str(LEGACY_ROOT))
    from config.legacy_script_config import BASE_ASK_MODEL_LIST, DEFAULT_MODEL_LIST, ROUND_NUM_LIST

    return BASE_ASK_MODEL_LIST, DEFAULT_MODEL_LIST, ROUND_NUM_LIST


def _default_subject_models() -> list[str]:
    _, default_list, _ = _config_imports()
    return list(default_list)


def _apply_utf8_runtime() -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")


def _scripts_dir() -> Path:
    d = PRISM_ROOT / "scripts"
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    return d


def _apply_full_bias_analysis_root_env() -> None:
    _scripts_dir()
    from data_assets_check import apply_bias_analysis_root_env

    path, n, how = apply_bias_analysis_root_env(LEGACY_ROOT)
    if path and n:
        print(f"Pillar 3 count data root: {path} ({n} subdirs, {how})")


def _apply_full_benchmark_env(models: list[str]) -> None:
    joined = ",".join(models)
    for key in (
        "PRISM_BASE_ASK_MODELS",
        "PRISM_BIAS_ASK_MODELS",
        "PRISM_CLASSIFICATION_MODELS",
        "PRISM_REASONING_MODELS",
        "PRISM_REASONING_SUMMARY_MODELS",
        "PRISM_COUNT_TARGET_MODELS",
    ):
        os.environ[key] = joined
    os.environ.setdefault("PRISM_REASONING_LLM_MODEL", "gemini-2.5-pro")


def _query_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len(pd.read_excel(path))


def _restore_full_data() -> None:
    script = PRISM_ROOT / "scripts" / "prepare_full_benchmark_data.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    subprocess.run([sys.executable, str(script)], cwd=str(LEGACY_ROOT), check=True)


def _auto_restore_full_data_if_needed() -> None:
    expected = _expected_full_rows()
    n = _query_row_count(ACTIVE_QUERY)
    if n >= expected:
        return
    if not FULL_QUERY_BACKUP.is_file():
        return
    print(f"Query table has only {n} rows; restoring full {expected} rows…")
    _restore_full_data()


def _rollback_progress_one_batch(round_num: str) -> None:
    progress = LEGACY_ROOT / "benchmark" / "result" / f"progress_round{round_num}.json"
    if not progress.is_file():
        return
    lib = str(LEGACY_ROOT / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    from base_ask_progress import (
        BASE_ASK_BATCH_SIZE,
        load_progress,
        next_case_index_from_progress,
        rollback_progress_file,
    )

    before = next_case_index_from_progress(load_progress(progress), total_cases=10**9)
    if rollback_progress_file(progress, current_batch_size=BASE_ASK_BATCH_SIZE):
        after = next_case_index_from_progress(load_progress(progress), total_cases=10**9)
        print(f"Rolled back progress {progress.name}: next_case_index {before} -> {after}")


def _auto_clear_base_ask_failures(model_ids: list[str]) -> int:
    _, _, round_num_list = _config_imports()
    total = 0
    for mid in model_ids:
        for rnd in round_num_list:
            out_dir = LEGACY_ROOT / "benchmark" / "result" / mid / rnd
            if not out_dir.is_dir():
                continue
            n_round = 0
            for failed in out_dir.glob("*.failed.json"):
                stem = failed.name.replace(".failed.json", "")
                meta = out_dir / f"{stem}.meta.json"
                failed.unlink(missing_ok=True)
                meta.unlink(missing_ok=True)
                n_round += 1
            if n_round:
                total += n_round
                print(f"Cleared {n_round} base_ask failure marker(s) under {mid}/{rnd}")
                _rollback_progress_one_batch(rnd)
    if total:
        print(f"Cleared {total} base_ask failure marker(s); pipeline will resume/retry those cases.")
    return total


def _resolve_model_ids(models: list[str]) -> list[str]:
    scripts_dir = PRISM_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from benchmark_verify import resolve_model_ids

    return resolve_model_ids(LEGACY_ROOT, models)


def _emit_completion_overview(models: list[str], *, phase: str) -> None:
    scripts_dir = PRISM_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from benchmark_coverage import (
        compute_completion_table,
        load_coverage_expectations,
        print_completion_table,
        write_completion_artifacts,
    )

    expectations = load_coverage_expectations(LEGACY_ROOT, ACTIVE_QUERY)
    model_ids = _resolve_model_ids(models)
    rows = compute_completion_table(LEGACY_ROOT, model_ids, expectations)
    title = "Before run — stage completion" if phase == "start" else "After run — stage completion"
    print_completion_table(rows, expectations=expectations, legacy_root=LEGACY_ROOT, title=title)

    runs_dir = PRISM_ROOT / "runs"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"completion_{phase}_{stamp}"
    json_path, xlsx_path = write_completion_artifacts(
        legacy_root=LEGACY_ROOT,
        rows=rows,
        expectations=expectations,
        output_dir=runs_dir,
        prefix=prefix,
    )
    print(f"Completion table JSON: {json_path}")
    if xlsx_path:
        print(f"Completion table Excel: {xlsx_path}")
    print(f"Latest snapshot: {runs_dir / 'latest_completion_table.json'}")


def _run_data_assets_check(*, check_only: bool) -> int:
    _scripts_dir()
    from data_assets_check import build_report, print_report

    if os.environ.get("PRISM_ALLOW_PARTIAL_SDOH", "").strip().lower() in ("1", "true", "yes"):
        pass  # build_report reads env
    report = build_report(LEGACY_ROOT)
    print_report(report)
    code = report.exit_code_full_run()
    if code == 6 and not check_only:
        print("Aborted: full run requires pillar 3 SDoH assets. See docs/BENCHMARK.md.", file=sys.stderr)
    return code


def _run_count_health_check(models: list[str], *, include_missing_outputs: bool) -> int:
    if str(LEGACY_ROOT) not in sys.path:
        sys.path.insert(0, str(LEGACY_ROOT))
    _, _, round_num_list = _config_imports()
    model_ids = _resolve_model_ids(models)
    from count_stage_health import (
        count_health_exit_code,
        format_count_health_message,
        print_count_health_summary,
        scan_count_input_prompt_errors,
    )

    if include_missing_outputs:
        prompt_issues, missing = print_count_health_summary(
            LEGACY_ROOT, model_ids, round_num_list, scan_inputs=True
        )
    else:
        prompt_issues = scan_count_input_prompt_errors(LEGACY_ROOT, model_ids, round_num_list)
        missing = []
        text = format_count_health_message(prompt_issues=prompt_issues)
        if text.strip():
            print("\n=== Count input preflight (prompt build from JSON) ===")
            print(text)
    return count_health_exit_code(prompt_issues, missing if include_missing_outputs else [])


def _reference_table_row_count() -> int:
    if str(LEGACY_ROOT) not in sys.path:
        sys.path.insert(0, str(LEGACY_ROOT))
    from config.legacy_script_config import resolve_reference_table_path

    ref = resolve_reference_table_path(LEGACY_ROOT / "benchmark")
    if not ref.is_file():
        return 0
    return len(pd.read_excel(ref))


def _print_preflight(models: list[str]) -> int:
    n_active = _query_row_count(ACTIVE_QUERY)
    expected = _expected_full_rows()
    print("=== PRISM startup ===")
    print("Working directory:", LEGACY_ROOT)
    print("Case count:", n_active)
    print("Subject models:", ", ".join(models))
    print("Reasoning judge model:", os.environ.get("PRISM_REASONING_LLM_MODEL", "gemini-2.5-pro"))
    print(
        "Tail sweeps (incomplete only): base_ask="
        f"{os.environ.get('PRISM_BASE_ASK_TAIL_PASSES', '1')}, "
        f"bias_ask={os.environ.get('PRISM_BIAS_ASK_TAIL_PASSES', '1')} "
        f"(hard max 2 per stage; 0=off)"
    )

    if not DEFAULT_CONFIG.is_file():
        print("Error: pipeline config not found.", file=sys.stderr)
        return 1
    if n_active < expected:
        print(
            f"Error: full run needs {expected} cases; found {n_active} and auto-restore failed.",
            file=sys.stderr,
        )
        return 2
    n_ref = _reference_table_row_count()
    if n_ref and n_ref != n_active:
        print(
            f"Error: reference_table_bias_with_doi.xlsx has {n_ref} rows but query has {n_active}. "
            f"Run: python .\\prism_benchmark\\scripts\\prepare_full_benchmark_data.py",
            file=sys.stderr,
        )
        return 8
    return _run_data_assets_check(check_only=False)


def _test_api(models: list[str], *, quiet_ok: bool = False) -> int:
    if str(LEGACY_ROOT) not in sys.path:
        sys.path.insert(0, str(LEGACY_ROOT))
    from model_config import resolve_model

    print("=== API probe ===")
    ok_all = True
    for name in models:
        mc = resolve_model(name)
        if not mc:
            print(f"[FAIL] {name}: not configured in model_config.json")
            ok_all = False
            continue
        api_model = mc.get("model_id") or mc.get("id")
        url = mc.get("url", "")
        try:
            from openai import OpenAI

            client = OpenAI(base_url=url, api_key=mc["api_key"], timeout=60)
            resp = client.chat.completions.create(
                model=api_model,
                messages=[{"role": "user", "content": "Reply with exactly: pong"}],
                max_tokens=8,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not quiet_ok:
                print(f"[OK] {name} ({api_model})")
            else:
                print(f"[OK] {name}: {text[:40]}")
        except Exception as e:
            print(f"[FAIL] {name}: {type(e).__name__}: {e}")
            ok_all = False
    if not ok_all:
        print("API probe failed. Check model_config/model_config.json and network.", file=sys.stderr)
    return 0 if ok_all else 3


def _run_full_pipeline(
    *,
    steps: list[str] | None,
    continue_on_error: bool,
    manifest_path: Path | None,
    models: list[str],
) -> int:
    src_root = PRISM_ROOT / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from prism_benchmark.config import load_config
    from prism_benchmark.pipeline import run_pipeline
    from prism_benchmark.steps import parse_steps

    cfg = load_config(str(DEFAULT_CONFIG))
    step_defs = parse_steps(cfg["steps"])
    legacy_root = (PRISM_ROOT / cfg.get("legacy_root", "..")).resolve()
    python_executable = cfg.get("python_executable", sys.executable)

    runs_dir = PRISM_ROOT / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    default_manifest = runs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    manifest = manifest_path.resolve() if manifest_path else default_manifest

    print("\n=== Starting 12-step pipeline (safe to interrupt and re-run to resume) ===")
    if steps:
        print("Selected steps:", ", ".join(steps))

    report = run_pipeline(
        steps=step_defs,
        python_executable=python_executable,
        legacy_root=legacy_root,
        selected_step_ids=steps,
        continue_on_error=continue_on_error,
        run_manifest_path=manifest,
    )
    print(f"\nPipeline status: {report['status']}")
    print("Run manifest:", manifest)
    print("Composite score:", LEGACY_ROOT / "benchmark" / "benchmark_scores_output.xlsx")

    scripts_dir = PRISM_ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from benchmark_run_report import print_run_verification_summary, write_run_verification_report

    verification_path = manifest.with_name(f"{manifest.stem}_verification.json")
    payload = write_run_verification_report(
        legacy_root=LEGACY_ROOT,
        models=models,
        query_xlsx=ACTIVE_QUERY,
        pipeline_report=report,
        manifest_path=manifest,
        output_path=verification_path,
    )
    print_run_verification_summary(payload, verification_path)
    _emit_completion_overview(models, phase="end")

    pipeline_ok = report.get("status") == "success"
    artifacts_ok = bool((payload.get("verification") or {}).get("all_ok"))
    completion_ok = bool((payload.get("completion") or {}).get("summary", {}).get("all_complete"))
    return 0 if pipeline_ok and artifacts_ok and completion_ok else 1


def _pause_if_needed(no_pause: bool, exit_code: int) -> None:
    if no_pause or os.environ.get("CI"):
        return
    if sys.platform != "win32":
        return
    try:
        if exit_code != 0:
            input("\nRun did not finish successfully. Press Enter to close…")
        elif not sys.stdin.isatty():
            input("\nPress Enter to close…")
    except EOFError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="PRISM full benchmark launcher")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check three-pillar data and stage completion only; no API or pipeline",
    )
    parser.add_argument(
        "--allow-partial-sdoh",
        action="store_true",
        help="Allow incomplete pillar 3 SDoH assets on a full case list (pillars 1–2 or partial 3)",
    )
    parser.add_argument("--test-api", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--restore-data", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--models", default="", help=argparse.SUPPRESS)
    parser.add_argument("--steps", nargs="*", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--strict", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-api-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-pause", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--manifest-path", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    os.chdir(LEGACY_ROOT)
    _apply_utf8_runtime()
    if args.allow_partial_sdoh:
        os.environ["PRISM_ALLOW_PARTIAL_SDOH"] = "1"
    _apply_full_bias_analysis_root_env()

    models = [m.strip() for m in args.models.split(",") if m.strip()] or _default_subject_models()
    _apply_full_benchmark_env(models)

    if args.restore_data:
        _restore_full_data()

    if args.test_api:
        return _test_api(models)

    _auto_restore_full_data_if_needed()

    code = _print_preflight(models)
    if args.check_only:
        expected = _expected_full_rows()
        if _query_row_count(ACTIVE_QUERY) >= expected:
            _emit_completion_overview(models, phase="check")
        health = _run_count_health_check(models, include_missing_outputs=True)
        if health != 0:
            return health
        return code
    if code != 0:
        return code

    pre_count = _run_count_health_check(models, include_missing_outputs=False)
    if pre_count != 0:
        print(
            "Aborted: count input JSON cannot build prompts (see list above). "
            "Fix inputs before running the pipeline.",
            file=sys.stderr,
        )
        return pre_count

    _emit_completion_overview(models, phase="start")

    _auto_clear_base_ask_failures(_resolve_model_ids(models))

    if not args.skip_api_check:
        code = _test_api(models, quiet_ok=True)
        if code != 0:
            return code

    return _run_full_pipeline(
        steps=args.steps,
        continue_on_error=not args.strict,
        manifest_path=Path(args.manifest_path) if args.manifest_path else None,
        models=models,
    )


if __name__ == "__main__":
    _no_pause = "--no-pause" in sys.argv
    _exit = main()
    _pause_if_needed(_no_pause, _exit)
    raise SystemExit(_exit)
