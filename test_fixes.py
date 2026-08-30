#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试：验证两个修复
1. 文本两端对齐
2. 翻译全文链接
"""
import sys
import re
sys.path.insert(0, '.')

from ai_daily_push import translate_page_url

# 测试 1: 翻译链接生成
print("=" * 60)
print("测试 1: 翻译链接生成")
print("=" * 60)

test_url = "https://techcrunch.com/2024/12/01/anthropic-arr/"
translated_url = translate_page_url(test_url)

print(f"原始链接: {test_url}")
print(f"翻译链接: {translated_url}")
print(f"✓ 翻译链接生成成功" if translated_url else "✗ 翻译链接生成失败")

# 测试 2: 检查 HTML 中的文本对齐样式
print("\n" + "=" * 60)
print("测试 2: 检查 HTML 文本对齐样式")
print("=" * 60)

try:
    with open('ai_daily_dashboard.html', 'r', encoding='utf-8') as f:
        html_content = f.read()

    # 检查是否包含 text-align:justify
    has_justify_h3 = 'text-align:justify' in html_content and '.card h3{' in html_content
    has_justify_summary = 'text-align:justify' in html_content and '.summary{' in html_content

    print(f"标题两端对齐: {'✓' if has_justify_h3 else '✗'}")
    print(f"摘要两端对齐: {'✓' if has_justify_summary else '✗'}")

    if has_justify_h3 and has_justify_summary:
        print("\n✓ HTML 样式修复成功")
    else:
        print("\n✗ HTML 样式需要重新生成")

except FileNotFoundError:
    print("✗ ai_daily_dashboard.html 文件不存在，需要运行 ai_daily_push.py")

# 测试 3: 模拟条目处理逻辑
print("\n" + "=" * 60)
print("测试 3: 翻译链接生成逻辑")
print("=" * 60)

test_cases = [
    {
        "title": "Anthropic ARR breakthrough",
        "originalTitle": "Anthropic ARR breakthrough",
        "original": "https://example.com/article",
        "expected": True,
        "reason": "英文标题应生成翻译链接"
    },
    {
        "title": "中文标题",
        "originalTitle": "中文标题",
        "original": "https://example.com/article",
        "expected": False,
        "reason": "纯中文标题不应生成翻译链接"
    },
    {
        "title": "Anthropic 融资消息",
        "originalTitle": "Anthropic funding news",
        "original": "https://example.com/article",
        "expected": True,
        "reason": "已翻译的内容应生成翻译链接"
    },
]

for i, tc in enumerate(test_cases, 1):
    original_title = tc['originalTitle']
    title = tc['title']
    original_link = tc['original']

    is_translated = bool(original_title) and original_title != title
    needs_translation = bool(original_link) and (
        is_translated or
        bool(re.search(r'[a-zA-Z]{3,}', original_title))
    )

    result = "✓ PASS" if needs_translation == tc['expected'] else "✗ FAIL"
    print(f"{i}. {result} - {tc['reason']}")
    print(f"   标题: {title}")
    print(f"   需要翻译: {needs_translation} (预期: {tc['expected']})")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
