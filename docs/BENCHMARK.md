# PRISM Benchmark — run guide

The benchmark has **three pillars**, merged into `Benchmark_Score_100` (see `stages/compute_composite_benchmark_score.py`).

| Pillar | Focus | Main data | Pipeline steps (overview) |
|--------|--------|-----------|---------------------------|
| **1 — Diagnostic** | Challenge-set Top1 / Top5, etc. | `dataset/Challenge_Dataset/` + `dataset/question/query_question.xlsx` | `base_ask` → `classification` → `classification_summary` → `classification_vote` |
| **2 — Reasoning** | Severe reasoning-flaw rate in answers | Same challenge cases and `base_ask` outputs | `reasoning_flaws` → `reasoning_flaws_summary` |
| **3 — SDoH bias** | IR, SSR, net change, etc. | `dataset/SDoH_Dataset/` + SDoH branch artifacts | `bias_ask` → `bias_classification` → `base_count` / `bias_count` → `bias_metrics` |

Pillar 3 **count** steps also read per-case `formatted.json` under `PRISM_BIAS_ANALYSIS_ROOT` (historical preprocessing tree, ~289 subdirs for a full run). That tree is **not** part of the public source bundle; you must supply it locally or use partial-SDoH mode.

## How to run

From the **repository root** (directory containing `run_prism_benchmark.py`):

```powershell
# 1) Configure API (once)
Copy-Item .\model_config\model_config.example.json .\model_config\model_config.json
# Edit model_config.json with your endpoints and keys.

# 2) Data and three-pillar asset check (no API calls)
python .\run_prism_benchmark.py --check-only --no-pause

# 3) Optional: restore full case table + bias path hints
python .\prism_benchmark\scripts\prepare_full_benchmark_data.py --restore-bias-analysis

# 4) Full 12-step run (API keys + complete pillar 3 data for a full score)
python .\run_prism_benchmark.py --no-pause
```

### Pillars 1–2 only

When pillar 3 assets are missing or you only care about diagnostic + reasoning metrics:

```powershell
$env:PRISM_ALLOW_PARTIAL_SDOH = "1"
python .\run_prism_benchmark.py --no-pause
```

Or pass the launcher flag:

```powershell
python .\run_prism_benchmark.py --allow-partial-sdoh --no-pause
```

### Pillar 3 preprocessing data (`bias_analysis_*`)

The count stages need ~289 case subfolders with `formatted.json`. Options:

**A — Environment variable (any path)**

```powershell
$env:PRISM_BIAS_ANALYSIS_ROOT = "E:\path\to\bias_analysis_second_gpt5_bias_diagnosis"
```

**B — Junction into this repo (Windows, no copy)**

If you have the tree elsewhere (e.g. a private monorepo checkout):

```powershell
New-Item -ItemType Directory -Force .\results | Out-Null
cmd /c mklink /J "results\bias_analysis_second_gpt5_bias_diagnosis" "E:\path\to\bias_analysis_second_gpt5_bias_diagnosis"
```

**C — Parent-relative candidate**

If this repo lives next to a larger checkout, `data_requirements.json` may auto-detect `../results/bias_analysis_*`. That works in a monorepo layout but **not** when this folder is cloned alone.

Thresholds and candidate paths: `prism_benchmark/configs/data_requirements.json`.

## Configuration

| Topic | Location |
|-------|----------|
| Step order | `prism_benchmark/configs/default.json` |
| Expected row counts / bias dir thresholds | `prism_benchmark/configs/data_requirements.json` |
| Subject models, rounds, paths | `config/legacy_script_config.py` and `PRISM_*` env vars |
| API aliases | `model_config/model_config.json` (local only; copy from `model_config.example.json`) |

Dataset copyright (NEJM/JAMA case text): [dataset/README.md](../dataset/README.md).

More layout detail: [PROJECT_LAYOUT.md](../PROJECT_LAYOUT.md), [prism_benchmark/README.md](../prism_benchmark/README.md).

## Outputs (local, not in git)

| Path | Contents |
|------|----------|
| `benchmark/result/` | Per-model LLM JSON/text artifacts |
| `benchmark/*.xlsx` | Score inputs, votes, composite score (after late pipeline steps) |
| `prism_benchmark/runs/` | Run manifests and completion tables |
| `results/` | Optional junction target for external bias trees |

After a cold clone, `--check-only` may show **0% stage completion** until you run the pipeline; that is expected if `benchmark/result/` is empty.
