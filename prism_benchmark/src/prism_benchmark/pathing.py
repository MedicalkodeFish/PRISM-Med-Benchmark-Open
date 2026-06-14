from __future__ import annotations

import sys
from pathlib import Path


def _install_legacy_import_paths(legacy_root: Path) -> None:
    root = legacy_root.resolve()
    for sub in ("", "config", "lib"):
        p = str(root / sub) if sub else str(root)
        if p not in sys.path:
            sys.path.insert(0, p)


def resolve_benchmark_dir_from_legacy(legacy_root: Path) -> Path:
    """Resolve benchmark dir; prefers ``legacy_script_config.resolve_benchmark_dir``."""
    _install_legacy_import_paths(legacy_root)
    try:
        from legacy_script_config import resolve_benchmark_dir

        return resolve_benchmark_dir()
    except ImportError:
        pass

    candidates = [legacy_root / "benchmark", legacy_root.parent / "benchmark"]
    key_files = ("benchmark_score_inputs.xlsx", "reference_table_bias_with_doi.xlsx")
    for c in candidates:
        if any((c / k).exists() for k in key_files):
            return c
    for c in candidates:
        if (c / "result").exists() or c.exists():
            return c
    return candidates[0]


def resolve_benchmark_dir_from_project(project_root: Path) -> Path:
    """Resolve benchmark dir from prism_benchmark project root (legacy opensource_prism)."""
    legacy_root = project_root.parent
    return resolve_benchmark_dir_from_legacy(legacy_root)

