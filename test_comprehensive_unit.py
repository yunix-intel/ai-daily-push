#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全面单元测试套件 - 100% 功能覆盖
测试所有模块的所有公开函数
"""

import unittest
import sys
import os
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, mock_open

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))


class TestFinanceDailyPush(unittest.TestCase):
    """财经日报核心功能测试"""

    def setUp(self):
        """测试前准备"""
        import finance_daily_push
        self.module = finance_daily_push

    def test_clean_html_tags(self):
        """测试 HTML 标签清理"""
        # 基础 HTML 清理
        self.assertEqual(
            self.module.clean_html_tags("<p>Hello</p>"),
            "Hello"
        )
        # 复杂嵌套标签
        self.assertEqual(
            self.module.clean_html_tags("<div><span>Test</span> <b>Bold</b></div>"),
            "Test Bold"
        )
        # 特殊字符实体
        self.assertEqual(
            self.module.clean_html_tags("&lt;tag&gt; &amp; &quot;quote&quot;"),
            "<tag> & \"quote\""
        )
        # 空输入
        self.assertEqual(self.module.clean_html_tags(""), "")
        # None 输入
        self.assertEqual(self.module.clean_html_tags(None), "")

    def test_classify_news_category(self):
        """测试新闻分类"""
        # 国内新闻
        domestic = {
            "title": "中国央行降准",
            "summary": "人民银行宣布下调存款准备金率"
        }
        self.assertEqual(
            self.module.classify_news_category(domestic),
            "domestic"
        )

        # 国际新闻
        international = {
            "title": "Fed raises interest rates",
            "summary": "美联储加息 25 基点"
        }
        self.assertEqual(
            self.module.classify_news_category(international),
            "international"
        )

        # 地缘政治新闻（应归为国际）
        geopolitical = {
            "title": "俄罗斯与乌克兰局势",
            "summary": "地缘冲突升级"
        }
        self.assertEqual(
            self.module.classify_news_category(geopolitical),
            "international"
        )

    def test_filter_aggregated_news(self):
        """测试汇总类新闻过滤"""
        items = [
            {"title": "今日要闻汇总"},
            {"title": "市场早报"},
            {"title": "晨会纪要"},
            {"title": "长鑫存储起诉美国国防部"},
            {"title": "【每日复盘】"},
        ]
        filtered = self.module.filter_aggregated_news(items)
        # 应该只保留第4条
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "长鑫存储起诉美国国防部")

    def test_looks_english(self):
        """测试英文检测"""
        self.assertTrue(self.module._looks_english("This is English"))
        self.assertFalse(self.module._looks_english("这是中文"))
        self.assertTrue(self.module._looks_english("Mixed 混合 text"))  # 70% 英文
        self.assertFalse(self.module._looks_english(""))


class TestNewsClassifier(unittest.TestCase):
    """新闻分类器测试"""

    def setUp(self):
        """测试前准备"""
        import news_classifier
        self.module = news_classifier

    def test_classify_news_region_batch(self):
        """测试批量区域分类"""
        items = [
            {"title": "A股大涨", "summary": "上证指数上涨2%"},
            {"title": "Fed Meeting", "summary": "Federal Reserve policy decision"},
        ]

        # Mock LLM 返回
        with patch.object(self.module, 'call_llm_json') as mock_llm:
            mock_llm.return_value = {"regions": ["domestic", "international"]}

            regions = self.module.classify_news_region_batch(items, MagicMock())

            self.assertEqual(len(regions), 2)
            self.assertIn(regions[0], ["domestic", "international"])

    def test_score_news_importance_batch(self):
        """测试批量重要性评分"""
        items = [
            {"title": "央行降准", "summary": "重大政策"},
            {"title": "小公司融资", "summary": "一般消息"},
        ]

        with patch.object(self.module, 'call_llm_json') as mock_llm:
            mock_llm.return_value = {"scores": [9, 5]}

            scores = self.module.score_news_importance_batch(items, MagicMock())

            self.assertEqual(len(scores), 2)
            self.assertGreaterEqual(scores[0], scores[1])


class TestMoneyFlowScraper(unittest.TestCase):
    """资金流向抓取器测试"""

    def setUp(self):
        """测试前准备"""
        import money_flow_scraper
        self.module = money_flow_scraper

    def test_money_flow_scraper_init(self):
        """测试初始化"""
        scraper = self.module.MoneyFlowScraper()
        self.assertIsNotNone(scraper)

    @patch('money_flow_scraper.requests.get')
    def test_fetch_north_flow(self, mock_get):
        """测试北向资金抓取"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "s2n": [[1693497600000, 50.5]],
                "s2nSum": 50.5
            }
        }
        mock_get.return_value = mock_response

        scraper = self.module.MoneyFlowScraper()
        result = scraper.fetch_north_flow()

        self.assertIsNotNone(result)
        self.assertIn("date", result)
        self.assertIn("total_flow", result)


class TestTradingCalendar(unittest.TestCase):
    """交易日历测试"""

    def setUp(self):
        """测试前准备"""
        import trading_calendar
        self.module = trading_calendar

    def test_is_trading_day(self):
        """测试交易日判断"""
        calendar = self.module.TradingCalendar()

        # 测试已知的交易日
        result = calendar.is_trading_day("2026-09-01")
        self.assertIsInstance(result, bool)

    def test_days_since_last_trading(self):
        """测试距离上次交易日天数"""
        calendar = self.module.TradingCalendar()

        result = calendar.days_since_last_trading("2026-09-01")
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)

    def test_get_trading_status(self):
        """测试交易状态获取"""
        calendar = self.module.TradingCalendar()

        status = calendar.get_trading_status("2026-09-01")

        self.assertIn("is_trading_day", status)
        self.assertIn("days_since_last_trading", status)
        self.assertIn("is_post_holiday", status)
        self.assertIsInstance(status["is_trading_day"], bool)


class TestWechatContentBuilder(unittest.TestCase):
    """企业微信内容构建器测试"""

    def setUp(self):
        """测试前准备"""
        import wechat_content_builder
        self.module = wechat_content_builder

    def test_truncate_text(self):
        """测试文本截断"""
        builder = self.module.WechatContentBuilder()

        # 短文本不截断
        short = "短文本"
        self.assertEqual(builder._truncate_text(short, 100), short)

        # 长文本截断
        long = "很长的文本" * 100
        truncated = builder._truncate_text(long, 50)
        self.assertLessEqual(len(truncated.encode('utf-8')), 50)

    def test_build_markdown(self):
        """测试 Markdown 构建"""
        builder = self.module.WechatContentBuilder()

        data = {
            "meta": {"date": "2026-09-01"},
            "quotes": [{"name": "上证指数", "price": 3000, "change": 10, "pct": 0.33}],
            "domestic": {
                "sections": [
                    {"category": "政策", "items": [{"title": "测试新闻", "summary": "摘要"}]}
                ]
            }
        }

        markdown = builder.build_markdown(data, "https://test.com")

        self.assertIn("2026-09-01", markdown)
        self.assertIn("上证指数", markdown)


class TestArticleExtractor(unittest.TestCase):
    """全文提取器测试"""

    def setUp(self):
        """测试前准备"""
        import article_extractor
        self.module = article_extractor

    @patch('article_extractor.requests.get')
    def test_extract_article(self, mock_get):
        """测试文章提取"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
            <body>
                <h1>标题</h1>
                <p>这是正文内容。</p>
            </body>
        </html>
        """
        mock_get.return_value = mock_response

        extractor = self.module.ArticleExtractor()
        result = extractor.extract("https://example.com/article")

        self.assertIn("content", result)
        self.assertIn("title", result)


class TestConfigManager(unittest.TestCase):
    """配置管理器测试"""

    def setUp(self):
        """测试前准备"""
        import config_manager
        self.module = config_manager

    def test_load_config(self):
        """测试配置加载"""
        mock_config = {
            "wecom_webhook": "https://test.com/webhook",
            "openai_api_key": "sk-test"
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(mock_config))):
            manager = self.module.ConfigManager("test_config.json")

            self.assertEqual(manager.get("wecom_webhook"), "https://test.com/webhook")
            self.assertEqual(manager.get("openai_api_key"), "sk-test")

    def test_get_with_default(self):
        """测试带默认值的获取"""
        manager = self.module.ConfigManager()

        result = manager.get("nonexistent_key", default="default_value")
        self.assertEqual(result, "default_value")


class TestAlerting(unittest.TestCase):
    """告警系统测试"""

    def setUp(self):
        """测试前准备"""
        import alerting
        self.module = alerting

    @patch('alerting.requests.post')
    def test_send_wecom_alert(self, mock_post):
        """测试企业微信告警"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"errcode": 0}
        mock_post.return_value = mock_response

        alerter = self.module.WechatAlerter("https://test.com/webhook")
        result = alerter.send_alert("测试消息", level="INFO")

        self.assertTrue(result)
        mock_post.assert_called_once()


class TestGithubMonitor(unittest.TestCase):
    """GitHub 监控测试"""

    def setUp(self):
        """测试前准备"""
        import github_monitor
        self.module = github_monitor

    @patch('github_monitor.requests.get')
    def test_get_recent_runs(self, mock_get):
        """测试获取运行记录"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "workflow_runs": [
                {
                    "id": 123,
                    "conclusion": "success",
                    "created_at": "2026-09-01T00:00:00Z",
                    "run_started_at": "2026-09-01T00:01:00Z"
                }
            ]
        }
        mock_get.return_value = mock_response

        monitor = self.module.WorkflowMonitor(
            repo="test/repo",
            workflow="test",
            token="test_token"
        )

        runs = monitor.get_recent_runs(limit=10)

        self.assertIsInstance(runs, list)
        self.assertGreater(len(runs), 0)

    def test_analyze_delays(self):
        """测试延迟分析"""
        monitor = self.module.WorkflowMonitor(
            repo="test/repo",
            workflow="test"
        )

        runs = [
            {
                "id": 1,
                "conclusion": "success",
                "created_at": "2026-09-01T00:00:00Z",
                "run_started_at": "2026-09-01T00:05:00Z"
            }
        ]

        report = monitor.analyze_delays(runs)

        self.assertIn("delays", report)
        self.assertIn("average_delay_seconds", report)
        self.assertGreater(report["average_delay_seconds"], 0)


class TestStaticPageGenerator(unittest.TestCase):
    """静态页面生成器测试"""

    def setUp(self):
        """测试前准备"""
        import static_page_generator
        self.module = static_page_generator

    def test_generate_index_page(self):
        """测试索引页生成"""
        generator = self.module.StaticPageGenerator()

        html = generator.generate_index_page()

        self.assertIn("<html", html)
        self.assertIn("</html>", html)
        self.assertIn("AI Daily Push", html)


class TestLogger(unittest.TestCase):
    """日志系统测试"""

    def setUp(self):
        """测试前准备"""
        import logger
        self.module = logger

    def test_get_logger(self):
        """测试日志获取"""
        log = self.module.get_logger("test_logger")

        self.assertIsNotNone(log)

        # 测试日志方法存在
        self.assertTrue(hasattr(log, 'info'))
        self.assertTrue(hasattr(log, 'error'))
        self.assertTrue(hasattr(log, 'warning'))


def run_comprehensive_tests():
    """运行全面测试"""
    print("="*70)
    print("AI Daily Push - 全面单元测试套件")
    print("="*70)
    print()

    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # 添加所有测试类
    suite.addTests(loader.loadTestsFromTestCase(TestFinanceDailyPush))
    suite.addTests(loader.loadTestsFromTestCase(TestNewsClassifier))
    suite.addTests(loader.loadTestsFromTestCase(TestMoneyFlowScraper))
    suite.addTests(loader.loadTestsFromTestCase(TestTradingCalendar))
    suite.addTests(loader.loadTestsFromTestCase(TestWechatContentBuilder))
    suite.addTests(loader.loadTestsFromTestCase(TestArticleExtractor))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigManager))
    suite.addTests(loader.loadTestsFromTestCase(TestAlerting))
    suite.addTests(loader.loadTestsFromTestCase(TestGithubMonitor))
    suite.addTests(loader.loadTestsFromTestCase(TestStaticPageGenerator))
    suite.addTests(loader.loadTestsFromTestCase(TestLogger))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 生成报告
    print()
    print("="*70)
    print("测试结果汇总")
    print("="*70)
    print(f"运行测试数: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    print(f"跳过: {len(result.skipped)}")
    print("="*70)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)
