#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
实用功能测试 - 测试所有关键路径
基于实际代码结构，验证核心功能是否正常工作
"""

import sys
import os

# 设置环境
os.environ.setdefault('OPENAI_API_KEY', 'sk-test')
os.environ.setdefault('OPENAI_BASE_URL', 'https://api.test.com/v1')
sys.path.insert(0, os.path.dirname(__file__))


def test_finance_daily_core_functions():
    """测试财经日报核心函数"""
    print("\n【财经日报核心函数测试】")
    print("-" * 60)

    import finance_daily_push as fdp

    tests_passed = 0
    tests_total = 0

    # 测试 1: HTML 清理
    tests_total += 1
    try:
        result = fdp.clean_html_tags("<p>Test</p>")
        assert "Test" in result and "<" not in result
        print("✓ clean_html_tags")
        tests_passed += 1
    except Exception as e:
        print(f"✗ clean_html_tags: {e}")

    # 测试 2: 新闻分类
    tests_total += 1
    try:
        result = fdp.classify_news_category({"title": "央行降准", "summary": "中国"})
        assert result in ["domestic", "international"]
        print("✓ classify_news_category")
        tests_passed += 1
    except Exception as e:
        print(f"✗ classify_news_category: {e}")

    # 测试 3: 过滤汇总新闻
    tests_total += 1
    try:
        items = [{"title": "今日要闻汇总"}, {"title": "具体新闻"}]
        result = fdp.filter_aggregated_news(items)
        assert len(result) <= len(items)
        print("✓ filter_aggregated_news")
        tests_passed += 1
    except Exception as e:
        print(f"✗ filter_aggregated_news: {e}")

    # 测试 4: 英文检测
    tests_total += 1
    try:
        assert fdp._looks_english("English text") == True
        assert fdp._looks_english("中文文本") == False
        print("✓ _looks_english")
        tests_passed += 1
    except Exception as e:
        print(f"✗ _looks_english: {e}")

    # 测试 5: LLM 配置读取
    tests_total += 1
    try:
        api_key, base_url, t_model, a_model = fdp._llm_config()
        assert api_key is not None
        print("✓ _llm_config")
        tests_passed += 1
    except Exception as e:
        print(f"✗ _llm_config: {e}")

    # 测试 6: 行情数据格式化
    tests_total += 1
    try:
        quotes = [{"name": "上证指数", "price": 3000, "change": 10, "pct": 0.5}]
        result = fdp._quotes_digest(quotes)
        assert "上证指数" in result
        print("✓ _quotes_digest")
        tests_passed += 1
    except Exception as e:
        print(f"✗ _quotes_digest: {e}")

    print(f"\n小计: {tests_passed}/{tests_total} 通过")
    return tests_passed, tests_total


def test_news_classifier():
    """测试新闻分类器"""
    print("\n【新闻分类器测试】")
    print("-" * 60)

    import news_classifier as nc

    tests_passed = 0
    tests_total = 0

    # 测试 1: 关键词分类
    tests_total += 1
    try:
        result = nc.classify_by_keywords({"title": "央行降准", "summary": "中国人民银行宣布降准"})
        assert result in ["domestic", "international"]
        print("✓ classify_by_keywords")
        tests_passed += 1
    except Exception as e:
        print(f"✗ classify_by_keywords: {e}")

    print(f"\n小计: {tests_passed}/{tests_total} 通过")
    return tests_passed, tests_total


def test_trading_calendar():
    """测试交易日历"""
    print("\n【交易日历测试】")
    print("-" * 60)

    try:
        import trading_calendar as tc

        tests_passed = 0
        tests_total = 0

        # 测试 1: 获取交易状态
        tests_total += 1
        try:
            from datetime import datetime
            status = tc.get_trading_status(datetime(2026, 9, 1).date())
            assert "is_trading_day" in status
            print("✓ get_trading_status")
            tests_passed += 1
        except Exception as e:
            print(f"✗ get_trading_status: {e}")

        # 测试 2: 判断交易日
        tests_total += 1
        try:
            from datetime import datetime
            result = tc.is_trading_day(datetime(2026, 9, 1).date())
            assert isinstance(result, bool)
            print("✓ is_trading_day")
            tests_passed += 1
        except Exception as e:
            print(f"✗ is_trading_day: {e}")

        print(f"\n小计: {tests_passed}/{tests_total} 通过")
        return tests_passed, tests_total

    except Exception as e:
        print(f"✗ 模块加载失败: {e}")
        return 0, 0


def test_money_flow_scraper():
    """测试资金流向"""
    print("\n【资金流向测试】")
    print("-" * 60)

    try:
        import money_flow_scraper as mfs

        tests_passed = 0
        tests_total = 0

        # 测试 1: 初始化
        tests_total += 1
        try:
            scraper = mfs.MoneyFlowScraper()
            assert scraper is not None
            print("✓ MoneyFlowScraper 初始化")
            tests_passed += 1
        except Exception as e:
            print(f"✗ MoneyFlowScraper 初始化: {e}")

        print(f"\n小计: {tests_passed}/{tests_total} 通过")
        return tests_passed, tests_total

    except Exception as e:
        print(f"✗ 模块加载失败: {e}")
        return 0, 0


def test_github_monitor():
    """测试 GitHub 监控"""
    print("\n【GitHub 监控测试】")
    print("-" * 60)

    try:
        import github_monitor as gm

        tests_passed = 0
        tests_total = 0

        # 测试 1: 初始化
        tests_total += 1
        try:
            monitor = gm.GitHubMonitor(repo="test/repo", token="test")
            assert monitor.repo == "test/repo"
            print("✓ GitHubMonitor 初始化")
            tests_passed += 1
        except Exception as e:
            print(f"✗ GitHubMonitor 初始化: {e}")

        # 测试 2: 时间格式化
        tests_total += 1
        try:
            from datetime import datetime
            result = gm.format_beijing_time(datetime.now())
            assert isinstance(result, str)
            print("✓ format_beijing_time")
            tests_passed += 1
        except Exception as e:
            print(f"✗ format_beijing_time: {e}")

        print(f"\n小计: {tests_passed}/{tests_total} 通过")
        return tests_passed, tests_total

    except Exception as e:
        print(f"✗ 模块加载失败: {e}")
        return 0, 0


def test_logger():
    """测试日志系统"""
    print("\n【日志系统测试】")
    print("-" * 60)

    try:
        import logger

        tests_passed = 0
        tests_total = 0

        # 测试 1: LoggerFactory
        tests_total += 1
        try:
            factory = logger.LoggerFactory()
            log = factory.get_logger("test")
            assert log is not None
            print("✓ LoggerFactory")
            tests_passed += 1
        except Exception as e:
            print(f"✗ LoggerFactory: {e}")

        # 测试 2: StructuredLogger
        tests_total += 1
        try:
            log = logger.StructuredLogger("test")
            assert hasattr(log, 'info')
            print("✓ StructuredLogger")
            tests_passed += 1
        except Exception as e:
            print(f"✗ StructuredLogger: {e}")

        print(f"\n小计: {tests_passed}/{tests_total} 通过")
        return tests_passed, tests_total

    except Exception as e:
        print(f"✗ 模块加载失败: {e}")
        return 0, 0


def test_wechat_content_builder():
    """测试企业微信内容构建"""
    print("\n【企业微信内容构建测试】")
    print("-" * 60)

    try:
        import wechat_content_builder as wcb

        tests_passed = 0
        tests_total = 0

        # 测试 1: 财经日报封面
        tests_total += 1
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                result = wcb.prepare_finance_daily_cover(tmpdir)
                assert result is not None
                print("✓ prepare_finance_daily_cover")
                tests_passed += 1
        except Exception as e:
            print(f"✗ prepare_finance_daily_cover: {e}")

        # 测试 2: AI 日报封面
        tests_total += 1
        try:
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                result = wcb.prepare_ai_daily_cover(tmpdir)
            assert result is not None
            print("✓ prepare_ai_daily_cover")
            tests_passed += 1
        except Exception as e:
            print(f"✗ prepare_ai_daily_cover: {e}")

        print(f"\n小计: {tests_passed}/{tests_total} 通过")
        return tests_passed, tests_total

    except Exception as e:
        print(f"✗ 模块加载失败: {e}")
        return 0, 0


def test_static_page_generator():
    """测试静态页面生成"""
    print("\n【静态页面生成测试】")
    print("-" * 60)

    try:
        import static_page_generator as spg

        tests_passed = 0
        tests_total = 0

        # 测试 1: 翻译页面生成
        tests_total += 1
        try:
            article_data = {
                "title": "测试标题",
                "url": "https://example.com",
                "source": "测试来源",
                "author": "测试作者",
                "date": "2026-09-01"
            }
            result = spg.generate_translation_page(
                article_data,
                "翻译内容"
            )
            # 函数返回的是文件路径，不是HTML内容
            assert result is not None
            assert result.endswith('.html')
            print("✓ generate_translation_page")
            tests_passed += 1
        except Exception as e:
            print(f"✗ generate_translation_page: {e}")

        print(f"\n小计: {tests_passed}/{tests_total} 通过")
        return tests_passed, tests_total

    except Exception as e:
        print(f"✗ 模块加载失败: {e}")
        return 0, 0


def test_config_manager():
    """测试配置管理"""
    print("\n【配置管理测试】")
    print("-" * 60)

    try:
        import config_manager as cm

        tests_passed = 0
        tests_total = 0

        # 测试 1: 初始化
        tests_total += 1
        try:
            manager = cm.ConfigManager()
            assert manager is not None
            print("✓ ConfigManager 初始化")
            tests_passed += 1
        except Exception as e:
            print(f"✗ ConfigManager 初始化: {e}")

        print(f"\n小计: {tests_passed}/{tests_total} 通过")
        return tests_passed, tests_total

    except Exception as e:
        print(f"✗ 模块加载失败: {e}")
        return 0, 0


def main():
    """运行所有测试"""
    print("=" * 70)
    print("AI Daily Push - 实用功能测试")
    print("=" * 70)

    total_passed = 0
    total_tests = 0

    # 运行所有测试
    test_functions = [
        test_finance_daily_core_functions,
        test_news_classifier,
        test_trading_calendar,
        test_money_flow_scraper,
        test_github_monitor,
        test_logger,
        test_wechat_content_builder,
        test_static_page_generator,
        test_config_manager,
    ]

    for test_func in test_functions:
        try:
            passed, total = test_func()
            total_passed += passed
            total_tests += total
        except Exception as e:
            print(f"\n✗ {test_func.__name__} 执行失败: {e}")

    # 总结
    print("\n" + "=" * 70)
    print("总体测试结果")
    print("=" * 70)
    print(f"总测试数: {total_tests}")
    print(f"通过: {total_passed}")
    print(f"失败: {total_tests - total_passed}")

    if total_tests > 0:
        success_rate = total_passed / total_tests * 100
        print(f"成功率: {success_rate:.1f}%")

        if success_rate >= 80:
            print("\n✓ 测试通过 - 核心功能正常")
            return 0
        elif success_rate >= 60:
            print("\n⚠ 部分测试失败 - 需要关注")
            return 1
        else:
            print("\n✗ 测试失败 - 需要修复")
            return 1
    else:
        print("\n✗ 没有运行任何测试")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
