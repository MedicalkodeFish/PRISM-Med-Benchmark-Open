import _bootstrap  # noqa: F401
import pandas as pd
from chat2llm import async_chat_claude
import os
import json
import asyncio
import re
import concurrent.futures
import sys
from benchmark_sdoh_utils import case_stem_from_filename, get_case_record
from flaws_excel import autofit_columns, open_flaws_excel_writer, query_case_basenames
from reasoning_flaws_constants import (
    HALLUCINATION_TYPES,
    apply_windows_proactor_event_loop_policy,
    make_json_serializable,
)
from benchmark_paths import (
    path_benchmark_flaws_round_summary_xlsx,
    path_model_ask_result_dir,
    path_model_flaws_dir,
)
from reasoning_flaws_aggregate import process_flaws_json_file
from reasoning_flaws_json import parse_reasoning_audit_from_full_record, parse_reasoning_audit_response
from legacy_script_config import (
    BENCHMARK_DATASET_NAME,
    CLASSIFICATION_RULE_EXCEL_PATH,
    MERGED_DATASET_ROOT,
    QUERY_EXCEL_PATH,
    REASONING_JUDGER_PROMPT_PATH,
    REASONING_LLM_MODEL,
    REASONING_MAX_WORKERS,
    REASONING_MODEL_LIST,
    REASONING_RUN_LIST,
    REASONING_TEMPERATURE,
    ROUND_NUM_LIST,
)


apply_windows_proactor_event_loop_policy()

# Shared benchmark paths and runtime settings (centralized via legacy_script_config / PRISM_* env vars)
excel_path = QUERY_EXCEL_PATH
excel_path_classification = CLASSIFICATION_RULE_EXCEL_PATH
prompt_path = REASONING_JUDGER_PROMPT_PATH
ROOT_DIR = MERGED_DATASET_ROOT
ask_num_list = ROUND_NUM_LIST
dataset_name = BENCHMARK_DATASET_NAME
model2test_list = REASONING_MODEL_LIST
run_list = REASONING_RUN_LIST  # Extend via PRISM_REASONING_RUNS when using multiple judges.
LLM_model = REASONING_LLM_MODEL
temperature = REASONING_TEMPERATURE
max_workers = REASONING_MAX_WORKERS


def write_flaws_json(json_out_path: str, response_text: str) -> bool:
    json_response = parse_reasoning_audit_response(response_text)
    if json_response is None:
        return False
    with open(json_out_path, "w", encoding="utf-8") as f:
        json.dump(json_response, f, ensure_ascii=False, indent=4)
    return True


def save_full_llm_return(full_out_path, prompt, model_name, temperature, response_text, raw_result):
    """Save complete LLM return info without changing existing output file formats."""
    payload = {
        "model": model_name,
        "temperature": temperature,
        "prompt": prompt,
        "response_text": response_text,
        "raw_result": make_json_serializable(raw_result)
    }
    with open(full_out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=4)


async def process_file(txt_file, sem, result_dir, flaws_dir, dict_basename_to_path, ROOT_DIR, prompt_template, LLM_model, temperature):
    async with sem:
        print(f"\nProcessing file: {txt_file}")
        txt_path = os.path.join(result_dir, txt_file)

        # Check if flaws files already exist
        flaws_txt_path = os.path.join(flaws_dir, txt_file.replace(".txt", "_flaws.txt"))
        flaws_json_path = os.path.join(flaws_dir, txt_file.replace(".txt", "_flaws.json"))
        flaws_full_path = os.path.join(flaws_dir, txt_file.replace(".txt", "_flaws_full.json"))

        if not os.path.exists(flaws_json_path) and os.path.exists(flaws_full_path):
            recovered = parse_reasoning_audit_from_full_record(flaws_full_path)
            if recovered is not None:
                with open(flaws_json_path, "w", encoding="utf-8") as f:
                    json.dump(recovered, f, ensure_ascii=False, indent=4)
                print(f"Recovered flaws.json from {flaws_full_path}")
                return

        if os.path.exists(flaws_txt_path):
            if os.path.exists(flaws_json_path):
                print(f"Skipping {txt_file} as both flaws.txt and flaws.json exist.")
                return
            with open(flaws_txt_path, "r", encoding="utf-8") as f:
                response = f.read()
            if write_flaws_json(flaws_json_path, response):
                print(f"Extracted and saved JSON from existing {flaws_txt_path}")
                return
            print(f"Failed to extract JSON from {flaws_txt_path}; proceeding to regenerate via LLM for {txt_file}")

        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                analysis = f.read()
                lines = analysis.splitlines()
                if lines and (lines[-1].startswith("total_elapsed_sec:") or "总耗时" in lines[-1]):
                    lines = lines[:-1]
                analysis = '\n'.join(lines)
        except OSError as e:
            print(f"Error opening file {txt_path}: {str(e)}. Skipping this file.")
            return

        # Find corresponding json path
        basename = txt_file.replace(".txt", "")
        if basename in dict_basename_to_path:
            json_rel_path = dict_basename_to_path[basename]
            dict_content = get_case_record(ROOT_DIR, json_rel_path)
            if dict_content:
                try:
                    case_record = dict_content.get("Presentation of Case", "")
                    true_diagnosis = dict_content.get("Diagnosis", "")

                    prompt = prompt_template.replace("{{ANALYSIS_TO_EVALUATE}}", analysis) \
                                            .replace("{{CASE_RECORD}}", case_record) \
                                            .replace("{{TRUE_DIAGNOSIS}}", true_diagnosis)

                    # Save prompt
                    prompt_out_path = os.path.join(flaws_dir, txt_file.replace(".txt", "_flaws_prompt.txt"))
                    with open(prompt_out_path, "w", encoding="utf-8") as f:
                        f.write(prompt)
                    print(f"Saved prompt: {prompt_out_path}")

                    # Call LLM for analysis
                    print(f"Calling LLM for {txt_file}")
                    llm_result = await async_chat_claude(prompt, LLM_model, temperature)

                    response = ""
                    raw_result = None

                    if isinstance(llm_result, tuple):
                        if len(llm_result) >= 1:
                            response = llm_result[0]
                        if len(llm_result) >= 2:
                            raw_result = llm_result[1]
                    else:
                        response = str(llm_result)
                        raw_result = llm_result

                    # Save to original text path, keeping original format unchanged
                    out_path = os.path.join(flaws_dir, txt_file.replace(".txt", "_flaws.txt"))
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(response)
                    print(f"Saved flaws.txt: {out_path}")

                    # Additional save: complete LLM return info
                    try:
                        save_full_llm_return(
                            full_out_path=flaws_full_path,
                            prompt=prompt,
                            model_name=LLM_model,
                            temperature=temperature,
                            response_text=response,
                            raw_result=raw_result
                        )
                        print(f"Saved full LLM return: {flaws_full_path}")
                    except Exception as e:
                        print(f"Failed to save full LLM return for {txt_file}: {str(e)}")

                    json_out_path = os.path.join(flaws_dir, txt_file.replace(".txt", "_flaws.json"))
                    if write_flaws_json(json_out_path, response):
                        print(f"Saved flaws.json: {json_out_path}")
                    else:
                        print(
                            f"Failed to parse response as JSON for {txt_file}; "
                            f"see {flaws_full_path} for raw output"
                        )
                except OSError as e:
                    print(f"Error processing case record for {txt_file}: {str(e)}. Skipping this file.")
                    return
            else:
                print(f"Case record not found for: {json_rel_path}")
        else:
            print(f"Basename not found in mapping: {basename}")


async def main_async():
    # Read the Excel file
    df = pd.read_excel(excel_path)
    df_classification = pd.read_excel(excel_path_classification)

    # Create dict: DOI to filename (assuming column 'File Name' for filenames)
    dict_doi_to_filename = dict(zip(df['DOI'], df['File Name']))

    # Create dict: DOI to Class 0.1 (assuming column 'Class 0.1')
    dict_doi_to_class = dict(zip(df_classification['DOI'], df_classification['Class 0.1']))

    # Create dict from basename (without extension) to full file path
    dict_basename_to_path = {case_stem_from_filename(p): p for p in df["File Name"]}
    allowed_cases = query_case_basenames(df)

    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()

    for ask_num in ask_num_list:
        # Process each run
        for run in run_list:

            # Process each model for this run
            for model in model2test_list:
                result_dir = path_model_ask_result_dir(model, ask_num)
                flaws_dir = path_model_flaws_dir(model, ask_num, run)
                os.makedirs(flaws_dir, exist_ok=True)

                # Add check for result_dir existence
                if not os.path.exists(result_dir):
                    print(f"Result directory not found: {result_dir}. Creating it now.")
                    os.makedirs(result_dir, exist_ok=True)

                txt_files = [
                    f
                    for f in os.listdir(result_dir)
                    if f.endswith(".txt") and f.replace(".txt", "") in allowed_cases
                ]
                total_files = len(txt_files)
                print(f"Processing model: {model} for round: {ask_num}_flaws{run} ({total_files} files)")

                sem = asyncio.Semaphore(max_workers)
                tasks = [process_file(txt_file, sem, result_dir, flaws_dir, dict_basename_to_path, ROOT_DIR, prompt_template, LLM_model, temperature) for txt_file in txt_files]
                # Gather with return_exceptions to capture errors
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        print(f"Task error: {str(res)}")

                print(f"Finished processing model: {model} for round: {ask_num}_flaws{run}")

            # After processing all models for this run, generate the Excel summary for this round_num
            output_excel = path_benchmark_flaws_round_summary_xlsx(ask_num, run)
            os.makedirs(os.path.dirname(output_excel), exist_ok=True)  # Ensure parent dir exists
            writer, xl_engine = open_flaws_excel_writer(output_excel)

            all_data = []

            for model in model2test_list:
                flaws_dir = path_model_flaws_dir(model, ask_num, run)
                if not os.path.exists(flaws_dir):
                    print(f"Directory not found: {flaws_dir}")
                    continue

                model_data = []
                json_files = [f for f in os.listdir(flaws_dir) if f.endswith('_flaws.json')]

                for json_file in json_files:
                    json_path = os.path.join(flaws_dir, json_file)
                    row = process_flaws_json_file(json_path)
                    if row is not None:
                        row['Model'] = model
                        model_data.append(row)
                        all_data.append(row)

                # Create DataFrame for this model
                df_model = pd.DataFrame(model_data)

                # Extra empty-content guard.
                if not df_model.empty:
                    columns = ['Model', 'Case ID', 'Rating', 'Total Hallucinations',
                               'High Severity Count', 'Medium Severity Count', 'Low Severity Count']
                    for t in HALLUCINATION_TYPES:
                        columns.append(f'{t} Count')
                    for t in HALLUCINATION_TYPES:
                        columns.append(f'{t} High Severity Count')
                    columns.extend(['Audit Summary', 'Hallucinations Details'])

                    df_model = df_model[columns]

                    # Write to sheet
                    sheet_name = model[:31]  # Excel sheet name limit
                    df_model.to_excel(writer, sheet_name=sheet_name, index=False)

                    autofit_columns(writer, sheet_name, df_model, xl_engine)

                # Create All Data and Summary sheets after processing all models
                if all_data:
                    df_all = pd.DataFrame(all_data)
                    df_all = df_all[columns]  # Same column order

                    # Add summary statistics
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

                    # Rating distribution
                    rating_count = df_all['Rating'].value_counts()
                    for rating in ['Logically Sound', 'Minor Reasoning Issues', 'Significant Reasoning Hallucinations']:
                        summary_stats[f'{rating} Count'] = rating_count.get(rating, 0)

                    df_summary = pd.DataFrame([summary_stats])

                    # Reindex to ensure column order matches summary_stats keys
                    df_summary = df_summary.reindex(columns=list(summary_stats.keys()))

                    # Debug prints for column verification
                    print("Summary stats keys:", list(summary_stats.keys()))
                    print("df_summary columns:", list(df_summary.columns))

                    # Write all data to 'All Data' sheet
                    df_all.to_excel(writer, sheet_name='All Data', index=False)

                    # Write summary to 'Summary' sheet
                    df_summary.to_excel(writer, sheet_name='Summary', index=False)

                    autofit_columns(writer, 'All Data', df_all, xl_engine)
                    autofit_columns(writer, 'Summary', df_summary, xl_engine)

                    if xl_engine == "xlsxwriter":
                        try:
                            if not df_all.empty:
                                worksheet = writer.sheets['All Data']
                                worksheet.conditional_format('C2:C' + str(len(df_all) + 1), {'type': 'cell',
                                                                                             'criteria': '==',
                                                                                             'value': '"Logically Sound"',
                                                                                             'format': writer.book.add_format({'bg_color': '#90EE90'})})
                                worksheet.conditional_format('C2:C' + str(len(df_all) + 1), {'type': 'cell',
                                                                                             'criteria': '==',
                                                                                             'value': '"Minor Reasoning Issues"',
                                                                                             'format': writer.book.add_format({'bg_color': '#FFFFE0'})})
                                worksheet.conditional_format('C2:C' + str(len(df_all) + 1), {'type': 'cell',
                                                                                             'criteria': '==',
                                                                                             'value': '"Significant Reasoning Hallucinations"',
                                                                                             'format': writer.book.add_format({'bg_color': '#FFCCCB'})})

                            if not df_summary.empty:
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
                                            'values': ['Summary', 1, avg_total_col_idx, 1, avg_total_col_idx]
                                        })
                                        chart.add_series({
                                            'name': 'Avg High Severity',
                                            'categories': ['Summary', 0, avg_high_col_idx, 0, avg_high_col_idx],
                                            'values': ['Summary', 1, avg_high_col_idx, 1, avg_high_col_idx]
                                        })
                                    except Exception as e:
                                        print(f"Error adding average chart: {str(e)}. Skipping.")

                                rating_cols = [col for col in df_summary.columns if col.endswith('Count') and 'Avg' not in col and 'Severity' not in col]
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
                                                'values': ['Summary', 1, col_idx, 1, col_idx]
                                            })
                                    except Exception as e:
                                        print(f"Error adding rating chart: {str(e)}. Skipping.")
                        except Exception as e:
                            print(f"Error adding visualizations: {str(e)}. File will be saved without charts.")

            writer.close()
            print(f"Excel file saved: {output_excel} for round: {ask_num}_flaws{run}")


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        print("Program interrupted by user. Shutting down gracefully...")
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
        sys.exit(0)
    except Exception as e:
        print(f"Main loop error: {str(e)}")
    finally:
        if not loop.is_closed():
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()


if __name__ == "__main__":
    main()
