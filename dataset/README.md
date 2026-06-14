# Benchmark datasets

This directory holds **structured case lists and prompts** used by the PRISM benchmark pipeline. It does **not** include LLM run outputs (those are written under `benchmark/result/` at runtime).

## Clinical case provenance

Many records are **clinical case vignettes tied to published journal articles**, primarily:

- **NEJM CPC** (*New England Journal of Medicine*), identified by DOIs such as `10.1056/NEJMcpc…` in `cases.jsonl` and related tables.
- **Other peer-reviewed clinical case reports** (including **JAMA** *Clinical Challenge* and similar series **when a DOI or catalog entry points to those sources**).

Each case entry typically includes a **`DOI` field** so you can locate the **original publication** and cite the primary literature.

### Copyright and acceptable use (important)

- **NEJM**, **JAMA**, and their publishers **own the copyright** in the underlying published case narratives, figures, and tables. **This repository is not affiliated with, endorsed by, or sponsored by NEJM, JAMA, or any publisher.**
- What we distribute here is intended to support **non-commercial research**: reproducing and evaluating LLM diagnostic benchmarks described in accompanying academic work. We **do not** grant any license to the publishers’ original text.
- **You are responsible** for ensuring your download, use, storage, and any further sharing comply with:
  - the **publisher’s terms of use** and copyright policies,
  - your **institution’s** policies, and
  - applicable **law** in your jurisdiction (including limitations and exceptions for research).
- **Do not** treat this folder as a substitute for **licensed access** to NEJM, JAMA, or other journals. For **commercial** products, **public republication** of full vignettes, or **model training** on publisher text beyond what your rights allow, obtain permission from the **rights holder** or use officially licensed sources.
- Benchmark outputs you generate locally (model responses, scores) are **your responsibility**; do not present them as medical advice.

### What this repo claims

| Component | Typical status in this repo |
|-----------|-----------------------------|
| Pipeline code (`stages/`, `lib/`, `prism_benchmark/`) | Open-source under [MIT License](../LICENSE) (software only) |
| Prompt templates, rules, query spreadsheets | Research artifacts distributed with the benchmark |
| Long-form case narrative text in `*.jsonl` | **Third-party published content** included for benchmark reproducibility; **cite the DOI**; comply with publisher terms |

### Recommended citation practice

Also cite the PRISM-Med paper and this repository as described in the root [README.md](../README.md).

## Files (overview)

| Path | Role |
|------|------|
| `Challenge_Dataset/cases.jsonl` | Challenge-set case catalog (DOI-linked vignettes) |
| `SDoH_Dataset/cases.jsonl` | SDoH benchmark branch cases (includes scenario variants) |
| `question/query_question.xlsx` | Active query / case index for full runs (942 rows in full mode) |
| `question/query_question.full.xlsx` | Backup of full query table |
| `classification_rule/` | Adjudication prompts and rules |

For pipeline behavior and pillar 3 external data, see [docs/BENCHMARK.md](../docs/BENCHMARK.md).
