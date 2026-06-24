# PRISM-Med Benchmark

**Languages:** [English](README.md) · [中文](README.zh-CN.md) · [Français](README.fr.md) · [Español](README.es.md)

**PRISM-Med is a multi-dimensional benchmark for evaluating large language models (LLMs) and AI agents** on complex clinical reasoning and diagnosis—not a single accuracy number, but diagnostic performance, reasoning reliability, and SDoH-related bias assessed under a common protocol.

**PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis**

This repository implements the **PRISM-Med** benchmark: challenge-set diagnostics, reasoning reliability, and SDoH (social determinants of health) bias are combined into a composite score (`Benchmark_Score_100`), suitable for comparing models and agentic pipelines on equal footing.

### Evaluation protocol (reference runs)

The public leaderboard and paper-style scores use a fixed **three-repetition** protocol:

1. **Three independent runs per case** — each subject model answers the same cases **three times** (round ids `1_5answer`, `1_5answer_1`, `1_5answer_2` in `config/legacy_script_config.py`), including challenge-set and SDoH branches where applicable.
2. **Diagnosis classification → majority vote** — after per-round judging of Top-1 and differential lists against the reference, **case-level diagnostic labels are merged by majority vote across the three rounds** (`classification_vote`). Challenge-set accuracy/coverage and related score inputs use these voted labels.
3. **Reasoning-flaw classification → direct pooling** — audits of reasoning content are **not** voted; the three rounds are **aggregated directly** (all per-round flaw classifications contribute to the pooled case set), and severe-reasoning-flaw rates are computed from that combined view.

Local reproduction uses the same defaults unless you override round lists via `PRISM_*` env vars (see [docs/BENCHMARK.md](docs/BENCHMARK.md)).

We **continuously update** the public **model leaderboard** as new evaluations complete, and **open-source additional benchmark datasets** over time. Watch this repository for refreshed figures, tables, and `dataset/` releases.

All commands below assume your shell’s current directory is **this repository root** (the folder that contains `run_prism_benchmark.py`).

## Overview

### Model leaderboard (reference run)

Illustrative rankings from a completed PRISM-Med evaluation (reproduce locally with the pipeline below). **This leaderboard is a snapshot** — we plan to refresh it as more models are evaluated; dataset coverage will also grow in future releases.

<p align="center">
  <img src="img/benchmark_scores.png" alt="PRISM-Med model score leaderboard" width="900">
</p>

<p align="center"><sub>High-resolution vector: <a href="img/benchmark_scores.pdf">img/benchmark_scores.pdf</a></sub></p>

#### Evaluated models (reference run)

The figure above summarizes **PRISM-Med** composite scores (`Benchmark_Score_100`) for the subject models below. **Version** values are the API `model_id` strings used in this benchmark (see `model_config/model_config.example.json`).

| LLM | Version (API model id) | Company |
|-----|------------------------|---------|
| Claude-4-Sonnet | `claude-sonnet-4-20250514` | Anthropic |
| Claude-4.5-Sonnet | `claude-sonnet-4-5-20250929` | Anthropic |
| DeepSeek-V3.1 | `deepseek-v3-1-250821` | DeepSeek |
| DeepSeek-V3.2 | `deepseek-v3.2-thinking` | DeepSeek |
| DeepSeek-V4 Pro | `deepseek-v4-pro` | DeepSeek |
| Gemini-2.5-Flash | `gemini-2.5-flash` | Google |
| Gemini-2.5-Pro | `gemini-2.5-pro` | Google |
| Gemini-3-Pro | `gemini-3-pro-preview` | Google |
| Gemini-3.5-Flash | `gemini-3.5-flash` | Google |
| GLM-4.5 | `glm-4.5` | Zhipu AI |
| GPT-4o | `gpt-4o-2024-11-20` | OpenAI |
| GPT-5 | `gpt-5-2025-08-07` | OpenAI |
| GPT-5-Mini | `gpt-5-mini-2025-08-07` | OpenAI |
| GPT-5.1-High | `gpt-5.1-high` | OpenAI |
| GPT-5.5 | `gpt-5.5` | OpenAI |
| Grok-4.1 | `grok-4.1` | xAI |
| O3 | `o3-2025-04-16` | OpenAI |
| O3-Pro | `o3-pro-2025-06-10` | OpenAI |
| O4-mini | `o4-mini-2025-04-16` | OpenAI |

Default subject models in `config/legacy_script_config.py` may list a subset for local runs; override with `PRISM_*_MODELS` or `--models` as documented in [docs/BENCHMARK.md](docs/BENCHMARK.md).

### Test datasets

PRISM-Med evaluates models on two linked case resources (overview in the paper Fig. 1):

**Challenging Case Dataset** — From 1,672 case reports collected across *NEJM* and *JAMA Network* journals, physician panels screened out 730 cases for diagnostic difficulty, leaving **942** cases spanning oncology (269), infectious diseases (159), genetic or congenital disorders (140), toxic/drug or iatrogenic conditions (74), traumatic/mechanical conditions (59), vascular diseases (39), and other categories (66) (paper Fig. 2A). In full mode, the active query table is `dataset/question/query_question.xlsx` (942 rows); catalogs and DOIs live under `dataset/Challenge_Dataset/`.

**Simulated SDoH Dataset** — **289** of the 942 cases (~30.7%) were retained after LLM pre-screening and physician review to assess SDoH-related stereotyping. Each case has paired counterfactual scenarios with less-resourced and more-resourced SDoH profiles (**578** scenarios total). Cases are labeled by whether the ground-truth diagnosis aligns with the stereotype-congruent direction under the paired profiles: less-resourced-congruent (89), more-resourced-congruent (88), and SDoH-neutral (112) (paper Fig. 2B). Lists are under `dataset/SDoH_Dataset/`; bias **count** stages additionally require a local `bias_analysis_*` preprocessing tree (~289 case folders)—see [docs/BENCHMARK.md](docs/BENCHMARK.md).

Copyright and citation notes: [dataset/README.md](dataset/README.md).

### Benchmark pipeline

`Benchmark_Score_100` combines three metric families: **challenge-set diagnostic performance** (Top-1 / Top-5, etc.), **severe reasoning-flaw rate** in model answers, and **SDoH-related bias metrics** (e.g. IR, SSR). The run comprises 12 stages; inputs, outputs, and optional partial-SDoH mode are documented in [docs/BENCHMARK.md](docs/BENCHMARK.md).

<p align="center">
  <img src="img/flowchart.png" alt="PRISM-Med benchmark pipeline flowchart" width="900">
</p>

<p align="center"><sub>High-resolution vector: <a href="img/flowchart.pdf">img/flowchart.pdf</a></sub></p>

**License:** [MIT License](LICENSE) applies to **software and documentation in this repository**. **Clinical case text** in `dataset/` remains subject to **original publisher copyright** — see [dataset/README.md](dataset/README.md). Machine-readable citation metadata: [CITATION.cff](CITATION.cff).

## Citation

If you use this benchmark or code, please cite:

> **PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis**  
> Xintian Yang¹*, Qin Su²*, Yukang Liu²*, Hui Luo², Xiangping Wang², Gui Ren², Xiaoyu Kang², Weijie Xue³, Yuemin Feng¹, Ben Wang¹, Qianqian Xu¹, Lei Shi¹, Qi Zhao¹, Shuhui Liang², Yong Lv², Yongzhan Nie², Lina Zhao⁴, Han Wang⁵‡, Yanglin Pan²‡, Hongwei Xu¹,⁶‡  
> *Equal contribution. ‡Corresponding authors.

Example BibTeX (add journal/conference fields and DOI when available):

```bibtex
@article{yang2026prismmed,
  title   = {PRISM-Med: multidimensional evaluation of large language models in complex medical diagnosis},
  author  = {Yang, Xintian and Su, Qin and Liu, Yukang and Luo, Hui and Wang, Xiangping and Ren, Gui and Kang, Xiaoyu and Xue, Weijie and Feng, Yuemin and Wang, Ben and Xu, Qianqian and Shi, Lei and Zhao, Qi and Liang, Shuhui and Lv, Yong and Nie, Yongzhan and Zhao, Lina and Wang, Han and Pan, Yanglin and Xu, Hongwei},
  year    = {2026},
  note    = {Benchmark code and data: see repository README and CITATION.cff}
}
```

## What is in this repository

| Included | Not shipped (generated locally) |
|----------|----------------------------------|
| Case lists and catalogs under `dataset/` (942 challenge queries in full mode) | LLM outputs under `benchmark/result/` |
| Prompts (`prompt/`), classification rules, reference bias table (`benchmark/reference_table_bias_with_doi.xlsx`) | Run manifests under `prism_benchmark/runs/` |
| Pipeline code (`stages/`, `lib/`, `prism_benchmark/`) | Composite score workbook until the pipeline finishes |
| Template API config (`model_config/model_config.example.json`) | Full SDoH-bias preprocessing tree (`bias_analysis_*`, ~289 case folders) — see [docs/BENCHMARK.md](docs/BENCHMARK.md) |

**Clinical data:** vignettes are linked to published **NEJM** / **JAMA** (and similar) case reports via **DOI**. Read [dataset/README.md](dataset/README.md) before redistributing or reusing case text.

## Requirements

- **Python 3.10+**
- Dependencies:

```powershell
pip install -r requirements.txt
```

## Quick Start

Commands below use **Windows PowerShell** from the **repository root** (this folder). On Linux/macOS, use `python3`, forward slashes, and `cp` instead of `Copy-Item`.

1. **Install dependencies** (see [Requirements](#requirements) above).

2. **Configure API access** — copy the template and edit `model_config/model_config.json`: set `api_key` and `url` for each model alias you plan to run (ids must match the [evaluated models](#evaluated-models-reference-run) table, e.g. `gpt-5.5`, `gemini-3.5-flash`).

```powershell
Copy-Item .\model_config\model_config.example.json .\model_config\model_config.json
# Edit model_config\model_config.json (do not commit real keys).
```

3. **Preflight (no API calls)** — if you do not yet have SDoH-branch `bias_analysis_*` data (~289 case folders), you can run diagnostic + reasoning only (partial-SDoH mode):

```powershell
$env:PRISM_ALLOW_PARTIAL_SDOH = "1"
python .\run_prism_benchmark.py --check-only --no-pause
```

   Exit code `0` means data assets look OK for the mode you selected. Details: [docs/BENCHMARK.md](docs/BENCHMARK.md).

4. **Choose subject models** — defaults live in `config/legacy_script_config.py` (`DEFAULT_MODEL_LIST`). Override without editing code (comma-separated **config ids**):

```powershell
$env:PRISM_BASE_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_BIAS_ASK_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_CLASSIFICATION_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_REASONING_SUMMARY_MODELS = "gpt-5.5,gemini-3.5-flash"
$env:PRISM_COUNT_TARGET_MODELS = "gpt-5.5,gemini-3.5-flash"
```

   Checker / judge models: set entries in `model_config.json` and optional env vars such as `PRISM_REASONING_LLM_MODEL`, `PRISM_COUNT_MODEL` (see [docs/BENCHMARK.md](docs/BENCHMARK.md)).

5. **Full composite score (with SDoH, paper-style)** — supply external `bias_analysis_*` (junction or `PRISM_BIAS_ANALYSIS_ROOT`), then run **without** `PRISM_ALLOW_PARTIAL_SDOH`. This runs all 12 steps, probes APIs, and may take long / incur API cost:

```powershell
Remove-Item Env:PRISM_ALLOW_PARTIAL_SDOH -ErrorAction SilentlyContinue
python .\run_prism_benchmark.py --no-pause
```

   **Diagnostic + reasoning only:** keep `$env:PRISM_ALLOW_PARTIAL_SDOH = "1"` or use `python .\run_prism_benchmark.py --allow-partial-sdoh --no-pause`.

6. **Outputs** (after a successful run):

| Artifact | Path |
|----------|------|
| Per-stage LLM JSON/text | `benchmark/result/<model>/…` |
| Composite score workbook | `benchmark/benchmark_scores_output.xlsx` |
| Run manifest / completion table | `prism_benchmark/runs/` |

   Re-run the same command to **resume** incomplete cases; use `--check-only` anytime to see stage completion.

More detail: [docs/BENCHMARK.md](docs/BENCHMARK.md) · [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md)

## Common commands (Windows PowerShell)

| Goal | Command |
|------|---------|
| Data and pipeline asset check | `python .\run_prism_benchmark.py --check-only --no-pause` (see [Quick Start](#quick-start) step 3) |
| Full 12-step benchmark | `python .\run_prism_benchmark.py --no-pause` or double-click `run_prism_full_benchmark.bat` |
| Restore full query + reference tables | `python .\prism_benchmark\scripts\prepare_full_benchmark_data.py` |
| Pipeline only (orchestration) | `python .\prism_benchmark\scripts\run_pipeline.py --config .\prism_benchmark\configs\default.json` |

Step-by-step guide: [docs/BENCHMARK.md](docs/BENCHMARK.md) · Layout: [PROJECT_LAYOUT.md](PROJECT_LAYOUT.md) · Orchestration layer: [prism_benchmark/README.md](prism_benchmark/README.md)

## Entry points

- `run_prism_benchmark.py` — recommended launcher (preflight, API probe, 12 steps, completion table)
- `prism_benchmark/scripts/run_pipeline.py` — config-driven pipeline without the launcher extras
- `prism_benchmark/scripts/data_assets_check.py` — dataset and three-module asset check (standalone)
- `prism_benchmark/scripts/benchmark_verify.py` — per-step artifact verification (`list_missing_cases.py` wraps this)
