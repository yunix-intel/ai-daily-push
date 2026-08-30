#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 辅助函数 - 统一的 LLM 调用接口
"""
import json
import os
import re
import urllib.request


def _llm_config():
    """读取 LLM 配置"""
    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(here, "push_config.json")

    if not os.path.exists(cfg_path):
        return None, None, None, None

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        api_key = cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        base_url = cfg.get("openai_base_url", "https://api.openai.com/v1")
        translate_model = cfg.get("translate_model", "deepseek-v4-flash")
        analysis_model = cfg.get("analysis_model", "gpt-4o")

        return api_key, base_url, translate_model, analysis_model
    except Exception as e:
        print(f"  [WARN] LLM 配置读取失败：{e}")
        return None, None, None, None


def call_llm_json(system_prompt, user_prompt, retries=2, model=None, timeout=180):
    """
    调用 OpenAI 兼容接口并解析 JSON 对象

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        retries: 重试次数
        model: 模型名称（可选，默认使用配置文件中的翻译模型）
        timeout: 超时时间（秒）

    Returns:
        dict: 解析后的 JSON 对象

    Raises:
        RuntimeError: 配置错误或调用失败
    """
    api_key, base_url, translate_model, _analysis_model = _llm_config()

    if not api_key:
        raise RuntimeError("未配置 OPENAI_API_KEY")

    payload = {
        "model": model or translate_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_exc = None

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {api_key}",
                },
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))

            content = body["choices"][0]["message"]["content"]

            # 有些网关会把 JSON 包在 ```json fence 里，剥掉再解析
            content = re.sub(r"^\s*```(?:json)?|```\s*$", "", content.strip())

            return json.loads(content)

        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                print(f"     LLM 调用失败，重试 {attempt + 1}/{retries}...")
                continue

    raise last_exc


def call_llm(system_prompt, user_prompt, retries=2, model=None, timeout=180):
    """
    调用 OpenAI 兼容接口并返回纯文本

    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        retries: 重试次数
        model: 模型名称（可选）
        timeout: 超时时间（秒）

    Returns:
        str: LLM 返回的文本内容

    Raises:
        RuntimeError: 配置错误或调用失败
    """
    api_key, base_url, translate_model, _analysis_model = _llm_config()

    if not api_key:
        raise RuntimeError("未配置 OPENAI_API_KEY")

    payload = {
        "model": model or translate_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_exc = None

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=data,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {api_key}",
                },
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))

            content = body["choices"][0]["message"]["content"]
            return content.strip()

        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                print(f"     LLM 调用失败，重试 {attempt + 1}/{retries}...")
                continue

    raise last_exc


# 测试函数
if __name__ == "__main__":
    print("测试 LLM 调用...")

    try:
        # 测试 JSON 调用
        result = call_llm_json(
            "你是一个测试助手。",
            '返回 JSON: {"message": "Hello World", "status": "ok"}'
        )
        print(f"JSON 调用成功: {result}")

        # 测试文本调用
        text = call_llm(
            "你是一个测试助手。",
            "用一句话介绍 AI。"
        )
        print(f"文本调用成功: {text}")

    except Exception as e:
        print(f"测试失败: {e}")
