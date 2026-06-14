# -*- coding: utf-8 -*-
"""
Multi-sheet Excel audit export: diagnostic performance, reasoning reliability, SDoH-bias,
and composite score calculation steps (for verification / debugging).
"""
from __future__ import annotations

import _bootstrap  # noqa: F401

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from benchmark_sdoh_utils import (
    SSR_FIELD_RULES,
    bias_count_base,
    canonical_doi_to_case_stem,
    extract_ssr_from_bias_json,
    load_json,
    normalize_key,
    safe_div,
)
from benchmark_column_names import (
    COL_BASE_ACCURACY,
    COL_COVERAGE,
    COL_MODEL_CANONICAL_NAME,
    normalize_score_input_columns,
)
from compute_composite_benchmark_score import compute_score_row_detailed
from legacy_script_config import ROUND_NUM_LIST, resolve_benchmark_dir, resolve_reference_table_path

ROUND_LIST = list(ROUND_NUM_LIST)

_load_json = load_json
_bias_base = bias_count_base
_extract_ssr = extract_ssr_from_bias_json


def _sheet_index_rows() -> pd.DataFrame:
    rows = [
        ("00_Index", "Index and sheet map"),
        ("01_ref_scope", "Reference table reference_table_bias_with_doi.xlsx (scoped DOIs)"),
        ("02_class_voted", "Case-level voted classification: classification_voted_caselevel.xlsx"),
        ("03_class_by_round", "Per-round, per-context raw classification JSON detail (audit)"),
        ("04_diag_performance", "Diagnostic performance: original per-case + model accuracy/coverage"),
        ("05_reasoning_cases", "Reasoning reliability: per-round flaws_summary JSON summaries"),
        ("06_reasoning_high_sev", "High_Severity_Rate breakdown (per-round flaws summary xlsx)"),
        ("07_sdoh_ir", "SDoH IR: whether less vs more Top-1 correctness flips"),
        ("08_sdoh_ssr_counts", "SDoH SSR: bias_count vs base_count counts (per case, per round)"),
        ("09_sdoh_net_change", "Net change four columns and acc/cov vs original"),
        ("10_sdoh_sources", "IR/SSR written to score_inputs vs ref recompute vs Bias_Analysis_Summary"),
        ("11_score_inputs", "Copy of benchmark_score_inputs.xlsx"),
        ("12_composite_audit", "Composite score step-by-step (weights, intermediates, subscores)"),
        ("13_scores_output", "Copy of benchmark_scores_output.xlsx (if present)"),
    ]
    return pd.DataFrame(rows, columns=["Sheet", "Description"])


def _ref_doi_set(ref_df: pd.DataFrame) -> Set[str]:
    if ref_df.empty or "DOI" not in ref_df.columns:
        return set()
    return {normalize_key(d) for d in ref_df["DOI"].dropna().astype(str)}


def _case_files_from_ref(ref_df: pd.DataFrame) -> List[str]:
    if ref_df.empty:
        return []
    if "base" in ref_df.columns:
        return [f"{str(b).strip()}.json" for b in ref_df["base"].dropna()]
    return []


def _collect_class_by_round(res: Path, model: str, ref_dois: Set[str]) -> pd.DataFrame:
    rows: List[dict] = []
    sources = {
        "original": lambda r: res / model / f"{r}_llm_responses_summary",
        "scenario1": lambda r: res / model / "bias" / f"{r}_llm_responses_1_scenario1",
        "scenario2": lambda r: res / model / "bias" / f"{r}_llm_responses_1_scenario2",
    }
    for run in ROUND_LIST:
        for src, dir_fn in sources.items():
            d = dir_fn(run)
            if not d.exists():
                continue
            for fp in sorted(d.glob("*_classification.json")):
                data = load_json(fp) or {}
                doi = data.get("DOI")
                if ref_dois and doi is not None:
                    if normalize_key(str(doi)) not in ref_dois and normalize_key(canonical_doi_to_case_stem(doi)) not in ref_dois:
                        continue
                ml = data.get("most_likely_diagnosis_class")
                pc = data.get("potential_diagnoses_class")
                rows.append({
                    "Model": model,
                    "Round": run,
                    "Source": src,
                    "DOI": doi,
                    "Most_Likely_Class": ml,
                    "Potential_Class": pc,
                    "Top1_Correct": (ml == 0) if ml is not None else None,
                    "Top5_Covered": (pc in (0, 1)) if pc is not None else None,
                    "Json_Path": str(fp),
                })
    return pd.DataFrame(rows)


def _collect_diag_performance(caselevel: pd.DataFrame, models: List[str]) -> pd.DataFrame:
    rows: List[dict] = []
    for model in models:
        for src in ("original", "scenario1", "scenario2"):
            sub = caselevel[
                (caselevel["Model"].astype(str) == model) & (caselevel["Source"].astype(str) == src)
            ] if not caselevel.empty else pd.DataFrame()
            for _, r in sub.iterrows():
                ml, pc = r.get("Most_Likely_Class"), r.get("Potential_Class")
                rows.append({
                    "Model": model,
                    "Source": src,
                    "DOI": r.get("DOI"),
                    "Most_Likely_Class": ml,
                    "Potential_Class": pc,
                    "Top1_Correct": ml == 0,
                    "Top5_Covered": pc in (0, 1),
                })
        o = caselevel[
            (caselevel["Model"].astype(str) == model) & (caselevel["Source"].astype(str) == "original")
        ] if not caselevel.empty else pd.DataFrame()
        if not o.empty:
            acc = (o["Most_Likely_Class"] == 0).mean()
            cov = o["Potential_Class"].isin([0, 1]).mean()
            rows.append({
                "Model": model,
                "Source": "_model_summary_original",
                "DOI": f"n_cases={len(o)}",
                "Most_Likely_Class": None,
                "Potential_Class": None,
                "Top1_Correct": acc,
                "Top5_Covered": cov,
                "Metric": "base_accuracy=mean(Top1_Correct); coverage=mean(Top5_Covered)",
            })
    return pd.DataFrame(rows)


def _collect_reasoning_cases(res: Path, models: List[str], ref_basenames: Set[str]) -> pd.DataFrame:
    rows: List[dict] = []
    for model in models:
        for run in ROUND_LIST:
            d = res / model / f"{run}_flaws_summary"
            if not d.exists():
                continue
            for fp in sorted(d.glob("*_flaws_summary.json")):
                stem = fp.name.replace("_flaws_summary.json", "")
                if ref_basenames and stem not in ref_basenames:
                    continue
                data = load_json(fp) or {}
                rows.append({
                    "Model": model,
                    "Round": run,
                    "Case_ID": stem,
                    "Rating": data.get("rating") or data.get("Rating"),
                    "Total_Hallucinations": data.get("total_hallucinations") or data.get("Total Hallucinations"),
                    "High_Severity_Count": data.get("high_severity_count") or data.get("High Severity Count"),
                    "Audit_Summary": (data.get("audit_summary") or data.get("Audit Summary") or "")[:500],
                    "Json_Path": str(fp),
                })
    return pd.DataFrame(rows)


def _collect_high_sev_detail(bench: Path, models: List[str]) -> pd.DataFrame:
    rows: List[dict] = []
    for run in ROUND_LIST:
        p = bench / f"{run}_flaws_summary.xlsx"
        if not p.exists():
            continue
        try:
            xls = pd.ExcelFile(p)
        except Exception:
            continue
        for sheet in xls.sheet_names:
            if sheet in ("All Data", "Summary"):
                continue
            if models and sheet not in models:
                continue
            try:
                df = pd.read_excel(p, sheet_name=sheet)
            except Exception:
                continue
            if "High Severity Count" not in df.columns:
                continue
            for _, r in df.iterrows():
                h = r.get("High Severity Count", 0)
                rows.append({
                    "Round": run,
                    "Model_Sheet": sheet,
                    "Case_ID": r.get("Case ID"),
                    "High_Severity_Count": h,
                    "Has_High_Severity": int(h) > 0 if pd.notna(h) else False,
                })
    out = pd.DataFrame(rows)
    if not out.empty and "Model_Sheet" in out.columns:
        for ms, g in out.groupby("Model_Sheet"):
            rows.append({
                "Round": "_avg_for_High_Severity_Rate",
                "Model_Sheet": ms,
                "Case_ID": f"n={len(g)}",
                "High_Severity_Count": None,
                "Has_High_Severity": g["Has_High_Severity"].mean(),
            })
    return pd.DataFrame(rows)


def _collect_sdoh_ir(caselevel: pd.DataFrame, models: List[str]) -> pd.DataFrame:
    rows: List[dict] = []
    for model in models:
        if caselevel.empty:
            continue
        s1 = caselevel[(caselevel["Model"].astype(str) == model) & (caselevel["Source"] == "scenario1")]
        s2 = caselevel[(caselevel["Model"].astype(str) == model) & (caselevel["Source"] == "scenario2")]
        o = caselevel[(caselevel["Model"].astype(str) == model) & (caselevel["Source"] == "original")]
        dois = set(s1["DOI"].astype(str)) & set(s2["DOI"].astype(str))
        discord = 0
        for doi in sorted(dois):
            r1 = s1[s1["DOI"].astype(str) == doi].iloc[0]
            r2 = s2[s2["DOI"].astype(str) == doi].iloc[0]
            c1 = r1["Most_Likely_Class"] == 0
            c2 = r2["Most_Likely_Class"] == 0
            flipped = c1 != c2
            if flipped:
                discord += 1
            ro = o[o["DOI"].astype(str) == doi]
            orig_ok = ro.iloc[0]["Most_Likely_Class"] == 0 if not ro.empty else None
            rows.append({
                "Model": model,
                "DOI": doi,
                "Original_Top1_Correct": orig_ok,
                "Less_Scenario1_Top1_Correct": c1,
                "More_Scenario2_Top1_Correct": c2,
                "Correctness_Flipped_IR": flipped,
            })
        n = len(dois)
        rows.append({
            "Model": model,
            "DOI": "_summary",
            "Original_Top1_Correct": None,
            "Less_Scenario1_Top1_Correct": None,
            "More_Scenario2_Top1_Correct": None,
            "Correctness_Flipped_IR": f"{discord}/{n} -> IR%={discord/n*100 if n else 'nan'}",
        })
    return pd.DataFrame(rows)


def _collect_ssr_counts(res: Path, models: List[str], ref_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[dict] = []
    if ref_df.empty or "base" not in ref_df.columns:
        return pd.DataFrame(rows)
    for model in models:
        for _, ref_row in ref_df.iterrows():
            base = _bias_base(str(ref_row["base"]).strip())
            doi = ref_row.get("DOI")
            for run in ROUND_LIST:
                bias_p = res / model / "bias" / run / "output_json_bias_count" / base / f"{base}_count.json"
                orig_p = res / model / f"{run}_output_json_bias_count" / base / f"{base}.json"
                bias_d = _load_json(bias_p)
                orig_d = _load_json(orig_p)
                entry = {"Model": model, "Round": run, "base": base, "DOI": doi}
                if not bias_d or not orig_d:
                    entry["status"] = "missing_json"
                    rows.append(entry)
                    continue
                ext = _extract_ssr(bias_d, orig_d)
                if not ext:
                    entry["status"] = "parse_error"
                    rows.append(entry)
                    continue
                entry["status"] = "ok"
                entry.update(ext)
                rows.append(entry)
    return pd.DataFrame(rows)


def _collect_net_change(score_in: pd.DataFrame) -> pd.DataFrame:
    if score_in.empty:
        return score_in
    cols = [c for c in score_in.columns if "Net_change" in c or "SDoH_less" in c or "SDoH_more" in c or c in (
        COL_MODEL_CANONICAL_NAME, COL_BASE_ACCURACY, COL_COVERAGE,
        "模型标准名", "基础准确率", "覆盖率",
    )]
    df = score_in[cols].copy() if cols else score_in.copy()
    note = pd.DataFrame([{
        COL_MODEL_CANONICAL_NAME: "(formula)",
        "SDoH_Net_change_less_top1acc": "(acc_scenario1 - acc_original)*100",
        "SDoH_Net_change_more_top1acc": "(acc_scenario2 - acc_original)*100",
        "SDoH_Net_change_less_top5cov": "(cov_scenario1 - cov_original)*100",
        "SDoH_Net_change_more_top5cov": "(cov_scenario2 - cov_original)*100",
    }])
    return pd.concat([note, df], ignore_index=True)


def _collect_sdoh_sources(
    score_in: pd.DataFrame,
    models: List[str],
    ir_ref: pd.DataFrame,
    ssr_df: pd.DataFrame,
    bias_summary_path: Path,
) -> pd.DataFrame:
    rows: List[dict] = []
    bias_rows = {}
    if bias_summary_path.exists():
        try:
            xls = pd.ExcelFile(bias_summary_path)
            sh = "Summary (All Base)" if "Summary (All Base)" in xls.sheet_names else xls.sheet_names[0]
            bdf = pd.read_excel(bias_summary_path, sheet_name=sh)
            for _, r in bdf.iterrows():
                bias_rows[str(r.get("Model", "")).strip()] = r.to_dict()
        except Exception:
            pass

    for model in models:
        si = {}
        if not score_in.empty:
            norm = normalize_score_input_columns(score_in)
            if COL_MODEL_CANONICAL_NAME in norm.columns:
                hit = norm[norm[COL_MODEL_CANONICAL_NAME].astype(str) == model]
                if not hit.empty:
                    si = hit.iloc[0].to_dict()
        ir_sum = ir_ref[(ir_ref["Model"] == model) & (ir_ref["DOI"] == "_summary")]
        ssr_sub = ssr_df[ssr_df["Model"] == model] if not ssr_df.empty else pd.DataFrame()
        ssr_tot = {k: 0 for k, _, _ in SSR_FIELD_RULES}
        for _, r in ssr_sub.iterrows():
            if r.get("status") != "ok":
                continue
            for k, _, _ in SSR_FIELD_RULES:
                ssr_tot[k] += int(r.get(k, 0) or 0)

        ref_ir = ir_sum.iloc[0]["Correctness_Flipped_IR"] if not ir_sum.empty else ""
        ref_ssr_less = safe_div(ssr_tot["S1_in_S1_main"], ssr_tot["Orig_S1_main"])
        ref_ssr_more = safe_div(ssr_tot["S2_in_S2_main"], ssr_tot["Orig_S2_main"])
        ref_ssr_less_pot = safe_div(ssr_tot["S1_in_S1_pot"], ssr_tot["Orig_S1_pot"])
        ref_ssr_more_pot = safe_div(ssr_tot["S2_in_S2_pot"], ssr_tot["Orig_S2_pot"])
        bs = bias_rows.get(model, {})
        rows.append({
            "Model": model,
            "In_score_inputs_SDoH_IR_pct": si.get("SDoH_IR"),
            "In_score_inputs_SSR_less": si.get("SDoH_SSR_less"),
            "In_score_inputs_SSR_more": si.get("SDoH_SSR_more"),
            "Ref_scope_IR_note": ref_ir,
            "Ref_scope_SSR_less_main": ref_ssr_less,
            "Ref_scope_SSR_more_main": ref_ssr_more,
            "Ref_scope_SSR_less_potential": ref_ssr_less_pot,
            "Ref_scope_SSR_more_potential": ref_ssr_more_pot,
            "Bias_Analysis_IR_overall": bs.get("IR_overall"),
            "Bias_Analysis_IR_N_paired": bs.get("IR_N_paired"),
            "Bias_Analysis_SSR_less_main": bs.get("SSR_less_main"),
            "Bias_Analysis_SSR_more_main": bs.get("SSR_more_main"),
            "Bias_Analysis_SSR_less_potential": bs.get("SSR_less_potential"),
            "Bias_Analysis_SSR_more_potential": bs.get("SSR_more_potential"),
            "Note": "Score SSR uses Top-1 (main) per paper; potential columns are audit-only",
        })
    return pd.DataFrame(rows)


def write_benchmark_audit_workbook(
    *,
    legacy_root: Optional[Path] = None,
    model_ids: Optional[List[str]] = None,
    case_files: Optional[List[str]] = None,
    output_path: Optional[Path] = None,
    verification_checks: Optional[List[dict]] = None,
) -> Path:
    legacy_root = legacy_root or resolve_benchmark_dir().parent
    bench = legacy_root / "benchmark"
    res = bench / "result"
    ref_path = resolve_reference_table_path(bench)
    ref_df = pd.read_excel(ref_path) if ref_path.exists() else pd.DataFrame()

    if model_ids is None:
        model_ids = []
        if res.exists():
            for p in sorted(res.iterdir()):
                if p.is_dir() and not p.name.startswith("_"):
                    if any((p / f"{r}_output_json").exists() for r in ROUND_LIST):
                        model_ids.append(p.name)
    if not model_ids:
        model_ids = ["(none)"]

    ref_dois = _ref_doi_set(ref_df)
    ref_basenames = {c.replace(".json", "") for c in (case_files or _case_files_from_ref(ref_df))}

    caselevel_path = bench / "classification_voted_caselevel.xlsx"
    score_in_path = bench / "benchmark_score_inputs.xlsx"
    score_out_path = bench / "benchmark_scores_output.xlsx"
    caselevel = pd.read_excel(caselevel_path) if caselevel_path.exists() else pd.DataFrame()
    score_in = normalize_score_input_columns(pd.read_excel(score_in_path)) if score_in_path.exists() else pd.DataFrame()
    score_out = pd.read_excel(score_out_path) if score_out_path.exists() else pd.DataFrame()

    composite_audit = pd.DataFrame()
    if not score_in.empty:
        composite_audit = score_in.apply(compute_score_row_detailed, axis=1)

    out_path = output_path or (bench / "benchmark_audit_workbook.xlsx")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = pd.DataFrame([
        {"Key": "generated_at_utc", "Value": datetime.now(timezone.utc).isoformat()},
        {"Key": "legacy_root", "Value": str(legacy_root)},
        {"Key": "models", "Value": ",".join(model_ids)},
        {"Key": "ref_rows", "Value": len(ref_df)},
    ])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        _sheet_index_rows().to_excel(writer, sheet_name="00_Index", index=False)
        meta.to_excel(writer, sheet_name="00_Meta", index=False)
        if not ref_df.empty:
            ref_df.to_excel(writer, sheet_name="01_ref_scope", index=False)
        if not caselevel.empty:
            caselevel.to_excel(writer, sheet_name="02_class_voted", index=False)

        class_round = pd.concat(
            [_collect_class_by_round(res, m, ref_dois) for m in model_ids if m != "(none)"],
            ignore_index=True,
        )
        class_round.to_excel(writer, sheet_name="03_class_by_round", index=False)

        _collect_diag_performance(caselevel, [m for m in model_ids if m != "(none)"]).to_excel(
            writer, sheet_name="04_diag_performance", index=False
        )

        _collect_reasoning_cases(res, [m for m in model_ids if m != "(none)"], ref_basenames).to_excel(
            writer, sheet_name="05_reasoning_cases", index=False
        )
        _collect_high_sev_detail(bench, [m for m in model_ids if m != "(none)"]).to_excel(
            writer, sheet_name="06_reasoning_high_sev", index=False
        )

        ir_df = _collect_sdoh_ir(caselevel, [m for m in model_ids if m != "(none)"])
        ir_df.to_excel(writer, sheet_name="07_sdoh_ir", index=False)

        ssr_df = _collect_ssr_counts(res, [m for m in model_ids if m != "(none)"], ref_df)
        ssr_df.to_excel(writer, sheet_name="08_sdoh_ssr_counts", index=False)

        _collect_net_change(score_in).to_excel(writer, sheet_name="09_sdoh_net_change", index=False)

        _collect_sdoh_sources(
            score_in,
            [m for m in model_ids if m != "(none)"],
            ir_df,
            ssr_df,
            legacy_root / "Bias_Analysis_Summary.xlsx",
        ).to_excel(writer, sheet_name="10_sdoh_sources", index=False)

        if not score_in.empty:
            score_in.to_excel(writer, sheet_name="11_score_inputs", index=False)
        if not composite_audit.empty:
            composite_audit.to_excel(writer, sheet_name="12_composite_audit", index=False)
        if not score_out.empty:
            score_out.to_excel(writer, sheet_name="13_scores_output", index=False)
        if verification_checks:
            pd.DataFrame(verification_checks).to_excel(writer, sheet_name="14_verification", index=False)

    return out_path


if __name__ == "__main__":
    p = write_benchmark_audit_workbook()
    print(f"Wrote {p}")
