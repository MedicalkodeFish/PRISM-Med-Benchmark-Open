"""Excel export helpers for reasoning-flaw judge scripts (xlsxwriter with openpyxl fallback)."""
from __future__ import annotations

from typing import Tuple

import pandas as pd


def open_flaws_excel_writer(output_path: str) -> Tuple[pd.ExcelWriter, str]:
    try:
        import xlsxwriter  # noqa: F401

        return pd.ExcelWriter(output_path, engine="xlsxwriter"), "xlsxwriter"
    except ImportError:
        print(
            "[warn] xlsxwriter not installed; writing Excel via openpyxl (no charts). "
            "Install with: pip install xlsxwriter"
        )
        return pd.ExcelWriter(output_path, engine="openpyxl"), "openpyxl"


def autofit_columns(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame, engine: str) -> None:
    if engine != "xlsxwriter":
        try:
            from openpyxl.utils import get_column_letter

            ws = writer.sheets[sheet_name]
            for i, col in enumerate(df.columns):
                max_length = max(df[col].astype(str).map(len).max(), len(col)) + 2
                ws.column_dimensions[get_column_letter(i + 1)].width = min(max_length, 80)
        except Exception:
            pass
        return
    worksheet = writer.sheets[sheet_name]
    for i, col in enumerate(df.columns):
        max_length = max(df[col].astype(str).map(len).max(), len(col)) + 2
        worksheet.set_column(i, i, max_length)


def query_case_basenames(df) -> set:
    from benchmark_sdoh_utils import case_stem_from_filename

    basenames = set()
    for fn in df["File Name"]:
        basenames.add(case_stem_from_filename(str(fn)))
    return basenames
