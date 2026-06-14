from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from prism_benchmark.config import load_config
from prism_benchmark.pipeline import run_pipeline
from prism_benchmark.steps import parse_steps


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PRISM benchmark pipeline")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to pipeline config JSON, e.g. prism_benchmark/configs/default.json",
    )
    parser.add_argument(
        "--steps",
        nargs="*",
        default=None,
        help="Optional step ids to run, e.g. --steps base_ask classification",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue remaining steps if one step fails.",
    )
    parser.add_argument(
        "--manifest-path",
        default=None,
        help="Optional manifest output path. Default: prism_benchmark/runs/<timestamp>.json",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    steps = parse_steps(cfg["steps"])

    legacy_root = (PROJECT_ROOT / cfg.get("legacy_root", "..")).resolve()
    python_executable = cfg.get("python_executable", "python")

    print("=== PRISM Pipeline ===")
    print("Project root:", PROJECT_ROOT)
    print("Legacy root :", legacy_root)
    print("Python exec :", python_executable)
    if args.steps:
        print("Selected steps:", ", ".join(args.steps))

    runs_dir = PROJECT_ROOT / "runs"
    default_manifest = runs_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    manifest_path = Path(args.manifest_path).resolve() if args.manifest_path else default_manifest

    report = run_pipeline(
        steps=steps,
        python_executable=python_executable,
        legacy_root=legacy_root,
        selected_step_ids=args.steps,
        continue_on_error=args.continue_on_error,
        run_manifest_path=manifest_path,
    )

    print(f"\nPipeline finished with status: {report['status']}")
    print(f"Run manifest: {manifest_path}")


if __name__ == "__main__":
    main()

