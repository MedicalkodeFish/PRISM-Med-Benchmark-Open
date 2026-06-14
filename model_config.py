"""Unified model configuration loader.

Reads ``model_config/model_config.json`` as the authoritative data source and
exposes the attribute surface historic scripts depend on:

- ``MODEL_CONFIG_PATH`` / ``MODEL_CONFIG_DATA``: path and raw parsed JSON
- ``loaded_configs``: entries from ``models`` section
- ``api_config``: ``loaded_configs`` plus ``aliases`` from JSON
- ``checker_model_list`` / ``classification_model``: from JSON ``defaults``
- ``resolve_model(name)``: unified lookup (exact key, then case-insensitive)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_CONFIG_PATH = PROJECT_ROOT / "model_config" / "model_config.json"

_DEFAULT_CLASSIFICATION_MODEL = "gemini-2.5-pro"
_DEFAULT_CHECKER_MODEL_LIST = [
    "gemini-2.0-flash-check-lite",
    "gemini-3-flash-preview",
]


def _load_raw_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with both ``id`` and ``model_id`` keys populated."""
    out = dict(entry)
    if "id" not in out and "model_id" in out:
        out["id"] = out["model_id"]
    if "model_id" not in out and "id" in out:
        out["model_id"] = out["id"]
    return out


def _build_loaded_configs(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for section in ("models",):
        for entry in data.get(section, []) or []:
            entry_id = entry.get("id") or entry.get("model_id")
            if not entry_id:
                continue
            out[entry_id] = _normalize_entry(entry)
    return out


def _build_api_config(
    loaded: Dict[str, Dict[str, Any]], data: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = dict(loaded)
    for entry in data.get("aliases", []) or []:
        entry_id = entry.get("id") or entry.get("model_id")
        if not entry_id:
            continue
        out.setdefault(entry_id, _normalize_entry(entry))
    return out


def _load_runtime_defaults(data: Dict[str, Any]) -> tuple[str, List[str]]:
    defaults = data.get("defaults") or {}
    classification = defaults.get("classification_model") or _DEFAULT_CLASSIFICATION_MODEL
    checker_list = defaults.get("checker_model_list")
    if not checker_list:
        checker_list = list(_DEFAULT_CHECKER_MODEL_LIST)
    return str(classification), [str(item) for item in checker_list]


def resolve_model(name: str) -> Optional[Dict[str, Any]]:
    """Resolve a logical model name to a config entry."""
    key = name.strip()
    if not key:
        return None
    if key in api_config:
        return api_config[key]
    lower = key.lower()
    for cfg_id, entry in api_config.items():
        if cfg_id.lower() == lower:
            return entry
    return None


MODEL_CONFIG_DATA: Dict[str, Any] = _load_raw_config(MODEL_CONFIG_PATH)
loaded_configs: Dict[str, Dict[str, Any]] = _build_loaded_configs(MODEL_CONFIG_DATA)
api_config: Dict[str, Dict[str, Any]] = _build_api_config(loaded_configs, MODEL_CONFIG_DATA)
classification_model, checker_model_list = _load_runtime_defaults(MODEL_CONFIG_DATA)


__all__ = [
    "MODEL_CONFIG_PATH",
    "MODEL_CONFIG_DATA",
    "loaded_configs",
    "api_config",
    "checker_model_list",
    "classification_model",
    "resolve_model",
]
