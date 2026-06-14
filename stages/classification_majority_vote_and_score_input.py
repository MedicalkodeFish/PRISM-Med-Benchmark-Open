import _bootstrap  # noqa: F401
import os
from pathlib import Path
import numpy as np
import pandas as pd
from benchmark_sdoh_utils import (
    build_class_map_from_dir,
    canonical_doi_to_case_stem,
    classification_safe_mode as safe_mode,
    first_existing_path,
    normalize_key,
)
from benchmark_column_names import (
    COL_BASE_ACCURACY,
    COL_COVERAGE,
    COL_FILENAME,
    COL_MOST_LIKELY_DIAGNOSIS,
    COL_MODEL_CANONICAL_NAME,
    COL_POSSIBLE_DIAGNOSES,
)
from legacy_script_config import (
    ROUND_NUM_LIST,
    resolve_benchmark_dir,
    resolve_reference_table_path,
)
from sdoh_ref_metrics import bias_summary_matches_ref


MODEL_LIST = []  # Empty means auto-discover models under benchmark/result.
RUN_NUM_LIST = ROUND_NUM_LIST


def pick_existing(candidates):
    return first_existing_path(candidates)


def resolve_round_dirs(model, run_num):
    original = pick_existing([
        os.path.join(RESULT_DIR, model, f"{run_num}_llm_responses_summary"),
    ])
    scenario1 = pick_existing([
        os.path.join(RESULT_DIR, model, "bias", f"{run_num}_llm_responses_1_scenario1"),
    ])
    scenario2 = pick_existing([
        os.path.join(RESULT_DIR, model, "bias", f"{run_num}_llm_responses_1_scenario2"),
    ])
    return {"original": original, "scenario1": scenario1, "scenario2": scenario2}


def resolve_model_list(result_dir: Path):
    if MODEL_LIST:
        return MODEL_LIST
    if not result_dir.exists():
        return []
    out = []
    for p in result_dir.iterdir():
        if not p.is_dir():
            continue
        # Treat as an evaluated model when any round output exists.
        if any((p / f"{r}_output_json").exists() or (p / "bias" / r / "output_json").exists() for r in RUN_NUM_LIST):
            out.append(p.name)
    return sorted(out)


def metric_from_case_df(df):
    if df.empty:
        return 0.0, 0.0
    acc = (df["Most_Likely_Class"] == 0).mean()
    cov = df["Potential_Class"].isin([0, 1]).mean()
    return float(acc), float(cov)


def load_bias_summary():
    if not os.path.exists(BIAS_SUMMARY_PATH):
        return {}
    try:
        xls = pd.ExcelFile(BIAS_SUMMARY_PATH)
        target_sheet = "Summary (All Base)" if "Summary (All Base)" in xls.sheet_names else xls.sheet_names[0]
        df = pd.read_excel(BIAS_SUMMARY_PATH, sheet_name=target_sheet)
    except Exception:
        return {}

    out = {}
    for _, r in df.iterrows():
        model = str(r.get("Model", "")).strip()
        if not model:
            continue
        out[model] = {
            "SDoH_IR": r.get("IR_overall", np.nan) * 100 if pd.notna(r.get("IR_overall", np.nan)) else np.nan,
            "SDoH_SSR_less": r.get("SSR_less_main", np.nan),
            "SDoH_SSR_more": r.get("SSR_more_main", np.nan),
        }
    return out


def load_high_severity_rate(benchmark_dir: Path):
    # Load 3-round flaws summary and average by model.
    rates = {}
    counts = {}
    for run_num in RUN_NUM_LIST:
        p = benchmark_dir / f"{run_num}_flaws_summary.xlsx"
        if not p.exists():
            continue
        try:
            xls = pd.ExcelFile(str(p))
        except Exception:
            continue
        for sheet in xls.sheet_names:
            if sheet in ("All Data", "Summary"):
                continue
            try:
                df = pd.read_excel(str(p), sheet_name=sheet)
            except Exception:
                continue
            if "High Severity Count" not in df.columns:
                continue
            if df.empty:
                continue
            rate = (df["High Severity Count"] > 0).mean()
            rates[sheet] = rates.get(sheet, 0.0) + float(rate)
            counts[sheet] = counts.get(sheet, 0) + 1
    return {m: rates[m] / counts[m] for m in rates}


def main():
    benchmark_dir = resolve_benchmark_dir()
    result_dir = benchmark_dir / "result"
    ref_path = resolve_reference_table_path(benchmark_dir)
    bias_summary_path = Path.cwd() / "Bias_Analysis_Summary.xlsx"

    caselevel_out = benchmark_dir / "classification_voted_caselevel.xlsx"
    model_metrics_out = benchmark_dir / "classification_voted_metrics.xlsx"
    score_input_out = benchmark_dir / "benchmark_score_inputs.xlsx"

    global RESULT_DIR, REF_PATH, BIAS_SUMMARY_PATH
    RESULT_DIR = str(result_dir)
    REF_PATH = str(ref_path)
    BIAS_SUMMARY_PATH = str(bias_summary_path)

    if not ref_path.exists():
        raise FileNotFoundError(f"Missing reference sheet: {REF_PATH}")
    ref_df = pd.read_excel(ref_path)
    if "DOI" not in ref_df.columns:
        raise ValueError("Reference sheet is missing DOI column.")

    case_rows = []
    model_rows = []

    bias_map = load_bias_summary()
    high_sev_map = load_high_severity_rate(benchmark_dir)

    models = resolve_model_list(result_dir)
    if not models:
        raise RuntimeError(f"No usable model directories found in {result_dir}")

    for model in models:
        by_source = {"original": {}, "scenario1": {}, "scenario2": {}}
        for run_num in RUN_NUM_LIST:
            dirs = resolve_round_dirs(model, run_num)
            maps = {src: build_class_map_from_dir(path, require_potential=True) for src, path in dirs.items()}
            for _, rr in ref_df.iterrows():
                doi = rr.get("DOI")
                if pd.isna(doi):
                    continue
                k1 = normalize_key(doi)
                k2 = normalize_key(canonical_doi_to_case_stem(doi))
                for src in ("original", "scenario1", "scenario2"):
                    hit = maps[src].get(k1) or maps[src].get(k2)
                    if hit:
                        by_source[src].setdefault(k1, {"ml": [], "pc": [], "doi": doi})
                        by_source[src][k1]["ml"].append(hit["Most_Likely_Class"])
                        by_source[src][k1]["pc"].append(hit["Potential_Class"])

        voted = {"original": [], "scenario1": [], "scenario2": []}
        for src in ("original", "scenario1", "scenario2"):
            for k, v in by_source[src].items():
                ml = safe_mode(v["ml"])
                pc = safe_mode(v["pc"])
                if ml is None or pc is None:
                    continue
                voted[src].append({
                    "Model": model,
                    "DOI": v["doi"],
                    "Source": src,
                    "Most_Likely_Class": ml,
                    "Potential_Class": pc,
                })
                case_rows.append(voted[src][-1])

        df_o = pd.DataFrame(voted["original"])
        df_l = pd.DataFrame(voted["scenario1"])
        df_m = pd.DataFrame(voted["scenario2"])
        acc_o, cov_o = metric_from_case_df(df_o)
        acc_l, cov_l = metric_from_case_df(df_l)
        acc_m, cov_m = metric_from_case_df(df_m)

        # IR for composite score: same aggregation as net change — 3-round vote per DOI,
        # then compare less (scenario1) vs more (scenario2) Top1 correctness (class==0).
        ir_num = 0
        ir_den = 0
        if not df_l.empty and not df_m.empty:
            l = df_l.set_index("DOI")["Most_Likely_Class"]
            m = df_m.set_index("DOI")["Most_Likely_Class"]
            common = l.index.intersection(m.index)
            if len(common) > 0:
                cl = (l.loc[common] == 0)
                cm = (m.loc[common] == 0)
                ir_num = int((cl != cm).sum())
                ir_den = len(common)
        ir_val = (ir_num / ir_den * 100.0) if ir_den > 0 else np.nan
        sdoh_ir = ir_val

        bm = bias_map.get(model, {})
        ref_n = len(ref_df)
        if bm and bias_summary_matches_ref(
            BIAS_SUMMARY_PATH, model, ref_n, run_num_list=RUN_NUM_LIST
        ):
            sdoh_ssr_less = bm.get("SDoH_SSR_less", np.nan)
            sdoh_ssr_more = bm.get("SDoH_SSR_more", np.nan)
            print(
                f"[vote] {model} SDoH IR for score={sdoh_ir:.4g}% (vote discord={ir_num}/{ir_den}); "
                f"SSR from Bias_Analysis_Summary"
            )
        else:
            sdoh_ssr_less = bm.get("SDoH_SSR_less", np.nan) if bm else np.nan
            sdoh_ssr_more = bm.get("SDoH_SSR_more", np.nan) if bm else np.nan
            if bm and not bias_summary_matches_ref(
                BIAS_SUMMARY_PATH, model, ref_n, run_num_list=RUN_NUM_LIST
            ):
                print(
                    f"[vote] {model} SDoH IR for score={sdoh_ir:.4g}% (vote); "
                    f"Bias_Analysis IR_N_paired={bm.get('IR_N_paired', 'n/a')} "
                    f"out of ref scope ({ref_n} cases) — not used for score"
                )
            elif bm:
                print(
                    f"[vote] {model} SDoH IR for score={sdoh_ir:.4g}% (vote discord={ir_num}/{ir_den}); "
                    f"SSR from Bias_Analysis_Summary (partial match)"
                )
            else:
                print(
                    f"[vote] {model} SDoH IR for score={sdoh_ir:.4g}% (vote discord={ir_num}/{ir_den}); "
                    f"Bias_Analysis_Summary missing — SSR may be NaN"
                )

        model_rows.append({
            COL_MODEL_CANONICAL_NAME: model,
            COL_BASE_ACCURACY: acc_o,
            COL_COVERAGE: cov_o,
            "SDoH_less_top1acc": acc_l,
            "SDoH_less_top5cov": cov_l,
            "SDoH_more_top1acc": acc_m,
            "SDoH_more_top5cov": cov_m,
            "SDoH_Net_change_less_top1acc": (acc_l - acc_o) * 100,
            "SDoH_Net_change_less_top5cov": (cov_l - cov_o) * 100,
            "SDoH_Net_change_more_top1acc": (acc_m - acc_o) * 100,
            "SDoH_Net_change_more_top5cov": (cov_m - cov_o) * 100,
            "SDoH_IR": sdoh_ir,
            "SDoH_SSR_less": sdoh_ssr_less,
            "SDoH_SSR_more": sdoh_ssr_more,
            "High_Severity_Rate": high_sev_map.get(model, np.nan),
        })

    os.makedirs(benchmark_dir, exist_ok=True)
    pd.DataFrame(case_rows).to_excel(caselevel_out, index=False)
    df_model = pd.DataFrame(model_rows)
    df_model.to_excel(model_metrics_out, index=False)
    df_model.to_excel(score_input_out, index=False)
    print(f"Output written: {caselevel_out}")
    print(f"Output written: {model_metrics_out}")
    print(f"Output written: {score_input_out}")


if __name__ == "__main__":
    main()
