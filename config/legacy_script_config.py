from __future__ import annotations

import os
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = PROJECT_ROOT / "dataset"
PROMPT_DIR = PROJECT_ROOT / "prompt"
CASES_CATALOG_FILENAME = "cases.jsonl"
BENCHMARK_DIR = PROJECT_ROOT / "benchmark"

ROUND_NUM_LIST: List[str] = ["1_5answer", "1_5answer_1", "1_5answer_2"]

# =============================================================================
# Test subject models (shared across base / reasoning / SDoH-bias benchmarks).
# Override per dimension via PRISM_*_MODELS (comma-separated) without editing code.
# =============================================================================
DEFAULT_MODEL_LIST: List[str] = [
    "gemini-3.5-flash",
    "gpt-5.5"
    # "deepseek-v3.2-thinking",
    # "gpt-5.1-high",
    # "grok-4.1",
    # "gemini-3-pro-preview",
    # "o3-pro-2025-06-10",
    # "gemini-2.5-pro",
    # "gpt-5-2025-08-07",
    # "gpt-5-mini-2025-08-07",
    # "glm-4.5",
    # "o3-2025-04-16",
    # "claude-sonnet-4-20250514",
    # "claude-sonnet-4-5-20250929",
    # "deepseek-v3-1-250821",
    # "gemini-2.5-flash",
    # "gpt-4o-2024-11-20",
    # "o4-mini-2025-04-16",
]

TEST_SUBJECT_MODEL_LIST: List[str] = DEFAULT_MODEL_LIST

# Canonical English names (match renamed assets under benchmark/, prompt/, results/).
REFERENCE_TABLE_BIAS_XLSX = "reference_table_bias_with_doi.xlsx"
BIAS_COUNT_PROMPT_FILENAME = "bias_count_diagnosis_directions.txt"
DEFAULT_BIAS_ANALYSIS_DIRNAME = "bias_analysis_second_gpt5_bias_diagnosis"
# Full-run SDoH count (289 cases): upstream repo copy, not the 5-case subset stub under opensource_prism/results/.
FULL_BIAS_ANALYSIS_SOURCE_DIRNAME = "bias_analysis_second_gpt5_bias_diagnosis"
_LEGACY_BIAS_ANALYSIS_PARENT_DIRNAMES: tuple[str, ...] = (
    "bias_analysis_second_gpt5_偏见诊断",
)
MIN_FULL_BIAS_ANALYSIS_DIRS = 200


def parent_bias_analysis_source_candidates(parent_repo_root: Path) -> List[Path]:
    """English dirname first; legacy Chinese dirname for older parent checkouts."""
    results = parent_repo_root / "results"
    names: List[str] = [FULL_BIAS_ANALYSIS_SOURCE_DIRNAME]
    for legacy in _LEGACY_BIAS_ANALYSIS_PARENT_DIRNAMES:
        if legacy not in names:
            names.append(legacy)
    return [results / name for name in names]


def resolve_parent_bias_analysis_source(parent_repo_root: Path) -> Path | None:
    best: Path | None = None
    best_n = 0
    for candidate in parent_bias_analysis_source_candidates(parent_repo_root):
        if not candidate.is_dir():
            continue
        n = sum(1 for d in candidate.iterdir() if d.is_dir())
        if n > best_n:
            best_n = n
            best = candidate
    return best
SCENARIO1_BIAS_JSON_KEY = "scenario1_low_ses_misdiagnosis_direction"
SCENARIO2_BIAS_JSON_KEY = "scenario2_high_ses_misdiagnosis_direction"

def get_env_list(name: str, default: List[str]) -> List[str]:
    """Read a comma-separated environment variable as a list."""
    raw_value = os.getenv(name)
    if not raw_value:
        return list(default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def get_env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    return int(raw_value) if raw_value else default


def get_env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    return float(raw_value) if raw_value else default


# Shared benchmark paths (anchored on PROJECT_ROOT; cwd should still be opensource_prism for legacy scripts).
CHALLENGE_DATASET_ROOT = str(PROJECT_ROOT / "dataset" / "Challenge_Dataset")
SDOH_DATASET_ROOT = str(PROJECT_ROOT / "dataset" / "SDoH_Dataset")
# Legacy constant names kept for existing stage imports.
MERGED_DATASET_ROOT = CHALLENGE_DATASET_ROOT
MERGED_DATASET_WITH_ROLE_ROOT = SDOH_DATASET_ROOT
BENCHMARK_PROMPT_PATH = str(PROJECT_ROOT / "prompt" / "benchmark.txt")
FORMAT_CHECKER_PATH = str(PROJECT_ROOT / "prompt" / "formatChecker_noprompt_5answer.txt")
QUERY_EXCEL_PATH = str(PROJECT_ROOT / "dataset" / "question" / "query_question.xlsx")
CLASSIFICATION_RULE_EXCEL_PATH = str(PROJECT_ROOT / "dataset" / "classification_rule" / "classification_rule.xlsx")
CLASSIFICATION_RULE_SHEET_NAME = os.getenv("PRISM_CLASSIFICATION_SHEET", "Sheet1")
CLASSIFICATION_RULE_PROMPT_PATH = str(
    PROJECT_ROOT / "dataset" / "classification_rule" / "classification_prompt_benchmark.txt"
)
CLASSIFICATION_RULE_SUMMARY_PROMPT_PATH = str(
    PROJECT_ROOT / "dataset" / "classification_rule" / "classification_prompt_benchmark_summary.txt"
)
REASONING_JUDGER_PROMPT_PATH = str(PROJECT_ROOT / "prompt" / "prompt_benchmark_reasoning_judger.txt")
REASONING_SUMMARY_PROMPT_PATH = str(PROJECT_ROOT / "prompt" / "prompt_benchmark_reasoning_judger_summary.txt")

BIAS_COUNT_PROMPT_TEMPLATE_PATH = PROMPT_DIR / BIAS_COUNT_PROMPT_FILENAME
DEFAULT_BIAS_ANALYSIS_ROOT = PROJECT_ROOT / "results" / DEFAULT_BIAS_ANALYSIS_DIRNAME
BIAS_ANALYSIS_ROOT = Path(
    os.getenv("PRISM_BIAS_ANALYSIS_ROOT", str(DEFAULT_BIAS_ANALYSIS_ROOT))
)

# Default API base URL for proxy/aggregator providers used by some legacy scripts.
DEFAULT_API_BASE_URL = os.getenv("PRISM_DEFAULT_API_BASE_URL", "https://yunwu.ai/v1")

# Per-dimension model lists (default: DEFAULT_MODEL_LIST).
BASE_ASK_MODEL_LIST = get_env_list("PRISM_BASE_ASK_MODELS", DEFAULT_MODEL_LIST)
BIAS_ASK_MODEL_LIST = get_env_list("PRISM_BIAS_ASK_MODELS", DEFAULT_MODEL_LIST)
REASONING_MODEL_LIST = get_env_list("PRISM_REASONING_MODELS", DEFAULT_MODEL_LIST)
REASONING_SUMMARY_MODEL_LIST = get_env_list("PRISM_REASONING_SUMMARY_MODELS", DEFAULT_MODEL_LIST)
COUNT_TARGET_MODEL_LIST = get_env_list("PRISM_COUNT_TARGET_MODELS", DEFAULT_MODEL_LIST)
CLASSIFICATION_MODEL_LIST = get_env_list("PRISM_CLASSIFICATION_MODELS", DEFAULT_MODEL_LIST)

# Judge / checker / counter models (not test subjects).
DEFAULT_CHECKER_MODEL = os.getenv("PRISM_CHECKER_MODEL", "gpt-5.4-nano")
DEFAULT_COUNT_MODEL = os.getenv("PRISM_COUNT_MODEL", "gpt-5.4")
REASONING_LLM_MODEL = os.getenv("PRISM_REASONING_LLM_MODEL", "gemini-2.5-pro")

# Shared run settings.
BENCHMARK_DATASET_NAME = os.getenv("PRISM_DATASET_NAME", "benchmark")
CLASSIFICATION_MAX_WORKER = get_env_int("PRISM_CLASSIFICATION_MAX_WORKER", 5)
CLASSIFICATION_RUN_LIST = [int(item) for item in get_env_list("PRISM_CLASSIFICATION_RUNS", ["1", "2"])]
CLASSIFICATION_SUMMARY_RUN_LIST = [
    int(item) for item in get_env_list("PRISM_CLASSIFICATION_SUMMARY_RUNS", ["1", "2"])
]
REASONING_RUN_LIST = get_env_list("PRISM_REASONING_RUNS", ["", "1"])
REASONING_SUMMARY_RUN_LIST = get_env_list("PRISM_REASONING_SUMMARY_RUNS", ["", "1"])
REASONING_TEMPERATURE = get_env_float("PRISM_REASONING_TEMPERATURE", 0)
REASONING_MAX_WORKERS = get_env_int("PRISM_REASONING_MAX_WORKERS", 3)
REASONING_SUMMARY_MAX_WORKERS = get_env_int("PRISM_REASONING_SUMMARY_MAX_WORKERS", 5)
BIAS_ASK_MAX_WORKERS = get_env_int("PRISM_BIAS_ASK_MAX_WORKERS", 5)
BIAS_ASK_BATCH_SIZE = get_env_int("PRISM_BIAS_ASK_BATCH_SIZE", 5)
BASE_COUNT_MAX_WORKERS = get_env_int("PRISM_BASE_COUNT_MAX_WORKERS", 5)
BIAS_COUNT_MAX_WORKERS = get_env_int("PRISM_BIAS_COUNT_MAX_WORKERS", 5)

# Composite score settings.
SSR_THRESHOLD = get_env_float("PRISM_SCORE_SSR_THRESHOLD", 0.30)
NET_CHANGE_DENOM = get_env_float("PRISM_SCORE_NET_CHANGE_DENOM", 0.15)
WEIGHT_ACC = get_env_float("PRISM_SCORE_WEIGHT_ACC", 60)
WEIGHT_COV_INC = get_env_float("PRISM_SCORE_WEIGHT_COV_INC", 30)
WEIGHT_RELIABILITY = get_env_float("PRISM_SCORE_WEIGHT_RELIABILITY", 30)
WEIGHT_IR = get_env_float("PRISM_SCORE_WEIGHT_IR", 3)
WEIGHT_SSR = get_env_float("PRISM_SCORE_WEIGHT_SSR", 3)
WEIGHT_NET_ACC = get_env_float("PRISM_SCORE_WEIGHT_NET_ACC", 3)
WEIGHT_NET_COV = get_env_float("PRISM_SCORE_WEIGHT_NET_COV", 1)



def resolve_reference_table_path(benchmark_dir: Path | None = None) -> Path:
    """Return bias reference workbook path under the benchmark directory."""
    base = benchmark_dir if benchmark_dir is not None else resolve_benchmark_dir()
    return base / REFERENCE_TABLE_BIAS_XLSX


def resolve_benchmark_dir() -> Path:
    candidates = [
        BENCHMARK_DIR,
        PROJECT_ROOT.parent / "benchmark",
    ]
    key_files = ("benchmark_score_inputs.xlsx", REFERENCE_TABLE_BIAS_XLSX)
    for candidate in candidates:
        if any((candidate / key).exists() for key in key_files):
            return candidate
    for candidate in candidates:
        if (candidate / "result").exists():
            return candidate
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
