#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Comprehensive deterministic checks against the current module signatures."""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))


class FakeResponse:
    def __init__(self, value):
        self.value = value if isinstance(value, bytes) else value.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.value


class TestAIDailyPush(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ai_daily_push
        cls.m = ai_daily_push

    def test_url_and_byte_helpers(self):
        self.assertEqual(self.m.safe_md_url("https://example.com/a b"), "https://example.com/a%20b")
        self.assertEqual(self.m.truncate_bytes("中文abc", 7), "…（")
        self.assertEqual(self.m.fmt_cst("2026-09-01T00:00:00Z", "%Y-%m-%d"), "2026-09-01")

    def test_http_get_uses_urllib(self):
        with patch.object(self.m.urllib.request, "urlopen", return_value=FakeResponse('{"items": [1]}')) as opened:
            self.assertEqual(self.m.http_get("https://example.invalid/data"), {"items": [1]})
        opened.assert_called_once()

    def test_similarity_and_highlights(self):
        self.assertGreater(self.m.calculate_similarity("AI model release", "AI model release"), 0.99)
        items = [{"title": "Important", "summary": "A major event", "source": "Test", "idx": 0}]
        highlights = self.m.pick_highlights([(items[0], "AI")], top_n=1)
        self.assertEqual(len(highlights), 1)
        self.assertEqual(highlights[0]["title"], "Important")


class TestFinanceDailyPush(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import finance_daily_push
        cls.m = finance_daily_push

    def test_translation_gates_and_markdown(self):
        self.assertTrue(self.m._looks_english("Federal Reserve raises rates"))
        self.assertFalse(self.m._looks_english("这是中文标题"))
        data = {"meta": {"date": "2026-09-01"}, "quotes": [], "domestic": {"sections": []},
                "international": {"sections": []}}
        html = self.m.build_finance_html(data)
        markdown = self.m.build_finance_markdown(data, "https://example.invalid/finance")
        self.assertIn("2026-09-01", html)
        self.assertIn("https://example.invalid/finance", markdown)

    def test_http_post_json_uses_urllib(self):
        with patch.object(self.m.urllib.request, "urlopen", return_value=FakeResponse('{"ok": true}')) as opened:
            result = self.m.http_post_json("https://example.invalid/hook", {"message": "x"})
        self.assertEqual(result, {"ok": True})
        opened.assert_called_once()


class TestNewsClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import news_classifier
        cls.m = news_classifier

    def test_empty_batches_are_deterministic(self):
        self.assertEqual(self.m.classify_news_region_batch([], MagicMock()), [])
        self.assertEqual(self.m.score_news_importance_batch([], MagicMock()), [])
        self.assertEqual(self.m.identify_breaking_news([], MagicMock()), [])

    def test_failed_batch_uses_real_keyword_fallback(self):
        call = MagicMock(side_effect=RuntimeError("offline"))
        result = self.m.classify_news_region_batch([{"title": "央行降准", "summary": ""}], call)
        self.assertEqual(result, ["domestic"])


class TestMoneyFlowScraper(unittest.TestCase):
    def test_network_error_returns_contract(self):
        from scrapers import money_flow_scraper as m
        with patch.object(m.requests, "get", side_effect=RuntimeError("offline")):
            result = m.MoneyFlowScraper().fetch_north_flow()
        self.assertEqual(set(result), {"date", "sh_flow", "sz_flow", "total_flow", "available"})
        self.assertFalse(result["available"])

    def test_rankings_use_both_sort_directions(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        with patch.object(scraper, "_clist", side_effect=[
            [{"f14": "In", "f62": "100000000", "f3": "1", "f184": "1"}],
            [{"f14": "Out", "f62": "-100000000", "f3": "-1", "f184": "-1"}],
        ]) as clist:
            result = scraper.fetch_sector_flow(top_n=1)
        self.assertEqual(result["top_inflow"][0]["name"], "In")
        self.assertEqual(result["top_outflow"][0]["name"], "Out")
        self.assertEqual(clist.call_count, 2)


class TestTradingCalendar(unittest.TestCase):
    def test_pure_local_calendar_contract(self):
        import trading_calendar as m
        with patch.object(m, "_fetch_online_holidays", return_value=([], None)):
            self.assertFalse(m.is_weekend(date(2026, 9, 5)))
            self.assertFalse(m.is_trading_day(date(2026, 1, 1)))
            status = m.get_trading_status(date(2026, 9, 1))
        self.assertIsInstance(status["days_since_last_trading"], int)
        self.assertIn(status["market_status"], {"trading", "post_holiday"})


class TestAlerting(unittest.TestCase):
    def test_configured_wecom_calls_urllib(self):
        import alerting as m
        response = FakeResponse('{"errcode": 0}')
        with patch.dict(os.environ, {"ALERT_WECOM_WEBHOOK": "https://example.invalid/hook"}, clear=False):
            notifier = m.AlertNotifier()
            with patch.object(m.urllib.request, "urlopen", return_value=response) as opened:
                self.assertTrue(notifier.send_alert("INFO", "Title", "Message"))
        opened.assert_called_once()

    def test_no_channels_is_false(self):
        import alerting as m
        with patch.dict(os.environ, {"ALERT_WECOM_WEBHOOK": "", "ALERT_DINGTALK_WEBHOOK": "",
                                     "ALERT_FEISHU_WEBHOOK": "", "ALERT_WEBHOOK": ""}, clear=False):
            self.assertFalse(m.AlertNotifier().send_alert("INFO", "T", "M"))


class TestGithubMonitor(unittest.TestCase):
    def test_current_constructor_and_http_architecture(self):
        import github_monitor as m
        monitor = m.GitHubMonitor(repo="owner/repo", workflow_name="CI", token="token")
        body = {"workflow_runs": [{"id": 1, "run_number": 4, "conclusion": "success",
                                    "created_at": "2026-09-01T00:00:00Z", "run_started_at": "2026-09-01T00:01:30Z",
                                    "html_url": "https://example.invalid/run"}]}
        with patch.object(monitor, "_http_get", return_value=body):
            runs = monitor.get_recent_runs(limit=1)
        self.assertEqual(len(runs), 1)
        self.assertEqual(monitor.analyze_delays(runs)["max_delay_seconds"], 90.0)


class TestConfigAndRendering(unittest.TestCase):
    def test_config_manager_loads_yaml_contract(self):
        import config_manager as m
        with tempfile.TemporaryDirectory() as directory:
            manager = m.ConfigManager(directory)
            with open(os.path.join(directory, "default.yaml"), "w", encoding="utf-8") as stream:
                stream.write("llm:\n  api_key: test-key\npush:\n  pushplus_token: token\n")
            config = manager.load()
        self.assertEqual(config.llm.api_key, "test-key")
        self.assertEqual(config.push.pushplus_token, "token")

    def test_static_page_generator_returns_path_and_escapes(self):
        import static_page_generator as m
        with tempfile.TemporaryDirectory() as directory:
            path = m.generate_translation_page({"url": "https://example.invalid/a", "title": "<title>", "source": "source"}, "text", directory)
            self.assertTrue(path.endswith(".html"))
            with open(path, encoding="utf-8") as stream:
                self.assertIn("&lt;title&gt;", stream.read())


class TestWechatAndLogger(unittest.TestCase):
    def test_wechat_rendering_does_not_download(self):
        import wechat_content_builder as m
        html = m.html_to_wechat_article("ignored", "AI 日报", "https://example.invalid")
        finance = m.html_to_wechat_finance_article("ignored", "财经日报", "https://example.invalid")
        self.assertIn("AI 日报", html)
        self.assertIn("财经日报", finance)

    def test_logger_factory_api(self):
        import logger as m
        log = m.LoggerFactory.get_logger("deterministic-test")
        self.assertTrue(all(hasattr(log, method) for method in ("info", "warning", "error")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
