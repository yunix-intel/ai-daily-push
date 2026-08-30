#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 日报市场数据系统 - 完整测试报告生成器
"""
import sys
import json
from datetime import datetime

sys.path.insert(0, '.')

from scrapers import fetch_openrouter_data, fetch_aa_data
from data.market_data_aggregator import aggregate_market_data, extract_news_metrics
from ai_daily_push import create_market_insights_section


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_all():
    """运行所有测试并生成报告"""
    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tests": []
    }

    print_section("AI 日报市场数据系统 - 完整测试")

    # 测试 1: 新闻数据提取
    print_section("测试 1: 新闻数据提取")
    try:
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
                    },
                    {
                        'title': 'DeepSeek 获得 5 亿美元融资',
                        'summary': 'DeepSeek 完成 5 亿美元 B 轮融资',
                        'source': {'name': 'TechCrunch'}
                    }
                ]
            }
        ]

        metrics = extract_news_metrics(mock_sections)

        print(f"✓ 测试通过")
        print(f"  - ARR/营收: {len(metrics['arr_revenue'])} 条")
        print(f"  - 融资: {len(metrics['funding'])} 条")
        print(f"  - 用户数: {len(metrics['users'])} 条")
        print(f"  - 价格变化: {len(metrics['price_changes'])} 条")

        if metrics['arr_revenue']:
            print(f"  示例: {metrics['arr_revenue'][0]['title']}")

        report['tests'].append({
            'name': '新闻数据提取',
            'status': 'PASS',
            'details': {
                'arr_count': len(metrics['arr_revenue']),
                'funding_count': len(metrics['funding']),
                'users_count': len(metrics['users']),
                'price_count': len(metrics['price_changes'])
            }
        })
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        report['tests'].append({'name': '新闻数据提取', 'status': 'FAIL', 'error': str(e)})

    # 测试 2: OpenRouter 爬虫
    print_section("测试 2: OpenRouter 爬虫")
    try:
        or_data = fetch_openrouter_data()
        print(f"✓ 测试通过")
        print(f"  - 数据源: {or_data.get('source')}")
        print(f"  - 模型数量: {len(or_data.get('top_models', []))}")
        print(f"  - 描述: {or_data.get('description', 'N/A')[:60]}...")
        print(f"  - 检测到的模型: {', '.join(or_data.get('detected_models', [])[:5])}")

        report['tests'].append({
            'name': 'OpenRouter 爬虫',
            'status': 'PASS',
            'details': {
                'models_count': len(or_data.get('top_models', [])),
                'has_description': bool(or_data.get('description')),
                'detected_models': or_data.get('detected_models', [])
            }
        })
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        report['tests'].append({'name': 'OpenRouter 爬虫', 'status': 'FAIL', 'error': str(e)})

    # 测试 3: Artificial Analysis 爬虫
    print_section("测试 3: Artificial Analysis 爬虫")
    try:
        aa_data = fetch_aa_data()
        print(f"✓ 测试通过")
        print(f"  - 数据源: {aa_data.get('source')}")
        print(f"  - Intelligence 数据: {len(aa_data.get('intelligence', []))} 条")
        print(f"  - Speed 数据: {len(aa_data.get('speed', []))} 条")
        print(f"  - Cost 数据: {len(aa_data.get('cost', []))} 条")

        report['tests'].append({
            'name': 'Artificial Analysis 爬虫',
            'status': 'PASS',
            'details': {
                'intelligence_count': len(aa_data.get('intelligence', [])),
                'speed_count': len(aa_data.get('speed', [])),
                'cost_count': len(aa_data.get('cost', []))
            }
        })
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        report['tests'].append({'name': 'AA 爬虫', 'status': 'FAIL', 'error': str(e)})

    # 测试 4: 数据整合
    print_section("测试 4: 数据整合")
    try:
        insights = aggregate_market_data(mock_sections, or_data, aa_data)

        total_highlights = sum(
            len(v) for v in insights['highlights'].values()
            if isinstance(v, list)
        )

        print(f"✓ 测试通过")
        print(f"  - 官方公告: {len(insights['highlights']['official_announcements'])} 条")
        print(f"  - 市场使用: {len(insights['highlights']['market_usage'])} 条")
        print(f"  - 性能基准: {len(insights['highlights']['performance_benchmarks'])} 条")
        print(f"  - 总计洞察: {total_highlights} 条")

        report['tests'].append({
            'name': '数据整合',
            'status': 'PASS',
            'details': {
                'total_insights': total_highlights,
                'official_count': len(insights['highlights']['official_announcements']),
                'usage_count': len(insights['highlights']['market_usage']),
                'benchmark_count': len(insights['highlights']['performance_benchmarks'])
            }
        })
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        report['tests'].append({'name': '数据整合', 'status': 'FAIL', 'error': str(e)})

    # 测试 5: 板块生成
    print_section("测试 5: 市场数据板块生成")
    try:
        section = create_market_insights_section(insights)

        print(f"✓ 测试通过")
        print(f"  - 板块名称: {section['label']}")
        print(f"  - 条目数量: {len(section['items'])}")
        print(f"\n  前 3 条:")
        for i, item in enumerate(section['items'][:3], 1):
            print(f"    {i}. {item['title'][:50]}")

        report['tests'].append({
            'name': '板块生成',
            'status': 'PASS',
            'details': {
                'label': section['label'],
                'items_count': len(section['items'])
            }
        })
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        report['tests'].append({'name': '板块生成', 'status': 'FAIL', 'error': str(e)})

    # 生成测试报告摘要
    print_section("测试摘要")
    passed = sum(1 for t in report['tests'] if t['status'] == 'PASS')
    total = len(report['tests'])

    print(f"\n  总计: {passed}/{total} 个测试通过")
    print(f"  通过率: {passed/total*100:.1f}%")

    if passed == total:
        print(f"\n  ✓ 所有测试通过！系统运行正常。")
    else:
        print(f"\n  ⚠ 部分测试失败，请检查错误信息。")

    # 保存报告
    report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n  详细报告已保存: {report_file}")
    print("=" * 70)

    return passed == total


if __name__ == "__main__":
    success = test_all()
    sys.exit(0 if success else 1)
