# -*- coding: utf-8 -*-
"""OpenAI chat helpers with on-disk recording (base_ask / bias_ask profiles)."""
from __future__ import annotations

import http.client
import json
import time
from typing import Any, Optional, Tuple

import openai

from llm_connection_utils import (
    ensure_parent_file,
    is_connection_error_text,
    response_has_failure_keywords,
)

O3_PRO_MODEL_ID = "o3-pro-2025-06-10"


def _write_success_records(
    *,
    log_record: str,
    path_record: str,
    prompt_record: str,
    prompt: str,
    result: str,
    response_for_log: Any,
    total_time: str,
    verbose: bool,
) -> None:
    ensure_parent_file(log_record)
    ensure_parent_file(path_record)
    ensure_parent_file(prompt_record)
    with open(log_record, "w", encoding="utf-8") as f:
        f.write(str(response_for_log) + "\n" + total_time)
    with open(path_record, "w", encoding="utf-8") as f:
        f.write(result + "\n" + total_time)
    with open(prompt_record, "w", encoding="utf-8") as f:
        f.write(prompt + "\n" + total_time)
    if verbose:
        print(f"Saved log file: {log_record}")
        print(f"Saved result file: {path_record}")
        print(f"Saved prompt file: {prompt_record}")


def _chat_o3_pro_recorded(
    prompt,
    path_record,
    prompt_record,
    log_record,
    model,
    api,
    *,
    max_retries: int,
    time_label: str,
) -> Tuple[Optional[str], Any]:
    start_time = time.time()
    retry_count = 0
    while retry_count < max_retries:
        try:
            conn = http.client.HTTPSConnection("yunwu.ai")
            payload = json.dumps(
                {
                    "model": model,
                    "input": [{"role": "user", "content": prompt}],
                }
            )
            headers = {
                "Accept": "application/json",
                "Authorization": "Bearer " + api,
                "Content-Type": "application/json",
            }
            conn.request("POST", "/v1/responses", payload, headers)
            res = conn.getresponse()
            data = res.read().decode("utf-8")
            response_data = json.loads(data)
            if (
                "output" in response_data
                and len(response_data["output"]) > 1
                and "content" in response_data["output"][1]
                and response_data["output"][1]["content"]
                and "text" in response_data["output"][1]["content"][0]
            ):
                result = response_data["output"][1]["content"][0]["text"]
            else:
                result = data
            total_time = f"{time_label}: {time.time() - start_time:.2f}s"
            if response_has_failure_keywords(result):
                print(
                    f"Model {model} reply contains failure keywords: '{result}' — "
                    f"retrying ({retry_count + 1}/{max_retries})"
                )
                retry_count += 1
                time.sleep(2)
                continue
            _write_success_records(
                log_record=log_record,
                path_record=path_record,
                prompt_record=prompt_record,
                prompt=prompt,
                result=result,
                response_for_log=response_data,
                total_time=total_time,
                verbose=True,
            )
            return result, response_data
        except Exception as e:
            print(f"Model {model} request error: {str(e)}, retrying ({retry_count + 1}/{max_retries})")
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(2)
            else:
                ensure_parent_file(log_record)
                with open(log_record, "w", encoding="utf-8") as f:
                    f.write(f"Error: {str(e)}\n")
                print(f"Saved error log: {log_record}")
                return None, None
    ensure_parent_file(log_record)
    with open(log_record, "w", encoding="utf-8") as f:
        f.write(f"Error: max retries ({max_retries}) exceeded; request still failed\n")
    print(f"Saved error log: {log_record}")
    return None, None


def _chat_openai_recorded(
    prompt,
    path_record,
    prompt_record,
    log_record,
    model,
    api,
    url,
    *,
    max_retries: int,
    connection_aware: bool,
    failure_keyword_retry: bool,
    time_label: str,
    verbose: bool,
) -> Tuple[Optional[str], Any]:
    start_time = time.time()
    retry_count = 0
    client = openai.OpenAI(base_url=url, api_key=api, timeout=200)

    while retry_count < max_retries:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.choices[0].message.content or ""

            if connection_aware and is_connection_error_text(result):
                retry_count += 1
                ensure_parent_file(log_record)
                with open(log_record, "w", encoding="utf-8") as f:
                    f.write(
                        f"Connection-like text detected in response. "
                        f"retry={retry_count}/{max_retries}\n"
                    )
                time.sleep(5)
                continue

            if failure_keyword_retry and response_has_failure_keywords(result):
                if verbose:
                    print(
                        f"Model {model} reply contains failure keywords: '{result}' — "
                        f"retrying ({retry_count + 1}/{max_retries})"
                    )
                retry_count += 1
                time.sleep(2)
                continue

            if connection_aware:
                total_time = f"Total time: {time.time() - start_time:.2f}s"
            else:
                total_time = f"{time_label}: {time.time() - start_time:.2f}s"

            _write_success_records(
                log_record=log_record,
                path_record=path_record,
                prompt_record=prompt_record,
                prompt=prompt,
                result=result,
                response_for_log=response,
                total_time=total_time,
                verbose=verbose,
            )
            return result, response

        except Exception as e:
            msg = str(e) if e is not None else ""
            retry_count += 1
            if connection_aware and is_connection_error_text(msg):
                ensure_parent_file(log_record)
                with open(log_record, "w", encoding="utf-8") as f:
                    f.write(
                        f"Connection error exception: {msg}\n"
                        f"retry={retry_count}/{max_retries}\n"
                    )
                time.sleep(5)
                continue
            if verbose:
                print(f"Model {model} request error: {msg}, retrying ({retry_count}/{max_retries})")
            if retry_count < max_retries:
                time.sleep(2)
                continue
            ensure_parent_file(log_record)
            with open(log_record, "w", encoding="utf-8") as f:
                f.write(f"Error: {msg}\n" if not connection_aware else f"Error: {msg}\n")
            if verbose:
                print(f"Saved error log: {log_record}")
            return None, None

    if connection_aware:
        return None, None
    ensure_parent_file(log_record)
    with open(log_record, "w", encoding="utf-8") as f:
        f.write(f"Error: max retries ({max_retries}) exceeded; request still failed\n")
    if verbose:
        print(f"Saved error log: {log_record}")
    return None, None


def chat_LLM_base_ask(prompt, path_record, prompt_record, log_record, model, api=None, url=None):
    return _chat_openai_recorded(
        prompt,
        path_record,
        prompt_record,
        log_record,
        model,
        api,
        url,
        max_retries=5,
        connection_aware=True,
        failure_keyword_retry=False,
        time_label="Total time",
        verbose=False,
    )


def chat_LLM_bias_ask(prompt, path_record, prompt_record, log_record, model, api=None, url=None):
    if model == O3_PRO_MODEL_ID:
        return _chat_o3_pro_recorded(
            prompt,
            path_record,
            prompt_record,
            log_record,
            model,
            api,
            max_retries=3,
            time_label="total_elapsed_sec",
        )
    return _chat_openai_recorded(
        prompt,
        path_record,
        prompt_record,
        log_record,
        model,
        api,
        url,
        max_retries=3,
        connection_aware=False,
        failure_keyword_retry=True,
        time_label="total_elapsed_sec",
        verbose=True,
    )
