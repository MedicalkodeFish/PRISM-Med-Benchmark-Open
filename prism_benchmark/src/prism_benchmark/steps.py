from __future__ import annotations

import importlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass
class Step:
    id: str
    script: str = ""
    entrypoint: str = ""
    enabled: bool = True
    description: str = ""
    params: Dict[str, Any] | None = None


def parse_steps(items: Iterable[dict]) -> List[Step]:
    steps: List[Step] = []
    for item in items:
        steps.append(
            Step(
                id=item["id"],
                script=item.get("script", ""),
                entrypoint=item.get("entrypoint", ""),
                enabled=bool(item.get("enabled", True)),
                description=item.get("description", ""),
                params=item.get("params", {}),
            )
        )
    return steps


def _run_script_step(step: Step, *, python_executable: str, legacy_root: Path) -> None:
    script_path = legacy_root / step.script
    if not script_path.exists():
        raise FileNotFoundError(f"[{step.id}] Script not found: {script_path}")

    cmd = [python_executable, str(script_path)]
    print(f"\n=== STEP: {step.id} ===")
    if step.description:
        print(f"Description: {step.description}")
    print("Command:", " ".join(cmd))
    print("Working dir:", legacy_root)

    subprocess.run(cmd, cwd=str(legacy_root), check=True)


def _run_module_step(step: Step, *, python_executable: str, legacy_root: Path) -> None:
    if ":" not in step.entrypoint:
        raise ValueError(f"[{step.id}] Invalid entrypoint format: {step.entrypoint}")
    module_name, func_name = step.entrypoint.split(":", 1)
    mod = importlib.import_module(module_name)
    fn = getattr(mod, func_name, None)
    if fn is None:
        raise AttributeError(f"[{step.id}] Function not found: {step.entrypoint}")

    print(f"\n=== STEP: {step.id} ===")
    if step.description:
        print(f"Description: {step.description}")
    print("Entrypoint:", step.entrypoint)
    print("Working dir:", legacy_root)
    fn(
        legacy_root=legacy_root,
        python_executable=python_executable,
        **(step.params or {}),
    )


def run_step(step: Step, *, python_executable: str, legacy_root: Path) -> None:
    if step.entrypoint:
        _run_module_step(step, python_executable=python_executable, legacy_root=legacy_root)
        return
    if step.script:
        _run_script_step(step, python_executable=python_executable, legacy_root=legacy_root)
        return
    raise ValueError(f"[{step.id}] Neither script nor entrypoint configured.")

