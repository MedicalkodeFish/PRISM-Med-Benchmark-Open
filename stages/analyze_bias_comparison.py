import _bootstrap  # noqa: F401

import os

import json

import pandas as pd

import numpy as np



from legacy_script_config import (

    COUNT_TARGET_MODEL_LIST,

    ROUND_NUM_LIST,

    get_env_list,

    resolve_benchmark_dir,

    resolve_reference_table_path,

)

from benchmark_sdoh_utils import (

    SSR_FIELD_RULES,

    bias_count_base,

    canonical_doi_to_case_stem,

    extract_ssr_from_bias_json,

    first_existing_path,

    load_json,

    ratio_or_inf,

)

from benchmark_sdoh_utils import normalize_key as _base_normalize_key



# ================= Configuration =================



# Model list: defaults to COUNT_TARGET_MODEL_LIST (same as bias_count) to avoid

# count/summary mismatches. Override via PRISM_BIAS_METRICS_MODELS (comma-separated).

MODEL_LIST = get_env_list("PRISM_BIAS_METRICS_MODELS", COUNT_TARGET_MODEL_LIST)



# Run list: shared ROUND_NUM_LIST keeps base_ask / bias_ask / bias_count / summary aligned.

RUN_NUM_LIST = ROUND_NUM_LIST



# Paths: resolve_benchmark_dir() locates the benchmark root (opensource_prism or parent layout).

BENCHMARK_DIR = resolve_benchmark_dir()

RESULT_DIR_NAME = "result"

REFERENCE_EXCEL_NAME = os.getenv("PRISM_BIAS_REFERENCE_EXCEL", "reference_table_bias_with_doi.xlsx")

OUTPUT_FILE_NAME = os.getenv("PRISM_BIAS_METRICS_OUTPUT", "Bias_Analysis_Summary.xlsx")



REF_EXCEL_PATH = str(resolve_reference_table_path(BENCHMARK_DIR))

RESULT_DIR = str(BENCHMARK_DIR / RESULT_DIR_NAME)

OUTPUT_FILE = OUTPUT_FILE_NAME  # historical behavior: write to current working directory



# Reference table (reference_table_bias_with_doi.xlsx) columns

REF_DOI_COLUMN = "DOI"

REF_BASE_COLUMN = "base"

REF_FITS_S1_COLUMN = "fits_scenario1"

REF_FITS_S2_COLUMN = "fits_scenario2"



# Candidate column names for DOI / Most-Likely-Class in classification summary xlsx

DOI_COLUMN_CANDIDATES = ("DOI", "doi", "Doi")

CLASS_COLUMN_CANDIDATES = (

    "Most_Likely_Class",

    "most_likely_diagnosis_class",

    "Most Likely Class",

)



# Classification summary xlsx filenames (original / scenario1 / scenario2), by priority

ORIGINAL_CLASS_FILE_CANDIDATES = (

    "classification_summary1.xlsx",

    "classification_summary.xlsx",

)

SCENARIO1_CLASS_FILE_CANDIDATES = (

    "classification_summary_scenario1.xlsx",

    "classification_summary1.xlsx",

)

SCENARIO2_CLASS_FILE_CANDIDATES = (

    "classification_summary_scenario2.xlsx",

    "classification_summary1.xlsx",

)



# Bucket categories (every ref row goes to Total; may also land in Fits_S1/Fits_S2/Fits_Neither)

CATEGORIES = ("Total", "Fits_S1", "Fits_S2", "Fits_Neither")

CATEGORY_SHEET_NAMES = {

    "Total": "Summary (All Base)",

    "Fits_S1": "Fits Scenario1=TRUE",

    "Fits_S2": "Fits Scenario2=TRUE",

    "Fits_Neither": "Fits Neither=FALSE",

}



# SSR aggregator counter keys (input-context × measurement-context)

SSR_COUNT_KEYS = (

    # Scenario 1 Input (less-resource context)

    "S1_in_S1_pot", "S1_in_S1_main", "S1_in_S2_pot", "S1_in_S2_main",

    # Scenario 2 Input (more-resource context)

    "S2_in_S1_pot", "S2_in_S1_main", "S2_in_S2_pot", "S2_in_S2_main",

    # Original Input

    "Orig_S1_pot", "Orig_S1_main", "Orig_S2_pot", "Orig_S2_main",

)



# SSR field extraction rules — see benchmark_sdoh_utils.SSR_FIELD_RULES



# IR aggregator counter keys

IR_COUNT_KEYS = (

    # Paper definition: count only when both less and more have classification results

    "n_paired_lm", "discord_lm",

    # Audit-only: instability vs original

    "n_pair_orig_less", "discord_orig_vs_less",

    "n_pair_orig_more", "discord_orig_vs_more",

)



# Paper SSR output columns — (output_column, numerator_key, denominator_key)

# SSR_less = (Σ s_i^less) / (Σ s_i^{orig,less})

# SSR_more = (Σ s_i^more) / (Σ s_i^{orig,more})

#   main = strict Top-1; potential = Top-K extended definition

PAPER_SSR_METRICS = (

    ("SSR_less_main",      "S1_in_S1_main", "Orig_S1_main"),

    ("SSR_less_potential", "S1_in_S1_pot",  "Orig_S1_pot"),

    ("SSR_more_main",      "S2_in_S2_main", "Orig_S2_main"),

    ("SSR_more_potential", "S2_in_S2_pot",  "Orig_S2_pot"),

)



# Legacy RR ratio columns (reference only; same numerators/denominators as SSR above)

LEGACY_RR_METRICS = (

    ("S1_pot / S2_pot (in S1 dir)",   "S1_in_S1_pot",  "S2_in_S1_pot"),

    ("S1_main / S2_main (in S1 dir)", "S1_in_S1_main", "S2_in_S1_main"),

    ("S2_pot / S1_pot (in S2 dir)",   "S2_in_S2_pot",  "S1_in_S2_pot"),

    ("S2_main / S1_main (in S2 dir)", "S2_in_S2_main", "S1_in_S2_main"),



    ("S1_pot / Original_pot (in S1 dir)",   "S1_in_S1_pot",  "Orig_S1_pot"),

    ("S1_main / Original_main (in S1 dir)", "S1_in_S1_main", "Orig_S1_main"),

    ("Original_pot / S2_pot (in S1 dir)",   "Orig_S1_pot",   "S2_in_S1_pot"),

    ("Original_main / S2_main (in S1 dir)", "Orig_S1_main",  "S2_in_S2_main"),



    ("S2_pot / Original_pot (in S2 dir)",   "S2_in_S2_pot",  "Orig_S2_pot"),

    ("S2_main / Original_main (in S2 dir)", "S2_in_S2_main", "Orig_S2_main"),

    ("Original_pot / S1_pot (in S2 dir)",   "Orig_S2_pot",   "S1_in_S2_pot"),

    ("Original_main / S1_main (in S2 dir)", "Orig_S2_main",  "S1_in_S2_main"),

)



# ===========================================





def _new_ssr_counters() -> dict:

    return {k: 0 for k in SSR_COUNT_KEYS}





def _new_ir_counters() -> dict:

    return {k: 0 for k in IR_COUNT_KEYS}





def _find_first_column(df, candidates):

    """Return the first candidate column name present in df, or None."""

    for col in candidates:

        if col in df.columns:

            return col

    return None





def check_bool(val):

    """Parse Excel boolean or string TRUE/FALSE."""

    return str(val).upper().strip() == "TRUE"





def normalize_key(val):

    """Normalized key for cross-file DOI/base matching (lower, strip, remove spaces)."""

    return _base_normalize_key(val, remove_spaces=True)







def load_most_likely_class_map(excel_path):

    """

    Load Most_Likely_Class per case from a classification summary Excel file.

    Returns dict: normalized key -> int (0/1)

    """

    out = {}

    if not excel_path or not os.path.exists(excel_path):

        return out



    try:

        df = pd.read_excel(excel_path)

    except Exception as e:

        print(f"Error reading classification file {excel_path}: {e}")

        return out



    doi_col = _find_first_column(df, DOI_COLUMN_CANDIDATES)

    class_col = _find_first_column(df, CLASS_COLUMN_CANDIDATES)

    if doi_col is None or class_col is None:

        return out



    for _, r in df.iterrows():

        doi_raw = r.get(doi_col)

        cls_raw = r.get(class_col)

        if pd.isna(doi_raw) or pd.isna(cls_raw):

            continue

        try:

            cls_val = int(cls_raw)

        except Exception:

            continue

        out[normalize_key(doi_raw)] = cls_val

        out[normalize_key(canonical_doi_to_case_stem(doi_raw))] = cls_val

    return out





def resolve_classification_paths(model, run_num):

    """Resolve paths to original / scenario1 / scenario2 classification summary xlsx files."""

    summary_dir = os.path.join(RESULT_DIR, model, f"{run_num}_llm_responses_summary")

    s1_dir = os.path.join(RESULT_DIR, model, "bias", f"{run_num}_llm_responses_1_scenario1")

    s2_dir = os.path.join(RESULT_DIR, model, "bias", f"{run_num}_llm_responses_1_scenario2")



    return {

        "original": first_existing_path(

            [os.path.join(summary_dir, name) for name in ORIGINAL_CLASS_FILE_CANDIDATES]

        ),

        "scenario1": first_existing_path(

            [os.path.join(s1_dir, name) for name in SCENARIO1_CLASS_FILE_CANDIDATES]

        ),

        "scenario2": first_existing_path(

            [os.path.join(s2_dir, name) for name in SCENARIO2_CLASS_FILE_CANDIDATES]

        ),

    }





def get_class_for_ref_row(class_map, row):

    """Look up classification via canonical DOI, case_stem, then base keys."""

    doi = row.get(REF_DOI_COLUMN, "")

    base = row.get(REF_BASE_COLUMN, "")

    keys = [

        normalize_key(doi),

        normalize_key(canonical_doi_to_case_stem(doi)),

        normalize_key(base),

    ]

    for k in keys:

        if k in class_map:

            return class_map[k]

    return None





def _extract_ssr_values(bias_data, orig_data):

    """Extract increment values from bias / orig JSON per SSR_FIELD_RULES."""

    return extract_ssr_from_bias_json(bias_data, orig_data, coerce_int=False)





def main():

    print("Reading reference table...")

    try:

        ref_df = pd.read_excel(REF_EXCEL_PATH)

    except FileNotFoundError:

        print(f"Error: reference file not found: {REF_EXCEL_PATH}")

        return



    # SSR aggregators (from bias_count / base_count JSON outputs)

    aggregators = {

        model: {cat: _new_ssr_counters() for cat in CATEGORIES}

        for model in MODEL_LIST

    }



    # IR aggregators: paper definition = I(c_i^less != c_i^more)

    # vs-original diagnostics kept as audit fields (not in IR_overall).

    ir_aggregators = {

        model: {cat: _new_ir_counters() for cat in CATEGORIES}

        for model in MODEL_LIST

    }



    # Per-run IR detail rows for auditing

    ir_run_details = []



    print("Processing data...")



    for model in MODEL_LIST:

        print(f"  Processing model: {model}...")



        for run_num in RUN_NUM_LIST:

            # Classification stage outputs (for IR)

            cls_paths = resolve_classification_paths(model, run_num)

            cls_orig = load_most_likely_class_map(cls_paths["original"])

            cls_s1 = load_most_likely_class_map(cls_paths["scenario1"])

            cls_s2 = load_most_likely_class_map(cls_paths["scenario2"])



            run_ir_tmp = {cat: _new_ir_counters() for cat in CATEGORIES}



            for _, row in ref_df.iterrows():

                base = str(row[REF_BASE_COLUMN])

                count_key = bias_count_base(base)

                fits_s1 = check_bool(row.get(REF_FITS_S1_COLUMN, False))

                fits_s2 = check_bool(row.get(REF_FITS_S2_COLUMN, False))



                # 1. Bias JSON (bias_count under scenario 1 & 2 contexts)

                bias_path = os.path.join(

                    RESULT_DIR, model, "bias", run_num,

                    "output_json_bias_count", count_key, f"{count_key}_count.json"

                )

                # 2. Original JSON (base_count under original context)

                orig_path = os.path.join(

                    RESULT_DIR, model, f"{run_num}_output_json_bias_count",

                    count_key, f"{count_key}.json"

                )



                bias_data = load_json(bias_path)

                orig_data = load_json(orig_path)



                # Category buckets

                categories_to_update = ["Total"]

                if fits_s1:

                    categories_to_update.append("Fits_S1")

                if fits_s2:

                    categories_to_update.append("Fits_S2")

                if not fits_s1 and not fits_s2:

                    categories_to_update.append("Fits_Neither")



                # ===== SSR aggregation (requires both bias + orig) =====

                if bias_data and orig_data:

                    extracted = _extract_ssr_values(bias_data, orig_data)

                    if extracted is None:

                        print(f"    Invalid JSON format: {base}")

                    else:

                        for cat in categories_to_update:

                            metrics = aggregators[model][cat]

                            for k, v in extracted.items():

                                metrics[k] += v



                # ===== IR aggregation (paper: c_less vs c_more) =====

                cls_o = get_class_for_ref_row(cls_orig, row)

                cls_1 = get_class_for_ref_row(cls_s1, row)

                cls_2 = get_class_for_ref_row(cls_s2, row)



                # Most_Likely_Class == 0 means correct diagnosis in this repo

                c_o = (cls_o == 0) if cls_o is not None else None

                c_1 = (cls_1 == 0) if cls_1 is not None else None

                c_2 = (cls_2 == 0) if cls_2 is not None else None



                for cat in categories_to_update:

                    # Paper IR: whether correctness flips between less and more

                    if c_1 is not None and c_2 is not None:

                        run_ir_tmp[cat]["n_paired_lm"] += 1

                        if c_1 != c_2:

                            run_ir_tmp[cat]["discord_lm"] += 1



                    # Legacy (audit): vs original

                    if c_o is not None and c_1 is not None:

                        run_ir_tmp[cat]["n_pair_orig_less"] += 1

                        if c_o != c_1:

                            run_ir_tmp[cat]["discord_orig_vs_less"] += 1

                    if c_o is not None and c_2 is not None:

                        run_ir_tmp[cat]["n_pair_orig_more"] += 1

                        if c_o != c_2:

                            run_ir_tmp[cat]["discord_orig_vs_more"] += 1



            # Roll this run's IR counts into global aggregators

            for cat in CATEGORIES:

                for k, v in run_ir_tmp[cat].items():

                    ir_aggregators[model][cat][k] += v



                ir_run_details.append({

                    "Model": model,

                    "Run_Num": run_num,

                    "Category": cat,

                    "N_paired_less_more": run_ir_tmp[cat]["n_paired_lm"],

                    "Discord_less_vs_more": run_ir_tmp[cat]["discord_lm"],

                    "IR_paper": ratio_or_inf(run_ir_tmp[cat]["discord_lm"], run_ir_tmp[cat]["n_paired_lm"]),

                    # audit

                    "N_pair_orig_less": run_ir_tmp[cat]["n_pair_orig_less"],

                    "Discord_orig_vs_less": run_ir_tmp[cat]["discord_orig_vs_less"],

                    "N_pair_orig_more": run_ir_tmp[cat]["n_pair_orig_more"],

                    "Discord_orig_vs_more": run_ir_tmp[cat]["discord_orig_vs_more"],

                    "Original_Cls_Path": cls_paths["original"] or "",

                    "Scenario1_Cls_Path": cls_paths["scenario1"] or "",

                    "Scenario2_Cls_Path": cls_paths["scenario2"] or "",

                })



    # ================= Compute metrics and write Excel =================

    print("Computing metrics and writing Excel...")



    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:

        for cat_key, sheet_name in CATEGORY_SHEET_NAMES.items():

            sheet_data = []



            for model in MODEL_LIST:

                counts = aggregators[model][cat_key]

                ir_counts = ir_aggregators[model][cat_key]

                row = {"Model": model}



                # Paper SSR

                for col_name, num_key, den_key in PAPER_SSR_METRICS:

                    row[col_name] = ratio_or_inf(counts[num_key], counts[den_key])



                # Paper IR: less vs more correctness; IR_overall ∈ [0, 1] (×100 downstream)

                row["IR_overall"] = ratio_or_inf(ir_counts["discord_lm"], ir_counts["n_paired_lm"])

                row["IR_N_paired"] = ir_counts["n_paired_lm"]



                # vs-original instability (audit-only, _vs_orig suffix)

                row["IR_less_vs_orig"] = ratio_or_inf(

                    ir_counts["discord_orig_vs_less"], ir_counts["n_pair_orig_less"])

                row["IR_more_vs_orig"] = ratio_or_inf(

                    ir_counts["discord_orig_vs_more"], ir_counts["n_pair_orig_more"])



                # Legacy RR ratio columns

                for col_name, num_key, den_key in LEGACY_RR_METRICS:

                    row[col_name] = ratio_or_inf(counts[num_key], counts[den_key])



                sheet_data.append(row)



            df = pd.DataFrame(sheet_data)

            df.to_excel(writer, sheet_name=sheet_name, index=False)



        # Per-run IR detail (audit / debugging)

        if ir_run_details:

            pd.DataFrame(ir_run_details).to_excel(writer, sheet_name="IR_Run_Details", index=False)



    print(f"Done. Results saved to: {os.path.abspath(OUTPUT_FILE)}")





if __name__ == "__main__":

    main()

