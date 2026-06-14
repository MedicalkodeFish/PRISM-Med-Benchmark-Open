# -*- coding: utf-8 -*-
"""Async LLM classification pipeline shared by round and summary benchmark scripts."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from benchmark_paths import (
    as_legacy_str,
    path_bias_classification_scenario_dir,
    path_model_bias_output_json,
    path_model_classification_run_dir,
)
from benchmark_sdoh_utils import canonical_doi_to_case_stem
from chat2llm import async_chat_claude
from classification_benchmark_common import (
    calculate_top_n_metrics,
    extract_classification_results_enhanced,
    extract_diagnoses_from_case_json,
    load_reference_text,
    parse_bias_scenario_filename,
    process_medical_data,
)
from model_config import classification_model


@dataclass(frozen=True)
class SummaryClassificationContext:
    model_name: str
    round_num: str
    dataset_name: str
    run_list: Sequence[str]


def _result_row(result: dict, most_likely_class, potential_class, correct_num) -> dict:
    return {
        "DOI": result["DOI"],
        "Potential_Diagnoses": "\n".join(result["Potential_Diagnoses"])
        if "Potential_Diagnoses" in result
        else "",
        "Most_Likely_Diagnosis": result["Most_Likely_Diagnosis"]
        if "Most_Likely_Diagnosis" in result
        else "",
        "Most_Likely_Class": most_likely_class,
        "Potential_Class": potential_class,
        "correct_num": correct_num,
    }


def extract_two_rounds_evaluations(
    model_name: str,
    canonical_doi: str,
    round_num: str,
    run_list: Sequence[str],
) -> tuple[str, str]:
    case_stem = canonical_doi_to_case_stem(canonical_doi)
    evaluation1 = None
    evaluation2 = None

    for idx, run in enumerate(run_list):
        run_suffix = str(run)
        classification_json_path = as_legacy_str(
            path_model_classification_run_dir(
                model_name, round_num, run_suffix, dataset_name="benchmark"
            )
            / f"{case_stem}_classification.json"
        )
        if not os.path.exists(classification_json_path):
            continue
        with open(classification_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        payload = {
            "most_likely_diagnosis_class": data.get("most_likely_diagnosis_class"),
            "potential_diagnoses_class": data.get("potential_diagnoses_class"),
            "correct_num": data.get("correct_num"),
        }
        if idx == 0:
            evaluation1 = payload
        elif idx == 1:
            evaluation2 = payload

    if evaluation1 and evaluation2 is None:
        print(
            f"Warning: only one classification adjudication run found for {canonical_doi}; "
            "reusing it as evaluation2 (set PRISM_CLASSIFICATION_RUNS=1,2 for two independent runs)."
        )
        evaluation2 = evaluation1

    eval1_str = json.dumps(evaluation1, ensure_ascii=False) if evaluation1 else "No evaluation1 available"
    eval2_str = json.dumps(evaluation2, ensure_ascii=False) if evaluation2 else "No evaluation2 available"
    return eval1_str, eval2_str


def _prepare_summary_prompt_or_short_circuit(
    result: dict,
    classification_json_path: str,
    summary_context: SummaryClassificationContext,
) -> tuple[Optional[str], Optional[dict], Optional[str]]:
    """Return (prompt, early_row, skip_reason). Exactly one of prompt / early_row / skip is set."""
    canonical_doi = result["DOI"]
    eval1_str, eval2_str = extract_two_rounds_evaluations(
        summary_context.model_name,
        canonical_doi,
        summary_context.round_num,
        summary_context.run_list,
    )
    evaluation1 = json.loads(eval1_str) if eval1_str != "No evaluation1 available" else None
    evaluation2 = json.loads(eval2_str) if eval2_str != "No evaluation2 available" else None

    if evaluation1 is None or evaluation2 is None:
        print(f"Missing evaluation1 or evaluation2, skipping canonical_doi: {canonical_doi}")
        return None, None, "missing_eval"

    if evaluation1 == evaluation2:
        print(f"canonical_doi: {canonical_doi} — both evaluation rounds match; using evaluation1")
        ml = evaluation1["most_likely_diagnosis_class"]
        pc = evaluation1["potential_diagnoses_class"]
        cn = evaluation1["correct_num"]
        classification_result = {
            "DOI": canonical_doi,
            "most_likely_diagnosis_class": ml,
            "potential_diagnoses_class": pc,
            "correct_num": cn,
        }
        with open(classification_json_path, "w", encoding="utf-8") as f:
            json.dump(classification_result, f, ensure_ascii=False, indent=2)
        print(f"Consistent result saved to: {classification_json_path}")
        result["LLM_Response"] = "Evaluations consistent, no LLM query needed."
        return None, _result_row(result, ml, pc, cn), None

    prompt = f"{result['Result']}"
    prompt = prompt.replace("{evaluation1}", eval1_str)
    prompt = prompt.replace("{evaluation2}", eval2_str)
    return prompt, None, None


async def process_and_query_llm(
    excel_path,
    sheet_name,
    template_path,
    root_path,
    output_dir,
    *,
    max_worker: int,
    summary_context: Optional[SummaryClassificationContext] = None,
):
    try:
        results = process_medical_data(excel_path, sheet_name, template_path, root_path)
        print("results:" + str(results))
        os.makedirs(output_dir, exist_ok=True)
        semaphore = asyncio.Semaphore(max_worker)

        async def process_single_result(result, semaphore):
            async with semaphore:
                canonical_doi = result["DOI"]
                case_stem = canonical_doi_to_case_stem(canonical_doi)
                llm_response_path = os.path.join(output_dir, f"{case_stem}_llm_response.txt")
                classification_json_path = os.path.join(output_dir, f"{case_stem}_classification.json")
                need_requery = False

                if os.path.exists(llm_response_path):
                    print(f"LLM response file exists, checking case: {canonical_doi} (stem={case_stem})")
                    with open(llm_response_path, "r", encoding="utf-8") as f:
                        response = f.read()
                    result["LLM_Response"] = response
                    most_likely_class = None
                    potential_class = None
                    correct_num = None

                    if os.path.exists(classification_json_path):
                        try:
                            with open(classification_json_path, "r", encoding="utf-8") as f:
                                classification_data = json.load(f)
                            most_likely_class = classification_data.get("most_likely_diagnosis_class")
                            potential_class = classification_data.get("potential_diagnoses_class")
                            correct_num = classification_data.get("correct_num")
                            print(f"Loaded classification from existing JSON: {classification_json_path}")
                            if most_likely_class is None or potential_class is None:
                                print(f"Invalid classification; re-querying LLM: {canonical_doi}")
                                need_requery = True
                        except Exception as e:
                            print(f"Error reading classification JSON: {e}")
                            need_requery = True
                    else:
                        most_likely_class, potential_class, correct_num = (
                            extract_classification_results_enhanced(response)
                        )
                        if most_likely_class is None or potential_class is None:
                            print(f"Invalid classification from LLM response; re-querying LLM: {canonical_doi}")
                            need_requery = True
                        else:
                            with open(classification_json_path, "w", encoding="utf-8") as f:
                                json.dump(
                                    {
                                        "DOI": canonical_doi,
                                        "most_likely_diagnosis_class": most_likely_class,
                                        "potential_diagnoses_class": potential_class,
                                        "correct_num": correct_num,
                                    },
                                    f,
                                    ensure_ascii=False,
                                    indent=2,
                                )
                            print(f"Extracted classification from existing LLM response and saved to: {classification_json_path}")

                    if need_requery:
                        print(f"Removing invalid response file: {llm_response_path}")
                        if os.path.exists(llm_response_path):
                            os.remove(llm_response_path)
                        if os.path.exists(classification_json_path):
                            os.remove(classification_json_path)
                    else:
                        return _result_row(result, most_likely_class, potential_class, correct_num)

                if summary_context is not None:
                    prompt, early_row, skip_reason = _prepare_summary_prompt_or_short_circuit(
                        result, classification_json_path, summary_context
                    )
                    if skip_reason:
                        return None
                    if early_row is not None:
                        return early_row
                else:
                    prompt = f"{result['Result']}"

                print(f"Querying LLM for case: {canonical_doi} (stem={case_stem})...")
                prompt_path = os.path.join(output_dir, f"{case_stem}_prompt.txt")
                try:
                    with open(prompt_path, "w", encoding="utf-8") as f:
                        f.write(prompt)
                    print(f"Prompt saved to: {prompt_path}")
                except Exception as e:
                    print(f"Error saving prompt: {e}")

                try:
                    response, result0 = await async_chat_claude(prompt, classification_model)
                    try:
                        with open(llm_response_path, "w", encoding="utf-8") as f:
                            f.write(response)
                        print(f"LLM reply saved to: {llm_response_path}")
                        llm_full_response_path = os.path.join(
                            output_dir, f"{case_stem}_llm_full_response.json"
                        )
                        with open(llm_full_response_path, "w", encoding="utf-8") as f:
                            json.dump(result0, f, ensure_ascii=False, indent=2)
                        print(f"Full LLM reply saved to: {llm_full_response_path}")
                    except Exception as e:
                        print(f"Error saving LLM reply: {e}")

                    result["LLM_Response"] = response
                    most_likely_class, potential_class, correct_num = (
                        extract_classification_results_enhanced(response)
                    )
                    if most_likely_class is None or potential_class is None:
                        print(f"Invalid classification from new LLM response; will re-query: {canonical_doi}")
                        if os.path.exists(llm_response_path):
                            os.remove(llm_response_path)
                        return None

                    with open(classification_json_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {
                                "DOI": canonical_doi,
                                "most_likely_diagnosis_class": most_likely_class,
                                "potential_diagnoses_class": potential_class,
                                "correct_num": correct_num,
                            },
                            f,
                            ensure_ascii=False,
                            indent=2,
                        )
                    return _result_row(result, most_likely_class, potential_class, correct_num)
                except Exception as e:
                    print(f"Error querying LLM: {e}")
                    result["LLM_Response"] = f"Error: {str(e)}"
                    return None

        tasks = [process_single_result(result, semaphore) for result in results]
        processed_entries = await asyncio.gather(*tasks)
        excel_results = [entry for entry in processed_entries if entry is not None]

        total_processed = len(excel_results)
        total_expected = len(results) if results else total_processed
        correct_most_likely = sum(1 for item in excel_results if item.get("Most_Likely_Class") == 0)
        accuracy = correct_most_likely / total_processed if total_processed > 0 else 0
        covered_potential = sum(1 for item in excel_results if item.get("Potential_Class") in [0, 1])
        coverage = covered_potential / total_processed if total_processed > 0 else 0
        completion_rate = total_processed / total_expected if total_expected > 0 else 0
        top_n_metrics = calculate_top_n_metrics(excel_results, [1, 2, 3, 4])

        for item in excel_results:
            item["Accuracy"] = accuracy
            item["Coverage"] = coverage
            item["Processed_Count_Metrics"] = total_processed
            item["Total_Expected"] = total_expected
            item["Completion_Rate"] = completion_rate
            for metric_name, metric_value in top_n_metrics.items():
                item[metric_name] = metric_value

        df_results = pd.DataFrame(excel_results)
        excel_output_path = os.path.join(output_dir, "classification_summary1.xlsx")
        df_results.to_excel(excel_output_path, index=False)
        print(f"Classification summary saved to: {excel_output_path}")

        summary_data = {
            "metric": ["total_samples", "processed_samples", "completion_rate", "base_accuracy", "coverage"]
            + [f"Top{n}_accuracy" for n in [1, 2, 3, 4]]
            + [f"Top{n}_correct_count" for n in [1, 2, 3, 4]],
            "value": [total_expected, total_processed, completion_rate, accuracy, coverage]
            + [top_n_metrics[f"Top{n}_Accuracy"] for n in [1, 2, 3, 4]]
            + [top_n_metrics[f"Top{n}_Count"] for n in [1, 2, 3, 4]],
        }
        summary_df = pd.DataFrame(summary_data)
        summary_excel_path = os.path.join(output_dir, "metrics_summary1.xlsx")
        summary_df.to_excel(summary_excel_path, index=False)
        print(f"Metrics summary saved to: {summary_excel_path}")
        return results
    except Exception as e:
        print(f"Error processing data: {e}")
        return []


async def process_bias_classification_round(
    round_num: str,
    model_name: str,
    rule_df: pd.DataFrame,
    case_stem_to_canonical_doi: Dict[str, str],
    template: str,
    *,
    dataset_name: str,
    max_worker: int,
) -> None:
    """Classify bias scenario outputs (scenario1 / scenario2) via the same LLM parser as base runs."""
    root_path = str(path_model_bias_output_json(model_name, round_num))
    if not os.path.exists(root_path):
        print(f"bias output_json not found, skipping: {root_path}")
        return

    out_dirs = {
        "scenario1": as_legacy_str(
            path_bias_classification_scenario_dir(
                model_name, round_num, "scenario1", dataset_name=dataset_name
            )
        ),
        "scenario2": as_legacy_str(
            path_bias_classification_scenario_dir(
                model_name, round_num, "scenario2", dataset_name=dataset_name
            )
        ),
    }
    for d in out_dirs.values():
        os.makedirs(d, exist_ok=True)

    files = [f for f in os.listdir(root_path) if f.endswith(".json") and "_scenario" in f]
    sem = asyncio.Semaphore(max_worker)
    scenario_rows: Dict[str, List[dict]] = {"scenario1": [], "scenario2": []}

    async def one_file(fn: str) -> None:
        async with sem:
            case_stem, scenario = parse_bias_scenario_filename(fn)
            if not case_stem or scenario not in out_dirs:
                return
            canonical_doi = case_stem_to_canonical_doi.get(case_stem, case_stem)
            src_json = os.path.join(root_path, fn)
            try:
                with open(src_json, "r", encoding="utf-8") as f:
                    json_data = json.load(f)
                potential, most_likely = extract_diagnoses_from_case_json(json_data)
            except Exception as e:
                print(f"Failed to read diagnoses: {src_json} -> {e}")
                return

            reference = load_reference_text(rule_df, canonical_doi)
            prompt = (
                template.replace(
                    "{record}",
                    json.dumps(
                        {"Potential_Diagnoses": potential, "Most_Likely_Diagnosis": most_likely},
                        ensure_ascii=False,
                        indent=2,
                    ),
                ).replace("{reference}", reference)
            )

            out_dir = out_dirs[scenario]
            artifact_stem = f"{case_stem}_{scenario}"
            prompt_path = os.path.join(out_dir, f"{artifact_stem}_prompt.txt")
            resp_path = os.path.join(out_dir, f"{artifact_stem}_llm_response.txt")
            json_path = os.path.join(out_dir, f"{artifact_stem}_classification.json")

            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(prompt)

            if os.path.exists(json_path):
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    scenario_rows[scenario].append(
                        {
                            "DOI": canonical_doi,
                            "Most_Likely_Class": d.get("most_likely_diagnosis_class"),
                            "Potential_Class": d.get("potential_diagnoses_class"),
                            "correct_num": d.get("correct_num"),
                        }
                    )
                    return
                except Exception:
                    pass

            try:
                response, _ = await async_chat_claude(prompt, classification_model)
            except Exception as e:
                print(f"Classification call failed: {artifact_stem} -> {e}")
                return

            with open(resp_path, "w", encoding="utf-8") as f:
                f.write(response)

            ml, pc, cn = extract_classification_results_enhanced(response)
            if ml is None or pc is None:
                print(f"Classification parse failed: {artifact_stem}")
                return

            out_json = {
                "DOI": canonical_doi,
                "most_likely_diagnosis_class": ml,
                "potential_diagnoses_class": pc,
                "correct_num": cn,
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(out_json, f, ensure_ascii=False, indent=2)

            scenario_rows[scenario].append(
                {
                    "DOI": canonical_doi,
                    "Most_Likely_Class": ml,
                    "Potential_Class": pc,
                    "correct_num": cn,
                }
            )

    await asyncio.gather(*[one_file(fn) for fn in files])

    for scenario in ("scenario1", "scenario2"):
        df = pd.DataFrame(scenario_rows[scenario])
        out_dir = out_dirs[scenario]
        out_xlsx = os.path.join(out_dir, f"classification_summary_{scenario}.xlsx")
        df.to_excel(out_xlsx, index=False)
        print(f"Saved: {out_xlsx}")
