# -*- coding: utf-8 -*-
"""Shared helpers for round/summary classification benchmark scripts."""
import os
import re
import json

import pandas as pd

from benchmark_sdoh_utils import canonical_doi_to_case_stem, get_case_record
from benchmark_column_names import RULE_NOTES_COLUMN_CANDIDATES, normalize_classification_rule_columns
from legacy_script_config import MERGED_DATASET_ROOT

REFERENCE_RULE_COLUMNS = ["Class 0.1", "Class 0.2", "Class 1", "notes"]


def case_stem_to_canonical_doi_map(excel_path: str, sheet_name: str):
    df = normalize_classification_rule_columns(pd.read_excel(excel_path, sheet_name=sheet_name))
    out = {}
    for _, r in df.iterrows():
        canonical_doi = r.get("DOI")
        if pd.isna(canonical_doi):
            continue
        case_stem = canonical_doi_to_case_stem(canonical_doi)
        out[case_stem] = str(canonical_doi)
    return out, df


def reference_text_from_rule_row(row) -> str:
    parts = []
    for col in REFERENCE_RULE_COLUMNS:
        if col in row.index and not pd.isna(row[col]):
            parts.append(f"{col}: {str(row[col])}")
            continue
        if col == "notes":
            for legacy_col in RULE_NOTES_COLUMN_CANDIDATES:
                if legacy_col != "notes" and legacy_col in row.index and not pd.isna(row[legacy_col]):
                    parts.append(f"notes: {str(row[legacy_col])}")
                    break
    return "\n".join(parts)


def load_reference_text(rule_df: pd.DataFrame, canonical_doi: str) -> str:
    hit = rule_df[rule_df["DOI"] == canonical_doi]
    if hit.empty:
        return ""
    return reference_text_from_rule_row(hit.iloc[0])


def parse_bias_scenario_filename(file_name: str):
    """Return (case_stem, scenario_key) for ``<stem>_scenario1.json`` / scenario2."""
    m = re.match(r"^(.*)_scenario([12])\.json$", file_name)
    if not m:
        return None, None
    return m.group(1), f"scenario{m.group(2)}"


def extract_diagnoses_from_case_json(json_data) -> tuple[list, str]:
    potential = []
    most_likely = ""
    for item in json_data:
        if isinstance(item, dict) and "Potential differential diagnoses" in item:
            potential = list(item["Potential differential diagnoses"].keys())
        if isinstance(item, dict) and "Most Likely Main Diagnosis" in item:
            most_likely = item["Most Likely Main Diagnosis"]
    if most_likely and most_likely not in potential:
        potential.append(most_likely)
    return [str(x) for x in potential], str(most_likely)


def process_medical_data(excel_path, sheet_name, template_path, root_path):
    """
    Build classification prompts from case outputs.

    Args:
        sheet_name: worksheet name to read.
        template_path: prompt template path.
        root_path: directory for source JSON files.
    """
    try:
        # Read Excel file.
        df = pd.read_excel(excel_path, sheet_name=sheet_name)

        # Read template file.
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read().replace("Other Potential differential diagnoses",
                                        "Potential Differential Diagnoses").replace(
                "Most Likely Diagnosis", "Most Likely Main Diagnosis").replace(
                "$$", "$").replace("$$$", "$").replace("<${", "<$[{").replace("}$>", "}]$>").replace(
                '."},', '."}},').replace('Other Potential differential diagnoses',
                                         'Potential differential diagnoses').replace("\n", "").replace("$<$", "<$")

        results = []

        # Iterate rows in the reference sheet.
        for _, row in df.iterrows():
            canonical_doi = row['DOI']
            if pd.isna(canonical_doi):
                continue

            case_stem = canonical_doi_to_case_stem(canonical_doi)

            output_file_path = os.path.join(root_path, case_stem + ".json")

            # Skip missing case output files.
            if not os.path.exists(output_file_path):
                print(f"File not found: {output_file_path}")
                continue

            # Read JSON file.
            with open(output_file_path, 'r', encoding='utf-8') as f:
                json_data = json.load(f)

            # Extract diagnosis content.
            potential_diagnoses = []
            mostlikely_diag = ""

            # Parse diagnosis records.
            for item in json_data:
                # Extract potential diagnoses.
                if "Potential differential diagnoses" in item:
                    # Keep only diagnosis names.
                    potential_diagnoses = list(item["Potential differential diagnoses"].keys())

                # Extract most likely diagnosis.
                if "Most Likely Main Diagnosis" in item:
                    mostlikely_diag = item["Most Likely Main Diagnosis"]
                    # Ensure most likely diagnosis is included in candidates.
                    if mostlikely_diag not in potential_diagnoses:
                        potential_diagnoses.append(mostlikely_diag)

            # Ensure valid output types.
            if potential_diagnoses is None:
                potential_diagnoses = []
            if mostlikely_diag is None:
                mostlikely_diag = ""

            # Ensure all diagnosis values are strings.
            potential_diagnoses = [str(item) for item in potential_diagnoses if item is not None]

            # Build reference text from rule columns.
            reference = reference_text_from_rule_row(row)

            # Build normalized diagnosis payload.
            clean_content = {
                "Potential_Diagnoses": potential_diagnoses,
                "Most_Likely_Diagnosis": mostlikely_diag
            }

            # Fill template placeholders.
            result = template.replace("{record}", json.dumps(clean_content, ensure_ascii=False, indent=2))
            result = result.replace("{reference}", reference)

            merged_data = get_case_record(MERGED_DATASET_ROOT, case_stem) or {}

            if merged_data:
                presentation = merged_data.get("Presentation of Case", "")

                # If it's a list or dict, convert to string as needed

                if isinstance(presentation, (list, dict)):

                    presentation = json.dumps(presentation, ensure_ascii=False)

            else:

                presentation = "Presentation of Case not found."

            result = result.replace("{medical_record}", presentation)

            results.append({
                'DOI': canonical_doi,
                'Potential_Diagnoses': potential_diagnoses,
                'Most_Likely_Diagnosis': mostlikely_diag,
                'Result': result
            })
        return results

    except Exception as e:
        print(f"Error while processing data: {e}")
        return []


def extract_classification_results_enhanced(llm_response_text):
    """
    Extract classes and correct diagnosis indices from LLM output.

    Returns:
        tuple: (most_likely_class, potential_class, correct_num_list)
    """
    try:
        # Debug: print response preview.
        print(f"Debug: parsing LLM response: {llm_response_text[:200]}..." if len(llm_response_text) > 200 else llm_response_text)

        # Normalize common wording variants before regex parsing.
        llm_response_text = llm_response_text.replace("总体分类", "分类")

        # First try to extract correct_num from plain text.
        correct_num = None

        # Multiple extraction patterns for compatibility.
        patterns = [
            r'"符合诊断的编号"\s*:\s*\[(.*?)\]',
            r'符合诊断的编号\s*:\s*\[(.*?)\]',
            r'"符合诊断编号"\s*:\s*\[(.*?)\]',
            r'符合诊断编号\s*:\s*\[(.*?)\]',
            r'"correct_num"\s*:\s*\[(.*?)\]',
            r'correct_num\s*:\s*\[(.*?)\]'
        ]

        for pattern in patterns:
            match = re.search(pattern, llm_response_text)
            if match:
                try:
                    # Parse numeric indices.
                    correct_num_str = match.group(1)
                    correct_num_list = [int(num.strip()) for num in correct_num_str.split(',') if
                                        num.strip().isdigit()]
                    # Map legacy diagnosis id 16 to id 1.
                    correct_num = [1 if num == 16 else num for num in correct_num_list]
                    print(f"Extracted correct_num: {correct_num}, raw: {correct_num_list}, pattern: {pattern}")
                    break
                except Exception as e:
                    print(f"Failed to parse correct_num: {e}")
                    continue

        # Fallback: parse JSON block and extract from structured content.
        if correct_num is None:
            json_pattern = r'\{[\s\S]*\}'
            json_match = re.search(json_pattern, llm_response_text)
            if json_match:
                json_str = json_match.group()
                try:
                    data = json.loads(json_str)
                    # Try extracting correct_num from JSON body.
                    if "符合诊断的编号" in data:
                        correct_num = data["符合诊断的编号"]
                        if isinstance(correct_num, list):
                            correct_num = [1 if num == 16 else num for num in correct_num]
                        print(f"Extracted correct_num from JSON: {correct_num}")
                except:
                    pass
            else:
                print("Debug: no JSON block found for correct_num extraction")

        if correct_num is None:
            print("Warning: no correct diagnosis ID list extracted")

        json_pattern = r'\{[\s\S]*\}'
        json_match = re.search(json_pattern, llm_response_text)

        if not json_match:
            print("No JSON content found")
            return None, None, correct_num

        json_str = json_match.group()
        data = json.loads(json_str)

        most_likely_class = data.get("most_likely_diagnosis", {}).get("classification")
        potential_class = data.get("possible_diagnoses", {}).get("classification")

        print(f"Parsed data: {data}")
        print(f"Most likely diagnosis class: {most_likely_class}")
        print(f"Potential diagnoses class: {potential_class}")
        print(f"Correct diagnosis IDs: {correct_num}")

        most_likely_class = int(most_likely_class) if most_likely_class is not None else None
        potential_class = int(potential_class) if potential_class is not None else None

        return most_likely_class, potential_class, correct_num

    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        return None, None, correct_num
    except Exception as e:
        print(f"Error extracting classification results: {e}")
        return None, None, correct_num


def extract_classification_results(llm_response_text):
    """
    Extract classification results from LLM response text (legacy-compatible API).

    Args:
        llm_response_text: Raw text returned by the LLM.

    Returns:
        tuple: (most_likely_class, potential_class)
    """
    most_likely_class, potential_class, _ = extract_classification_results_enhanced(llm_response_text)
    return most_likely_class, potential_class


def calculate_top_n_metrics(excel_results, top_n_values=[1, 2, 3, 4]):
    """
    Compute Top-N accuracy metrics.

    Args:
        excel_results: List of per-case result dicts.
        top_n_values: Top-N values to compute.

    Returns:
        dict: Top-N metric names to values.
    """
    metrics = {}
    total_processed = len(excel_results)

    for n in top_n_values:
        # Top-N accuracy: fraction where the correct ID appears in the first N slots.
        # Uses only the first element of correct_num; maps diagnosis id 16 to 1.
        correct_top_n = sum(1 for item in excel_results if
                            'correct_num' in item and
                            item['correct_num'] is not None and
                            len(item['correct_num']) > 0 and
                            (item['correct_num'][0] <= n or (item['correct_num'][0] == 16 and 1 <= n)))

        top_n_accuracy = correct_top_n / total_processed if total_processed > 0 else 0
        metrics[f'Top{n}_Accuracy'] = top_n_accuracy
        metrics[f'Top{n}_Count'] = correct_top_n

    return metrics
