# -*- coding: utf-8 -*-
"""Challenge / SDoH case catalogs: one ``cases.jsonl`` per dataset directory.

Each line is one case object. Lookup is by ``case_id`` (filename stem, e.g.
``scg150001`` or ``10.1056aNEJMcpc1900419``). Legacy per-case ``.json`` /
``.jsonl`` files are still read if present and no catalog entry exists.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

CaseRecord = Dict[str, Any]

CASES_CATALOG_NAME = "cases.jsonl"
_CASE_SUFFIXES = (".jsonl", ".json")
_catalog_cache: Dict[str, Dict[str, CaseRecord]] = {}


def case_stem_from_filename(name: str) -> str:
    """Strip path and ``.json`` / ``.jsonl`` extension → case id stem."""
    base = str(name).replace("\\", "/").split("/")[-1].strip()
    for suffix in _CASE_SUFFIXES:
        if base.lower().endswith(suffix):
            return base[: -len(suffix)]
    return base


def normalize_case_filename(name: str) -> str:
    """Normalize Excel ``File Name`` to legacy ``<stem>.json`` (lookup uses stem only)."""
    stem = case_stem_from_filename(name)
    return f"{stem}.json" if stem else str(name).strip()


def catalog_path(dataset_root: Union[str, Path]) -> Path:
    return Path(dataset_root) / CASES_CATALOG_NAME


def _legacy_per_case_path(dataset_root: Path, stem: str) -> Optional[Path]:
    for suffix in _CASE_SUFFIXES:
        p = dataset_root / f"{stem}{suffix}"
        if p.exists() and p.name != CASES_CATALOG_NAME:
            return p
    return None


def _load_legacy_file(path: Path) -> Optional[CaseRecord]:
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        if path.suffix.lower() == ".jsonl":
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                return obj if isinstance(obj, dict) else None
            return None
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def load_catalog(dataset_root: Union[str, Path]) -> Dict[str, CaseRecord]:
    """Load (and cache) all cases from ``<dataset_root>/cases.jsonl``."""
    root = Path(dataset_root).resolve()
    cache_key = str(root)
    if cache_key in _catalog_cache:
        return _catalog_cache[cache_key]

    index: Dict[str, CaseRecord] = {}
    path = catalog_path(root)
    if path.is_file():
        with path.open("r", encoding="utf-8") as f:
            for line_no, raw in enumerate(f, 1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                case_id = obj.get("case_id") or obj.get("id")
                if not case_id:
                    continue
                index[str(case_id)] = obj

    _catalog_cache[cache_key] = index
    return index


def clear_catalog_cache() -> None:
    _catalog_cache.clear()


def get_case_record(dataset_root: Union[str, Path], ref: str) -> Optional[CaseRecord]:
    """Resolve a case by Excel ``File Name`` or stem from the dataset catalog."""
    root = Path(dataset_root)
    stem = case_stem_from_filename(ref)
    if not stem:
        return None

    hit = load_catalog(root).get(stem)
    if hit is not None:
        return dict(hit)

    legacy = _legacy_per_case_path(root, stem)
    if legacy is not None:
        return _load_legacy_file(legacy)
    return None


# Backward-compatible aliases used during migration
def load_case_record(path: Union[str, Path]) -> Optional[CaseRecord]:
    """Load from a concrete file path (legacy per-case files only)."""
    return _load_legacy_file(Path(path))


def resolve_case_record_path(dataset_root: Union[str, Path], rel_or_name: str) -> Optional[str]:
    stem = case_stem_from_filename(rel_or_name)
    root = Path(dataset_root)
    if stem in load_catalog(root):
        return str(catalog_path(root))
    legacy = _legacy_per_case_path(root, stem)
    return str(legacy) if legacy else None


def case_record_path(dataset_root: Union[str, Path], rel_or_name: str) -> Path:
    root = Path(dataset_root)
    stem = case_stem_from_filename(rel_or_name)
    legacy = _legacy_per_case_path(root, stem)
    if legacy is not None:
        return legacy
    return catalog_path(root)
