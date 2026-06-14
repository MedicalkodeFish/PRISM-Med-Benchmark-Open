# -*- coding: utf-8 -*-
"""
Register benchmark import directories on sys.path for legacy flat imports.

Directory names (under opensource_prism / legacy_root):
  lib/      — shared libraries (paths, pipelines, LLM helpers)
  config/   — env vars, model lists, dataset paths
  stages/   — pipeline entry scripts (main())

Legacy aliases benchmark_lib / benchmark_config / benchmark_stages are still
added when those folders exist.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

BENCHMARK_IMPORT_SUBDIRS = (
    "lib",
    "config",
    "stages",
    "benchmark_lib",
    "benchmark_config",
    "benchmark_stages",
)


def install_import_paths(root: Path | None = None) -> Path:
    root = root or ROOT
    root_s = str(root)
    for sub in BENCHMARK_IMPORT_SUBDIRS:
        sub_path = root / sub
        if not sub_path.is_dir():
            continue
        p = str(sub_path)
        if p not in sys.path:
            sys.path.insert(0, p)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root
