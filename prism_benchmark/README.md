# Prism Benchmark (Open-Source Oriented Rebuild)

This folder contains the **orchestration layer** for the benchmark pipeline at the repository root (`stages/`, `lib/`, `config/`).

## Goals

- Keep research logic unchanged:
  - 3-round model runs
  - multi-stage adjudication
  - classification majority-vote aggregation
  - reasoning flaw analysis (no cross-round voting)
  - SDoH bias/stability metrics (IR/SSR)
  - composite benchmark scoring
- Improve engineering quality:
  - standardized project structure
  - config-driven execution
  - reproducible pipeline entrypoint
  - clear logs and output checks

## Layout

See **`../PROJECT_LAYOUT.md`** for the full directory map (`config/`, `lib/`, `stages/`).

```text
<repo-root>/               ← legacy_root (cwd for pipeline)
  config/  lib/  stages/  dataset/  prompt/  benchmark/
  run_prism_benchmark.py
  prism_benchmark/         ← you are here
    configs/
    scripts/run_pipeline.py
    src/prism_benchmark/
```

## Quick Start (Windows PowerShell)

From the repository root:

```powershell
python .\prism_benchmark\scripts\run_pipeline.py --config .\prism_benchmark\configs\default.json
```

With run manifest + keep-going mode:

```powershell
python .\prism_benchmark\scripts\run_pipeline.py `
  --config .\prism_benchmark\configs\default.json `
  --continue-on-error
```

Run only a subset of steps:

```powershell
python .\prism_benchmark\scripts\run_pipeline.py --config .\prism_benchmark\configs\default.json --steps base_ask classification classification_summary
```

## Current Strategy

This rebuild orchestrates the benchmark through native stage modules in
`src/prism_benchmark/stages/`. Each stage:

- imports the corresponding root-level research script (e.g. `base_ask.py`)
  via `importlib` and calls its `main()` function **in-process**;
- runs pre-checks for required inputs and post-checks for expected outputs;
- chdirs into the repository root so that existing relative paths keep resolving.

Removing the previous `subprocess` boundary means real Python tracebacks,
mockable internals for unit tests, and one less process per step.

## What Was De-Hardcoded

To improve open-source usability, several hardcoded parts were centralized:

- **Round constants** are centralized in `src/prism_benchmark/legacy_registry.py`
- **Legacy script filenames/locations** are centralized in
  `src/prism_benchmark/legacy_registry.py` via `LEGACY_SCRIPTS` (filename map)
  and `LEGACY_MODULES` (module + callable map used by the in-process runner).
- **Benchmark path resolution** is centralized in
  `src/prism_benchmark/pathing.py`
- **Legacy script constants** (model list, round list, shared paths) are
  centralized in `../config/legacy_script_config.py`
- **Model configuration** has a single source of truth:
  `../model_config/model_config.json` (copy from `model_config.example.json`) loaded by `../model_config.py`
  and re-exported as `loaded_configs` / `api_config`. Older scripts that
  used to open the JSON inline now `from model_config import loaded_configs`.

## Legacy Entry Point Structure

`legacy_entrypoints/` has been removed. Each step in
`prism_benchmark.legacy_registry.LEGACY_SCRIPTS` now points directly at its
corresponding root-level script, and the matching entry in `LEGACY_MODULES`
gives the importable module and callable (`main` by default).

Stages call those modules through `prism_benchmark.stages._invoke.invoke_legacy_main`,
which:

1. verifies the script file exists,
2. inserts `legacy_root` into `sys.path` and `os.chdir`s into it,
3. imports (or reloads) the module and invokes its `main()` function,
4. restores the previous working directory.

## Remaining Hardcoded Parts

Some hardcoding still exists inside legacy research scripts (expected in migration phase):

- fixed prompt/dataset filenames in old scripts
- model lists in some scripts
- output filename conventions inherited from historical pipeline

These are intentionally preserved for reproducibility and should be migrated gradually.

Recent cleanup in counting scripts (`base_count.py`, `bias_count.py`):

- path resolution now anchors on repository root (not current shell cwd)
- count model can be overridden with `PRISM_COUNT_MODEL`
- bias-analysis source directory can be overridden with `PRISM_BIAS_ANALYSIS_ROOT`

Example (Windows PowerShell):

```powershell
$env:PRISM_COUNT_MODEL = "gpt-5.1-high"
$env:PRISM_BIAS_ANALYSIS_ROOT = "E:\path\to\bias_analysis_second_gpt5_bias_diagnosis"
python .\stages\base_count.py
python .\stages\bias_count.py
```

## Full Benchmark Chain

The default pipeline executes:

1. `base_ask` (3 rounds, original dataset)
2. `classification` (per round)
3. `classification_summary` (per round)
4. `reasoning_flaws` (per round)
5. `reasoning_flaws_summary` (2-pass + summary per round, no cross-round voting)
6. `bias_ask` (3 rounds, SDoH variants)
7. `bias_classification` (scenario1/scenario2)
8. `base_count` and `bias_count`
9. `bias_metrics` (IR/SSR/net-change)
10. `classification_vote` (3-round majority vote for diagnosis metrics)
11. `composite_score` (fixed benchmark scoring formula)

Run manifests are written to `prism_benchmark/runs/`.

## Configuration Management (Recommended)

For open-source usage, manage config in this order:

1. `configs/default.json`: step orchestration and execution order
2. `legacy_registry.py`: legacy script mapping and round constants
3. `pathing.py`: benchmark directory discovery

Avoid placing new path/model constants directly in stage modules.

## Open-source checklist

- Read [../docs/BENCHMARK.md](../docs/BENCHMARK.md) (three pillars and pillar 3 data)
- Copy `../model_config/model_config.example.json` → `model_config.json` and configure API access
- Run `python ..\run_prism_benchmark.py --check-only --no-pause` before full API runs
- Keep `PY_WHITELIST.md` aligned with mainline `.py` files

See [../PROJECT_LAYOUT.md](../PROJECT_LAYOUT.md) and [../README.md](../README.md).

