#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 翻译服务模块
支持分段翻译长文章
"""

import json
import os
import re

# 翻译任务跟着翻译模型走，与 finance_daily_push / ai_daily_push 使用同一环境变量。
TRANSLATE_MODEL_DEFAULT = "deepseek-v4-flash"


def _translate_model():
    """全文翻译使用的模型。"""
    return (os.environ.get("OPENAI_MODEL_TRANSLATE") or TRANSLATE_MODEL_DEFAULT).strip()


def translate_article_llm(article_text, call_llm_func, max_chars_per_batch=3000):
    """
    使用 LLM 翻译文章，分段处理

    Args:
        article_text: 原文文本
        call_llm_func: LLM 调用函数
        max_chars_per_batch: 每批最大字符数

    Returns:
        翻译后的文本
    """
    # 按双换行分段
    paragraphs = article_text.split('\n\n')

    translated_paragraphs = []
    batch = []
    batch_chars = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)

        # 如果当前批次 + 新段落超限，先翻译当前批次
        if batch and batch_chars + para_len > max_chars_per_batch:
            batch_text = '\n\n'.join(batch)
            translated = _translate_batch(batch_text, call_llm_func)
            translated_paragraphs.append(translated)
            batch = []
            batch_chars = 0

        batch.append(para)
        batch_chars += para_len

    # 翻译最后一批
    if batch:
        batch_text = '\n\n'.join(batch)
        translated = _translate_batch(batch_text, call_llm_func)
        translated_paragraphs.append(translated)

    return '\n\n'.join(translated_paragraphs)


def _translate_batch(text, call_llm_func):
    """
    翻译一批文本

    Args:
        text: 待翻译文本
        call_llm_func: LLM 调用函数，签名为 (system_prompt, user_prompt, model=None, retries=1)

    Returns:
        翻译后的文本
    """
    system_prompt = (
        "你是专业的财经翻译。把用户给出的英文财经文章翻译成简体中文，"
        "保持段落结构和格式，财经术语准确，公司名、人名保留通用译名。"
        "直接返回翻译后的文本，不要添加额外说明。"
    )

    user_prompt = f"翻译以下英文财经文章为简体中文，保持段落结构：\n\n{text}"

    try:
        # 翻译走翻译模型（deepseek-v4-flash 量大且便宜），不写死模型名：
        # 硬编码的模型在自建网关上不存在会直接 503，让全文翻译整体失效。
        result = call_llm_func(
            system_prompt,
            user_prompt,
            model=_translate_model(),
            retries=2
        )

        # LLM 可能返回 JSON 或纯文本
        if isinstance(result, dict):
            # 尝试多个可能的字段
            translated = (
                result.get('translation') or
                result.get('text') or
                result.get('content') or
                str(result)
            )
        elif isinstance(result, str):
            # 尝试解析 JSON
            try:
                data = json.loads(result)
                translated = (
                    data.get('translation') or
                    data.get('text') or
                    data.get('content') or
                    result
                )
            except:
                translated = result
        else:
            translated = str(result)

        # 清理可能的 JSON 标记
        translated = translated.strip()
        if translated.startswith('```'):
            # 移除代码块标记
            translated = re.sub(r'^```(?:json)?\s*\n?', '', translated)
            translated = re.sub(r'\n?```\s*$', '', translated)

        return translated.strip()

    except Exception as e:
        print(f"     批次翻译失败：{e}")
        return text  # 失败时返回原文


if __name__ == '__main__':
    # 测试
    def mock_llm(system, user, model=None, retries=1):
        """模拟 LLM 调用"""
        return "这是翻译后的文本（测试）"

    test_text = """
This is the first paragraph.

This is the second paragraph with more content.

And this is the third one.
"""

    result = translate_article_llm(test_text, mock_llm)
    print("翻译结果:")
    print(result)
