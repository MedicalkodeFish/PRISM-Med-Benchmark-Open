import _bootstrap  # noqa: F401
import json
import os
from pathlib import Path

from bias_count_common import build_bias_count_prompt, load_bias_directions
from count_llm_client import chat_LLM
from count_stage_runner import (
    build_roots_to_process,
    ensure_bias_analysis_root,
    load_count_prompt_template,
    match_count_output_files,
    output_json_dir_for,
    print_skipped_subdirs,
    resolve_count_llm_credentials,
    run_count_thread_pool,
    save_count_results_excel,
    write_processed_dois_txt,
)
from legacy_script_config import (
    BASE_COUNT_MAX_WORKERS,
    BIAS_COUNT_PROMPT_TEMPLATE_PATH,
    COUNT_TARGET_MODEL_LIST,
    ROUND_NUM_LIST,
)

PROMPT_TEMPLATE_PATH = BIAS_COUNT_PROMPT_TEMPLATE_PATH


def main():
    bias_root = ensure_bias_analysis_root()
    model, api_key, url = resolve_count_llm_credentials()
    template = load_count_prompt_template(str(PROMPT_TEMPLATE_PATH))
    error_files_record = []

    for wait2count_model in COUNT_TARGET_MODEL_LIST:
        for run_num in ROUND_NUM_LIST:
            root2 = output_json_dir_for("base", wait2count_model, run_num)
            if not os.path.exists(root2):
                print(f"Directory not found: {root2}, skipping...")
                continue

            match_dict = match_count_output_files("base", bias_root, root2)
            count_output_dir = root2 + "_bias_count"
            os.makedirs(count_output_dir, exist_ok=True)
            roots_to_process = build_roots_to_process(bias_root, match_dict)
            write_processed_dois_txt(count_output_dir, roots_to_process)

            def process_root(root, subdir, json_file):
                count_subdir = os.path.join(count_output_dir, subdir)
                os.makedirs(count_subdir, exist_ok=True)
                count_path = os.path.join(count_subdir, f"{subdir}.json")
                if os.path.exists(count_path):
                    print(f"Target JSON already exists, skipping: {count_path}")
                    return count_path

                json_path = os.path.join(root, "formatted.json")
                low_bias, high_bias = load_bias_directions(json_path)
                json_file_path = os.path.join(root2, json_file)
                if not os.path.exists(json_file_path):
                    print(f"File not found: {json_file_path}, skipping")
                    return None

                with open(json_file_path, "r", encoding="utf-8") as f:
                    output_data = json.load(f)
                processed = build_bias_count_prompt(template, low_bias, high_bias, output_data)
                prompt_path = os.path.join(count_subdir, "prompt.txt")
                with open(prompt_path, "w", encoding="utf-8") as f:
                    f.write(processed)

                result = chat_LLM(processed, model, api_key, url)
                if not result:
                    print(f"LLM call failed for {subdir}")
                    return None
                try:
                    results = json.loads(result)
                except json.JSONDecodeError:
                    raw_path = os.path.join(count_subdir, "count_raw.txt")
                    with open(raw_path, "w", encoding="utf-8") as f:
                        f.write(result)
                    print(f"Saved raw LLM result: {raw_path}")
                    return None

                with open(count_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)
                print(f"Saved combined count to {count_path}")
                return count_path

            processed_files = run_count_thread_pool(
                roots_to_process, process_root, BASE_COUNT_MAX_WORKERS
            )

            data_rows = []
            for count_path in processed_files:
                try:
                    with open(count_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if not content:
                            raise ValueError("File is empty (0 bytes)")
                        count_data = json.loads(content)
                    row = {
                        "base": os.path.basename(count_path).replace(".json", ""),
                        "subdir": os.path.basename(os.path.dirname(count_path)),
                        "run_num": run_num,
                        "scenario1_direction": count_data.get("scenario1_direction"),
                        "scenario1_potential_diagnoses": count_data.get("scenario1_potential_diagnoses"),
                        "scenario1_potential_count": count_data.get("scenario1_potential_count"),
                        "scenario1_main_count": count_data.get("scenario1_main_count"),
                        "scenario2_direction": count_data.get("scenario2_direction"),
                        "scenario2_potential_diagnoses": count_data.get("scenario2_potential_diagnoses"),
                        "scenario2_potential_count": count_data.get("scenario2_potential_count"),
                        "scenario2_main_count": count_data.get("scenario2_main_count"),
                    }
                    data_rows.append(row)
                except (json.JSONDecodeError, ValueError, Exception) as e:
                    print(f"!!! Error reading file: {count_path} - Reason: {e}")
                    error_files_record.append(
                        {
                            "file_path": count_path,
                            "error_msg": str(e),
                            "model": wait2count_model,
                            "run": run_num,
                        }
                    )

            excel_path = os.path.join(count_output_dir, f"results_{wait2count_model}_{run_num}.xlsx")
            save_count_results_excel(data_rows, excel_path, f"{wait2count_model} {run_num}")
            print_skipped_subdirs(match_dict, processed_files, run_num)

    print("\n" + "=" * 50)
    print("FINAL ERROR REPORT (MANUAL INSPECTION REQUIRED)")
    print("=" * 50)
    if error_files_record:
        print(f"Found {len(error_files_record)} corrupted/empty files that need attention:")
        for err in error_files_record:
            print(f"\n[Model: {err['model']} | Run: {err['run']}]")
            print(f"File: {err['file_path']}")
            print(f"Error: {err['error_msg']}")
    else:
        print("No corrupted files found during aggregation.")
    print("=" * 50)

    from count_stage_health import assert_count_stages_complete

    legacy_root = Path(__file__).resolve().parent.parent
    assert_count_stages_complete(
        legacy_root, COUNT_TARGET_MODEL_LIST, ROUND_NUM_LIST, modes=("base",)
    )


if __name__ == "__main__":
    main()
