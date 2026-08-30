#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据功能测试脚本
"""
import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from scrapers import fetch_openrouter_data, fetch_aa_data
from data.market_data_aggregator import aggregate_market_data, extract_news_metrics


def test_scrapers():
    """测试爬虫功能"""
    print("=" * 60)
    print("测试 1: OpenRouter 爬虫")
    print("=" * 60)
    try:
        or_data = fetch_openrouter_data()
        print(f"✓ 成功获取数据")
        print(f"  - 发现 {len(or_data.get('top_models', []))} 个模型")
        print(f"  - 描述: {or_data.get('description', 'N/A')[:80]}...")
    except Exception as e:
        print(f"✗ 失败: {e}")

    print("\n" + "=" * 60)
    print("测试 2: Artificial Analysis 爬虫")
    print("=" * 60)
    try:
        aa_data = fetch_aa_data()
        print(f"✓ 成功获取数据")
        print(f"  - Intelligence: {len(aa_data.get('intelligence', []))} 条")
        print(f"  - Speed: {len(aa_data.get('speed', []))} 条")
        print(f"  - Cost: {len(aa_data.get('cost', []))} 条")
    except Exception as e:
        print(f"✗ 失败: {e}")


def test_news_extraction():
    """测试新闻数据提取"""
    print("\n" + "=" * 60)
    print("测试 3: 新闻数据提取")
    print("=" * 60)

    mock_sections = [
        {
            'label': '📊 行业趋势',
            'items': [
                {
                    'title': 'Anthropic ARR 突破 10 亿美元',
                    'summary': 'Anthropic 的年度经常性收入达到 10 亿美元',
                    'source': {'name': 'TechCrunch'}
                },
                {
                    'title': 'ChatGPT 用户数突破 3 亿',
                    'summary': 'OpenAI 宣布 ChatGPT 周活跃用户达到 3 亿',
                    'source': {'name': 'OpenAI'}
                },
                {
                    'title': 'GPT-4o 价格下调 50%',
                    'summary': 'OpenAI 宣布 GPT-4o API 价格下调 50%',
                    'source': {'name': 'OpenAI Blog'}
                }
            ]
        }
    ]

    metrics = extract_news_metrics(mock_sections)
    print(f"✓ 成功提取数据")
    print(f"  - ARR/营收: {len(metrics['arr_revenue'])} 条")
    print(f"  - 用户数: {len(metrics['users'])} 条")
    print(f"  - 价格变化: {len(metrics['price_changes'])} 条")

    if metrics['arr_revenue']:
        print(f"\n  示例 (ARR): {metrics['arr_revenue'][0]['title']}")
    if metrics['price_changes']:
        print(f"  示例 (价格): {metrics['price_changes'][0]['title']}")


def test_aggregation():
    """测试数据整合"""
    print("\n" + "=" * 60)
    print("测试 4: 数据整合")
    print("=" * 60)

    mock_sections = [
        {
            'label': '📊 行业趋势',
            'items': [
                {
                    'title': 'Anthropic ARR 突破 10 亿美元',
                    'summary': 'Anthropic 的年度经常性收入达到 10 亿美元',
                    'source': {'name': 'TechCrunch'}
                }
            ]
        }
    ]

    try:
        or_data = fetch_openrouter_data()
        aa_data = fetch_aa_data()
        insights = aggregate_market_data(mock_sections, or_data, aa_data)

        print(f"✓ 成功整合数据")
        print(f"  - 官方公告: {len(insights['highlights']['official_announcements'])} 条")
        print(f"  - 市场使用: {len(insights['highlights']['market_usage'])} 条")
        print(f"  - 性能基准: {len(insights['highlights']['performance_benchmarks'])} 条")

        total = sum(len(v) for v in insights['highlights'].values() if isinstance(v, list))
        print(f"\n  总计: {total} 条关键洞察")

    except Exception as e:
        print(f"✗ 失败: {e}")


def main():
    print("\n" + "=" * 60)
    print("AI 日报市场数据功能测试")
    print("=" * 60 + "\n")

    test_scrapers()
    test_news_extraction()
    test_aggregation()

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
