#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试：验证市场数据板块生成
"""
import sys
sys.path.insert(0, '.')

from data.market_data_aggregator import aggregate_market_data
from ai_daily_push import create_market_insights_section

# 模拟市场洞察数据
market_insights = {
    'date': '2026-08-30',
    'highlights': {
        'official_announcements': [
            {
                'text': 'Anthropic ARR 突破 10 亿美元',
                'source': 'TechCrunch',
                'type': 'revenue'
            },
            {
                'text': 'ChatGPT 周活跃用户达到 3 亿',
                'source': 'OpenAI',
                'type': 'users'
            }
        ],
        'market_usage': [
            {
                'text': 'Claude Sonnet 3.5 本周 15.2T tokens',
                'rank': 1,
                'source': 'OpenRouter'
            }
        ],
        'performance_benchmarks': [
            {
                'text': 'Claude Opus 5 - 智能指数 63',
                'type': 'intelligence',
                'source': 'Artificial Analysis'
            }
        ],
        'cross_validated': []
    }
}

# 生成板块
section = create_market_insights_section(market_insights)

if section:
    print(f"✓ 成功生成市场数据板块")
    print(f"  板块名称: {section['label']}")
    print(f"  条目数量: {len(section['items'])}")
    print()
    print("条目列表:")
    for i, item in enumerate(section['items'], 1):
        print(f"  {i}. {item['title'][:60]}")
        print(f"     来源: {item['source']}")
else:
    print("✗ 未能生成板块")
