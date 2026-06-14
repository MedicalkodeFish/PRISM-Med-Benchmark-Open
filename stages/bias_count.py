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
    BIAS_COUNT_MAX_WORKERS,
    BIAS_COUNT_PROMPT_TEMPLATE_PATH,
    COUNT_TARGET_MODEL_LIST,
    ROUND_NUM_LIST,
)

PROMPT_TEMPLATE_PATH = BIAS_COUNT_PROMPT_TEMPLATE_PATH


def main():
    bias_root = ensure_bias_analysis_root()
    model, api_key, url = resolve_count_llm_credentials()
    template = load_count_prompt_template(str(PROMPT_TEMPLATE_PATH))

    for wait2count_model in COUNT_TARGET_MODEL_LIST:
        for run_id in ROUND_NUM_LIST:
            root2 = output_json_dir_for("bias", wait2count_model, run_id)
            if not os.path.exists(root2):
                print(f"Directory not found: {root2}, skipping...")
                continue

            match_dict = match_count_output_files("bias", bias_root, root2)
            count_output_dir = root2 + "_bias_count"
            os.makedirs(count_output_dir, exist_ok=True)
            roots_to_process = build_roots_to_process(bias_root, match_dict)
            write_processed_dois_txt(count_output_dir, roots_to_process)

            def process_root(root, subdir, scenario_files):
                count_subdir = os.path.join(count_output_dir, subdir)
                os.makedirs(count_subdir, exist_ok=True)
                count_path = os.path.join(count_subdir, f"{subdir}_count.json")
                if os.path.exists(count_path):
                    print(f"Count file already exists, skipping: {count_path}")
                    return count_path

                low_bias, high_bias = load_bias_directions(os.path.join(root, "formatted.json"))
                results = {}
                for file in scenario_files:
                    if "_scenario1" in file:
                        scenario = 1
                    elif "_scenario2" in file:
                        scenario = 2
                    else:
                        continue
                    scenario_path = os.path.join(root2, file)
                    if not os.path.exists(scenario_path):
                        continue
                    with open(scenario_path, "r", encoding="utf-8") as f:
                        output_data = json.load(f)
                    processed = build_bias_count_prompt(template, low_bias, high_bias, output_data)
                    prompt_path = os.path.join(count_subdir, f"scenario{scenario}_prompt.txt")
                    with open(prompt_path, "w", encoding="utf-8") as f:
                        f.write(processed)
                    result = chat_LLM(processed, model, api_key, url)
                    if not result:
                        continue
                    try:
                        results[f"scenario{scenario}"] = json.loads(result)
                    except json.JSONDecodeError:
                        raw_path = os.path.join(count_subdir, f"scenario{scenario}_count_raw.txt")
                        with open(raw_path, "w", encoding="utf-8") as f:
                            f.write(result)

                if not results:
                    return None
                with open(count_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=4)
                return count_path

            processed_files = run_count_thread_pool(
                roots_to_process, process_root, BIAS_COUNT_MAX_WORKERS
            )

            data_rows = []
            for count_path in processed_files:
                with open(count_path, "r", encoding="utf-8") as f:
                    count_data = json.load(f)
                row = {
                    "base": os.path.basename(count_path).replace("_count.json", ""),
                    "subdir": os.path.basename(os.path.dirname(count_path)),
                    "run_id": run_id,
                }
                for scenario in (1, 2):
                    key = f"scenario{scenario}"
                    if key not in count_data:
                        continue
                    scen_data = count_data[key]
                    prefix = f"scenario{scenario}_"
                    row[prefix + "low_direction"] = scen_data.get("scenario1_direction")
                    row[prefix + "low_potential_diagnoses"] = scen_data.get("scenario1_potential_diagnoses")
                    row[prefix + "low_potential_count"] = scen_data.get("scenario1_potential_count")
                    row[prefix + "low_main_count"] = scen_data.get("scenario1_main_count")
                    row[prefix + "high_direction"] = scen_data.get("scenario2_direction")
                    row[prefix + "high_potential_diagnoses"] = scen_data.get("scenario2_potential_diagnoses")
                    row[prefix + "high_potential_count"] = scen_data.get("scenario2_potential_count")
                    row[prefix + "high_main_count"] = scen_data.get("scenario2_main_count")
                data_rows.append(row)

            excel_path = os.path.join(count_output_dir, f"results_{wait2count_model}_{run_id}.xlsx")
            save_count_results_excel(data_rows, excel_path, wait2count_model)

            print_skipped_subdirs(match_dict, processed_files, run_id)

    from count_stage_health import assert_count_stages_complete

    legacy_root = Path(__file__).resolve().parent.parent
    assert_count_stages_complete(
        legacy_root, COUNT_TARGET_MODEL_LIST, ROUND_NUM_LIST, modes=("bias",)
    )


if __name__ == "__main__":
    main()
