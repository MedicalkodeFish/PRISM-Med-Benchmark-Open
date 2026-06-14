# -*- coding: utf-8 -*-
"""Simple OpenAI chat client for base_count / bias_count stages."""
from __future__ import annotations

import time

import openai


def chat_LLM(prompt, model, api_key, url):
    max_retries = 3
    retry_count = 0
    client = openai.OpenAI(base_url=url, api_key=api_key, timeout=250)

    while retry_count < max_retries:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.choices[0].message.content
            failure_keywords = ["失败", "错误", "通讯失败", "请求失败"]
            if any(keyword in result.lower() for keyword in failure_keywords):
                retry_count += 1
                time.sleep(0.5)
                continue
            return result
        except Exception as e:
            print(f"Error: {str(e)}, retrying ({retry_count + 1}/{max_retries})")
            retry_count += 1
            time.sleep(0.5)
    return None
