#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Deterministic unit tests for current production APIs."""

import json
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))


class FakeResponse:
    def __init__(self, body):
        self.body = body if isinstance(body, bytes) else body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class TestFinanceDailyPush(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import finance_daily_push
        cls.m = finance_daily_push

    def test_text_cleanup_and_classification(self):
        self.assertEqual(self.m.clean_html_tags("<p>Hello</p> &amp;"), "Hello &")
        self.assertEqual(self.m.clean_html_tags(None), "")
        self.assertEqual(self.m.classify_news_category({"title": "A股半导体回升，受美股影响"}), "domestic")
        self.assertEqual(self.m.classify_news_category({"title": "美联储加息"}), "international")

    def test_filter_and_english_detection(self):
        items = [{"title": "今日要闻汇总"}, {"title": "具体政策新闻"}]
        self.assertEqual(self.m.filter_aggregated_news(items), [items[1]])
        self.assertTrue(self.m._looks_english("Federal Reserve raises rates"))
        self.assertFalse(self.m._looks_english("中文标题 English"))

    def test_fetch_quotes_uses_urllib_and_parses_fields(self):
        fields = [""] * 33
        fields[1], fields[3], fields[31], fields[32] = "上证指数", "3000.12", "12.3", "0.41"
        payload = 'v_sh000001="' + "~".join(fields) + '";'
        with patch.object(self.m.urllib.request, "urlopen", return_value=FakeResponse(payload)) as opened:
            result = self.m.fetch_quotes()
        self.assertEqual(result[0], {"name": "上证指数", "price": 3000.12, "change": 12.3, "pct": 0.41})
        opened.assert_called_once()

    def test_http_post_json_is_network_free(self):
        with patch.object(self.m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps({"errcode": 0}))) as opened:
            result = self.m.http_post_json("https://example.invalid", {"x": 1})
        self.assertEqual(result, {"errcode": 0})
        self.assertEqual(opened.call_args.args[0].full_url, "https://example.invalid")


class TestNewsClassifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import news_classifier
        cls.m = news_classifier

    def test_keyword_fallback(self):
        self.assertEqual(self.m.classify_by_keywords({"title": "央行降准"}), "domestic")
        self.assertEqual(self.m.classify_by_keywords({"title": "Fed raises rates"}), "international")

    def test_batches_and_normalizes_llm_result(self):
        call = MagicMock(return_value={"result": ["Domestic", "国际"]})
        result = self.m.classify_news_region_batch(
            [{"title": "A", "summary": ""}, {"title": "B", "summary": ""}], call
        )
        self.assertEqual(result, ["domestic", "international"])
        call.assert_called_once()

    def test_score_batch_clamps_values(self):
        call = MagicMock(return_value={"scores": [11, -2]})
        result = self.m.score_news_importance_batch([{"title": "A"}, {"title": "B"}], call)
        self.assertEqual(result, [10, 0])


class TestMoneyFlowScraper(unittest.TestCase):
    def test_parse_and_shape_current_scraper(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        parsed = scraper._parse_north_flow({"data": {
            "hk2sh": {"dayNetAmtIn": "100000000"},
            "hk2sz": {"dayNetAmtIn": "-25000000"},
        }})
        self.assertEqual(parsed["total_flow"], 0.75)
        self.assertTrue(parsed["available"])
        self.assertEqual(
            scraper._shape_flow({"f14": "银行", "f62": "200000000", "f3": "4.4", "f184": "2.1"}, True),
            {"name": "银行", "net_inflow": 2.0, "change_pct": 4.4, "net_ratio": 2.1, "code": ""},
        )

    def test_fetch_north_flow_patches_requests_at_its_module(self):
        from scrapers import money_flow_scraper
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": {"hk2sh": {"dayNetAmtIn": 0}, "hk2sz": {"dayNetAmtIn": 0}}}
        with patch.object(money_flow_scraper.requests, "get", return_value=response) as get:
            result = money_flow_scraper.MoneyFlowScraper().fetch_north_flow()
        self.assertFalse(result["available"])
        get.assert_called_once()


class TestTradingCalendar(unittest.TestCase):
    def test_calendar_without_network(self):
        import trading_calendar as m
        with patch.object(m, "_fetch_online_holidays", return_value=([], None)):
            self.assertFalse(m.is_trading_day(date(2026, 1, 1)))
            self.assertTrue(m.is_trading_day(date(2026, 9, 1)))
            status = m.get_trading_status(date(2026, 9, 1))
        self.assertIn(status["market_status"], {"trading", "post_holiday"})
        self.assertIsInstance(status["last_trading_day"], date)


class TestOtherCurrentAPIs(unittest.TestCase):
    def test_github_monitor_urllib_and_analysis(self):
        import github_monitor as m
        monitor = m.GitHubMonitor(repo="owner/repo", workflow_name="CI", token="token")
        data = {"workflow_runs": [{"id": 1, "run_number": 2, "conclusion": "success",
                                    "created_at": "2026-09-01T00:00:00Z", "run_started_at": "2026-09-01T00:05:00Z",
                                    "html_url": "https://example.invalid/run/1"}]}
        with patch.object(monitor, "_http_get", return_value=data):
            runs = monitor.get_recent_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(monitor.analyze_delays(runs)["average_delay_seconds"], 300.0)

    def test_article_extractor_fallback_is_deterministic(self):
        import article_extractor as m
        html = b"<html><head><title>Title</title></head><body><article>" + b"content " * 30 + b"</article></body></html>"
        response = MagicMock(content=html)
        response.raise_for_status.return_value = None
        with patch.object(m.requests, "get", return_value=response):
            with patch.dict(sys.modules, {"newspaper": None, "readability": None}):
                result = m.extract_article("https://example.invalid/article")
        self.assertEqual(result["title"], "Title")
        self.assertGreater(len(result["text"]), 100)

    def test_static_page_generator_escapes_and_writes(self):
        import static_page_generator as m
        with tempfile.TemporaryDirectory() as directory:
            path = m.generate_translation_page(
                {"url": "https://example.invalid/a", "title": "<T>", "source": "S"}, "A & B", directory
            )
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as generated:
                self.assertIn("&lt;T&gt;", generated.read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
