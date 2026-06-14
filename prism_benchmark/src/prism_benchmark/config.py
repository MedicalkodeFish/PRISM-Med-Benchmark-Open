from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_config(config_path: str | Path) -> Dict[str, Any]:
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "steps" not in data or not isinstance(data["steps"], list):
        raise ValueError("Config must contain a list field `steps`.")
    return data

