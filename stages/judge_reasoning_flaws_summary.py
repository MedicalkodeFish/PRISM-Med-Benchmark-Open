import _bootstrap  # noqa: F401
import pandas as pd
from chat2llm import async_chat_claude
import os
import json
import asyncio
import re
import concurrent.futures
from collections import Counter
import time
import sys
from benchmark_sdoh_utils import case_stem_from_filename, get_case_record
from flaws_excel import autofit_columns, open_flaws_excel_writer, query_case_basenames
from benchmark_paths import (
    flaws_dirs_for_model_runs,
    path_model_ask_result_dir,
    path_model_flaws_summary_dir,
)
from base_ask_answer_paths import iter_case_stems_with_answer, read_answer_analysis
from reasoning_flaws_aggregate import process_flaws_summary_json_file
from reasoning_flaws_constants import HALLUCINATION_TYPES, apply_windows_proactor_event_loop_policy
from legacy_script_config import (
    BENCHMARK_DATASET_NAME,
    CLASSIFICATION_RULE_EXCEL_PATH,
    MERGED_DATASET_ROOT,
    QUERY_EXCEL_PATH,
    REASONING_LLM_MODEL,
    REASONING_SUMMARY_MAX_WORKERS,
    REASONING_SUMMARY_MODEL_LIST,
    REASONING_SUMMARY_PROMPT_PATH,
    REASONING_SUMMARY_RUN_LIST,
    REASONING_TEMPERATURE,
    ROUND_NUM_LIST,
)

apply_windows_proactor_event_loop_policy()

# Shared paths and runtime settings (centralized via legacy_script_config / PRISM_* env vars)
excel_path = QUERY_EXCEL_PATH
excel_path_classification = CLASSIFICATION_RULE_EXCEL_PATH
prompt_path = REASONING_SUMMARY_PROMPT_PATH  # Summary judger prompt
ROOT_DIR = MERGED_DATASET_ROOT
ask_num_list = ROUND_NUM_LIST
dataset_name = BENCHMARK_DATASET_NAME
model2test_list = REASONING_SUMMARY_MODEL_LIST

run_list = REASONING_SUMMARY_RUN_LIST  # For the two rounds
LLM_model = REASONING_LLM_MODEL
temperature = REASONING_TEMPERATURE
max_workers = REASONING_SUMMARY_MAX_WORKERS

# Function to process a single case for summary
async def process_summary(
    model,
    case_id,
    ask_num,
    sem,
    result_dir,
    flaws_dirs,
    dict_basename_to_path,
    ROOT_DIR,
    prompt_template,
    LLM_model,
    temperature,
):
    async with sem:
        # Check if summary already exists
        summary_dir = path_model_flaws_summary_dir(model, ask_num)
        json_out_path = os.path.join(summary_dir, f"{case_id}_flaws_summary.json")
        if os.path.exists(json_out_path):
            print(f"Summary for {case_id} already exists. Skipping.")
            return

        print(f"\nProcessing summary for model: {model}, case: {case_id}")
        
        # Paths for two evaluations
        eval1_path = os.path.join(flaws_dirs[0], f"{case_id}_flaws.json")
        eval2_path = os.path.join(flaws_dirs[1], f"{case_id}_flaws.json")  # Assuming run=1 is _flaws1
        
        if not (os.path.exists(eval1_path) and os.path.exists(eval2_path)):
            print(f"Skipping {case_id} as one or both evaluations missing.")
            if not os.path.exists(eval1_path):
                print(f"Missing Evaluation 1: {eval1_path}")
            if not os.path.exists(eval2_path):
                print(f"Missing Evaluation 2: {eval2_path}")
            return
        
        # Load evaluations
        try:
            with open(eval1_path, 'r', encoding='utf-8') as f:
                eval1 = json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to load eval1 for {case_id}: {str(e)}. Skipping.")
            return

        try:
            with open(eval2_path, 'r', encoding='utf-8') as f:
                eval2 = json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to load eval2 for {case_id}: {str(e)}. Skipping.")
            return
        
        analysis = read_answer_analysis(result_dir, case_id)
        if not analysis:
            print(f"Skipping {case_id}: no readable base_ask answer under {result_dir}")
            return
        
        case_record = ""
        true_diagnosis = ""
        # Load case record and true diagnosis
        basename = case_id
        if basename in dict_basename_to_path:
            json_rel_path = dict_basename_to_path[basename]
            dict_content = get_case_record(ROOT_DIR, json_rel_path) or {}
            case_record = dict_content.get("Presentation of Case", "")
            true_diagnosis = dict_content.get("Diagnosis", "")
        
        # Prepare prompt
        prompt = prompt_template.replace("{{ANALYSIS_TO_EVALUATE}}", analysis) \
                                .replace("{{CASE_RECORD}}", case_record) \
                                .replace("{{TRUE_DIAGNOSIS}}", true_diagnosis) \
                                .replace("{{EVALUATION1}}", json.dumps(eval1, ensure_ascii=False)) \
                                .replace("{{EVALUATION2}}", json.dumps(eval2, ensure_ascii=False))
        
        # Save prompt
        summary_dir = path_model_flaws_summary_dir(model, ask_num)
        os.makedirs(summary_dir, exist_ok=True)
        prompt_out_path = os.path.join(summary_dir, f"{case_id}_flaws_summary_prompt.txt")
        try:
            with open(prompt_out_path, "w", encoding="utf-8") as f:
                f.write(prompt)
        except PermissionError:
            print(f"Permission denied when writing prompt to {prompt_out_path}. Skipping.")
        
        # Call LLM
        response, _ = await async_chat_claude(prompt, LLM_model, temperature)
        time.sleep(6.5)

        # Save response
        out_path = os.path.join(summary_dir, f"{case_id}_flaws_summary.txt")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(response)
        except PermissionError:
            print(f"Permission denied when writing response to {out_path}. Skipping.")
        
        # Try to save as JSON
        try:
            json_response = None
            
            # Try direct parse
            try:
                json_response = json.loads(response)
            except json.JSONDecodeError:
                pass
            
            # If failed, try extracting from code block
            if json_response is None:
                code_block_match = re.search(r'```json\s*([\s\S]*?)\s*```', response, re.IGNORECASE)
                if code_block_match:
                    json_str = code_block_match.group(1)
                    json_response = json.loads(json_str)
            
            # If still failed, try extracting from any code block
            if json_response is None:
                general_code_block_match = re.search(r'```\s*([\s\S]*?)\s*```', response)
                if general_code_block_match:
                    json_str = general_code_block_match.group(1)
                    try:
                        json_response = json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
            
            # If still failed, try extracting outer {}
            if json_response is None:
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    json_str = json_match.group(0)
                    json_response = json.loads(json_str)
            
            if json_response is None:
                raise ValueError("No valid JSON found in response")
            
            json_out_path = os.path.join(summary_dir, f"{case_id}_flaws_summary.json")
            try:
                with open(json_out_path, "w", encoding="utf-8") as f:
                    json.dump(json_response, f, ensure_ascii=False, indent=4)
                print(f"Saved flaws_summary.json: {json_out_path}")
            except PermissionError:
                print(f"Permission denied when writing JSON to {json_out_path}. Skipping.")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse response as JSON for {case_id}: {str(e)}")

# Main function similar to original, but for summary
async def main_async():
    # Load data similar to original
    df = pd.read_excel(excel_path)
    df_classification = pd.read_excel(excel_path_classification)
    dict_basename_to_path = {case_stem_from_filename(p): p for p in df["File Name"]}
    allowed_cases = query_case_basenames(df)
    
    # Load prompt template
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()
    
    for ask_num in ask_num_list:
        for model in model2test_list:
            result_dir = path_model_ask_result_dir(model, ask_num)
            flaws_dirs = flaws_dirs_for_model_runs(model, ask_num, run_list)
            if not os.path.exists(result_dir):
                continue
            case_ids = iter_case_stems_with_answer(result_dir, sorted(allowed_cases))

            sem = asyncio.Semaphore(max_workers)
            tasks = [
                process_summary(
                    model,
                    case_id,
                    ask_num,
                    sem,
                    result_dir,
                    flaws_dirs,
                    dict_basename_to_path,
                    ROOT_DIR,
                    prompt_template,
                    LLM_model,
                    temperature,
                )
                for case_id in case_ids
            ]
            await asyncio.gather(*tasks)

        # Generate Excel
        output_excel = f"benchmark\\{ask_num}_flaws_summary.xlsx"
        os.makedirs(os.path.dirname(output_excel), exist_ok=True)
        writer, xl_engine = open_flaws_excel_writer(output_excel)

        all_data = []
        columns = None

        for model in model2test_list:
            summary_dir = path_model_flaws_summary_dir(model, ask_num)
            if not os.path.exists(summary_dir):
                continue

            model_data = []
            json_files = [f for f in os.listdir(summary_dir) if f.endswith('_flaws_summary.json')]

            for json_file in json_files:
                json_path = os.path.join(summary_dir, json_file)
                row = process_flaws_summary_json_file(json_path)
                row['Model'] = model
                model_data.append(row)
                all_data.append(row)

            df_model = pd.DataFrame(model_data)

            if not df_model.empty:
                columns = ['Model', 'Case ID', 'Rating', 'Total Hallucinations',
                           'High Severity Count', 'Medium Severity Count', 'Low Severity Count']
                for t in HALLUCINATION_TYPES:
                    columns.append(f'{t} Count')
                for t in HALLUCINATION_TYPES:
                    columns.append(f'{t} High Severity Count')
                columns.extend(['Audit Summary', 'Eval1 Summary', 'Eval2 Summary', 'Hallucinations Details'])

                df_model = df_model[columns]

                sheet_name = model[:31]
                df_model.to_excel(writer, sheet_name=sheet_name, index=False)

                autofit_columns(writer, sheet_name, df_model, xl_engine)

        if all_data and columns:
            df_all = pd.DataFrame(all_data)
            df_all = df_all[columns]

            summary_stats = {
                'Model': 'Summary',
                'Total Cases': len(df_all),
                'Avg Total Hallucinations': df_all['Total Hallucinations'].mean(),
                'Avg High Severity': df_all['High Severity Count'].mean(),
            }
            for t in HALLUCINATION_TYPES:
                summary_stats[f'Avg {t} Count'] = df_all[f'{t} Count'].mean()
            for t in HALLUCINATION_TYPES:
                summary_stats[f'Avg {t} High Severity'] = df_all[f'{t} High Severity Count'].mean()

            rating_count = df_all['Rating'].value_counts()
            for rating in ['Logically Sound', 'Minor Reasoning Issues', 'Significant Reasoning Hallucinations']:
                summary_stats[f'{rating} Count'] = rating_count.get(rating, 0)

            df_summary = pd.DataFrame([summary_stats])
            df_summary = df_summary.reindex(columns=list(summary_stats.keys()))

            df_all.to_excel(writer, sheet_name='All Data', index=False)
            df_summary.to_excel(writer, sheet_name='Summary', index=False)

            autofit_columns(writer, 'All Data', df_all, xl_engine)
            autofit_columns(writer, 'Summary', df_summary, xl_engine)

            if xl_engine == "xlsxwriter":
                worksheet = writer.sheets['All Data']
                worksheet.conditional_format(
                    'C2:C' + str(len(df_all) + 1),
                    {
                        'type': 'cell',
                        'criteria': '==',
                        'value': '"Logically Sound"',
                        'format': writer.book.add_format({'bg_color': '#90EE90'}),
                    },
                )
                worksheet.conditional_format(
                    'C2:C' + str(len(df_all) + 1),
                    {
                        'type': 'cell',
                        'criteria': '==',
                        'value': '"Minor Reasoning Issues"',
                        'format': writer.book.add_format({'bg_color': '#FFFFE0'}),
                    },
                )
                worksheet.conditional_format(
                    'C2:C' + str(len(df_all) + 1),
                    {
                        'type': 'cell',
                        'criteria': '==',
                        'value': '"Significant Reasoning Hallucinations"',
                        'format': writer.book.add_format({'bg_color': '#FFCCCB'}),
                    },
                )

                worksheet = writer.sheets['Summary']
                try:
                    avg_total_col_idx = df_summary.columns.get_loc('Avg Total Hallucinations')
                    avg_high_col_idx = df_summary.columns.get_loc('Avg High Severity')
                except KeyError as e:
                    print(f"Missing column for averages: {str(e)}. Skipping average chart.")
                    avg_total_col_idx = None
                    avg_high_col_idx = None

                if avg_total_col_idx is not None and avg_high_col_idx is not None:
                    try:
                        chart = writer.book.add_chart({'type': 'column'})
                        worksheet.insert_chart('A10', chart)
                        chart.set_title({'name': 'Average Hallucinations'})
                        chart.add_series({
                            'name': 'Avg Total Hallucinations',
                            'categories': ['Summary', 0, avg_total_col_idx, 0, avg_total_col_idx],
                            'values': ['Summary', 1, avg_total_col_idx, 1, avg_total_col_idx],
                        })
                        chart.add_series({
                            'name': 'Avg High Severity',
                            'categories': ['Summary', 0, avg_high_col_idx, 0, avg_high_col_idx],
                            'values': ['Summary', 1, avg_high_col_idx, 1, avg_high_col_idx],
                        })
                    except Exception as e:
                        print(f"Error adding average chart: {str(e)}. Skipping.")

                rating_cols = [
                    col for col in df_summary.columns
                    if col.endswith('Count') and 'Avg' not in col and 'Severity' not in col
                ]
                if rating_cols:
                    try:
                        chart2 = writer.book.add_chart({'type': 'column'})
                        worksheet.insert_chart('A25', chart2)
                        chart2.set_title({'name': 'Rating Distribution'})
                        for col in rating_cols:
                            col_idx = df_summary.columns.get_loc(col)
                            chart2.add_series({
                                'name': col,
                                'categories': ['Summary', 0, col_idx, 0, col_idx],
                                'values': ['Summary', 1, col_idx, 1, col_idx],
                            })
                    except Exception as e:
                        print(f"Error adding rating chart: {str(e)}. Skipping.")

        writer.close()
        print(f"Excel file saved: {output_excel}")

    return {
        "ask_num": "ALL",
        "processed_models": len(model2test_list),
        "total_models": len(model2test_list),
        "error_files": []
    }

def main():
    error_summary = asyncio.run(main_async())

    print(f"\n=== Error Summary for {error_summary['ask_num']} ===")
    print(f"Processed models: {error_summary['processed_models']}/{error_summary['total_models']}")
    if error_summary['error_files']:
        print("Error files/issues:")
        for error in error_summary['error_files']:
            print(f"  - {error}")
    else:
        print("No errors found.")
    return error_summary


if __name__ == "__main__":
    main()
