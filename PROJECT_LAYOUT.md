# Project layout

## Directory structure (by role)

```text
<repo-root>/                         ← legacy_root; pipeline cwd (contains run_prism_benchmark.py)
├── config/
│   └── legacy_script_config.py      ← PRISM_* env vars, model lists, dataset paths
├── lib/                             ← shared libraries (imported by stages and scripts)
├── stages/                          ← pipeline stage entrypoints
│   └── _bootstrap.py                ← adds lib/config/stages to sys.path
├── model_config.py + model_config/  ← model API config (JSON path stability at repo root)
├── prism_bootstrap.py
├── dataset/  prompt/  benchmark/    ← data, prompts, reference tables; result/ is output
├── results/                         ← optional external bias_analysis junction
└── prism_benchmark/                 ← orchestration (configs, scripts, src/prism_benchmark)
```

## How to run

**Full pipeline (orchestration only)**

```powershell
python .\prism_benchmark\scripts\run_pipeline.py --config .\prism_benchmark\configs\default.json
```

**Recommended launcher (preflight + API probe + completion tables)**

```powershell
python .\run_prism_benchmark.py --no-pause
```

**Single stage**

```powershell
python .\stages\base_ask.py
```

Each `stages/*.py` starts with `import _bootstrap`, which adds `lib/` and `config/` to the import path, so flat imports such as `from legacy_script_config import …` and `from benchmark_paths import …` still work.

**In-process invocation (`prism_benchmark`)**

Before importing a stage module, `prism_benchmark.stages._invoke`:

1. Adds `lib/`, `config/`, `stages/`, and the repo root to `sys.path`
2. `chdir`s to the repo root
3. `importlib.import_module("base_ask")` etc. (module names unchanged; files live under `stages/`)

Stage script paths are listed in `prism_benchmark/src/prism_benchmark/legacy_registry.py`.

## Path resolution

- **`PROJECT_ROOT`**: parent of `config/legacy_script_config.py` → repo root
- **`resolve_benchmark_dir()`**: resolves `benchmark/` under repo root vs parent `benchmark/`
- **`lib/benchmark_paths.py`**: builds per-stage paths under `benchmark/result/`

## Design notes

| Layer | Role |
|-------|------|
| `config/` | Static config and PRISM_* environment variables |
| `lib/` | Reusable logic without `main()` |
| `stages/` | Pipeline-callable `main()` entrypoints |
| `prism_benchmark/` | Step order, validation, manifests; does not duplicate research logic |

`model_config.py` stays at the repo root so `model_config/model_config.json` keeps a stable relative path.

## Related docs

- [README.md](README.md)
- [docs/BENCHMARK.md](docs/BENCHMARK.md)
- [prism_benchmark/README.md](prism_benchmark/README.md)
- [prism_benchmark/PY_WHITELIST.md](prism_benchmark/PY_WHITELIST.md)
