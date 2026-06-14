import _bootstrap  # noqa: F401
import json
import os
import time
import pandas as pd
import openai
from extract_json_from_txt import extract_content, extract_diagnoses
import concurrent.futures
from tqdm import tqdm
from legacy_script_config import (
    BENCHMARK_PROMPT_PATH,
    BIAS_ASK_BATCH_SIZE,
    BIAS_ASK_MAX_WORKERS,
    BIAS_ASK_MODEL_LIST,
    DEFAULT_API_BASE_URL,
    DEFAULT_CHECKER_MODEL,
    FORMAT_CHECKER_PATH,
    MERGED_DATASET_WITH_ROLE_ROOT,
    QUERY_EXCEL_PATH,
    ROUND_NUM_LIST,
)
from benchmark_column_names import (
    COL_FILENAME,
    COL_MOST_LIKELY_DIAGNOSIS,
    COL_POSSIBLE_DIAGNOSES,
)
from benchmark_sdoh_utils import (
    case_stem_from_filename,
    get_case_record,
    normalize_case_filename,
)
from model_config import resolve_model
from ask_llm_client import chat_LLM_bias_ask as chat_LLM
from benchmark_paths import path_bias_ask_round_base
from llm_output_health import (
    remove_file_quiet,
    should_regenerate_answer_txt,
    tail_pass_limit,
    text_indicates_llm_failure,
)

# Centralized paths and runtime settings (overridable via PRISM_* env vars).
ROOT_DIR = MERGED_DATASET_WITH_ROLE_ROOT
PROMPT_QUERY_PATH = BENCHMARK_PROMPT_PATH
EXCEL_PATH = QUERY_EXCEL_PATH
url = DEFAULT_API_BASE_URL
wait2test = BIAS_ASK_MODEL_LIST

model_checker = DEFAULT_CHECKER_MODEL
round_num_list = ROUND_NUM_LIST

BIAS_ASK_API_MAX_RETRIES = 3


def _bias_scenario_json_valid(json_path: str) -> bool:
    if not os.path.exists(json_path):
        return False
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            json_content = json.load(f)
        diagnoses, mostlikely_diag = extract_diagnoses(json_content)
        return bool(mostlikely_diag or diagnoses)
    except Exception:
        return False


def _scenario_keys_for_record(dict_content: dict) -> list[str]:
    return [
        key
        for key in dict_content
        if key.startswith("scenario1") or key.startswith("scenario2")
    ]


def bias_case_index_needs_work(json_num: int, json_name_list, model_dirs: dict) -> bool:
    rel = json_name_list[json_num]
    dict_content = get_case_record(ROOT_DIR, rel)
    if not dict_content or not isinstance(dict_content, dict):
        return False
    scenario_keys = _scenario_keys_for_record(dict_content)
    if not scenario_keys:
        return False
    stem = case_stem_from_filename(rel)
    for md in model_dirs.values():
        for scenario_key in scenario_keys:
            jpath = os.path.join(md["json_save_dir"], f"{stem}_{scenario_key}.json")
            if not _bias_scenario_json_valid(jpath):
                return True
    return False


def list_bias_incomplete_indices(json_name_list, model_dirs: dict) -> list[int]:
    return [i for i in range(len(json_name_list)) if bias_case_index_needs_work(i, json_name_list, model_dirs)]


def process_file(
    json_num,
    json_name_list,
    question_list,
    prompt_query,
    model_name,
    model,
    api_key,
    url,
    out_dir,
    prompt_save_dir,
    log_save_dir,
    json_save_dir,
):
    print(f"Processing file for model {model_name}, json_num: {json_num}, json_file: {json_name_list[json_num]}")
    rel = json_name_list[json_num]
    base_filename = case_stem_from_filename(rel)
    results = []

    dict_content = get_case_record(ROOT_DIR, rel)
    if not dict_content or not isinstance(dict_content, dict):
        print(f"Case record not found: {rel}")
        return [{"status": "error", "file": rel, "error": "Case record not found"}]

    primary_content = dict_content.get("Primary Symptom", "")
    scenario_keys = [key for key in dict_content if key.startswith("scenario")]
    filtered_scenario_keys = [
        key for key in scenario_keys if key.startswith("scenario1") or key.startswith("scenario2")
    ]

    print(f"Found {len(filtered_scenario_keys)} scenarios for processing: {filtered_scenario_keys}")
    if not filtered_scenario_keys:
        print(f"No valid scenarios found in {path_query}.")

    for scenario_key in filtered_scenario_keys:
        presentation_content = dict_content[scenario_key]
        query_content = (
            prompt_query.replace("{$Primary Symptom$}", primary_content)
            .replace("{$Presentation of Case$}", presentation_content)
            .replace("{$question$}", question_list[json_num])
        )
        outpath_txt = os.path.join(out_dir, f"{base_filename}_{scenario_key}.txt")
        outprompt_txt = os.path.join(prompt_save_dir, f"{base_filename}_{scenario_key}.txt")
        outlog_txt = os.path.join(log_save_dir, f"{base_filename}_{scenario_key}.txt")
        json_file_path = os.path.join(json_save_dir, f"{base_filename}_{scenario_key}.json")

        if _bias_scenario_json_valid(json_file_path):
            print(f"Skipping complete JSON: {json_file_path} for model {model_name}")
            results.append({"status": "skipped", "file": f"{rel}_{scenario_key}"})
            continue

        if os.path.exists(outpath_txt):
            if should_regenerate_answer_txt(
                outpath_txt,
                json_path=json_file_path,
                json_is_valid=_bias_scenario_json_valid,
            ):
                print(f"Removing unusable answer txt for retry: {outpath_txt}")
                remove_file_quiet(outpath_txt)
            else:
                print(f"Skipping usable answer txt (checker pass pending): {outpath_txt}")
                results.append({"status": "skipped", "file": f"{rel}_{scenario_key}"})
                continue

        print(f"Generating new output for {outpath_txt}")
        max_retries = BIAS_ASK_API_MAX_RETRIES
        retry_count = 0
        while retry_count < max_retries:
            try:
                result, response = chat_LLM(
                    query_content, outpath_txt, outprompt_txt, outlog_txt, model, api_key, url=url
                )
                if result:
                    if text_indicates_llm_failure(result):
                        retry_count += 1
                        remove_file_quiet(outpath_txt)
                        time.sleep(2)
                        continue
                    results.append({"status": "success", "file": f"{rel}_{scenario_key}"})
                    break
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(2)
                else:
                    results.append({"status": "error", "file": f"{rel}_{scenario_key}", "error": "API call failed"})
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(2)
                else:
                    results.append({"status": "error", "file": f"{rel}_{scenario_key}", "error": str(e)})
        if retry_count >= max_retries and not any(r.get("file") == f"{rel}_{scenario_key}" for r in results):
            results.append(
                {
                    "status": "error",
                    "file": f"{rel}_{scenario_key}",
                    "error": f"Max retries ({max_retries}) exceeded; processing still failed",
                }
            )

    return results


def process_output_file(file, out_dir, output_dir, output_prompt_dir, output_log_dir, json_save_dir,
                        format_checker_prompt, checker_model, checker_api_key, checker_url):
    # Skip if JSON output already exists
    # Clean the filename by removing '_Low SES' or '_High SES'
    cleaned_file = file.replace('_Low SES', '').replace('_High SES', '')
    json_file_path = os.path.join(json_save_dir, cleaned_file.replace('.txt', '.json'))
    if os.path.exists(json_file_path):
        try:
            with open(json_file_path, "r", encoding="utf-8") as f:
                json_content = json.load(f)
                diagnoses, mostlikely_diag = extract_diagnoses(json_content)

                # Validate extracted diagnoses
                if mostlikely_diag or diagnoses:
                    print(f"Skipping already processed JSON file: {json_file_path} (valid diagnoses found)")
                    return {
                        "status": "skipped",
                        "file": file,
                        "mostlikely_diag": mostlikely_diag,
                        "diagnoses": diagnoses
                    }
                else:
                    print(
                        f"Existing JSON file {json_file_path} exists but has invalid or empty diagnoses, will reprocess.")
        except Exception as e:
            print(f"Error reading existing JSON file {json_file_path}: {str(e)}, will reprocess.")
            # On JSON read error, continue and reprocess
            pass

    with open(os.path.join(out_dir, file), "r", encoding="utf-8") as f:
        content = f.read()
    prompt_content = format_checker_prompt.replace("{%primary_record%}", content)

    outpath_txt = os.path.join(output_dir, file)
    outprompt_txt = os.path.join(output_prompt_dir, file)
    outlog_txt = os.path.join(output_log_dir, file)

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        result, response = chat_LLM(prompt_content, outpath_txt, outprompt_txt, outlog_txt, model=checker_model,
                                    api=checker_api_key, url=checker_url)

        if result:
            # Retry if the checker reply contains failure keywords
            failure_keywords = ["失败", "错误", "通讯失败", "请求失败"]
            if result is not None and any(keyword in result.lower() for keyword in failure_keywords):
                print(f"Checker reply contains failure keywords, retrying ({retry_count + 1}/{max_retries})")
                retry_count += 1
                time.sleep(2)
                continue

            # Extract diagnosis JSON immediately
            json_content = extract_content(result)

            if json_content is not None:
                try:
                    diagnoses, mostlikely_diag = extract_diagnoses(json_content)

                    # Normalize JSON to list form
                    if not isinstance(json_content, list):
                        formatted_json = []
                        if "Potential differential diagnoses" in json_content or "Potential Differential Diagnoses" in json_content:
                            formatted_json.append(json_content)
                        if "Most Likely Main Diagnosis" in json_content or "Most Likely Main Diagnoses" in json_content:
                            if not formatted_json:
                                formatted_json.append(json_content)
                        if not formatted_json:
                            formatted_json = [json_content]
                    else:
                        formatted_json = json_content

                    json.dumps(formatted_json)

                    with open(json_file_path, "w", encoding="utf-8") as f:
                        json.dump(formatted_json, f, ensure_ascii=False, indent=4)
                    print(f"Saved JSON file: {json_file_path}")

                    return {
                        "status": "success",
                        "file": file,
                        "mostlikely_diag": mostlikely_diag,
                        "diagnoses": diagnoses
                    }

                except Exception as e:
                    print(f"Error processing JSON content: {str(e)}, retrying ({retry_count + 1}/{max_retries})")
                    retry_count += 1
                    if retry_count < max_retries:
                        time.sleep(2)
                    else:
                        return {"status": "error", "file": file, "error": f"Error processing JSON content: {str(e)}"}
            else:
                print(f"Could not extract JSON content, retrying ({retry_count + 1}/{max_retries})")
                retry_count += 1
                if retry_count < max_retries:
                    time.sleep(2)
                else:
                    return {"status": "error", "file": file, "error": "Could not extract JSON content"}
        else:
            print(f"API call failed, retrying ({retry_count + 1}/{max_retries})")
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(2)
            else:
                return {"status": "error", "file": file, "error": "API call failed"}

    return {"status": "error", "file": file, "error": f"Max retries ({max_retries}) exceeded; processing still failed"}


def run_bias_ask_batch(
    *,
    batch_indices: list[int],
    batch_label: str,
    json_name_list,
    question_list,
    prompt_query: str,
    format_checker_prompt: str,
    model_dirs: dict,
    model_results: dict,
    model_dfs: dict,
    max_workers: int,
    checker_model: str,
    checker_api_key: str,
    checker_url: str,
) -> None:
    print(batch_label)
    print("Phase 1: parallel model answers for this batch")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        all_futures = {}

        for model_name in wait2test:
            model_config = resolve_model(model_name)
            if not model_config or not model_config["api_key"] or not model_config["url"]:
                continue

            api_key = model_config["api_key"]
            url = model_config["url"]
            model = model_config["id"]

            for json_num in batch_indices:
                future = executor.submit(
                    process_file,
                    json_num,
                    json_name_list,
                    question_list,
                    prompt_query,
                    model_name,
                    model,
                    api_key,
                    url,
                    model_dirs[model_name]["out_dir"],
                    model_dirs[model_name]["prompt_save_dir"],
                    model_dirs[model_name]["log_save_dir"],
                    model_dirs[model_name]["json_save_dir"],
                )
                all_futures[future] = model_name

        for future in tqdm(
            concurrent.futures.as_completed(all_futures),
            total=len(all_futures),
            desc="Model answers",
        ):
            model_name = all_futures[future]
            try:
                batch_results = future.result()
                for result in batch_results:
                    model_results[model_name]["results"].append(result)
                    if result["status"] == "success":
                        model_results[model_name]["processed_count"] += 1
                    elif result["status"] == "skipped":
                        model_results[model_name]["skipped_count"] += 1
                    else:
                        model_results[model_name]["error_count"] += 1
            except Exception as e:
                print(f"Error processing task for {model_name}: {str(e)}")
                model_results[model_name]["error_count"] += 1

    print("Phase 2: process batch outputs and extract diagnoses")

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        all_futures = {}

        for model_name in wait2test:
            if model_name not in model_dirs:
                continue

            batch_files = []
            for json_num in batch_indices:
                base_filename = case_stem_from_filename(json_name_list[json_num])
                out_dir_files = os.listdir(model_dirs[model_name]["out_dir"])
                for file_name in out_dir_files:
                    if file_name.startswith(base_filename) and file_name.endswith(".txt"):
                        batch_files.append(file_name)

            print(
                f"Model: {model_name}, Batch indices: {batch_indices}, "
                f"Found {len(batch_files)} files to process: {batch_files}"
            )
            if not batch_files:
                print(
                    f"No files found for processing in {model_dirs[model_name]['out_dir']}. "
                    "Check if first stage generated any new txt files."
                )

            for file in batch_files:
                future = executor.submit(
                    process_output_file,
                    file,
                    model_dirs[model_name]["out_dir"],
                    model_dirs[model_name]["output_dir"],
                    model_dirs[model_name]["output_prompt_dir"],
                    model_dirs[model_name]["output_log_dir"],
                    model_dirs[model_name]["json_save_dir"],
                    format_checker_prompt,
                    checker_model,
                    checker_api_key,
                    checker_url,
                )
                all_futures[future] = model_name

        for future in tqdm(
            concurrent.futures.as_completed(all_futures),
            total=len(all_futures),
            desc="Output files",
        ):
            model_name = all_futures[future]
            try:
                result = future.result()
                if result["status"] in ["success", "skipped"]:
                    diagnoses_formatted = ""
                    if result["diagnoses"]:
                        diagnoses_formatted = "\n".join(result["diagnoses"])
                    model_dfs[model_name] = pd.concat(
                        [
                            model_dfs[model_name],
                            pd.DataFrame(
                                {
                                    COL_FILENAME: [result["file"]],
                                    COL_MOST_LIKELY_DIAGNOSIS: [result["mostlikely_diag"]],
                                    COL_POSSIBLE_DIAGNOSES: [diagnoses_formatted],
                                }
                            ),
                        ],
                        ignore_index=True,
                    )
            except Exception as e:
                print(f"Error processing output file task for {model_name}: {str(e)}")


def main():
    excel = pd.read_excel(EXCEL_PATH)
    json_name_list = [
        normalize_case_filename(name.replace("/", "a")) for name in excel["File Name"]
    ]
    question_list = list(excel["question"])

    with open(PROMPT_QUERY_PATH, "r", encoding="utf-8") as f:
        prompt_query = f.read()

    with open(FORMAT_CHECKER_PATH, "r", encoding="utf-8") as f:
        format_checker_prompt = f.read()

    max_workers = BIAS_ASK_MAX_WORKERS

    checker_model_config = resolve_model(model_checker)
    if not checker_model_config:
        print(f"Error: no API config for checker model {model_checker}")
        return
    checker_api_key = checker_model_config["api_key"]
    checker_url = checker_model_config["url"]
    checker_model = checker_model_config["id"]

    for round_num in round_num_list:
        print(f"Starting evaluation round {round_num}")



        # Per-model result tracking
        model_results = {model_name: {
            "processed_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "results": []
        } for model_name in wait2test}

        model_dfs = {model_name: pd.DataFrame(columns=[COL_FILENAME, COL_MOST_LIKELY_DIAGNOSIS, COL_POSSIBLE_DIAGNOSES]) for model_name in wait2test}

        model_dirs = {}
        for model_name in wait2test:
            model_config = resolve_model(model_name)
            if not model_config:
                print(f"Error: no API config for model {model_name}")
                continue

            model_id = model_config["id"]

            base_dir = path_bias_ask_round_base(model_id, round_num)
            bias_dir = base_dir
            out_dir = bias_dir
            prompt_save_dir = os.path.join(bias_dir, "prompt")
            log_save_dir = os.path.join(bias_dir, "log")

            output_dir = os.path.join(bias_dir, "output")
            output_prompt_dir = os.path.join(bias_dir, "output_prompt")
            output_log_dir = os.path.join(bias_dir, "output_log")
            json_save_dir = os.path.join(bias_dir, "output_json")

            for directory in [bias_dir, prompt_save_dir, log_save_dir, output_dir, output_prompt_dir, output_log_dir,
                            json_save_dir]:
                os.makedirs(directory, exist_ok=True)

            model_dirs[model_name] = {
                "out_dir": out_dir,
                "prompt_save_dir": prompt_save_dir,
                "log_save_dir": log_save_dir,
                "output_dir": output_dir,
                "output_prompt_dir": output_prompt_dir,
                "output_log_dir": output_log_dir,
                "json_save_dir": json_save_dir
            }

        progress_file = f"results\\progress_round{round_num}.json"
        last_completed_batch = 0

        if os.path.exists(progress_file):
            try:
                with open(progress_file, "r", encoding="utf-8") as f:
                    progress_data = json.load(f)
                    last_completed_batch = progress_data.get("last_completed_batch", 0)

                    for model_name in wait2test:
                        if model_name in progress_data.get("model_results", {}):
                            model_results[model_name]["processed_count"] = progress_data["model_results"][model_name].get(
                                "processed_count", 0)
                            model_results[model_name]["skipped_count"] = progress_data["model_results"][model_name].get(
                                "skipped_count", 0)
                            model_results[model_name]["error_count"] = progress_data["model_results"][model_name].get(
                                "error_count", 0)

                    for model_name in wait2test:
                        model_id = resolve_model(model_name)["id"]
                        base_dir = path_bias_ask_round_base(model_id, round_num)
                        excel_path = os.path.join(base_dir, "results.xlsx")
                        if os.path.exists(excel_path):
                            try:
                                model_dfs[model_name] = pd.read_excel(excel_path)
                            except Exception as e:
                                print(f"Error reading Excel for model {model_name}: {str(e)}")

                    print(
                        f"Resuming from batch {last_completed_batch + 1}; "
                        f"{last_completed_batch} batch(es) already completed"
                    )
            except Exception as e:
                print(f"Error reading progress file: {str(e)}; starting from scratch")
                last_completed_batch = 0

        batch_size = BIAS_ASK_BATCH_SIZE
        total_batches = (len(json_name_list) + batch_size - 1) // batch_size
        remaining_batches = total_batches - last_completed_batch

        for batch_idx in tqdm(range(remaining_batches), desc=f"Batches (total: {total_batches})"):
            current_batch = last_completed_batch + batch_idx
            batch_start = current_batch * batch_size
            batch_end = min(batch_start + batch_size, len(json_name_list))
            if batch_start >= len(json_name_list):
                break
            batch_indices = list(range(batch_start, batch_end))

            run_bias_ask_batch(
                batch_indices=batch_indices,
                batch_label=(
                    f"Processing batch {current_batch + 1}/{total_batches}, "
                    f"question indices: {batch_indices}"
                ),
                json_name_list=json_name_list,
                question_list=question_list,
                prompt_query=prompt_query,
                format_checker_prompt=format_checker_prompt,
                model_dirs=model_dirs,
                model_results=model_results,
                model_dfs=model_dfs,
                max_workers=max_workers,
                checker_model=checker_model,
                checker_api_key=checker_api_key,
                checker_url=checker_url,
            )

            for model_name, df in model_dfs.items():
                if model_name in model_dirs:
                    model_id = resolve_model(model_name)["id"]
                    base_dir = path_bias_ask_round_base(model_id, round_num)
                    out_xlsx_path = os.path.join(base_dir, "results.xlsx")
                    df.to_excel(out_xlsx_path, index=False)

            progress_data = {
                "last_completed_batch": current_batch,
                "total_batches": total_batches,
                "model_results": {model_name: {
                    "processed_count": model_results[model_name]["processed_count"],
                    "skipped_count": model_results[model_name]["skipped_count"],
                    "error_count": model_results[model_name]["error_count"]
                } for model_name in wait2test}
            }

            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=4)

            print(f"Finished batch {current_batch + 1}/{total_batches}; progress saved")

        tail_sweeps = tail_pass_limit("PRISM_BIAS_ASK_TAIL_PASSES", default=1)
        for sweep in range(1, tail_sweeps + 1):
            gap_indices = list_bias_incomplete_indices(json_name_list, model_dirs)
            if not gap_indices:
                break
            print(
                f"Round {round_num} bias_ask tail sweep {sweep}/{tail_sweeps}: "
                f"{len(gap_indices)} case(s) with missing SDoH JSON"
            )
            for offset in range(0, len(gap_indices), batch_size):
                batch_indices = gap_indices[offset : offset + batch_size]
                run_bias_ask_batch(
                    batch_indices=batch_indices,
                    batch_label=(
                        f"Tail sweep {sweep}: indices {batch_indices} "
                        f"({offset // batch_size + 1}/"
                        f"{(len(gap_indices) + batch_size - 1) // batch_size})"
                    ),
                    json_name_list=json_name_list,
                    question_list=question_list,
                    prompt_query=prompt_query,
                    format_checker_prompt=format_checker_prompt,
                    model_dirs=model_dirs,
                    model_results=model_results,
                    model_dfs=model_dfs,
                    max_workers=max_workers,
                    checker_model=checker_model,
                    checker_api_key=checker_api_key,
                    checker_url=checker_url,
                )
                for model_name, df in model_dfs.items():
                    if model_name in model_dirs:
                        model_id = resolve_model(model_name)["id"]
                        base_dir = path_bias_ask_round_base(model_id, round_num)
                        out_xlsx_path = os.path.join(base_dir, "results.xlsx")
                        df.to_excel(out_xlsx_path, index=False)

        still = list_bias_incomplete_indices(json_name_list, model_dirs)
        if still:
            print(
                f"Round {round_num}: {len(still)} SDoH case(s) still incomplete after main + "
                f"up to {tail_sweeps} tail sweep(s). Re-run the benchmark to retry "
                f"(no further automatic retries this run)."
            )

        for model_name, df in model_dfs.items():
            if model_name in model_dirs:
                model_id = resolve_model(model_name)["id"]
                base_dir = path_bias_ask_round_base(model_id, round_num)
                out_xlsx_path = os.path.join(base_dir, "results.xlsx")
                df.to_excel(out_xlsx_path, index=False)
                print(f"Saved diagnosis results for model {model_name} to: {out_xlsx_path}")
                print(
                    f"Model {model_name} stats: processed {model_results[model_name]['processed_count']} files, "
                    f"skipped {model_results[model_name]['skipped_count']} files, "
                    f"errors {model_results[model_name]['error_count']} files"
                )

        if os.path.exists(progress_file):
            os.remove(progress_file)
            print(f"Removed progress file: {progress_file}")

        print(f"Finished evaluation round {round_num} for all models")


if __name__ == "__main__":
    main()
