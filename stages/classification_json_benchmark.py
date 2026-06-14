import _bootstrap  # noqa: F401
import asyncio

from benchmark_paths import (
    as_legacy_str,
    path_model_classification_run_dir,
    path_model_classification_summary_dir,
    path_model_round_output_json,
)
from async_runtime import apply_windows_selector_event_loop_policy
from classification_benchmark_pipeline import process_and_query_llm
from legacy_script_config import (
    BENCHMARK_DATASET_NAME,
    CLASSIFICATION_MAX_WORKER,
    CLASSIFICATION_MODEL_LIST,
    CLASSIFICATION_RULE_EXCEL_PATH,
    CLASSIFICATION_RULE_PROMPT_PATH,
    CLASSIFICATION_RULE_SHEET_NAME,
    CLASSIFICATION_RUN_LIST,
    ROUND_NUM_LIST,
)
from model_config import api_config, classification_model

dataset_name = BENCHMARK_DATASET_NAME
model2classify_list = CLASSIFICATION_MODEL_LIST
max_worker = CLASSIFICATION_MAX_WORKER
round_num_list = ROUND_NUM_LIST
run_list = CLASSIFICATION_RUN_LIST


async def main_async():
    excel_path = CLASSIFICATION_RULE_EXCEL_PATH
    sheet_name = CLASSIFICATION_RULE_SHEET_NAME
    template_path = CLASSIFICATION_RULE_PROMPT_PATH

    print(f"Classification model: {classification_model}")
    print(f"Model ID: {api_config[classification_model.lower()]['model_id']}")

    for model_name in model2classify_list:
        for round_num in round_num_list:
            for run in run_list:
                root_path = as_legacy_str(path_model_round_output_json(model_name, round_num))
                output_dir = as_legacy_str(
                    path_model_classification_run_dir(
                        model_name, round_num, run, dataset_name=dataset_name
                    )
                )
                print(f"\nStarting classification: model={model_name}, round={round_num}, run={run}")

                results = await process_and_query_llm(
                    excel_path,
                    sheet_name,
                    template_path,
                    root_path,
                    output_dir,
                    max_worker=max_worker,
                )

                for result in results:
                    print(f"DOI: {result['DOI']}")
                    print(f"Potential diagnoses: {', '.join(result['Potential_Diagnoses'])}")
                    print(f"Most likely diagnosis: {result['Most_Likely_Diagnosis']}")
                    print("LLM response excerpt:")
                    llm_response = result.get("LLM_Response", "")
                    print(f"{llm_response[:200]}..." if len(llm_response) > 200 else llm_response)
                    print("-" * 80)


def main():
    apply_windows_selector_event_loop_policy()
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
