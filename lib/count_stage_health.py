# -*- coding: utf-8 -*-
"""Health checks for base_count / bias_count (input parse + output completeness)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple

CountMode = str  # "base" | "bias"


def _ensure_legacy_imports(legacy_root: Path) -> None:
    root = str(legacy_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    import prism_bootstrap

    prism_bootstrap.install_import_paths(legacy_root)


def count_output_path(count_dir: Path, key: str, mode: CountMode) -> Path:
    if mode == "base":
        return count_dir / key / f"{key}.json"
    return count_dir / key / f"{key}_count.json"


def _count_jobs(
    legacy_root: Path, model_id: str, round_id: str, mode: CountMode
) -> Tuple[List[Tuple[str, Any, Path, Path]], str]:
    """Return (jobs, note) where each job is (key, file_spec, formatted_json, input_json_path)."""
    _ensure_legacy_imports(legacy_root)
    from count_stage_runner import (
        build_roots_to_process,
        ensure_bias_analysis_root,
        match_count_output_files,
        output_json_dir_for,
    )

    bias_root = ensure_bias_analysis_root()
    out_json = output_json_dir_for(mode, model_id, round_id)
    out_path = Path(out_json)
    if not out_path.is_dir():
        return [], "no output_json directory"

    match = match_count_output_files(mode, bias_root, out_json)
    roots = build_roots_to_process(bias_root, match)
    jobs: List[Tuple[str, Any, Path, Path]] = []

    for root, key, spec in roots:
        formatted = Path(root) / "formatted.json"
        if mode == "base":
            fn = spec if isinstance(spec, str) else str(spec)
            jobs.append((key, spec, formatted, out_path / fn))
        else:
            for fn in spec if isinstance(spec, list) else [spec]:
                jobs.append((key, fn, formatted, out_path / fn))

    bias_subdirs = sum(1 for d in Path(bias_root).iterdir() if d.is_dir())
    expected_cases = len(roots)
    note = (
        f"bias_analysis subdirs {bias_subdirs}; this round matches {expected_cases} count case(s)"
        if expected_cases
        else f"bias_analysis subdirs {bias_subdirs}; no output_json match this round"
    )
    return jobs, note


def count_round_stats(
    legacy_root: Path, model_id: str, round_id: str, mode: CountMode
) -> Tuple[int, int, List[str], str]:
    """done, expected, missing_output_keys, note."""
    _ensure_legacy_imports(legacy_root)
    from count_stage_runner import ensure_bias_analysis_root, match_count_output_files, output_json_dir_for, build_roots_to_process

    bias_root = ensure_bias_analysis_root()
    out_json = output_json_dir_for(mode, model_id, round_id)
    out_path = Path(out_json)
    if not out_path.is_dir():
        return 0, 0, [], "no output_json directory"

    match = match_count_output_files(mode, bias_root, out_json)
    roots = build_roots_to_process(bias_root, match)
    expected = len(roots)
    count_dir = Path(out_json + "_bias_count")
    missing: List[str] = []
    done = 0
    for _root, key, _spec in roots:
        fp = count_output_path(count_dir, key, mode)
        if fp.is_file():
            done += 1
        else:
            missing.append(key)

    bias_subdirs = sum(1 for d in Path(bias_root).iterdir() if d.is_dir())
    note = (
        f"bias_analysis subdirs {bias_subdirs}; this round matches {expected} count case(s)"
        if expected
        else f"bias_analysis subdirs {bias_subdirs}; no output_json match this round"
    )
    return done, expected, missing, note


def scan_count_input_prompt_errors(
    legacy_root: Path,
    model_ids: Sequence[str],
    round_ids: Sequence[str],
    *,
    modes: Sequence[CountMode] = ("base", "bias"),
) -> List[dict[str, Any]]:
    """Try build_bias_count_prompt on every count input JSON; return parse/build failures."""
    _ensure_legacy_imports(legacy_root)
    from bias_count_common import build_bias_count_prompt, load_bias_directions
    from legacy_script_config import BIAS_COUNT_PROMPT_TEMPLATE_PATH

    template = Path(BIAS_COUNT_PROMPT_TEMPLATE_PATH).read_text(encoding="utf-8")
    issues: List[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()

    for mode in modes:
        for model_id in model_ids:
            for round_id in round_ids:
                jobs, _note = _count_jobs(legacy_root, model_id, round_id, mode)
                for key, _spec, formatted, input_path in jobs:
                    dedupe = (mode, model_id, round_id, key, str(input_path))
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    if not input_path.is_file():
                        issues.append(
                            {
                                "kind": "missing_input",
                                "mode": mode,
                                "model_id": model_id,
                                "round": round_id,
                                "case_key": key,
                                "input_file": str(input_path),
                                "error": "file not found",
                            }
                        )
                        continue
                    try:
                        output_data = json.loads(input_path.read_text(encoding="utf-8"))
                        low, high = load_bias_directions(str(formatted))
                        build_bias_count_prompt(template, low, high, output_data)
                    except Exception as exc:
                        issues.append(
                            {
                                "kind": "unbuildable_prompt",
                                "mode": mode,
                                "model_id": model_id,
                                "round": round_id,
                                "case_key": key,
                                "input_file": str(input_path),
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                        )
    return issues


def collect_missing_count_outputs(
    legacy_root: Path,
    model_ids: Sequence[str],
    round_ids: Sequence[str],
    *,
    modes: Sequence[CountMode] = ("base", "bias"),
) -> List[dict[str, Any]]:
    rows: List[dict[str, Any]] = []
    for mode in modes:
        stage = "base_count" if mode == "base" else "bias_count"
        for model_id in model_ids:
            for round_id in round_ids:
                done, expected, missing, note = count_round_stats(legacy_root, model_id, round_id, mode)
                if expected == 0:
                    continue
                if missing:
                    rows.append(
                        {
                            "stage": stage,
                            "mode": mode,
                            "model_id": model_id,
                            "round": round_id,
                            "done": done,
                            "expected": expected,
                            "missing_keys": missing,
                            "note": note,
                        }
                    )
    return rows


def format_count_health_message(
    *,
    prompt_issues: Sequence[dict[str, Any]] | None = None,
    missing_outputs: Sequence[dict[str, Any]] | None = None,
    max_lines: int = 25,
) -> str:
    lines: List[str] = []
    prompt_issues = prompt_issues or []
    missing_outputs = missing_outputs or []

    if prompt_issues:
        lines.append(f"count inputs cannot build prompts: {len(prompt_issues)} issue(s)")
        for item in prompt_issues[:max_lines]:
            lines.append(
                f"  [{item['mode']}] {item['model_id']}/{item['round']} "
                f"{item['case_key']}: {item['input_file']}"
            )
            lines.append(f"    -> {item['error']}")
        if len(prompt_issues) > max_lines:
            lines.append(f"  … {len(prompt_issues) - max_lines} more issue(s)")

    if missing_outputs:
        lines.append(f"count outputs incomplete: {len(missing_outputs)} group(s) (round×model×branch)")
        for item in missing_outputs[:max_lines]:
            keys = item["missing_keys"]
            preview = ", ".join(keys[:5])
            if len(keys) > 5:
                preview += f", … (+{len(keys) - 5})"
            lines.append(
                f"  [{item['stage']}] {item['model_id']}/{item['round']} "
                f"{item['done']}/{item['expected']} missing: {preview}"
            )
        if len(missing_outputs) > max_lines:
            lines.append(f"  … {len(missing_outputs) - max_lines} more group(s)")

    return "\n".join(lines)


def assert_count_stages_complete(
    legacy_root: Path,
    model_ids: Sequence[str],
    round_ids: Sequence[str],
    *,
    modes: Sequence[CountMode],
) -> None:
    missing = collect_missing_count_outputs(legacy_root, model_ids, round_ids, modes=modes)
    if not missing:
        return
    msg = format_count_health_message(missing_outputs=missing)
    raise RuntimeError("count stage artifacts incomplete:\n" + msg)


def print_count_health_summary(
    legacy_root: Path,
    model_ids: Sequence[str],
    round_ids: Sequence[str],
    *,
    scan_inputs: bool = True,
) -> Tuple[List[dict[str, Any]], List[dict[str, Any]]]:
    """Print summary; return (prompt_issues, missing_outputs)."""
    prompt_issues: List[dict[str, Any]] = []
    if scan_inputs:
        prompt_issues = scan_count_input_prompt_errors(legacy_root, model_ids, round_ids)
    missing = collect_missing_count_outputs(legacy_root, model_ids, round_ids)
    text = format_count_health_message(prompt_issues=prompt_issues, missing_outputs=missing)
    if text.strip():
        print("\n=== Count stage health (base_count / bias_count) ===")
        print(text)
    else:
        print("\n=== Count stage health: inputs parseable and outputs complete ===")
    return prompt_issues, missing


def count_health_exit_code(
    prompt_issues: Sequence[dict[str, Any]],
    missing_outputs: Sequence[dict[str, Any]],
) -> int:
    if prompt_issues or missing_outputs:
        return 7
    return 0
