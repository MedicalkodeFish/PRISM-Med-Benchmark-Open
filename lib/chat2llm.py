import aiohttp
import time
import requests
import json
import os
from model_config import api_config
from model_config import checker_model_list
from model_config import resolve_model
import asyncio
from openai import OpenAI
from openai import AsyncOpenAI
import random


async def async_chat_claude(prompt: str, model: str, temperature: float = 1) -> str:
    max_retries = 4
    retry_delay = 2
    attempt = 0
    timeout = 400

    while attempt < max_retries:
        attempt += 1
        try:
            print(f"Communicating with {model} (attempt {attempt}/{max_retries})\nContent: {prompt}")

            model_cfg = resolve_model(model)
            if not model_cfg:
                raise ValueError(f"Configuration not found for model {model}")

            if "deepseek" in model.lower():
                client = None
                try:
                    client = AsyncOpenAI(
                        api_key=model_cfg['api_key'],
                        base_url=model_cfg['url']
                    )

                    completion = await client.chat.completions.create(
                        model=model_cfg["model_id"],
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                    )

                    response_content = completion.choices[0].message.content

                    error_keywords = ["请求错误", "connection error"]
                    if any(keyword in response_content.lower() for keyword in error_keywords) or len(
                            response_content) < 40:
                        raise Exception(
                            f"{model} LLM response contains error text or is too short: {response_content[:1000]}..."
                        )

                    return response_content, str(completion)

                except Exception as e:
                    if attempt >= max_retries:
                        raise Exception(f"{model} API call failed after {max_retries} retries: {str(e)}")
                    print(
                        f"{model} API call failed (attempt {attempt}/{max_retries}): {str(e)}; "
                        f"retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                finally:
                    if client:
                        await client.close()
            elif "o3-pro" in model.lower():
                payload = json.dumps({
                    "model": model,
                    "input": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                })
                headers = {
                    'Accept': 'application/json',
                    "Authorization": "Bearer " + model_cfg['api_key'],
                    "Content-Type": "application/json"
                }
                async with aiohttp.ClientSession() as session:
                    async with session.post("https://yunwu.ai/v1/responses", headers=headers, data=payload) as response:
                        if response.status == 200:
                            data = await response.text()
                            response_data = json.loads(data)
                            if 'output' in response_data and len(response_data['output']) > 1 and 'content' in response_data['output'][1] and response_data['output'][1]['content'] and 'text' in response_data['output'][1]['content'][0]:
                                result = response_data['output'][1]['content'][0]['text']
                            else:
                                result = data
                            return result, response_data
                        else:
                            raise Exception(f"API call failed: {response.status}")
            else:
                headers = {
                    "Authorization": model_cfg["api_key"],
                    "Content-Type": "application/json"
                }

                data = {
                    "messages": [{"role": "user", "content": prompt}],
                    "model": model_cfg["model_id"],
                    "temperature": temperature,
                    "stream": False
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(model_cfg["url"] + "/chat/completions", headers=headers, json=data,
                                            timeout=timeout) as response:
                        if response.status == 200:
                            result = await response.json()
                            response_content = result['choices'][0]['message']['content']

                            error_keywords = ["请求错误", "connection error"]
                            if any(keyword in response_content.lower() for keyword in error_keywords) or len(
                                    response_content) < 40:
                                raise Exception(
                                    f"LLM response contains error text or is too short: {response_content[:1000]}..."
                                )

                            return response_content, result
                        else:
                            error_text = await response.text()
                            if attempt >= max_retries:
                                raise Exception(
                                    f"{model} API call failed after {max_retries} retries: "
                                    f"{response.status}, {error_text}"
                                )
                            print(
                                f"{model} API call failed (attempt {attempt}/{max_retries}): "
                                f"{response.status}, {error_text}; retrying in {retry_delay}s..."
                            )
                            await asyncio.sleep(retry_delay)
                            continue
        except Exception as e:
            if attempt >= max_retries:
                raise Exception(
                    f"Error while requesting {model} after {max_retries} retries: {str(e)}"
                )
            print(
                f"Error while requesting {model} (attempt {attempt}/{max_retries}): {str(e)}; "
                f"retrying in {retry_delay}s..."
            )
            await asyncio.sleep(retry_delay)

    raise Exception(f"Still failed after {max_retries} attempts")


def chat_claude(prompt, path_record, log_record, model_list=checker_model_list):
    model = random.choice(model_list)

    max_retries = 4
    retry_delay = 2
    attempt = 0
    timeout = 300

    while attempt < max_retries:
        attempt += 1
        start_time = time.time()

        try:
            print(f"Communicating with {model} (attempt {attempt}/{max_retries})")

            model_config = resolve_model(model)
            if not model_config:
                raise ValueError(f"Configuration not found for model {model}")

            if "deepseek" in model.lower():
                client = OpenAI(
                    api_key=model_config['api_key'],
                    base_url=model_config['url']
                )

                result = ""
                log_string = ""

                try:
                    response = client.chat.completions.create(
                        model=model_config.get("model_id") or model_config["id"],
                        messages=[
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0,
                        stream=True,
                        timeout=timeout
                    )

                    for chunk in response:
                        if chunk.choices and len(chunk.choices) > 0:
                            delta = chunk.choices[0].delta
                            if delta.content:
                                content = delta.content
                                result += content
                                print(content, end='', flush=True)
                                log_string += json.dumps({"choices": [{"delta": {"content": content}}]}) + "\n"

                    print("\n")

                    error_keywords = ["请求错误", "connection error"]
                    if any(keyword in result.lower() for keyword in error_keywords) or len(result) < 40:
                        if attempt >= max_retries:
                            raise Exception(
                                f"LLM response contains error text or is too short after {max_retries} retries: "
                                f"{result[:1000]}..."
                            )
                        print(
                            f"LLM response contains error text or is too short "
                            f"(attempt {attempt}/{max_retries}); retrying in {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                        continue

                    end_time = time.time()
                    total_time = "total_elapsed_sec: {:.2f}s".format(end_time - start_time)
                    print(total_time)

                    try:
                        with open(log_record, "w", encoding="utf-8") as f:
                            f.write(log_string)
                    except Exception as e:
                        print(f"Failed to save log file: {str(e)}")

                    try:
                        os.makedirs(os.path.dirname(path_record), exist_ok=True)
                        with open(path_record, "w", encoding="utf-8") as f:
                            f.write(result)
                            print("txt response saved")
                    except Exception as e:
                        print(f"Failed to save result file: {str(e)}")

                    try:
                        prompt_path = path_record.replace(".txt", "format_prompt.txt")
                        with open(prompt_path, "w", encoding="utf-8") as f:
                            f.write(prompt)
                    except Exception as e:
                        print(f"Failed to save prompt file: {str(e)}")

                    return result

                except Exception as e:
                    if attempt >= max_retries:
                        print(f"Request error after {max_retries} retries: {str(e)}")
                        result = f"Error: Request failed after {max_retries} attempts - {str(e)}"
                        return result
                    print(
                        f"Request error (attempt {attempt}/{max_retries}): {str(e)}; "
                        f"retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    continue

            else:
                headers = {
                    "Authorization": model_config["api_key"],
                    "Content-Type": "application/json"
                }

                data = {
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    "model": model_config.get("model_id") or model_config["id"],
                    "max_tokens_to_sample": 4090,
                    "temperature": 0,
                    "stream": True
                }

                result = ""
                log_string = ""

                try:
                    with requests.post(model_config["url"], headers=headers, json=data, stream=True,
                                       timeout=timeout) as response:
                        if response.status_code == 200:
                            for line in response.iter_lines():
                                if line:
                                    decoded_line = line.decode('utf-8')
                                    log_string += decoded_line + "\n"
                                    if decoded_line.startswith('data: '):
                                        try:
                                            json_data = json.loads(decoded_line[6:])
                                            if 'choices' in json_data and len(json_data['choices']) > 0:
                                                delta = json_data['choices'][0].get('delta', {})
                                                if 'content' in delta:
                                                    content = delta['content']
                                                    result += content
                                                    print(content, end='', flush=True)
                                        except json.JSONDecodeError:
                                            pass
                            print("\n")

                            error_keywords = ["请求错误", "connection error"]
                            if any(keyword in result.lower() for keyword in error_keywords) or len(result) < 40:
                                if attempt >= max_retries:
                                    raise Exception(
                                        f"LLM response contains error text or is too short after {max_retries} retries: "
                                        f"{result[:1000]}..."
                                    )
                                print(
                                    f"LLM response contains error text or is too short "
                                    f"(attempt {attempt}/{max_retries}); retrying in {retry_delay}s..."
                                )
                                time.sleep(retry_delay)
                                continue

                            end_time = time.time()
                            total_time = "total_elapsed_sec: {:.2f}s".format(end_time - start_time)
                            print(total_time)

                            try:
                                with open(log_record, "w", encoding="utf-8") as f:
                                    f.write(log_string)
                            except Exception as e:
                                print(f"Failed to save log file: {str(e)}")

                            try:
                                os.makedirs(os.path.dirname(path_record), exist_ok=True)
                                with open(path_record, "w", encoding="utf-8") as f:
                                    f.write(result)
                                    print("txt response saved")
                            except Exception as e:
                                print(f"Failed to save result file: {str(e)}")

                            try:
                                prompt_path = path_record.replace(".txt", "format_prompt.txt")
                                with open(prompt_path, "w", encoding="utf-8") as f:
                                    f.write(prompt)
                            except Exception as e:
                                print(f"Failed to save prompt file: {str(e)}")

                            return result

                        else:
                            if attempt >= max_retries:
                                print(f"Error: {response.status_code}")
                                print(response.text)
                                result = f"Error: {response.status_code}\n{response.text}"
                                return result
                            print(
                                f"API call failed (attempt {attempt}/{max_retries}): {response.status_code}; "
                                f"retrying in {retry_delay}s..."
                            )
                            time.sleep(retry_delay)
                            continue

                except Exception as e:
                    if attempt >= max_retries:
                        print(f"Request error after {max_retries} retries: {str(e)}")
                        result = f"Error: Request failed after {max_retries} attempts - {str(e)}"
                        return result
                    print(
                        f"Request error (attempt {attempt}/{max_retries}): {str(e)}; "
                        f"retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    continue

        except Exception as e:
            if attempt >= max_retries:
                print(f"Request error after {max_retries} retries: {str(e)}")
                return f"Error: Request failed after {max_retries} attempts - {str(e)}"
            print(
                f"Request error (attempt {attempt}/{max_retries}): {str(e)}; "
                f"retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)

    return f"Error: Still failed after {max_retries} attempts"
