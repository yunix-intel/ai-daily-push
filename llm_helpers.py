#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 辅助函数 - 统一的 LLM 调用接口
"""
import json
import os
import re
import time
import urllib.request


_BASE_URL_WARNED = False


def _llm_config():
    """读取 LLM 配置。

    环境变量优先于配置文件：生产环境（GitHub Actions）只发环境变量，
    push_config.json 里这几项是空字符串。之前用 cfg.get(key, default)，
    空字符串是「存在的值」，default 不会生效，base_url 变成 ""，
    拼出来的请求地址就是 "/chat/completions"，报 unknown url type。
    模型名同理，不能写死 gpt-4o —— 自建网关没挂这个模型。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(here, "push_config.json")

    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"  [WARN] LLM 配置读取失败：{e}")

    api_key = (os.getenv("OPENAI_API_KEY") or cfg.get("openai_api_key") or "").strip()
    base_url = ((os.getenv("OPENAI_BASE_URL") or cfg.get("openai_base_url") or
                 "https://api.openai.com/v1").strip().rstrip("/"))
    translate_model = (os.getenv("OPENAI_MODEL_TRANSLATE")
                       or cfg.get("openai_model_translate")
                       or cfg.get("translate_model") or "deepseek-v4-flash").strip()
    analysis_model = (os.getenv("OPENAI_MODEL_ANALYSIS")
                      or cfg.get("openai_model_analysis")
                      or cfg.get("analysis_model") or "gpt-5.6-sol").strip()

    if not api_key:
        return None, None, None, None

    # 没配 OPENAI_BASE_URL 时不要静默走官方地址：默认模型名只挂在自建网关上，
    # 官方 OpenAI 没有这些模型，请求必然 401，还会把自建网关的 key 发给第三方。
    global _BASE_URL_WARNED
    if not _BASE_URL_WARNED and base_url == "https://api.openai.com/v1":
        _BASE_URL_WARNED = True
        print("  [WARN] 未设置 OPENAI_BASE_URL，将请求官方 api.openai.com。")
        print("         若 key 属于自建网关，请求会以 401 失败，且 key 已发往第三方。")

    return api_key, base_url, translate_model, analysis_model


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
                # 带上异常内容：只打印「调用失败」会把 504 超时、401 认证、
                # 模型名不存在这些完全不同的原因混成一句话，没法定位。
                print(f"     LLM 调用失败（{exc!r}），重试 {attempt + 1}/{retries}...")
                # 504/429 是网关瞬时压力，退避后再试
                time.sleep(3 * (attempt + 1))
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
                # 带上异常内容：只打印「调用失败」会把 504 超时、401 认证、
                # 模型名不存在这些完全不同的原因混成一句话，没法定位。
                print(f"     LLM 调用失败（{exc!r}），重试 {attempt + 1}/{retries}...")
                # 504/429 是网关瞬时压力，退避后再试
                time.sleep(3 * (attempt + 1))
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
