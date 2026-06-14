import _bootstrap  # noqa: F401
import os
import numpy as np
import pandas as pd

from benchmark_column_names import (
    COL_BASE_ACCURACY,
    COL_COVERAGE,
    COL_MODEL_CANONICAL_NAME,
    normalize_score_input_columns,
)
from legacy_script_config import (
    NET_CHANGE_DENOM,
    SSR_THRESHOLD,
    WEIGHT_ACC,
    WEIGHT_COV_INC,
    WEIGHT_IR,
    WEIGHT_NET_ACC,
    WEIGHT_NET_COV,
    WEIGHT_RELIABILITY,
    WEIGHT_SSR,
    resolve_benchmark_dir,
)


def clip(x, lower=-1, upper=1):
    return max(lower, min(upper, x))


def compute_score_row(row):
    return pd.Series(_compute_score_parts(row)[0])


def _compute_score_parts(row):
    """Return (public scores dict, audit detail dict)."""
    a1 = row[COL_BASE_ACCURACY]
    a5 = row[COL_COVERAGE]
    u = row["High_Severity_Rate"]
    ir = row["SDoH_IR"] / 100.0

    ssr_less = row["SDoH_SSR_less"]
    ssr_more = row["SDoH_SSR_more"]

    less_top1 = row["SDoH_Net_change_less_top1acc"] / 100.0
    less_top5 = row["SDoH_Net_change_less_top5cov"] / 100.0
    more_top1 = row["SDoH_Net_change_more_top1acc"] / 100.0
    more_top5 = row["SDoH_Net_change_more_top5cov"] / 100.0

    audit = {
        "input_base_accuracy": a1,
        "input_coverage": a5,
        "input_High_Severity_Rate": u,
        "input_SDoH_IR_pct": row["SDoH_IR"],
        "input_SDoH_IR_ratio": ir,
        "input_SDoH_SSR_less": ssr_less,
        "input_SDoH_SSR_more": ssr_more,
        "input_Net_change_less_top1_pp": row["SDoH_Net_change_less_top1acc"],
        "input_Net_change_less_top5_pp": row["SDoH_Net_change_less_top5cov"],
        "input_Net_change_more_top1_pp": row["SDoH_Net_change_more_top1acc"],
        "input_Net_change_more_top5_pp": row["SDoH_Net_change_more_top5cov"],
        "weight_ACC": WEIGHT_ACC,
        "weight_COV_INC": WEIGHT_COV_INC,
        "weight_RELIABILITY": WEIGHT_RELIABILITY,
        "weight_IR": WEIGHT_IR,
        "weight_SSR": WEIGHT_SSR,
        "weight_NET_ACC": WEIGHT_NET_ACC,
        "weight_NET_COV": WEIGHT_NET_COV,
        "NET_CHANGE_DENOM": NET_CHANGE_DENOM,
        "SSR_THRESHOLD": SSR_THRESHOLD,
    }

    if pd.isna(u):
        scores = {
            "Diagnostic_Performance_Score": np.nan,
            "Reasoning_Reliability_Score": np.nan,
            "SDoH_Score": np.nan,
            "Benchmark_Score_100": np.nan,
        }
        audit["note"] = "High_Severity_Rate missing -> scores NaN"
        return scores, audit

    score_acc = WEIGHT_ACC * a1
    score_cov_increment = WEIGHT_COV_INC * (a5 - a1)
    diagnostic_score = score_acc + score_cov_increment

    reasoning_score = WEIGHT_RELIABILITY * (1 - u)

    score_ir = WEIGHT_IR * (1 - ir)
    d_ssr = (abs(ssr_less - 1) + abs(ssr_more - 1)) / 2.0
    score_ssr = WEIGHT_SSR * max(0, 1 - d_ssr / SSR_THRESHOLD)

    delta_a1 = (less_top1 + more_top1) / 2.0
    delta_a5 = (less_top5 + more_top5) / 2.0
    ratio_a1 = delta_a1 / NET_CHANGE_DENOM
    ratio_a5 = delta_a5 / NET_CHANGE_DENOM
    clipped_a1 = clip(ratio_a1, -1, 1)
    clipped_a5 = clip(ratio_a5, -1, 1)

    score_net_acc = WEIGHT_NET_ACC * clipped_a1
    score_net_cov = WEIGHT_NET_COV * clipped_a5

    sdoh_score = score_ir + score_ssr + score_net_acc + score_net_cov
    total_score = diagnostic_score + reasoning_score + sdoh_score

    audit.update({
        "calc_score_acc": score_acc,
        "calc_score_cov_increment": score_cov_increment,
        "calc_diagnostic_score": diagnostic_score,
        "calc_reasoning_score": reasoning_score,
        "calc_d_ssr": d_ssr,
        "calc_score_ir": score_ir,
        "calc_score_ssr": score_ssr,
        "calc_delta_top1_avg": delta_a1,
        "calc_delta_top5_avg": delta_a5,
        "calc_net_acc_ratio": ratio_a1,
        "calc_net_cov_ratio": ratio_a5,
        "calc_net_acc_clipped": clipped_a1,
        "calc_net_cov_clipped": clipped_a5,
        "calc_score_net_acc": score_net_acc,
        "calc_score_net_cov": score_net_cov,
        "calc_sdoh_score": sdoh_score,
        "calc_benchmark_total": total_score,
    })

    scores = {
        "Diagnostic_Performance_Score": diagnostic_score,
        "Reasoning_Reliability_Score": reasoning_score,
        "SDoH_Score": sdoh_score,
        "Benchmark_Score_100": total_score,
    }
    return scores, audit


def compute_score_row_detailed(row):
    scores, audit = _compute_score_parts(row)
    out = {**audit, **scores}
    if COL_MODEL_CANONICAL_NAME in row.index:
        out[COL_MODEL_CANONICAL_NAME] = row[COL_MODEL_CANONICAL_NAME]
    return pd.Series(out)


def main():
    benchmark_dir = resolve_benchmark_dir()
    input_path = benchmark_dir / "benchmark_score_inputs.xlsx"
    output_path = benchmark_dir / "benchmark_scores_output.xlsx"

    if not input_path.exists():
        raise FileNotFoundError(f"Missing input file: {input_path}")

    df = normalize_score_input_columns(pd.read_excel(input_path))
    required_cols = [
        COL_BASE_ACCURACY, COL_COVERAGE, "High_Severity_Rate", "SDoH_IR",
        "SDoH_SSR_less", "SDoH_SSR_more",
        "SDoH_Net_change_less_top1acc", "SDoH_Net_change_less_top5cov",
        "SDoH_Net_change_more_top1acc", "SDoH_Net_change_more_top5cov",
    ]
    miss = [c for c in required_cols if c not in df.columns]
    if miss:
        raise ValueError(f"Input file missing columns: {miss}")

    score_df = df.apply(compute_score_row, axis=1)
    out_df = pd.concat([df, score_df], axis=1)
    out_df = out_df.sort_values(by="Benchmark_Score_100", ascending=False, na_position="last").reset_index(drop=True)

    os.makedirs(benchmark_dir, exist_ok=True)
    out_df.to_excel(output_path, index=False)
    print(f"Composite score output written: {output_path}")

    try:
        from benchmark_audit_workbook import write_benchmark_audit_workbook

        audit_path = write_benchmark_audit_workbook(
            legacy_root=benchmark_dir.parent,
            output_path=benchmark_dir / "benchmark_audit_workbook.xlsx",
        )
        print(f"Audit workbook written: {audit_path}")
    except Exception as exc:
        print(f"[warn] Audit workbook not written: {exc}")


if __name__ == "__main__":
    main()
