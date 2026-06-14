"""Resolve configured test-subject model directory names under benchmark/result."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List


def _ensure_legacy_on_path(legacy_root: Path) -> None:
    root = str(legacy_root.resolve())
    if root not in sys.path:
        sys.path.insert(0, root)


def model_ids_for_env_list(legacy_root: Path, env_list: Iterable[str]) -> List[str]:
    _ensure_legacy_on_path(legacy_root)
    from model_config import resolve_model

    out: List[str] = []
    for name in env_list:
        conf = resolve_model(name)
        if conf and conf.get("id"):
            out.append(str(conf["id"]))
    return out


def iter_scoped_model_dirs(legacy_root: Path, model_ids: List[str]):
    result_root = legacy_root / "benchmark" / "result"
    if not result_root.exists():
        return
    allow = set(model_ids)
    for d in result_root.iterdir():
        if d.is_dir() and d.name in allow:
            yield d
