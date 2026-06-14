import _bootstrap  # noqa: F401
import asyncio
import os

from async_runtime import apply_windows_selector_event_loop_policy
from benchmark_paths import benchmark_result_root
from classification_benchmark_common import case_stem_to_canonical_doi_map
from classification_benchmark_pipeline import process_bias_classification_round
from legacy_script_config import (
    BENCHMARK_DATASET_NAME,
    CLASSIFICATION_MAX_WORKER,
    CLASSIFICATION_MODEL_LIST,
    CLASSIFICATION_RULE_EXCEL_PATH,
    CLASSIFICATION_RULE_PROMPT_PATH,
    CLASSIFICATION_RULE_SHEET_NAME,
    ROUND_NUM_LIST,
)

dataset_name = BENCHMARK_DATASET_NAME
round_num_list = ROUND_NUM_LIST
max_worker = CLASSIFICATION_MAX_WORKER
model_list = CLASSIFICATION_MODEL_LIST


async def main_async():
    excel_path = CLASSIFICATION_RULE_EXCEL_PATH
    sheet_name = CLASSIFICATION_RULE_SHEET_NAME
    template_path = CLASSIFICATION_RULE_PROMPT_PATH
    case_stem_to_canonical_doi, rule_df = case_stem_to_canonical_doi_map(excel_path, sheet_name)
    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read().replace("\n", "")

    result_root = benchmark_result_root()
    if not result_root.exists():
        raise FileNotFoundError(f"Missing directory: {result_root}")
    models = [
        m
        for m in model_list
        if (result_root / m).is_dir()
    ]
    if not models:
        models = [d.name for d in result_root.iterdir() if d.is_dir()]

    for model in models:
        for round_num in round_num_list:
            await process_bias_classification_round(
                round_num,
                model,
                rule_df,
                case_stem_to_canonical_doi,
                template,
                dataset_name=dataset_name,
                max_worker=max_worker,
            )


def main():
    apply_windows_selector_event_loop_policy()
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
