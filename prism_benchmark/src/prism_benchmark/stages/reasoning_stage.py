from __future__ import annotations

from pathlib import Path

from prism_benchmark.legacy_registry import ROUND_NUM_LIST
from prism_benchmark.stages._invoke import invoke_legacy_main


def _verify_flaws_outputs(legacy_root: Path) -> None:
    bench_dir = legacy_root / "benchmark"
    missing = []
    for r in ROUND_NUM_LIST:
        # run_list defaults to [""], so check the main summary file first.
        p = bench_dir / f"{r}_flaws_summary.xlsx"
        if not p.exists():
            missing.append(str(p))
    if missing:
        raise RuntimeError("Missing reasoning_flaws outputs:\n" + "\n".join(missing))


def run_reasoning_flaws(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "reasoning_flaws")
    _verify_flaws_outputs(legacy_root)
    print("reasoning_flaws stage completed and outputs verified.")


def run_reasoning_flaws_summary(*, legacy_root: Path, python_executable: str = "python", **kwargs) -> None:
    invoke_legacy_main(legacy_root, "reasoning_flaws_summary")
    _verify_flaws_outputs(legacy_root)
    print("reasoning_flaws_summary stage completed and outputs verified.")
