#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全面测试脚本 - 测试所有模块的基本功能
"""
import sys
import os
import io

# 设置标准输出编码为 UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_trading_calendar():
    """测试交易日历模块"""
    print("\n=== 测试交易日历模块 ===")
    try:
        from trading_calendar import is_trading_day, get_trading_status
        import datetime

        today = datetime.date.today()
        is_trading = is_trading_day(today, market='A')
        print(f"  今天是否交易日: {is_trading}")

        status = get_trading_status(today, market='A')
        print(f"  交易状态: {status}")
        print("  ✓ 交易日历模块正常")
        return True
    except Exception as e:
        print(f"  ✗ 交易日历模块错误: {e}")
        return False


def test_llm_helpers():
    """测试 LLM 辅助模块"""
    print("\n=== 测试 LLM 辅助模块 ===")
    try:
        from llm_helpers import _llm_config

        api_key, base_url, translate_model, analysis_model = _llm_config()
        print(f"  API Key 配置: {'已配置' if api_key else '未配置'}")
        print(f"  Base URL: {base_url or '默认'}")
        print(f"  翻译模型: {translate_model or '默认'}")
        print(f"  分析模型: {analysis_model or '默认'}")

        if not api_key:
            print("  ⚠ 未配置 OPENAI_API_KEY，LLM 功能将无法使用")
        else:
            print("  ✓ LLM 辅助模块配置正常")

        return True
    except Exception as e:
        print(f"  ✗ LLM 辅助模块错误: {e}")
        return False


def test_event_impact_analyzer():
    """测试突发事件影响分析模块"""
    print("\n=== 测试突发事件影响分析模块 ===")
    try:
        from event_impact_analyzer import EventImpactAnalyzer

        analyzer = EventImpactAnalyzer()
        print("  ✓ 突发事件影响分析模块加载成功")

        # 测试示例（不实际调用 LLM）
        print("  模块功能: analyze_event_impact()")
        return True
    except Exception as e:
        print(f"  ✗ 突发事件影响分析模块错误: {e}")
        return False


def test_article_translator():
    """测试全文翻译模块"""
    print("\n=== 测试全文翻译模块 ===")
    try:
        from article_translator import ArticleTranslator

        translator = ArticleTranslator()
        print("  ✓ 全文翻译模块加载成功")
        print("  模块功能: translate_article()")
        return True
    except Exception as e:
        print(f"  ✗ 全文翻译模块错误: {e}")
        return False


def test_money_flow_scraper():
    """测试资金流向抓取模块"""
    print("\n=== 测试资金流向抓取模块 ===")
    try:
        from money_flow_scraper import MoneyFlowScraper

        scraper = MoneyFlowScraper()
        print("  ✓ 资金流向抓取模块加载成功")
        print("  模块功能: get_all_money_flow_data()")
        return True
    except Exception as e:
        print(f"  ✗ 资金流向抓取模块错误: {e}")
        return False


def test_news_metrics_extractor():
    """测试新闻指标提取模块"""
    print("\n=== 测试新闻指标提取模块 ===")
    try:
        from news_metrics_extractor import NewsMetricsExtractor

        extractor = NewsMetricsExtractor()
        print("  ✓ 新闻指标提取模块加载成功")
        print("  模块功能: extract_metrics()")
        return True
    except Exception as e:
        print(f"  ✗ 新闻指标提取模块错误: {e}")
        return False


def test_wechat_official():
    """测试微信公众号模块"""
    print("\n=== 测试微信公众号模块 ===")
    try:
        from wechat_official_publisher import WechatOfficialPublisher
        from wechat_content_formatter import format_ai_daily_for_wechat, format_finance_daily_for_wechat
        from cover_generator import create_default_cover

        print("  ✓ 微信公众号发布模块加载成功")
        print("  ✓ 内容格式化模块加载成功")
        print("  ✓ 封面生成模块加载成功")

        # 测试封面生成
        cover_path = create_default_cover(cover_type="ai")
        if cover_path:
            print(f"  ✓ 默认封面生成成功: {cover_path}")
        else:
            print("  ⚠ 封面生成失败（可能缺少 Pillow 或字体）")

        return True
    except Exception as e:
        print(f"  ✗ 微信公众号模块错误: {e}")
        return False


def test_main_scripts():
    """测试主脚本语法"""
    print("\n=== 测试主脚本语法 ===")

    success = True

    # 测试 AI 日报
    try:
        import ai_daily_push
        print("  ✓ AI 日报脚本导入成功")
    except Exception as e:
        print(f"  ✗ AI 日报脚本错误: {e}")
        success = False

    # 测试财经日报
    try:
        import finance_daily_push
        print("  ✓ 财经日报脚本导入成功")
    except Exception as e:
        print(f"  ✗ 财经日报脚本错误: {e}")
        success = False

    return success


def main():
    """运行所有测试"""
    print("=" * 60)
    print("开始全面测试")
    print("=" * 60)

    results = []

    # 运行各项测试
    results.append(("交易日历", test_trading_calendar()))
    results.append(("LLM 辅助", test_llm_helpers()))
    results.append(("突发事件分析", test_event_impact_analyzer()))
    results.append(("全文翻译", test_article_translator()))
    results.append(("资金流向", test_money_flow_scraper()))
    results.append(("新闻指标提取", test_news_metrics_extractor()))
    results.append(("微信公众号", test_wechat_official()))
    results.append(("主脚本", test_main_scripts()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 项测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
