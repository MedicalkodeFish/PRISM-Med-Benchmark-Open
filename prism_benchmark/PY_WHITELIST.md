# Python Whitelist (Benchmark Mainline)

## Repository root

- model_config.py
- prism_bootstrap.py

## config/

- config/legacy_script_config.py

## lib/ (shared libraries)

- lib/async_runtime.py
- lib/ask_llm_client.py
- lib/benchmark_paths.py
- lib/benchmark_sdoh_utils.py
- lib/bias_count_common.py
- lib/chat2llm.py
- lib/classification_benchmark_common.py
- lib/classification_benchmark_pipeline.py
- lib/count_llm_client.py
- lib/count_stage_health.py
- lib/count_stage_runner.py
- lib/extract_json_from_txt.py
- lib/flaws_excel.py
- lib/llm_connection_utils.py
- lib/reasoning_flaws_aggregate.py
- lib/reasoning_flaws_constants.py
- lib/reasoning_flaws_json.py
- lib/sdoh_ref_metrics.py

## stages/ (pipeline entry scripts)

- stages/analyze_bias_comparison.py
- stages/base_ask.py
- stages/base_count.py
- stages/benchmark_audit_workbook.py
- stages/bias_ask_.py
- stages/bias_count.py
- stages/classification_json_benchmark.py
- stages/classification_json_benchmark_summary.py
- stages/classification_json_bias_benchmark.py
- stages/classification_majority_vote_and_score_input.py
- stages/compute_composite_benchmark_score.py
- stages/judge_reasoning_flaws.py
- stages/judge_reasoning_flaws_summary.py
- stages/_bootstrap.py

## prism_benchmark package

- prism_benchmark/scripts/benchmark_verify.py
- prism_benchmark/scripts/benchmark_coverage.py
- prism_benchmark/scripts/benchmark_run_report.py
- prism_benchmark/scripts/data_assets_check.py
- prism_benchmark/scripts/list_missing_cases.py
- prism_benchmark/scripts/prepare_full_benchmark_data.py
- prism_benchmark/scripts/run_pipeline.py
- prism_benchmark/src/prism_benchmark/__init__.py
- prism_benchmark/src/prism_benchmark/config.py
- prism_benchmark/src/prism_benchmark/composite.py
- prism_benchmark/src/prism_benchmark/pipeline.py
- prism_benchmark/src/prism_benchmark/pathing.py
- prism_benchmark/src/prism_benchmark/steps.py
- prism_benchmark/src/prism_benchmark/legacy_registry.py
- prism_benchmark/src/prism_benchmark/stages/__init__.py
- prism_benchmark/src/prism_benchmark/stages/_invoke.py
- prism_benchmark/src/prism_benchmark/stages/base_ask_stage.py
- prism_benchmark/src/prism_benchmark/stages/classification_stage.py
- prism_benchmark/src/prism_benchmark/stages/reasoning_stage.py
- prism_benchmark/src/prism_benchmark/stages/sdoh_stage.py
- prism_benchmark/src/prism_benchmark/stages/metrics_stage.py
