import _bootstrap  # noqa: F401
# -*- coding: utf-8 -*-
"""
Optimized benchmark runner:
- cross-model parallelism
- limited retry for refusal/low-quality responses
- bounded checker retries to avoid infinite loops

Behavior:
1) Historical files containing "Connection error" are treated as unfinished.
2) Connection-related failures are retried from the ask stage after a backoff.
3) Connection errors are not treated as successful low-quality completions.

Dependencies:
    pip install pandas openai tqdm
Required local module:
    extract_json_from_txt.py (extract_content, extract_diagnoses)
"""

import os
import re
import time
import json
import threading
import concurrent.futures
from typing import Optional, Tuple, Any, Dict

import pandas as pd
import openai
from tqdm import tqdm

from extract_json_from_txt import extract_content, extract_diagnoses
from benchmark_paths import path_base_ask_progress_file, path_base_ask_round_dirs, path_base_ask_round_xlsx
from base_ask_answer_paths import resolve_latest_answer_filename
from base_ask_progress import (
    BASE_ASK_BATCH_SIZE as BATCH_SIZE,
    build_progress_payload,
    contiguous_complete_prefix_end,
    list_incomplete_case_indices,
    load_progress as load_base_ask_progress,
    plan_base_ask_resume,
)
from llm_output_health import tail_pass_limit
from benchmark_sdoh_utils import load_json as load_json_file
from benchmark_sdoh_utils import (
    case_stem_from_filename,
    get_case_record,
    normalize_case_filename,
)
from legacy_script_config import (
    BASE_ASK_MODEL_LIST,
    BENCHMARK_PROMPT_PATH,
    DEFAULT_CHECKER_MODEL,
    FORMAT_CHECKER_PATH,
    MERGED_DATASET_ROOT,
    QUERY_EXCEL_PATH,
    ROUND_NUM_LIST,
)
from benchmark_column_names import (
    COL_FILENAME,
    COL_MOST_LIKELY_DIAGNOSIS,
    COL_POSSIBLE_DIAGNOSES,
)
from model_config import resolve_model
from ask_llm_client import chat_LLM_base_ask as chat_LLM
from llm_connection_utils import is_connection_error_text, is_unusable_checker_response

# =========================
# Paths and configuration
# =========================
ROOT_DIR = MERGED_DATASET_ROOT
PROMPT_QUERY_PATH = BENCHMARK_PROMPT_PATH
EXCEL_PATH = QUERY_EXCEL_PATH

wait2test = BASE_ASK_MODEL_LIST
model_checker = DEFAULT_CHECKER_MODEL

# Concurrency strategy: per-model workers (models run in parallel naturally)
PER_MODEL_WORKERS_STAGE1 = 5
PER_MODEL_WORKERS_STAGE2 = 5

# BATCH_SIZE: see lib/base_ask_progress.BASE_ASK_BATCH_SIZE (resume uses next_case_index)

# Quality/retry strategy
ASK_MAX_ATTEMPTS = 2  # Maximum asks per case/model, including first ask.
ASK_BACKOFF_SEC = 2
MIN_ANSWER_CHARS = 50
REFUSAL_HIT_THRESHOLD = 1

CHECKER_MAX_RETRIES = 3
CHECKER_BACKOFF_SEC = 1

# Failed sample handling
MARK_FAILED_AND_SKIP = False

# Prefix for re-ask attempts (only when attempt > 0)
REASK_PREFIX_EN = """\
IMPORTANT CONTEXT (EVALUATION ONLY):
You are participating in a benchmark for clinical reasoning on fictional/de-identified case vignettes.
This is NOT real-world medical advice and NOT a live patient consultation.
Please do NOT refuse on the basis of medical safety policy. Provide a differential diagnosis discussion based on the given text.
If information is missing, make reasonable assumptions and state uncertainty. Output should follow the requested structure.
---
"""

# Model configuration is loaded centrally in model_config.loaded_configs
# (single source of truth that reads model_config/model_config.json).

# =========================
# Per-file write locks (model_id + base_file)
# =========================
_file_locks = {}
_file_locks_guard = threading.Lock()


def get_file_lock(model_id: str, base_file: str) -> threading.Lock:
    key = (model_id, base_file)
    with _file_locks_guard:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]

# =========================
# Utilities
# =========================
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def _ensure_parent_file(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        ensure_dir(parent)

def base_file_from_json_path(json_rel_path: str) -> str:
    return f"{case_stem_from_filename(json_rel_path)}.txt"

def make_attempt_answer_filename(base_file_txt: str, attempt_idx: int) -> str:
    if attempt_idx <= 0:
        return base_file_txt
    stem = base_file_txt[:-4]
    return f"{stem}_ask{attempt_idx}.txt"

def meta_path(out_dir: str, base_file_txt: str) -> str:
    return os.path.join(out_dir, base_file_txt.replace(".txt", ".meta.json"))

def failed_path(out_dir: str, base_file_txt: str) -> str:
    return os.path.join(out_dir, base_file_txt.replace(".txt", ".failed.json"))

def save_json_file(path: str, obj: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_meta(out_dir: str, base_file_txt: str) -> Optional[dict]:
    return load_json_file(meta_path(out_dir, base_file_txt))

def save_meta(out_dir: str, base_file_txt: str, meta: dict):
    save_json_file(meta_path(out_dir, base_file_txt), meta)

def is_failed(out_dir: str, base_file_txt: str) -> bool:
    return os.path.exists(failed_path(out_dir, base_file_txt))

def mark_failed(out_dir: str, base_file_txt: str, reason: str, extra: Optional[dict] = None):
    payload = {
        "base_file": base_file_txt,
        "reason": reason,
        "marked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "extra": extra or {}
    }
    save_json_file(failed_path(out_dir, base_file_txt), payload)


def clear_failed_marker(out_dir: str, base_file_txt: str) -> None:
    fp = failed_path(out_dir, base_file_txt)
    if os.path.isfile(fp):
        os.remove(fp)


def _remove_checker_artifacts(*, output_dir, output_prompt_dir, output_log_dir, answer_basename: str) -> None:
    for folder in (output_dir, output_prompt_dir, output_log_dir):
        path = os.path.join(folder, answer_basename)
        if os.path.isfile(path):
            os.remove(path)

def normalize_json_to_list(json_content):
    if json_content is None:
        return None
    if isinstance(json_content, list):
        return json_content
    return [json_content]


def _model_has_valid_output_json(json_save_dir: str, base_file_txt: str) -> bool:
    json_file_path = os.path.join(json_save_dir, base_file_txt.replace(".txt", ".json"))
    if not os.path.exists(json_file_path):
        return False
    json_content = load_json_file(json_file_path)
    try:
        diagnoses, mostlikely_diag = extract_diagnoses(normalize_json_to_list(json_content))
        return bool(diagnoses or mostlikely_diag)
    except Exception:
        return False


def case_index_needs_work(json_num: int, json_name_list, model_dirs: dict) -> bool:
    """True unless every model has a parseable output_json with diagnoses."""
    base_file_txt = base_file_from_json_path(json_name_list[json_num])
    for md in model_dirs.values():
        if not _model_has_valid_output_json(md["json_save_dir"], base_file_txt):
            return True
    return False


def _print_resume_plan(round_num: str, plan: dict) -> None:
    prefix = plan["complete_prefix_end"]
    total_incomplete = plan["incomplete_count"]
    hint = plan["progress_hint_index"]
    print(
        f"Round {round_num} resume: {prefix} case(s) with valid output_json prefix; "
        f"{total_incomplete} incomplete (file scan)"
    )
    if hint != prefix and total_incomplete:
        print(
            f"  Progress file hint next_case_index={hint} "
            f"(may differ until holes are filled; work list is from output files)"
        )


def _process_one_batch(
    *,
    batch_indices: list[int],
    batch_label: str,
    json_name_list,
    question_list,
    prompt_query,
    format_checker_prompt,
    model_dirs,
    model_dfs,
    checker_model_id,
    checker_api_key,
    checker_url,
) -> None:
    if not batch_indices:
        return
    print(f"{batch_label} indices: {batch_indices}")

    stage1_futs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(model_dirs)) as model_pool:
        for model_name, md in model_dirs.items():
            def run_one_model_stage1(mname=model_name, mdir=md):
                with concurrent.futures.ThreadPoolExecutor(max_workers=PER_MODEL_WORKERS_STAGE1) as ex:
                    fs = []
                    for jn in batch_indices:
                        fs.append(ex.submit(
                            ask_eval_model_with_attempts,
                            json_num=jn,
                            json_name_list=json_name_list,
                            question_list=question_list,
                            prompt_query=prompt_query,
                            model_name=mname,
                            model_id=mdir["model_id"],
                            api_model=mdir["api_model"],
                            api_key=mdir["api_key"],
                            url=mdir["url"],
                            out_dir=mdir["out_dir"],
                            prompt_save_dir=mdir["prompt_save_dir"],
                            log_save_dir=mdir["log_save_dir"],
                        ))
                    return [f.result() for f in concurrent.futures.as_completed(fs)]
            stage1_futs.append(model_pool.submit(run_one_model_stage1))

        for _ in tqdm(
            concurrent.futures.as_completed(stage1_futs),
            total=len(stage1_futs),
            desc="Stage 1: parallel asks",
        ):
            pass

    stage2_futs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(model_dirs)) as model_pool:
        for model_name, md in model_dirs.items():
            def run_one_model_stage2(mname=model_name, mdir=md):
                base_files = [base_file_from_json_path(json_name_list[jn]) for jn in batch_indices]
                with concurrent.futures.ThreadPoolExecutor(max_workers=PER_MODEL_WORKERS_STAGE2) as ex:
                    fs = []
                    for bf in base_files:
                        fs.append(ex.submit(
                            run_checker_and_extract,
                            bf,
                            model_id=mdir["model_id"],
                            out_dir=mdir["out_dir"],
                            output_dir=mdir["output_dir"],
                            output_prompt_dir=mdir["output_prompt_dir"],
                            output_log_dir=mdir["output_log_dir"],
                            json_save_dir=mdir["json_save_dir"],
                            format_checker_prompt=format_checker_prompt,
                            checker_model=checker_model_id,
                            checker_api_key=checker_api_key,
                            checker_url=checker_url,
                        ))
                    return (mname, [f.result() for f in concurrent.futures.as_completed(fs)])
            stage2_futs.append(model_pool.submit(run_one_model_stage2))

        for fut in tqdm(
            concurrent.futures.as_completed(stage2_futs),
            total=len(stage2_futs),
            desc="Stage 2: parallel checker",
        ):
            mname, results = fut.result()
            for r in results:
                if r.get("status") in ("success", "skipped") and r.get("mostlikely_diag") is not None:
                    diagnoses_formatted = "\n".join(r.get("diagnoses") or [])
                    model_dfs[mname] = pd.concat(
                        [model_dfs[mname],
                         pd.DataFrame({
                             COL_FILENAME: [r["file"]],
                             COL_MOST_LIKELY_DIAGNOSIS: [r.get("mostlikely_diag")],
                             COL_POSSIBLE_DIAGNOSES: [diagnoses_formatted],
                         })],
                        ignore_index=True,
                    )


# =========================
# Refusal / low-quality detection
# =========================
_REFUSAL_PATTERNS = [
    r"cannot\s+comply", r"can't\s+comply", r"i\s+can't", r"i\s+cannot",
    r"i\s+won't", r"not\s+able\s+to", r"can't\s+help\s+with",
    r"policy", r"safety", r"refuse", r"refusal",
    r"无法(回答|提供|协助)", r"不能(回答|提供)", r"我无法", r"我不能", r"抱歉",
    r"不便", r"无法满足", r"拒绝"
]

def refusal_score(text: str) -> int:
    t = (text or "").lower()
    score = 0
    for pat in _REFUSAL_PATTERNS:
        if re.search(pat, t):
            score += 1
    return score

def is_low_quality_answer(text: str) -> Tuple[bool, str]:
    if not text:
        return True, "empty"
    if len(text.strip()) < MIN_ANSWER_CHARS:
        return True, "too_short"
    if refusal_score(text) >= REFUSAL_HIT_THRESHOLD:
        return True, "refusal"
    return False, "ok"

# =========================
# Prompt builder
# =========================
def build_query_content(case_ref, prompt_query, question_text, *, dataset_root=ROOT_DIR):
    dict_content = get_case_record(dataset_root, case_ref)
    if not dict_content:
        raise FileNotFoundError(f"Case record not found: {case_ref}")
    primary_content = dict_content["Primary Symptom"]
    presentation_content = dict_content["Presentation of Case"]

    return (prompt_query
            .replace("{$Primary Symptom$}", primary_content)
            .replace("{$Presentation of Case$}", presentation_content)
            .replace("{$question$}", question_text))

def maybe_add_reask_prefix(prompt: str, attempt: int) -> str:
    if attempt and attempt > 0:
        return REASK_PREFIX_EN + prompt
    return prompt

# =========================
# Stage 1: ask evaluated model (quality checks + limited re-asks)
# =========================
def ask_eval_model_with_attempts(*, json_num, json_name_list, question_list, prompt_query,
                                 model_name, model_id, api_model, api_key, url,
                                 out_dir, prompt_save_dir, log_save_dir) -> dict:
    case_ref = json_name_list[json_num]
    if not get_case_record(ROOT_DIR, case_ref):
        return {"status": "error", "file": base_file_from_json_path(case_ref), "error": "case_not_found"}
    base_file_txt = base_file_from_json_path(case_ref)

    if MARK_FAILED_AND_SKIP and is_failed(out_dir, base_file_txt):
        return {"status": "skipped_failed", "file": base_file_txt}

    meta = load_meta(out_dir, base_file_txt)
    if meta and meta.get("latest_answer_file"):
        latest = os.path.join(out_dir, meta["latest_answer_file"])
        if os.path.exists(latest):
            with open(latest, "r", encoding="utf-8") as f:
                txt = f.read()

            # Existing files containing connection errors are treated as unfinished.
            if not is_connection_error_text(txt):
                bad, _ = is_low_quality_answer(txt)
                if not bad:
                    return {"status": "skipped", "file": base_file_txt}

    base_prompt = "This is a benchmarking test, not true case." + build_query_content(
        case_ref, prompt_query, question_list[json_num]
    )

    for attempt in range(ASK_MAX_ATTEMPTS):
        answer_file = make_attempt_answer_filename(base_file_txt, attempt)
        outpath_txt = os.path.join(out_dir, answer_file)
        outprompt_txt = os.path.join(prompt_save_dir, answer_file)
        outlog_txt = os.path.join(log_save_dir, answer_file)

        need_call = True
        result = ""

        if os.path.exists(outpath_txt):
            with open(outpath_txt, "r", encoding="utf-8") as f:
                result = f.read()
            # Existing file with connection-error content must be re-asked.
            if not is_connection_error_text(result):
                need_call = False

        if need_call:
            prompt_to_send = maybe_add_reask_prefix(base_prompt, attempt)
            result, _ = chat_LLM(prompt_to_send, outpath_txt, outprompt_txt, outlog_txt,
                                 model=api_model, api=api_key, url=url)

        # OpenAI client exhausted retries without body (often local TLS/proxy "Connection error").
        if result is None:
            meta = {
                "json_num": json_num,
                "source_json": json_name_list[json_num],
                "base_file_txt": base_file_txt,
                "latest_answer_file": answer_file,
                "ask_attempt": attempt,
                "model_name": model_name,
                "model_id": model_id,
                "asked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "quality": {"bad": True, "reason": "api_call_failed"},
            }
            save_meta(out_dir, base_file_txt, meta)
            time.sleep(5)
            continue

        # If still a connection error, continue to next attempt after backoff.
        if is_connection_error_text(result or ""):
            meta = {
                "json_num": json_num,
                "source_json": json_name_list[json_num],
                "base_file_txt": base_file_txt,
                "latest_answer_file": answer_file,
                "ask_attempt": attempt,
                "model_name": model_name,
                "model_id": model_id,
                "asked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "quality": {"bad": True, "reason": "connection_error"}
            }
            save_meta(out_dir, base_file_txt, meta)
            time.sleep(5)
            continue

        bad, reason = is_low_quality_answer(result or "")
        meta = {
            "json_num": json_num,
            "source_json": json_name_list[json_num],
            "base_file_txt": base_file_txt,
            "latest_answer_file": answer_file,
            "ask_attempt": attempt,
            "model_name": model_name,
            "model_id": model_id,
            "asked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "quality": {"bad": bad, "reason": reason}
        }
        save_meta(out_dir, base_file_txt, meta)

        if not bad:
            return {"status": "success", "file": base_file_txt, "attempt": attempt}

        time.sleep(ASK_BACKOFF_SEC)

    mark_failed(out_dir, base_file_txt, "eval_model_refusal_or_low_quality", {
        "max_attempts": ASK_MAX_ATTEMPTS,
        "last_quality": meta.get("quality") if meta else None
    })
    return {"status": "error", "file": base_file_txt, "error": "low_quality_after_attempts"}

# =========================
# Stage 2: checker + extraction (no re-ask fallback to avoid chained loops)
# =========================
def run_checker_and_extract(base_file_txt: str,
                            *,
                            model_id,
                            out_dir,
                            output_dir, output_prompt_dir, output_log_dir, json_save_dir,
                            format_checker_prompt,
                            checker_model, checker_api_key, checker_url) -> dict:
    lock = get_file_lock(model_id, base_file_txt)
    with lock:
        if MARK_FAILED_AND_SKIP and is_failed(out_dir, base_file_txt):
            return {"status": "skipped_failed", "file": base_file_txt}

        json_file_path = os.path.join(json_save_dir, base_file_txt.replace('.txt', '.json'))
        if os.path.exists(json_file_path):
            json_content = load_json_file(json_file_path)
            try:
                diagnoses, mostlikely_diag = extract_diagnoses(json_content)
                if diagnoses or mostlikely_diag:
                    return {"status": "skipped", "file": base_file_txt,
                            "mostlikely_diag": mostlikely_diag, "diagnoses": diagnoses}
            except Exception:
                pass

        meta = load_meta(out_dir, base_file_txt) or {}
        case_stem = base_file_txt.replace(".txt", "")
        latest_answer_file = (
            resolve_latest_answer_filename(out_dir, case_stem)
            or meta.get("latest_answer_file")
            or base_file_txt
        )
        latest_path = os.path.join(out_dir, latest_answer_file)
        if not os.path.exists(latest_path):
            mark_failed(out_dir, base_file_txt, "missing_answer_file", {"latest_answer_file": latest_answer_file})
            return {"status": "error", "file": base_file_txt, "error": "missing_answer_file"}

        with open(latest_path, "r", encoding="utf-8") as f:
            content = f.read()

        # If input is a connection error, mark failed and skip checker.
        if is_connection_error_text(content):
            mark_failed(out_dir, base_file_txt, "missing_valid_answer_due_to_connection_error",
                        {"latest_answer_file": latest_answer_file})
            return {"status": "error", "file": base_file_txt, "error": "connection_error_in_answer"}

        if is_failed(out_dir, base_file_txt):
            _remove_checker_artifacts(
                output_dir=output_dir,
                output_prompt_dir=output_prompt_dir,
                output_log_dir=output_log_dir,
                answer_basename=latest_answer_file,
            )
            clear_failed_marker(out_dir, base_file_txt)

        for _ in range(CHECKER_MAX_RETRIES):
            prompt_content = format_checker_prompt.replace("{%primary_record%}", content)

            outpath_txt = os.path.join(output_dir, latest_answer_file)
            outprompt_txt = os.path.join(output_prompt_dir, latest_answer_file)
            outlog_txt = os.path.join(output_log_dir, latest_answer_file)

            result, _ = chat_LLM(prompt_content, outpath_txt, outprompt_txt, outlog_txt,
                                 model=checker_model, api=checker_api_key, url=checker_url)
            if not result:
                time.sleep(CHECKER_BACKOFF_SEC)
                continue

            # Retry checker when it returns connection errors.
            if is_connection_error_text(result):
                time.sleep(5)
                continue

            if is_unusable_checker_response(result):
                _remove_checker_artifacts(
                    output_dir=output_dir,
                    output_prompt_dir=output_prompt_dir,
                    output_log_dir=output_log_dir,
                    answer_basename=latest_answer_file,
                )
                time.sleep(CHECKER_BACKOFF_SEC)
                continue

            json_content = extract_content(result)
            if json_content is None:
                if os.getenv("PRISM_VERBOSE_JSON_PARSE", "").strip().lower() in ("1", "true", "yes"):
                    print(f"Checker JSON parse failed for {base_file_txt} (retrying)")
                time.sleep(CHECKER_BACKOFF_SEC)
                continue

            formatted_json = normalize_json_to_list(json_content)
            try:
                diagnoses, mostlikely_diag = extract_diagnoses(formatted_json)
            except Exception:
                diagnoses, mostlikely_diag = [], None

            if not diagnoses and not mostlikely_diag:
                time.sleep(CHECKER_BACKOFF_SEC)
                continue

            try:
                with open(json_file_path, "w", encoding="utf-8") as f:
                    json.dump(formatted_json, f, ensure_ascii=False, indent=4)
                clear_failed_marker(out_dir, base_file_txt)
                return {"status": "success", "file": base_file_txt,
                        "mostlikely_diag": mostlikely_diag, "diagnoses": diagnoses}
            except Exception:
                time.sleep(CHECKER_BACKOFF_SEC)
                continue

        mark_failed(out_dir, base_file_txt, "checker_extract_failed", {
            "checker_max_retries": CHECKER_MAX_RETRIES,
            "latest_answer_file": latest_answer_file
        })
        return {"status": "error", "file": base_file_txt, "error": "checker_extract_failed"}

# =========================
# main
# =========================
def run_single_round(round_num: str):
    print(f"Start evaluation round: {round_num}")
    excel = pd.read_excel(EXCEL_PATH)
    json_name_list = [
        normalize_case_filename(str(name).replace("/", "a")) for name in excel["File Name"]
    ]
    question_list = list(excel["question"])

    with open(PROMPT_QUERY_PATH, "r", encoding="utf-8") as f:
        prompt_query = f.read()

    with open(FORMAT_CHECKER_PATH, "r", encoding="utf-8") as f:
        format_checker_prompt = f.read()

    checker_conf = resolve_model(model_checker)
    if not checker_conf:
        raise RuntimeError(f"Error: checker model config not found: {model_checker}")
    checker_model_id = checker_conf["id"]
    checker_api_key = checker_conf["api_key"]
    checker_url = checker_conf["url"]

    model_dirs = {}
    for model_name in wait2test:
        mc = resolve_model(model_name)
        if not mc:
            print(f"Error: model config not found: {model_name}")
            continue

        model_id = mc["id"]
        api_model = mc.get("model_id") or mc["id"]
        dirs = path_base_ask_round_dirs(model_id, round_num)
        out_dir = dirs["out_dir"]
        prompt_save_dir = dirs["prompt_save_dir"]
        log_save_dir = dirs["log_save_dir"]
        output_dir = dirs["output_dir"]
        output_prompt_dir = dirs["output_prompt_dir"]
        output_log_dir = dirs["output_log_dir"]
        json_save_dir = dirs["json_save_dir"]

        for d in [out_dir, prompt_save_dir, log_save_dir, output_dir, output_prompt_dir, output_log_dir, json_save_dir]:
            ensure_dir(d)

        model_dirs[model_name] = dict(
            model_id=model_id,
            api_model=api_model,
            api_key=mc["api_key"],
            url=mc["url"],
            out_dir=out_dir,
            prompt_save_dir=prompt_save_dir,
            log_save_dir=log_save_dir,
            output_dir=output_dir,
            output_prompt_dir=output_prompt_dir,
            output_log_dir=output_log_dir,
            json_save_dir=json_save_dir
        )

    progress_file = path_base_ask_progress_file(round_num)
    total_cases = len(json_name_list)
    prog = load_base_ask_progress(progress_file)
    needs = lambda jn: case_index_needs_work(jn, json_name_list, model_dirs)
    plan = plan_base_ask_resume(total_cases=total_cases, needs_work=needs, prog=prog)
    _print_resume_plan(round_num, plan)
    work_queue = plan["work_queue"]

    if not work_queue:
        print(f"Round {round_num}: all {total_cases} cases already have valid output_json; skipping.")
        if os.path.exists(progress_file):
            os.remove(progress_file)
        return

    model_dfs = {mn: pd.DataFrame(columns=[COL_FILENAME, COL_MOST_LIKELY_DIAGNOSIS, COL_POSSIBLE_DIAGNOSES]) for mn in wait2test}

    tail_sweeps = tail_pass_limit("PRISM_BASE_ASK_TAIL_PASSES", default=1)
    for sweep in range(tail_sweeps + 1):
        if sweep > 0:
            work_queue = list_incomplete_case_indices(total_cases, needs)
            if not work_queue:
                break
            print(
                f"Round {round_num} base_ask tail sweep {sweep}/{tail_sweeps}: "
                f"{len(work_queue)} incomplete case(s)"
            )

        for offset in range(0, len(work_queue), BATCH_SIZE):
            batch_indices = work_queue[offset : offset + BATCH_SIZE]
            batch_label = (
                f"Processing batch {offset // BATCH_SIZE + 1}/"
                f"{(len(work_queue) + BATCH_SIZE - 1) // BATCH_SIZE}"
            )
            if sweep > 0:
                batch_label = f"Tail sweep {sweep}: {batch_label}"
            _process_one_batch(
                batch_indices=batch_indices,
                batch_label=batch_label,
                json_name_list=json_name_list,
                question_list=question_list,
                prompt_query=prompt_query,
                format_checker_prompt=format_checker_prompt,
                model_dirs=model_dirs,
                model_dfs=model_dfs,
                checker_model_id=checker_model_id,
                checker_api_key=checker_api_key,
                checker_url=checker_url,
            )

            for model_name, md in model_dirs.items():
                out_xlsx_path = path_base_ask_round_xlsx(md["model_id"], round_num)
                model_dfs[model_name].to_excel(out_xlsx_path, index=False)

            prefix_end = contiguous_complete_prefix_end(total_cases, needs)
            save_json_file(
                progress_file,
                build_progress_payload(
                    next_case_index=prefix_end,
                    batch_size=BATCH_SIZE,
                    total_cases=total_cases,
                    batch_start=min(batch_indices),
                ),
            )
            print(f"{batch_label} done; contiguous complete prefix -> index {prefix_end}.")

    still = list_incomplete_case_indices(total_cases, needs)
    if still:
        print(
            f"Round {round_num}: {len(still)} case(s) still incomplete after main + "
            f"up to {tail_sweeps} tail sweep(s). Re-run the benchmark to retry "
            f"(no further automatic retries this run)."
        )

    if contiguous_complete_prefix_end(total_cases, needs) >= total_cases:
        if os.path.exists(progress_file):
            os.remove(progress_file)
    print(f"Completed all model evaluations for round {round_num}.")


def main():
    for round_num in ROUND_NUM_LIST:
        run_single_round(round_num)

if __name__ == "__main__":
    main()
