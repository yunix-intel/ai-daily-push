#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic whole-product white-box tests.

This module is intentionally discoverable by ``unittest``.  External services
are replaced with fixtures or mocks so a failure is a real test failure rather
than an implicit skip caused by network availability.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(__file__))


class FakeResponse:
    def __init__(self, payload, encoding="utf-8"):
        if isinstance(payload, bytes):
            self.body = payload
        else:
            self.body = payload.encode(encoding)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body

    def close(self):
        return None

    """Every production entry point must remain importable."""

    def test_production_modules_import(self):
        module_names = [
            "ai_daily_push", "finance_daily_push", "llm_helpers",
            "concurrent_fetcher", "trading_calendar", "news_classifier",
            "article_translator", "article_extractor", "config_manager",
            "logger", "monitoring", "monitor_decorator", "alerting",
            "push_history_recorder", "github_monitor", "cloudfunction_handler",
            "wechat_content_builder", "wechat_content_formatter",
            "wechat_official_publisher", "workflow_lock",
            "scrapers.money_flow_scraper", "scrapers.twitter_scraper",
            "scrapers.weibo_scraper", "scrapers.blogger_scraper",
            "analyzers.market_data_aggregator", "analyzers.news_metrics_extractor",
            "analyzers.trend_analyzer",
        ]
        for module_name in module_names:
            __import__(module_name)


class TestAIDailyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ai_daily_push
        cls.module = ai_daily_push

    def test_helpers_handle_boundaries(self):
        self.assertEqual(self.module.safe_md_url("https://example.com/a b"),
                         "https://example.com/a%20b")
        self.assertGreaterEqual(len(self.module.truncate_bytes("中文abc", 7)), 1)
        self.assertEqual(self.module.fmt_cst("2026-09-01T00:00:00Z", "%Y-%m-%d"),
                         "2026-09-01")
        self.assertGreater(self.module.calculate_similarity("same", "same"), 0.99)
        self.assertLess(self.module.calculate_similarity("abc", "xyz"), 0.5)

    def test_shape_preserves_original_and_translated_content(self):
        report = {"sections": [{"label": "International", "items": [{
            "title": "译文", "originalTitle": "Original title",
            "summary": "摘要", "originalSummary": "Original summary",
            "source": {"name": "Fixture"}, "links": {
                "original": "https://example.invalid/article"
            }, "translated_content": "全文译文",
        }]}]}
        data = self.module.shape(report, market_insights=[])
        item = data["sections"][0]["items"][0]
        self.assertEqual(item["originalTitle"], "Original title")
        self.assertEqual(item["originalSummary"], "Original summary")
        self.assertEqual(item["translated_content"], "全文译文")
        self.assertIn("翻译全文", self.module.build_html(data))

    def test_http_get_and_highlights_are_deterministic(self):
        with patch.object(self.module.urllib.request, "urlopen",
                          return_value=FakeResponse('{"items": [1]}')):
            self.assertEqual(self.module.http_get("https://example.invalid/data"),
                             {"items": [1]})
        item = {"title": "Important", "summary": "Event", "source": "Fixture", "idx": 0}
        self.assertEqual(self.module.pick_highlights([(item, "AI")], top_n=1)[0]["title"],
                         "Important")


class TestFinanceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import finance_daily_push
        cls.module = finance_daily_push

    def setUp(self):
        self._base_url_env = os.environ.pop("OPENAI_BASE_URL", None)
        self._api_key_env = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        if self._base_url_env is not None:
            os.environ["OPENAI_BASE_URL"] = self._base_url_env
        if self._api_key_env is not None:
            os.environ["OPENAI_API_KEY"] = self._api_key_env

    def test_classification_and_aggregate_filter(self):
        self.assertEqual(self.module.classify_news_category({"title": "A股半导体回升"}),
                         "domestic")
        self.assertEqual(self.module.classify_news_category({"title": "美联储加息"}),
                         "international")
        items = [{"title": "今日要闻汇总"}, {"title": "政策新闻"}]
        self.assertEqual(self.module.filter_aggregated_news(items), [items[1]])

    def test_finance_shape_contains_failure_states(self):
        twitter = {"rumors": [], "media": [], "available": False,
                   "errors": {"rumors": "RSSHub unavailable"}}
        data = self.module.shape_finance([], [], {}, {}, {}, {},
                                         blogger_views=[], twitter_content=twitter)
        self.assertFalse(data["twitter"]["available"])
        html = self.module.build_finance_html(data)
        self.assertIn("RSSHub unavailable", html)

    def test_markdown_and_translation_disabled_contract(self):
        data = {"meta": {"date": "2026-09-01"}, "quotes": [],
                "domestic": {"sections": []}, "international": {"sections": []}}
        html = self.module.build_finance_html(data)
        markdown = self.module.build_finance_markdown(data, "https://example.invalid/finance")
        self.assertIn("2026-09-01", html)
        self.assertIsInstance(markdown, tuple)
        self.assertEqual(self.module.translate_page_url("https://example.invalid/a"), "")

    def test_quote_parsers_and_fallbacks(self):
        m = self.module
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse("[]")):
            self.assertIsNone(m._sina_ashare_close("sh000001"))
        rows = [{"close": "100", "day": "2026-09-06"},
                {"close": "110", "day": "2026-09-07"}]
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps(rows))):
            self.assertEqual(m._sina_ashare_close("sh000001"),
                             (110.0, 10.0, 10.0, "2026-09-07"))
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps([{"close": "9"}]))):
            self.assertEqual(m._sina_ashare_close("sh000001"), (9.0, 0.0, 0.0, ""))

        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse("bad")):
            self.assertIsNone(m._sina_hk_close("hkHSI"))
        fields = ["x"] * 18
        fields[6], fields[7], fields[8], fields[17] = "20000", "100", "0.5", "2026/09/07"
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse('x="' + ','.join(fields) + '"')):
            self.assertEqual(m._sina_hk_close("hkHSI"),
                             (20000.0, 100.0, 0.5, "2026/09/07"))
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps({"data": {"klines": []}}))):
            self.assertIsNone(m._eastmoney_close("sh000001"))
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps({"data": {"klines": [
                              "2026-09-07,1,110,0,0,2" ]}}))):
            self.assertEqual(m._eastmoney_close("sh000001"),
                             (110.0, 2.2, 2.0, "2026-09-07"))
        self.assertIsNone(m._eastmoney_close("unknown"))
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse('x="1,2,3"')):
            self.assertIsNone(m._sina_hk_close("hkHSI"))
        with patch.object(m.urllib.request, "urlopen",
                          return_value=FakeResponse(json.dumps({"data": {"klines": [
                              "2026-09-06,1,100,0,0,5",
                              "2026-09-07,1,110,0,0,10"]}}))):
            self.assertEqual(m._eastmoney_close("sh000001"),
                             (110.0, 10.0, 10.0, "2026-09-07"))

        with patch.object(m, "_sina_ashare_close", side_effect=RuntimeError("primary")), \
             patch.object(m, "_sina_hk_close", return_value=None), \
             patch.object(m, "_eastmoney_close", side_effect=[(1, 2, 3, "2026/09/07"), None, None, None, None]):
            result = m._fetch_last_close_quotes()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["as_of"], "2026-09-07")

        with patch.object(m, "_fetch_last_close_quotes", return_value=[]), \
             patch.object(m, "is_trading_hour", return_value=False), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse("")):
            self.assertEqual(m.fetch_quotes(), [])

    def test_quote_realtime_and_rss_mirror_paths(self):
        m = self.module
        chunks = 'v_sh000001="x~上证指数~x~100~' + '~'*27 + '2~3";garbage;'
        with patch.object(m, "is_trading_hour", return_value=True), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(chunks)):
            self.assertEqual(m.fetch_quotes()[0]["price"], 100.0)
        with patch.object(m, "fetch_rss", return_value=[{"title": "x"}]) as fetch:
            self.assertEqual(m._fetch_rss_with_mirrors("source", "https://fixture/rss"),
                             [{"title": "x"}])
            fetch.assert_called_once()
        with patch.object(m, "fetch_rss", side_effect=[RuntimeError("one"),
                                                           [{"title": "fallback"}]]):
            self.assertEqual(m._fetch_rss_with_mirrors("source", "/fixture"),
                             [{"title": "fallback"}])
        with patch.object(m, "fetch_rss", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                m._fetch_rss_with_mirrors("source", "/fixture")

    def test_finance_collection_translation_and_sections(self):
        m = self.module
        feeds = [("国内源", "/dom"), ("国际源", "https://fixture/en")]
        payloads = {
            "国内源": [{"title": "A股政策", "summary": "摘要", "link": "u", "published": ""},
                       {"title": "今日要闻汇总", "summary": "", "link": "x", "published": ""}],
            "国际源": [{"title": "Federal Reserve raises rates", "summary": "Markets update", "link": "e", "published": ""}],
        }
        def fake_fetch(source, path, limit=20):
            return payloads[source]
        with patch.object(m, "FINANCE_FEEDS_ZH", [feeds[0]]), \
             patch.object(m, "FINANCE_FEEDS_EN", [feeds[1]]), \
             patch.object(m, "_fetch_rss_with_mirrors", side_effect=fake_fetch), \
             patch("trading_calendar.is_trading_hour", return_value=True):
            result = m.fetch_finance_items(hours=24)
        self.assertEqual(len(result["domestic"]), 1)
        self.assertEqual(len(result["international"]), 1)
        items = [{"title": "Federal Reserve policy", "summary": "English summary", "isEnglish": True}]
        with patch.object(m, "translate_batch_llm", return_value={0: ("美联储政策", "英文摘要")}):
            m.translate_finance_items(items)
        self.assertEqual(items[0]["title"], "美联储政策")
        self.assertEqual(items[0]["originalTitle"], "Federal Reserve policy")
        items = [{"title": "Federal Reserve policy", "summary": "English summary", "isEnglish": True}]
        with patch.object(m, "translate_batch_llm", side_effect=[{}, {}]):
            m.translate_finance_items(items)
        self.assertEqual(items[0]["title"], "Federal Reserve policy")
        items = [{"title": "中文标题", "summary": "中文摘要", "isEnglish": False}]
        self.assertEqual(m.translate_finance_items(items)[0]["title"], "中文标题")
        items = [{"title": "Federal Reserve policy", "summary": "English summary", "isEnglish": True}]
        with patch.object(m, "translate_batch_llm", side_effect=RuntimeError("translate down")):
            self.assertEqual(m.translate_finance_items(items)[0]["title"], "Federal Reserve policy")
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "0"}):
            self.assertEqual(m.translate_finance_items(items)[0]["originalSummary"], "English summary")
        self.assertEqual(len(m.classify_sections(
            [{"title": "央行降准", "summary": ""}, {"title": "无关", "summary": ""}],
            m.SECTION_RULES_DOMESTIC)), 2)

    def test_rendering_history_and_blogger_paths(self):
        m = self.module
        domestic = [{"label": "政策", "items": [{"title": "降准", "summary": "摘要", "link": "u", "source": "源"}]}]
        international = [{"label": "全球", "items": [{"title": "美联储更新", "summary": "summary", "link": "e", "source": "Bloomberg", "isEnglish": True, "originalTitle": "Fed update"}]}]
        with patch.object(m, "translate_page_url", return_value="translated"):
            data = m.shape_finance(domestic, international, [{"name": "指数", "price": 1, "change": 0, "pct": 0}], {}, {}, {"aShare": "A", "hkShare": "H", "risk": "R"}, blogger_views=[], twitter_content={"available": True})
        self.assertEqual(data["meta"]["domesticCount"], 1)
        self.assertEqual(data["meta"]["internationalCount"], 1)
        self.assertEqual(data["international"]["sections"][0]["items"][0]["translatedPage"], "translated")
        html = m.build_finance_html(data)
        body, tail = m.build_finance_markdown(data, "https://dash.test/a b")
        self.assertIn("查看财经日报", tail)
        self.assertIn("国际要闻（1 条）", body)
        self.assertTrue(m.compose_markdown("body", "very long tail", 2))
        rich = {
            "meta": {"date": "2026-09-01", "domesticCount": 1, "internationalCount": 1},
            "quotes": [{"name": "上证", "price": 3000, "pct": 1}],
            "strategy": {"aShare": "A", "hkShare": "H", "risk": "R",
                         "is_post_holiday": True, "holiday_summary": "回顾"},
            "domestic": {"sections": [{}], "emergencyEvents": [{"title": "D", "desc": "d"}],
                         "analysis": {"summary": "国内总结"}},
            "international": {"sections": [{}], "emergencyEvents": [{"title": "I", "desc": "i"}],
                              "analysis": {"summary": "国际总结"}},
        }
        rich_body, _ = m.build_finance_markdown(rich, "")
        self.assertIn("休市期间要闻回顾", rich_body)
        self.assertIn("国内总结", rich_body)
        self.assertIn("国际总结", rich_body)
        closed = {**rich, "strategy": {"aShare": "休市", "is_trading_day": False,
                                         "last_trading_day": "9月1日"}}
        self.assertIn("市场状态", m.build_finance_markdown(closed, "")[0])
        ordinary = {**rich, "strategy": {"aShare": "A", "hkShare": "H",
                                           "is_trading_day": True}}
        self.assertIn("A 股", m.build_finance_markdown(ordinary, "")[0])
        with patch.object(m, "http_post_json", return_value={"ok": True}) as post:
            self.assertEqual(m.push_feishu_markdown("hook", "title", "body", "tail",
                                                    "https://example.invalid"), {"ok": True})
            self.assertEqual(post.call_args.args[1]["card"]["elements"][-1]["tag"], "action")
        with patch.object(m, "_llm_config", return_value=("key", "https://api.example.com/v1", "tr", "analysis")), \
             patch.object(m, "call_llm_json", return_value={"aShare": "A", "hkShare": "H",
                                                              "risk": m.DISCLAIMER}):
            holiday = {"market_status": "trading", "last_trading_day": date(2026, 9, 4),
                       "is_post_holiday": True, "days_since_last_trading": 4}
            self.assertTrue(m.generate_strategy({}, [], holiday)["is_post_holiday"])
        with patch.object(m, "get_trading_status", return_value={
                "market_status": "weekend", "last_trading_day": date(2026, 9, 4),
                "is_post_holiday": False, "days_since_last_trading": 2}):
            self.assertFalse(m.generate_strategy({}, [], None)["is_trading_day"])
        with patch("article_translator.batch_translate_articles", side_effect=RuntimeError("full text")):
            m.pre_translate_articles([])
        with patch.object(m, "call_llm_json", return_value={"viewpoint": "观点", "focus": ["芯片"], "tone": "中性"}):
            blogger = {"name": "博主", "uid": "1", "articles": [{"title": "文章", "content": "正文", "published": "今天"}]}
            self.assertEqual(m.generate_blogger_digest(blogger)["tone"], "中性")
        self.assertEqual(m.generate_blogger_digest({}), {})
        with patch.dict(sys.modules, {"scrapers.blogger_scraper": None}):
            self.assertEqual(m.collect_blogger_views([{"uid": "1"}]), [])

    def test_finance_edge_filters_and_translation_batch(self):
        m = self.module
        self.assertEqual(m.clean_html_tags('<style>.x{color:red}</style><b>A&nbsp;&amp; B</b><span'), 'A & B')
        self.assertIsNone(m._published_dt('not-a-date'))
        self.assertIsNone(m._published_dt(None))
        self.assertFalse(m._looks_english('中文标题'))
        self.assertFalse(m._looks_english('short'))
        self.assertTrue(m._looks_english('Federal Reserve policy'))
        self.assertEqual(m._apply_translation(
            [{'title': 'old', 'summary': 'old'}], [0], {0: ('新标题', '')}), {0})
        self.assertEqual(m._apply_translation(
            [{'title': 'old', 'summary': 'old'}], [0], {}), set())

        feeds = [('国内', '/dom'), ('国际', '/en')]
        payloads = {
            '国内': [{'title': '旧消息', 'summary': 'x', 'published': 'Mon, 01 Jan 2000 00:00:00 GMT'},
                    {'title': '', 'summary': '', 'published': ''},
                    {'title': 'A股政策', 'summary': '<b>摘要</b>', 'published': ''}],
            '国际': [{'title': 'Markets Wrap', 'summary': '', 'published': ''}],
        }
        with patch.object(m, 'FINANCE_FEEDS_ZH', [feeds[0]]), \
             patch.object(m, 'FINANCE_FEEDS_EN', [feeds[1]]), \
             patch.object(m, '_fetch_rss_with_mirrors', side_effect=lambda s, p, limit=20: payloads[s]), \
             patch('trading_calendar.is_trading_hour', return_value=False), \
             patch('trading_calendar.is_intraday_news', side_effect=lambda t, s: t == 'A股政策'):
            result = m.fetch_finance_items(hours=24)
        self.assertEqual(result, {'domestic': [], 'international': []})

        pairs = [(0, 'One English title', 'English summary'), (1, 'Another title', '')]
        with patch.object(m, 'call_llm_json', side_effect=[
            {'items': [{'id': '0', 'title': '中文一', 'summary': '摘要一'}, {'id': None, 'title': 'x'}]},
            RuntimeError('batch down')]):
            translated = m.translate_batch_llm(pairs, batch_size=1)
        self.assertEqual(translated[0], ('中文一', '摘要一'))

    def test_finance_analysis_blogger_and_collection_failures(self):
        m = self.module
        self.assertIn('无可用点位', m._quotes_digest([]))
        self.assertIn('Source', m._news_digest([{'source': 'Source', 'title': 'T', 'summary': 'S'}]))
        with patch.object(m, '_llm_config', return_value=('key', 'url', 'tr', 'analysis')), \
             patch.object(m, 'call_llm_json', return_value={'summary': 'ok'}):
            self.assertEqual(m.generate_analysis([], [], '国内')['summary'], 'ok')
        holiday = {'market_status': 'trading', 'last_trading_day': date(2026, 9, 4),
                   'is_post_holiday': False, 'days_since_last_trading': 3}
        with patch.object(m, '_llm_config', return_value=('key', 'url', 'tr', 'analysis')), \
             patch.object(m, 'call_llm_json', side_effect=RuntimeError('strategy down')):
            with self.assertRaisesRegex(RuntimeError, 'strategy down'):
                m.generate_strategy({'summary': '', 'macro': '', 'sector': '', 'emergencyEvents': []}, [], holiday)
        with patch('scrapers.blogger_scraper.BloggerScraper') as scraper_cls:
            scraper_cls.return_value.fetch_all.return_value = []
            self.assertEqual(m.collect_blogger_views([{'uid': '1'}]), [])
        with patch('scrapers.blogger_scraper.BloggerScraper') as scraper_cls, \
             patch.object(m, 'generate_blogger_digest', side_effect=RuntimeError('digest down')):
            scraper_cls.return_value.fetch_all.return_value = [
                {'name': '微博用户', 'uid': '1', 'articles': [{'title': 'T', 'url': 'u', 'published': '', 'isLive': True}]},
                {'name': '博客用户', 'uid': '2', 'articles': []},
            ]
            result = m.collect_blogger_views([{'uid': '1', 'type': 'weibo'}, {'uid': '2'}])
        self.assertEqual(result[0]['platform'], 'weibo')
        self.assertEqual(result[0]['focus'], [])

        m = self.module
        config = ("sk-fixture", "https://llm.invalid/v1", "translate", "analysis")
        body = {
            "choices": [{"message": {"content": "```json\n{\"ok\": true}\n```"}}]
        }
        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps(body))):
            self.assertEqual(m.call_llm_json("s", "u", retries=0), {"ok": True})
        with patch.object(m, "_llm_config", return_value=("", "url", "t", "a")):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                m.call_llm_text("s", "u", retries=0)
        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", side_effect=RuntimeError("down")), \
             patch.object(m.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "down"):
                m.call_llm_text("s", "u", retries=1)
            self.assertEqual(sleep.call_count, 1)

        analysis = {"summary": "summary", "macro": "macro", "sector": "sector",
                    "emergencyEvents": []}
        weekend = {"market_status": "weekend", "last_trading_day": date(2026, 9, 4),
                   "is_post_holiday": False, "days_since_last_trading": 2}
        result = m.generate_strategy(analysis, [], weekend)
        self.assertFalse(result["is_trading_day"])
        with patch.object(m, "call_llm_json", return_value={
                "aShare": "A", "hkShare": "H", "risk": "R"}):
            ordinary = {"market_status": "trading", "last_trading_day": date(2026, 9, 7),
                        "is_post_holiday": False, "days_since_last_trading": 1}
            result = m.generate_strategy(analysis, [], ordinary)
        self.assertTrue(result["is_trading_day"])
        self.assertIn(m.DISCLAIMER, result["risk"])

        with patch.object(m, "http_post_json", return_value={"errcode": 0}) as post:
            self.assertEqual(m.push_wecom_news_card("hook", "https://dash"), {"errcode": 0})
            self.assertEqual(m.push_markdown("hook", "body", "tail"), {"errcode": 0})
            self.assertEqual(m.push_feishu_markdown("hook", "title", "body", "tail"),
                             {"errcode": 0})
            self.assertEqual(post.call_count, 3)


class TestClassificationAndTranslation(unittest.TestCase):
    def test_classifier_fallback_and_empty_batches(self):
        import news_classifier
        self.assertEqual(news_classifier.classify_news_region_batch([], MagicMock()), [])
        self.assertEqual(news_classifier.score_news_importance_batch([], MagicMock()), [])
        self.assertEqual(news_classifier.identify_breaking_news([], MagicMock()), [])
        failed = MagicMock(side_effect=RuntimeError("offline"))
        self.assertEqual(
            news_classifier.classify_news_region_batch(
                [{"title": "央行降准", "summary": ""}], failed),
            ["domestic"],
        )

    def test_classifier_normalizes_and_clamps_llm_results(self):
        import news_classifier
        classify = MagicMock(return_value={"result": ["Domestic", "国际"]})
        self.assertEqual(
            news_classifier.classify_news_region_batch(
                [{"title": "A"}, {"title": "B"}], classify),
            ["domestic", "international"],
        )
        score = MagicMock(return_value={"scores": [11, -2]})
        self.assertEqual(news_classifier.score_news_importance_batch(
            [{"title": "A"}, {"title": "B"}], score), [10, 0])

    def test_article_extractor_fixture_fallback(self):
        import article_extractor
        html = b"<html><head><title>Title</title></head><body><article>" + b"content " * 30 + b"</article></body></html>"
        response = MagicMock(content=html)
        response.raise_for_status.return_value = None
        with patch.object(article_extractor.requests, "get", return_value=response):
            with patch.dict(sys.modules, {"newspaper": None, "readability": None}):
                result = article_extractor.extract_article("https://example.invalid/article")
        self.assertEqual(result["title"], "Title")
        self.assertGreater(len(result["text"]), 100)

    def test_article_extractor_newspaper_success(self):
        import types
        import article_extractor

        class FakeArticle:
            title = "News title"
            text = "article body " * 20
            html = "<p>article body</p>"
            authors = ["A", "B"]
            publish_date = datetime(2026, 9, 1)

            def __init__(self, url):
                self.url = url

            def download(self):
                return None

            def parse(self):
                return None

        newspaper = types.ModuleType("newspaper")
        newspaper.Article = FakeArticle
        with patch.dict(sys.modules, {"newspaper": newspaper, "readability": None}):
            result = article_extractor.extract_article("https://example.invalid/news")
        self.assertEqual(result["title"], "News title")
        self.assertEqual(result["author"], "A, B")
        self.assertEqual(result["publish_date"], "2026-09-01 00:00:00")


class TestNewsClassifierWhiteBox(unittest.TestCase):
    def test_extract_array_shapes_and_errors(self):
        import news_classifier as m
        self.assertEqual(m._extract_json_array([1, 2]), [1, 2])
        self.assertEqual(m._extract_json_array({"result": [3]}), [3])
        self.assertEqual(m._extract_json_array("prefix [4, 5] suffix"), [4, 5])
        with self.assertRaises(ValueError):
            m._extract_json_array({"result": "not-array"})
        with self.assertRaises(ValueError):
            m._extract_json_array("no json array")

    def test_keyword_classification_priority_and_sources(self):
        import news_classifier as m
        self.assertEqual(m.classify_by_keywords({"title": "美国与中国市场"}), "domestic")
        self.assertEqual(m.classify_by_keywords({"title": "Fed raises rates"}), "international")
        self.assertEqual(m.classify_by_keywords({"source": {"name": "Reuters"}}), "international")
        self.assertEqual(m.classify_by_keywords({"source": "新浪财经"}), "domestic")
        self.assertEqual(m.classify_by_keywords({}), "domestic")

    def test_batches_and_single_batch_failures(self):
        import news_classifier as m
        items = [{"title": f"A{i}", "summary": ""} for i in range(21)]
        llm = MagicMock(side_effect=['["domestic",' * 0 + '[' + ','.join(['"domestic"'] * 20) + ']', RuntimeError("offline")])
        result = m.classify_news_region_batch(items, llm)
        self.assertEqual(len(result), 21)
        self.assertEqual(result[-1], "domestic")
        score = m.score_news_importance_batch(items, MagicMock(side_effect=RuntimeError("offline")))
        self.assertEqual(len(score), 21)
        self.assertTrue(all(0 <= value <= 10 for value in score))
        self.assertGreater(m.deterministic_importance_score({"title": "重大政策：央行降准"}),
                           m.deterministic_importance_score({"title": "普通行业观点"}))

    def test_chunk_validation_and_model_selection(self):
        import news_classifier as m
        with patch.dict(os.environ, {"OPENAI_MODEL_TRANSLATE": " translate-model ", "OPENAI_MODEL_CLASSIFY": ""}, clear=False):
            call = MagicMock(return_value='["domestic"]')
            self.assertEqual(m._classify_region_chunk([{"title": "x"}], call), ["domestic"])
            self.assertEqual(call.call_args.kwargs["model"], "translate-model")
        with self.assertRaises(ValueError):
            m._classify_region_chunk([{"title": "x"}, {"title": "y"}], MagicMock(return_value='["domestic"]'))
        with self.assertRaises(ValueError):
            m._score_importance_chunk([{"title": "x"}], MagicMock(return_value="[1, 2]"))

    def test_breaking_heuristic_llm_filter_and_region_hints(self):
        import news_classifier as m
        items = [
            {"title": "突发：中国央行政策", "summary": "紧急消息"},
            {"title": "暴跌：美国市场", "summary": "危机"},
            {"title": "突发普通消息", "summary": ""},
        ]
        heuristic = m.identify_breaking_news(items, None)
        self.assertEqual(len(heuristic), 2)
        self.assertEqual(heuristic[0]["_region_hint"], "domestic")
        self.assertEqual(heuristic[1]["_region_hint"], "international")
        analyses = [{"is_breaking": True, "importance": 8, "brief_analysis": "重大", "affected_sectors": ["金融"]},
                    {"is_breaking": False, "importance": 10}, "bad"]
        result = m.identify_breaking_news(items, MagicMock(return_value=analyses))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["direction"], "中性")
        self.assertEqual(result[0]["_region_hint"], "domestic")
        self.assertEqual(m.identify_breaking_news([{"title": "平静", "summary": ""}], None), [])
    def test_breaking_llm_failure_fallback_and_source_dict(self):
        import news_classifier as m
        score_call = MagicMock(return_value="[7]")
        self.assertEqual(m._score_importance_chunk(
            [{"title": "x", "summary": "text", "source": {"name": "Fixture"}}],
            score_call), [7])
        item = {"title": "突发：美国市场危机", "summary": ""}
        result = m.identify_breaking_news([item], MagicMock(side_effect=RuntimeError("offline")))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["_region_hint"], "international")

    def test_breaking_analysis_ignores_extra_results(self):
        import news_classifier as m
        result = m._analyze_breaking_chunk(
            [{"title": "突发", "summary": "x"}],
            MagicMock(return_value=[{"is_breaking": False}, {"is_breaking": True, "importance": 9}]),
        )
        self.assertEqual(result, [])


class TestLLMHelpers(unittest.TestCase):
    def test_config_defaults_and_missing_key(self):
        import llm_helpers as m
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key", "OPENAI_BASE_URL": ""}, clear=False), \
             patch.object(m, "_BASE_URL_WARNED", False), \
             patch.object(m.os.path, "exists", return_value=False):
            key, base, translate, analysis = m._llm_config()
        self.assertEqual(key, "env-key")
        self.assertEqual(base, "https://api.openai.com/v1")
        self.assertEqual(translate, "")
        self.assertEqual(analysis, "")

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False), \
             patch.object(m.os.path, "exists", return_value=False):
            self.assertEqual(m._llm_config(), (None, None, None, None))

    def test_text_and_json_calls_success_and_errors(self):
        import llm_helpers as m
        config = ("key", "https://llm.invalid/v1", "translate", "analysis")
        text_body = {"choices": [{"message": {"content": " plain text "}}]}
        json_body = {"choices": [{"message": {"content": "```json\n{\"ok\": true}\n```"}}]}
        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", side_effect=[
                 FakeResponse(json.dumps(text_body)), FakeResponse(json.dumps(json_body))]):
            self.assertEqual(m.call_llm("system", "user", retries=0), "plain text")
            self.assertEqual(m.call_llm_json("system", "user", retries=0), {"ok": True})

        with patch.object(m, "_llm_config", return_value=("", "url", "t", "a")):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                m.call_llm("s", "u", retries=0)
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                m.call_llm_json("s", "u", retries=0)

        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse("{}")):
            with self.assertRaises(KeyError):
                m.call_llm("s", "u", retries=0)

    def test_retry_and_model_semaphore_paths(self):
        import llm_helpers as m
        config = ("key", "https://llm.invalid/v1", "translate", "analysis")
        body = {"choices": [{"message": {"content": "done"}}]}
        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", side_effect=[
                 RuntimeError("temporary"), FakeResponse(json.dumps(body))]), \
             patch.object(m.time, "sleep") as sleep:
            self.assertEqual(m.call_llm("s", "u", retries=1, model="analysis", timeout=7), "done")
        sleep.assert_called_once_with(3)
        self.assertIs(m._semaphore_for_model("analysis", "translate", "analysis"),
                      m._ANALYSIS_SEMAPHORE)
        self.assertIs(m._semaphore_for_model("other", "translate", "analysis"),
                      m._DEEPSEEK_SEMAPHORE)
    def test_config_file_error_and_json_retry_exhaustion(self):
        import llm_helpers as m

        with patch.dict(os.environ, {
                "OPENAI_API_KEY": "env-key",
                "OPENAI_BASE_URL": "",
                "OPENAI_MODEL_TRANSLATE": "",
                "OPENAI_MODEL_ANALYSIS": "",
             }, clear=False), \
             patch.object(m.os.path, "exists", return_value=True), \
             patch("builtins.open", side_effect=OSError("config unavailable")):
            key, base, translate, analysis = m._llm_config()
        self.assertEqual(key, "env-key")
        self.assertTrue(base)
        self.assertEqual(translate, "")
        self.assertEqual(analysis, "")

        config = ("key", "https://llm.invalid/v1", "translate", "analysis")
        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", side_effect=RuntimeError("down")), \
             patch.object(m.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "down"):
                m.call_llm_json("s", "u", retries=1)
        sleep.assert_called_once_with(3)


class TestStructuredLogger(unittest.TestCase):
    def setUp(self):
        import logger as m
        self.module = m
        self.previous_loggers = m.LoggerFactory._loggers
        self.previous_dir = m.LoggerFactory._log_dir
        self.previous_level = m.LoggerFactory._default_level
        m.LoggerFactory._loggers = {}

    def tearDown(self):
        for structured in self.module.LoggerFactory._loggers.values():
            for handler in structured.logger.handlers[:]:
                handler.close()
                structured.logger.removeHandler(handler)
        self.module.LoggerFactory._loggers = self.previous_loggers
        self.module.LoggerFactory._log_dir = self.previous_dir
        self.module.LoggerFactory._default_level = self.previous_level

    def test_json_formatter_includes_context_and_exception(self):
        import logging
        m = self.module
        record = logging.LogRecord("fixture", logging.ERROR, __file__, 10,
                                   "failed %s", ("call",), None, "func")
        record.trace_id = "trace"
        record.user_id = 7
        record.extra_data = {"token": "masked"}
        try:
            raise ValueError("boom")
        except ValueError:
            record.exc_info = sys.exc_info()
        payload = json.loads(m.JsonFormatter().format(record))
        self.assertEqual(payload["message"], "failed call")
        self.assertEqual(payload["trace_id"], "trace")
        self.assertEqual(payload["user_id"], 7)
        self.assertEqual(payload["extra"], {"token": "masked"})
        self.assertEqual(payload["exception"]["type"], "ValueError")
        self.assertIn("boom", payload["exception"]["message"])

    def test_structured_logger_methods_and_factory_cache(self):
        m = self.module
        with tempfile.TemporaryDirectory() as directory:
            m.LoggerFactory.configure(directory, "DEBUG")
            log = m.LoggerFactory.get_logger("white-box-logger")
            self.assertIs(log, m.LoggerFactory.get_logger("white-box-logger"))
            trace_id = log.start_trace()
            self.assertTrue(trace_id)
            with patch.object(log.logger, "log") as emit:
                log.debug("debug", value=1)
                log.info("info", value=2)
                log.warning("warning", value=3)
                log.error("error", code=4)
                log.critical("critical", code=5)
                log.performance("fetch", 1.25, items=6)
                log.audit("read", user="tester", target="fixture")
            self.assertEqual(emit.call_count, 7)
            self.assertEqual(emit.call_args_list[0].kwargs["extra"]["trace_id"], trace_id)
            self.assertEqual(emit.call_args_list[0].kwargs["extra"]["extra_data"], {"value": 1})
            self.assertTrue(os.path.exists(os.path.join(directory, "white-box-logger.json.log")))
            self.assertTrue(os.path.exists(os.path.join(directory, "white-box-logger.error.log")))
            for handler in log.logger.handlers[:]:
                handler.close()
                log.logger.removeHandler(handler)

    def test_exception_logging_and_execution_decorator(self):
        m = self.module
        fake = MagicMock()
        fake.start_trace.return_value = "trace"
        with patch.object(m.LoggerFactory, "get_logger", return_value=fake):
            @m.log_execution("decorator-test")
            def add(a, b):
                return a + b

            @m.log_execution()
            def fail():
                raise LookupError("bad")

            self.assertEqual(add(2, 3), 5)
            fake.performance.assert_called_once()
            with self.assertRaisesRegex(LookupError, "bad"):
                fail()
            fake.error.assert_called_once()
            self.assertTrue(fake.error.call_args.kwargs["exc_info"])

        with tempfile.TemporaryDirectory() as directory:
            log = m.StructuredLogger("exception-logger", directory, "DEBUG")
            with patch.object(log.logger, "error") as error, \
                 patch.object(log.logger, "critical") as critical:
                try:
                    raise RuntimeError("failure")
                except RuntimeError:
                    log.error("error", exc_info=True, operation="op")
                    log.critical("critical", exc_info=True, operation="op")
            self.assertTrue(error.call_args.kwargs["exc_info"])
            self.assertTrue(critical.call_args.kwargs["exc_info"])
            for handler in log.logger.handlers[:]:
                handler.close()
                log.logger.removeHandler(handler)


class TestArticleExtractorFallbacks(unittest.TestCase):
    def test_article_extractor_readability_success(self):
        import types
        import article_extractor

        class FakeDocument:
            def __init__(self, content):
                self.content = content

            def summary(self):
                return "<div>" + ("readable body " * 20) + "</div>"

            def title(self):
                return "Readable title"

        readability = types.ModuleType("readability")
        readability.Document = FakeDocument
        response = MagicMock(content=b"source")
        response.raise_for_status.return_value = None
        with patch.dict(sys.modules, {"newspaper": None, "readability": readability}):
            with patch.object(article_extractor.requests, "get", return_value=response):
                result = article_extractor.extract_article("https://example.invalid/readable")
        self.assertEqual(result["title"], "Readable title")
        self.assertGreater(len(result["text"]), 100)
        self.assertIn("readable body", result["html"])

    def test_article_extractor_readability_error_falls_back_to_soup(self):
        import types
        import article_extractor

        class BrokenDocument:
            def __init__(self, content):
                raise ValueError("bad document")

        readability = types.ModuleType("readability")
        readability.Document = BrokenDocument
        html = b"<html><head><title>Fallback</title></head><body><main>" + b"body " * 30 + b"</main></body></html>"
        response = MagicMock(content=html)
        response.raise_for_status.return_value = None
        with patch.dict(sys.modules, {"newspaper": None, "readability": readability}):
            with patch.object(article_extractor.requests, "get", return_value=response):
                result = article_extractor.extract_article("https://example.invalid/fallback")
        self.assertEqual(result["title"], "Fallback")
        self.assertGreater(len(result["text"]), 100)

    def test_article_extractor_short_newspaper_falls_back(self):
        import types
        import article_extractor

        class ShortArticle:
            text = "too short"
            title = ""
            html = ""
            authors = []
            publish_date = None

            def __init__(self, url):
                self.url = url

            def download(self):
                return None

            def parse(self):
                return None

        newspaper = types.ModuleType("newspaper")
        newspaper.Article = ShortArticle
        response = MagicMock(content=b"<html><body><article>" + b"body " * 30 + b"</article></body></html>")
        response.raise_for_status.return_value = None
        with patch.dict(sys.modules, {"newspaper": newspaper, "readability": None}):
            with patch.object(article_extractor.requests, "get", return_value=response):
                result = article_extractor.extract_article("https://example.invalid/short")
        self.assertIsNotNone(result)

    def test_article_extractor_short_readability_and_missing_region(self):
        import types
        import article_extractor

        class ShortDocument:
            def __init__(self, content):
                self.content = content

            def summary(self):
                return "<div>short</div>"

            def title(self):
                return "Short"

        readability = types.ModuleType("readability")
        readability.Document = ShortDocument
        short_response = MagicMock(content=b"source")
        short_response.raise_for_status.return_value = None
        missing_response = MagicMock(content=b"<html><head><title>Missing</title></head></html>")
        missing_response.raise_for_status.return_value = None
        with patch.dict(sys.modules, {"newspaper": None, "readability": readability}):
            with patch.object(article_extractor.requests, "get", side_effect=[short_response, missing_response, missing_response]):
                self.assertIsNone(article_extractor.extract_article("https://example.invalid/short-readable"))

        with patch.dict(sys.modules, {"newspaper": None, "readability": None}):
            with patch.object(article_extractor.requests, "get", return_value=missing_response):
                self.assertIsNone(article_extractor.extract_article("https://example.invalid/missing"))

    def test_article_extractor_soup_short_content(self):
        import article_extractor
        response = MagicMock(content=b"<html><body><main>short</main></body></html>")
        response.raise_for_status.return_value = None
        with patch.dict(sys.modules, {"newspaper": None, "readability": None}):
            with patch.object(article_extractor.requests, "get", return_value=response):
                self.assertIsNone(article_extractor.extract_article("https://example.invalid/short-soup"))

    def test_article_extractor_soup_removes_script_and_style(self):
        import article_extractor
        response = MagicMock(content=(
            b"<html><body><article><script>bad()</script><style>.x{}</style>"
            + b"useful body " * 30 + b"</article></body></html>"
        ))
        response.raise_for_status.return_value = None
        with patch.dict(sys.modules, {"newspaper": None, "readability": None}):
            with patch.object(article_extractor.requests, "get", return_value=response):
                result = article_extractor.extract_article("https://example.invalid/scripts")
        self.assertIsNotNone(result)
        self.assertNotIn("bad()", result["text"])

    def test_article_extractor_returns_none_when_all_strategies_fail(self):
        import article_extractor
        response = MagicMock(content=b"<html><body>short</body></html>")
        response.raise_for_status.side_effect = RuntimeError("HTTP failure")
        with patch.dict(sys.modules, {"newspaper": None, "readability": None}):
            with patch.object(article_extractor.requests, "get", return_value=response):
                self.assertIsNone(article_extractor.extract_article("https://example.invalid/fail"))


class TestDataSourcesAndConcurrency(unittest.TestCase):
    def test_money_flow_partial_failure_contract(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        with patch.object(scraper, "_clist", side_effect=[
            [{"f14": "In", "f62": "100000000", "f3": "1", "f184": "1"}],
            RuntimeError("sector unavailable"),
        ]):
            result = scraper.fetch_sector_flow(top_n=1)
        self.assertTrue(result["available"])
        self.assertEqual(result["top_inflow"][0]["name"], "In")
        self.assertEqual(result["top_outflow"], [])
        self.assertIn("sector unavailable", result["error"])

    def test_current_money_flow_scraper_fallback_and_shape_paths(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        self.assertEqual(scraper._num("-"), 0.0)
        self.assertEqual(scraper._num(None), 0.0)
        self.assertEqual(scraper._shape_flow({"f14": "A", "f62": "100000000", "f3": "2.5", "f184": "1"}),
                         {"name": "A", "net_inflow": 1.0, "change_pct": 2.5, "net_ratio": 1.0})
        shaped = scraper._shape_flow({"f12": "000001", "f14": "A", "f62": 0, "f3": 0, "f184": 0}, with_code=True)
        self.assertEqual(shaped["code"], "000001")
        self.assertFalse(scraper._parse_north_flow({"data": {}})["available"])
        parsed = scraper._parse_north_flow({"data": {"hk2sh": {"dayNetAmtIn": "100000000"}, "hk2sz": {"dayNetAmtIn": "-50000000"}}})
        self.assertTrue(parsed["available"])
        self.assertEqual(parsed["total_flow"], 0.5)
        with patch.object(scraper, "_get_json", return_value={"data": {"hk2sh": ["2026-09-01,100000000,0"], "hk2sz": ["2026-09-01,200000000,0"]}}):
            result = scraper._fetch_eastmoney_post_close("2026-09-01")
        self.assertEqual(result["total_flow"], 3.0)
        with patch.object(scraper, "_get_json", return_value={"data": {}}):
            with self.assertRaises(ValueError):
                scraper._fetch_eastmoney_post_close("2026-09-01")
        with patch.object(scraper, "_clist", side_effect=[[{"f14": "in", "f62": 100000000, "f3": 1, "f184": 2}], [{"f14": "out", "f62": -100000000, "f3": -1, "f184": 3}]]):
            self.assertTrue(scraper.fetch_sector_flow(top_n=1)["available"])
        with patch.object(scraper, "_clist", side_effect=RuntimeError("offline")):
            self.assertEqual(scraper.fetch_stock_flow(top_n=1)["top_inflow"], [])
        with patch.object(scraper, "_fetch_eastmoney_post_close", side_effect=RuntimeError("down")), patch.object(scraper, "_fetch_10jqka_post_close", return_value={"available": True}):
            self.assertEqual(scraper.fetch_north_flow("2026-09-01")["attempted_sources"], ["10jqka"])
        with patch.object(scraper, "_fetch_eastmoney_post_close", side_effect=RuntimeError("down")), patch.object(scraper, "_fetch_10jqka_post_close", side_effect=RuntimeError("down")):
            self.assertFalse(scraper.fetch_north_flow("2026-09-01")["available"])

    def test_money_flow_northbound_success_and_failure(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        payload = {"data": {"hk2sh": ["2026-09-03,120000000,0,0"],
                             "hk2sz": ["2026-09-03,-20000000,0,0"]}}
        with patch.object(scraper, "_get_json", return_value=payload):
            result = scraper.fetch_north_flow("2026-09-03")
        self.assertTrue(result["available"])
        self.assertEqual(result["total_flow"], 1.0)
        with patch.object(scraper, "_fetch_eastmoney_post_close",
                          side_effect=TimeoutError("timeout")):
            with patch.object(scraper, "_fetch_10jqka_post_close",
                              side_effect=RuntimeError("blocked")):
                with patch.object(scraper, "_load_cached_north", return_value=None):
                    failed = scraper.fetch_north_flow("2026-09-03")
        self.assertFalse(failed["available"])
        self.assertIn("eastmoney", failed["reason"])

    def test_money_flow_north_cache_hit_validation_and_write_isolation(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper

        with tempfile.TemporaryDirectory() as directory:
            cache_path = os.path.join(directory, "north.json")
            with patch.dict(os.environ, {"MONEY_FLOW_CACHE": cache_path}):
                scraper = MoneyFlowScraper()
                payload = [
                    {"trade_date": "2026-99-99", "available": True},
                    {"trade_date": "2026-09-10", "available": True,
                     "total_flow": 10},
                    {"trade_date": "2026-09-04", "available": True,
                     "total_flow": 4},
                    {"trade_date": "2026-09-03", "available": True,
                     "total_flow": 3},
                ]
                with open(cache_path, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream)
                cached = scraper._load_cached_north("2026-09-05")
                self.assertEqual(cached["trade_date"], "2026-09-04")
                self.assertTrue(cached["stale"])
                self.assertEqual(cached["collection_mode"], "cached_post_close")
                self.assertIn("2026-09-04", cached["reason"])

                with patch.object(scraper, "_fetch_eastmoney_post_close",
                                  side_effect=RuntimeError("down")), \
                     patch.object(scraper, "_fetch_10jqka_post_close",
                                  side_effect=RuntimeError("down")):
                    fallback = scraper.fetch_north_flow("2026-09-05")
                self.assertTrue(fallback["available"])
                self.assertEqual(fallback["attempted_sources"],
                                 ["eastmoney", "10jqka", "cache"])

                for index in range(31):
                    scraper._save_cached_north({
                        "date": f"2026-08-{index + 1:02d}",
                        "trade_date": f"2026-08-{index + 1:02d}",
                        "available": True,
                        "total_flow": index,
                    })
                with open(cache_path, "r", encoding="utf-8") as stream:
                    self.assertLessEqual(len(json.load(stream)), 30)

                with patch("pathlib.Path.write_text",
                                  side_effect=OSError("read-only")):
                    live = {"trade_date": "2026-09-05", "available": True}
                    scraper._save_cached_north(live)
                    self.assertTrue(live["available"])

    def test_money_flow_north_cache_io_failures_are_unavailable(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper

        scraper = MoneyFlowScraper()
        with patch("pathlib.Path.read_text", side_effect=OSError("offline")):
            self.assertIsNone(scraper._load_cached_north("2026-09-05"))
        with patch("pathlib.Path.read_text",
                   side_effect=json.JSONDecodeError("bad", "", 0)):
            self.assertIsNone(scraper._load_cached_north("2026-09-05"))

    def test_money_flow_transport_10jqka_and_script_paths(self):
        import scrapers.money_flow_scraper as module
        from scrapers.money_flow_scraper import MoneyFlowScraper

        scraper = MoneyFlowScraper()
        response = MagicMock()
        response.json.return_value = {"data": {"diff": [{"f14": "Fixture"}]}}
        response.raise_for_status.return_value = None
        with patch.object(module.requests, "get", side_effect=[RuntimeError("first host"), response]):
            self.assertEqual(scraper._get_json("/fixture", {"q": "1"})["data"]["diff"][0]["f14"], "Fixture")
        with patch.object(module.requests, "get", side_effect=RuntimeError("all hosts failed")):
            with self.assertRaisesRegex(RuntimeError, "all hosts failed"):
                scraper._get_json("/fixture", {})

        with patch.dict(sys.modules, {"trading_calendar": None}):
            self.assertEqual(scraper._resolve_target_date(), datetime.now().date().isoformat())
        self.assertEqual(scraper._resolve_target_date(date(2026, 9, 4)), "2026-09-04")
        self.assertEqual(scraper._resolve_target_date("2026-09-04"), "2026-09-04")

        tenjqka_response = MagicMock()
        tenjqka_response.raise_for_status.return_value = None
        tenjqka_response.json.return_value = {
            "data": {"zhuri": {"date": ["2026-09-04"], "h": ["120000000"], "total": ["170000000"]}}
        }
        with patch.object(module.requests, "get", return_value=tenjqka_response):
            tenjqka = scraper._fetch_10jqka_post_close("2026-09-04")
        self.assertEqual(tenjqka["sz_flow"], 0.5)
        tenjqka_response.json.return_value = {"data": {"zhuri": {"date": [], "h": [], "total": []}}}
        with patch.object(module.requests, "get", return_value=tenjqka_response):
            with self.assertRaisesRegex(ValueError, "日期不匹配"):
                scraper._fetch_10jqka_post_close("2026-09-04")
        tenjqka_response.json.return_value = {
            "data": {"zhuri": {"date": ["2026-09-04"], "h": ["nan"], "total": ["1"]}}
        }
        with patch.object(module.requests, "get", return_value=tenjqka_response):
            with self.assertRaisesRegex(ValueError, "有限数值"):
                scraper._fetch_10jqka_post_close("2026-09-04")

        with patch.object(scraper, "_clist", side_effect=[
            [{"f12": "000001", "f14": "In", "f62": 100000000, "f3": 3, "f184": 1}],
            [{"f12": "000002", "f14": "Out", "f62": -100000000, "f3": -2, "f184": 2}],
        ]):
            stock = scraper.fetch_stock_flow(top_n=1)
        self.assertEqual(stock["top_inflow"][0]["code"], "000001")
        self.assertEqual(stock["top_outflow"][0]["name"], "Out")
        self.assertFalse(scraper._parse_north_flow({"data": []})["available"])

        fake_scraper = MagicMock()
        fake_scraper.fetch_north_flow.return_value = {"date": "2026-09-04", "sh_flow": 1, "sz_flow": 2, "total_flow": 3}
        fake_scraper.fetch_sector_flow.return_value = {"date": "2026-09-04", "top_inflow": [{"name": "Sector", "net_inflow": 1}], "top_outflow": []}
        fake_scraper.fetch_stock_flow.return_value = {"date": "2026-09-04", "top_inflow": [{"name": "Stock", "net_inflow": 1}], "top_outflow": []}
        with patch.object(module, "MoneyFlowScraper", return_value=fake_scraper):
            module.test_scraper()

    def test_rsshub_failures_are_structured(self):
        from scrapers.twitter_scraper import TwitterScraper
        from scrapers.weibo_scraper import WeiboScraper
        twitter = TwitterScraper(rsshub_base="https://invalid.example", timeout=0.01)
        weibo = WeiboScraper(rsshub_base="https://invalid.example", timeout=0.01)
        with patch("scrapers.twitter_scraper.requests.get", side_effect=RuntimeError("offline")):
            twitter_result = twitter.fetch_tweets("fixture", limit=1)
        with patch("scrapers.weibo_scraper.requests.get", side_effect=RuntimeError("offline")):
            weibo_result = weibo.fetch_weibo_user("1", limit=1)
        self.assertFalse(twitter_result["available"])
        self.assertFalse(weibo_result["available"])
        self.assertIn("source_url", twitter_result)
        self.assertIn("source_url", weibo_result)

    def test_concurrent_fetcher_deadline_returns_partial_results(self):
        from concurrent_fetcher import ConcurrentFetcher
        fetcher = ConcurrentFetcher(max_workers=2, timeout=1, max_retries=0)
        result = fetcher.fetch_rss_concurrent(
            [("ok", "https://example.invalid/ok"), ("bad", "https://example.invalid/bad")],
            lambda name, url, limit: [{"source": name}] if name == "ok"
            else (_ for _ in ()).throw(RuntimeError("offline")),
        )
        self.assertEqual(result, [{"source": "ok"}])

    def test_concurrent_fetcher_retry_and_url_deadline_paths(self):
        from concurrent_fetcher import ConcurrentFetcher
        from urllib.error import HTTPError, URLError
        fetcher = ConcurrentFetcher(max_workers=1, timeout=1, max_retries=1)
        with patch("concurrent_fetcher.time.sleep"):
            calls = MagicMock(side_effect=[URLError("offline"), ["ok"]])
            self.assertEqual(fetcher._fetch_with_retry(calls, "n", "u"), ["ok"])
            self.assertEqual(calls.call_count, 2)
            forbidden = MagicMock(side_effect=HTTPError("u", 404, "missing", {}, None))
            with self.assertRaises(HTTPError):
                fetcher._fetch_with_retry(forbidden, "n", "u")
            other = MagicMock(side_effect=RuntimeError("bad"))
            with self.assertRaises(RuntimeError):
                fetcher._fetch_with_retry(other, "n", "u")
        results = fetcher.fetch_urls_concurrent(["u1", "u2"], lambda url: {"url": url})
        self.assertEqual(results["u1"], {"url": "u1"})
        self.assertEqual(results["u2"], {"url": "u2"})
        with patch.object(fetcher, "_fetch_with_retry_generic", side_effect=RuntimeError("bad")):
            failed = fetcher.fetch_urls_concurrent(["u"], lambda url: url)
        self.assertEqual(failed["u"]["error"], "bad")
        import concurrent_fetcher as module
        module.configure_fetcher(0, 0, -1)
        self.assertEqual(module.get_fetcher().max_workers, 1)

    def test_concurrent_fetcher_deadline_and_empty_paths(self):
        from concurrent_fetcher import ConcurrentFetcher
        fetcher = ConcurrentFetcher(max_workers=1, timeout=1, max_retries=0)
        self.assertEqual(fetcher.fetch_rss_concurrent([], lambda *args: []), [])
        self.assertEqual(fetcher.fetch_urls_concurrent([], lambda url: url), {})
        with patch.object(fetcher, "_fetch_with_retry_generic", side_effect=TimeoutError):
            result = fetcher.fetch_urls_concurrent(["u"], lambda url: url, deadline=0.001)
        self.assertIn("error", result["u"])


    def test_base_scraper_cache_retry_and_cleanup_edges(self):
        from scrapers.base_scraper import BaseScraper

        with tempfile.TemporaryDirectory() as directory:
            scraper = BaseScraper(directory)
            self.assertIsNone(scraper.load_cache("missing"))
            scraper.save_cache("fixture", {"value": 1})
            self.assertEqual(scraper.load_cache("fixture"), {"value": 1})
            with open(scraper.get_cache_path("broken"), "w", encoding="utf-8") as stream:
                stream.write("not-json")
            self.assertIsNone(scraper.load_cache("broken"))

            old_path = os.path.join(directory, "old_2020-01-01.json")
            recent_path = os.path.join(directory, "recent_2099-01-01.json")
            invalid_path = os.path.join(directory, "invalid-date.json")
            for path in (old_path, recent_path, invalid_path):
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write("{}")
            scraper.cleanup_old_cache(days=30)
            self.assertFalse(os.path.exists(old_path))
            self.assertTrue(os.path.exists(recent_path))
            self.assertTrue(os.path.exists(invalid_path))

            with patch("scrapers.base_scraper.open", side_effect=OSError("save offline")):
                scraper.save_cache("save-fail", {"value": 1})
            with patch("pathlib.Path.glob", return_value=[]):
                scraper.cleanup_old_cache()
            with patch("pathlib.Path.exists", return_value=False):
                self.assertIsNone(scraper.cleanup_old_cache())
            with patch("pathlib.Path.glob", side_effect=OSError("glob offline")):
                scraper.cleanup_old_cache()

            unlink_fail_path = os.path.join(directory, "unlink_2020-01-01.json")
            with open(unlink_fail_path, "w", encoding="utf-8") as stream:
                stream.write("{}")
            with patch("pathlib.Path.unlink", side_effect=OSError("unlink offline")):
                scraper.cleanup_old_cache(days=30)

            with patch("scrapers.base_scraper.time.sleep"):
                calls = MagicMock(side_effect=[RuntimeError("first"), {"ok": True}])
                self.assertEqual(scraper.fetch_with_retry(calls, retries=2), {"ok": True})
                self.assertEqual(calls.call_count, 2)
                failing = MagicMock(side_effect=RuntimeError("final"))
                with self.assertRaisesRegex(RuntimeError, "final"):
                    scraper.fetch_with_retry(failing, retries=1)

        self.assertIsNone(BaseScraper(tempfile.mkdtemp()).fetch_with_retry(
            lambda: {"ok": True}, retries=0))

        import trading_calendar
        with patch.object(trading_calendar, "_fetch_online_holidays", return_value=([], None)):
            self.assertFalse(trading_calendar.is_trading_day(date(2026, 1, 1)))
            self.assertTrue(trading_calendar.is_trading_day(date(2026, 9, 1)))
            status = trading_calendar.get_trading_status(date(2026, 9, 1))
        self.assertIsInstance(status["last_trading_day"], date)
        self.assertIsInstance(status["days_since_last_trading"], int)

    def test_config_environment_override_first_fixture(self):
        import config_manager
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "default.yaml"), "w", encoding="utf-8") as stream:
                stream.write("llm:\n  api_key: yaml-key\npush:\n  pushplus_token: token\n")
            with patch.dict(os.environ, {"LLM_API_KEY": "env-key"}, clear=False):
                config = config_manager.ConfigManager(directory).load()
        self.assertEqual(config.llm.api_key, "env-key")
        with self.assertRaises(config_manager.ConfigError):
            config_manager.AppConfig().validate()

    def test_config_validation_reports_all_invalid_fields(self):
        import config_manager
        config = config_manager.AppConfig(environment="invalid", llm=config_manager.LLMConfig(api_key=""),
                                          logging=config_manager.LoggingConfig(level="TRACE"))
        with self.assertRaisesRegex(config_manager.ConfigError, "无效的环境") as raised:
            config.validate()
        self.assertIn("至少一种推送渠道", str(raised.exception))
        self.assertIn("LLM API Key", str(raised.exception))
        self.assertIn("无效的日志级别", str(raised.exception))

    def test_config_env_variable_sections_and_partial_merge(self):
        import config_manager
        manager = config_manager.ConfigManager(tempfile.mkdtemp())
        with patch.dict(os.environ, {"LLM_API_KEY": "k", "WECOM_CORPID": "c"}, clear=True):
            data = manager._load_env_variables({})
        self.assertEqual(data, {"llm": {"api_key": "k"}, "push": {"wecom_corpid": "c"}})
        self.assertEqual(manager._merge_config({"a": 1}, {"a": {"nested": 2}}),
                         {"a": {"nested": 2}})

    def test_config_environment_override_first_fixture(self):
        import config_manager
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "default.yaml"), "w", encoding="utf-8") as stream:
                stream.write("llm:\n  api_key: yaml-key\npush:\n  pushplus_token: token\n")
            with patch.dict(os.environ, {"LLM_API_KEY": "env-key"}, clear=False):
                config = config_manager.ConfigManager(directory).load()
        self.assertEqual(config.llm.api_key, "env-key")
        with self.assertRaises(config_manager.ConfigError):
            config_manager.AppConfig().validate()

    def test_config_environment_override_first_fixture_duplicate(self):
        import config_manager
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "default.yaml"), "w", encoding="utf-8") as stream:
                stream.write("llm:\n  api_key: yaml-key\npush:\n  pushplus_token: token\n")
            with patch.dict(os.environ, {"LLM_API_KEY": "env-key"}, clear=False):
                config = config_manager.ConfigManager(directory).load()
        self.assertEqual(config.llm.api_key, "env-key")
        with self.assertRaises(config_manager.ConfigError):
            config_manager.AppConfig().validate()

    def test_config_environment_override_second_fixture(self):
        import config_manager
        with tempfile.TemporaryDirectory() as directory:
            manager = config_manager.ConfigManager(directory)
            with patch.dict(os.environ, {"APP_ENV": "staging", "LLM_API_KEY": "key",
                                         "LLM_BASE_URL": "https://llm.invalid",
                                         "WECOM_CORPID": "corp", "WECOM_CORPSECRET": "secret"}, clear=False):
                manager._env = "staging"
                config = manager.load(validate=False)
                self.assertEqual(config.llm.base_url, "https://llm.invalid")
                self.assertEqual(config.push.wecom_corpid, "corp")
                self.assertEqual(config.push.wecom_corpsecret, "secret")
                self.assertIs(manager.get(), config)
                self.assertIsNot(manager.reload(), config)
            self.assertEqual(manager._load_default_config(), {})
            self.assertEqual(manager._load_env_config("staging"), {})
            self.assertEqual(manager._merge_config({"a": {"b": 1}}, {"a": {"c": 2}}),
                             {"a": {"b": 1, "c": 2}})

    def test_config_builds_all_nested_sections_and_templates(self):
        import config_manager
        manager = config_manager.ConfigManager(tempfile.mkdtemp())
        data = {
            "environment": "dev", "debug": True, "app_name": "Fixture", "version": "9",
            "data_dir": "d", "cache_dir": "c",
            "push": {"pushplus_token": "p"}, "llm": {"api_key": "k"},
            "data_source": {"fetch_timeout": 4}, "monitoring": {"enabled": False},
            "logging": {"level": "DEBUG"}, "schedule": {"timezone": "UTC"},
        }
        config = manager._build_config(data)
        self.assertEqual(config.app_name, "Fixture")
        self.assertEqual(config.data_source.fetch_timeout, 4)
        self.assertFalse(config.monitoring.enabled)
        self.assertEqual(config.logging.level, "DEBUG")
        self.assertEqual(config.schedule.timezone, "UTC")
        self.assertIn("environment: production", manager._get_default_template())
        self.assertIn("environment: dev", manager._get_dev_template())
        self.assertIn("environment: production", manager._get_production_template())
        with tempfile.TemporaryDirectory() as directory:
            manager = config_manager.ConfigManager(directory)
            manager.save_template()
            self.assertTrue(os.path.exists(os.path.join(directory, "default.yaml")))
            manager.save_template()

        import trading_calendar as calendar
        old_cache_dir, old_cache_file = calendar.CACHE_DIR, calendar.CACHE_FILE
        with tempfile.TemporaryDirectory() as directory:
            calendar.CACHE_DIR = directory
            calendar.CACHE_FILE = os.path.join(directory, "calendar.json")
            try:
                self.assertEqual(calendar._load_cache(), {})
                calendar._save_cache({"A_2026": ["2026-01-01"]})
                cached = calendar._load_cache()
                self.assertEqual(cached["A_2026"], ["2026-01-01"])
                with open(calendar.CACHE_FILE, "w", encoding="utf-8") as stream:
                    stream.write("not json")
                self.assertEqual(calendar._load_cache(), {})
                with patch.object(calendar, "_ensure_cache_dir", side_effect=OSError("offline")):
                    calendar._save_cache({})

                xml = {"days": [
                    {"date": "2026-01-01", "isOffDay": True},
                    {"date": "2026-01-03", "isOffDay": True},
                    {"date": "2026-01-04", "isOffDay": False},
                ]}
                with patch("trading_calendar.urllib.request.urlopen",
                           return_value=FakeResponse(json.dumps(xml))):
                    holidays = calendar._fetch_official_holidays_from_github(2026)
                self.assertEqual(holidays, [date(2026, 1, 1)])
                with patch("trading_calendar.urllib.request.urlopen",
                           side_effect=OSError("offline")):
                    self.assertEqual(calendar._fetch_official_holidays_from_github(2026), [])

                self.assertEqual(calendar._fetch_online_holidays(2026, "HK"), ([], None))
                with patch.object(calendar, "_fetch_official_holidays_from_github",
                                  return_value=[date(2026, 1, 1)]):
                    holidays, last = calendar._fetch_online_holidays(2026, "A")
                self.assertEqual(holidays, [date(2026, 1, 1)])
                self.assertEqual(last, date(2026, 12, 31))

                eastmoney = {"data": {"klines": ["2026-01-02,x", "2026-01-05,x"]}}
                with patch.object(calendar, "_fetch_official_holidays_from_github", return_value=[]), \
                     patch("trading_calendar.urllib.request.urlopen",
                           return_value=FakeResponse(json.dumps(eastmoney))):
                    holidays, last = calendar._fetch_online_holidays(2026, "A")
                self.assertIn(date(2026, 1, 1), holidays)
                self.assertEqual(last, date(2026, 1, 5))
                with patch.object(calendar, "_fetch_official_holidays_from_github", return_value=[]), \
                     patch("trading_calendar.urllib.request.urlopen", side_effect=OSError("offline")):
                    self.assertEqual(calendar._fetch_online_holidays(2026, "A"), ([], None))
            finally:
                calendar.CACHE_DIR, calendar.CACHE_FILE = old_cache_dir, old_cache_file

    def test_trading_calendar_status_hours_and_local_data(self):
        import trading_calendar as calendar
        holiday = date(2026, 10, 1)
        with patch.object(calendar, "_load_cache", return_value={}), \
             patch.object(calendar, "_fetch_online_holidays", return_value=([], None)):
            self.assertFalse(calendar.is_trading_day(holiday))
            self.assertFalse(calendar.is_trading_day(date(2026, 10, 3)))
            self.assertTrue(calendar.is_trading_day(date(2026, 9, 1)))
            self.assertEqual(calendar.get_last_trading_day(date(2026, 9, 1)), date(2026, 8, 31))
            self.assertGreaterEqual(calendar.count_non_trading_days(date(2026, 8, 28), date(2026, 9, 1)), 2)
            self.assertFalse(calendar.is_post_holiday_first_day(holiday))
            status = calendar.get_trading_status(holiday)
            self.assertEqual(status["market_status"], "holiday")
            self.assertEqual(calendar.get_trading_status(date(2026, 10, 3))["market_status"], "weekend")
            self.assertEqual(calendar.get_trading_status(date(2026, 9, 1))["market_status"], "trading")

        with patch.object(calendar, "is_trading_day", return_value=True):
            self.assertTrue(calendar.is_trading_hour(datetime(2026, 9, 1, 9, 30)))
            self.assertTrue(calendar.is_trading_hour(datetime(2026, 9, 1, 15, 0)))
            self.assertFalse(calendar.is_trading_hour(datetime(2026, 9, 1, 12, 0)))
            self.assertFalse(calendar.is_trading_hour(datetime(2026, 9, 1, 10, 0), market="HK"))
        with patch.object(calendar, "is_trading_day", return_value=False):
            self.assertFalse(calendar.is_trading_hour(datetime(2026, 9, 1, 10, 0)))
        with patch.object(calendar, "is_trading_hour", return_value=True):
            self.assertTrue(calendar.is_intraday_news("盘中异动", "摘要", datetime(2026, 9, 1, 10, 0)))
        with patch.object(calendar, "is_trading_hour", return_value=False):
            self.assertFalse(calendar.is_intraday_news("尾盘消息", "摘要", datetime(2026, 9, 1, 20, 0)))
        self.assertTrue(calendar.is_intraday_news("开盘公告", "摘要"))
        self.assertFalse(calendar.is_intraday_news("普通公告", "摘要"))
        self.assertEqual(calendar.format_date_cn(date(2026, 9, 1)), "2026年09月01日")

    def test_trading_calendar_remaining_cache_and_status_paths(self):
        import trading_calendar as calendar
        old_cache_dir, old_cache_file = calendar.CACHE_DIR, calendar.CACHE_FILE
        with tempfile.TemporaryDirectory() as directory:
            calendar.CACHE_DIR = os.path.join(directory, "nested")
            calendar.CACHE_FILE = os.path.join(calendar.CACHE_DIR, "calendar.json")
            try:
                calendar._save_cache({"A_2026": ["2026-01-01"]})
                self.assertTrue(os.path.exists(calendar.CACHE_FILE))
                with open(calendar.CACHE_FILE, "w", encoding="utf-8") as stream:
                    json.dump({"update_time": "2000-01-01", "A_2026": ["bad-date"]}, stream)
                self.assertEqual(calendar._load_cache(), {})

                with open(calendar.CACHE_FILE, "w", encoding="utf-8") as stream:
                    json.dump({"update_time": "2026-01-01", "A_2026": ["bad-date"]}, stream)
                with patch.object(calendar, "_fetch_online_holidays", return_value=([], None)):
                    self.assertEqual(calendar._get_holidays_for_year(2026), calendar.A_STOCK_HOLIDAYS_2026)
                with patch.object(calendar, "_load_cache", return_value={}), \
                     patch.object(calendar, "_fetch_online_holidays", return_value=([], None)):
                    self.assertEqual(calendar._get_holidays_for_year(2030), [])

                with patch.object(calendar, "_fetch_official_holidays_from_github", return_value=[]), \
                     patch("trading_calendar.urllib.request.urlopen",
                           return_value=FakeResponse(json.dumps({"data": {"other": []}}))):
                    self.assertEqual(calendar._fetch_online_holidays(2026, "A"), ([], None))
                eastmoney = {"data": {"klines": ["2026-01-05,x", "2026-01-02,x"]}}
                with patch.object(calendar, "_fetch_official_holidays_from_github", return_value=[]), \
                     patch("trading_calendar.urllib.request.urlopen",
                           return_value=FakeResponse(json.dumps(eastmoney))):
                    holidays, last_date = calendar._fetch_online_holidays(2026, "A")
                self.assertEqual(last_date, date(2026, 1, 5))
                self.assertIn(date(2026, 1, 1), holidays)

                online = [date(2026, 1, 1)]
                with patch.object(calendar, "_load_cache", return_value={}), \
                     patch.object(calendar, "_fetch_online_holidays",
                                  return_value=(online, date(2026, 1, 31))), \
                     patch.object(calendar, "_save_cache") as save_cache:
                    holidays = calendar._get_holidays_for_year(2026, "A")
                self.assertIn(date(2026, 2, 16), holidays)
                save_cache.assert_called_once()

                with patch.object(calendar, "_load_cache",
                                  return_value={"A_2026_last_date": "bad-date"}):
                    self.assertIsNone(calendar._get_last_api_date(2026))
                with patch.object(calendar, "_load_cache",
                                  return_value={"A_2026_last_date": "2026-01-31"}):
                    self.assertEqual(calendar._get_last_api_date(2026), date(2026, 1, 31))
            finally:
                calendar.CACHE_DIR, calendar.CACHE_FILE = old_cache_dir, old_cache_file

        with patch.object(calendar, "is_trading_day", return_value=False):
            self.assertEqual(calendar.get_last_trading_day(date(2026, 1, 1)), date(2026, 1, 1))
        with patch.object(calendar, "is_trading_day", return_value=True), \
             patch.object(calendar, "get_last_trading_day", return_value=date(2026, 9, 1)), \
             patch.object(calendar, "count_non_trading_days", return_value=3):
            status = calendar.get_trading_status(date(2026, 9, 5))
        self.assertEqual(status["market_status"], "post_holiday")
        with patch.object(calendar, "is_trading_day", return_value=True), \
             patch.object(calendar, "is_trading_hour", wraps=calendar.is_trading_hour):
            aware = datetime(2026, 9, 1, 2, 0, tzinfo=timezone.utc)
            self.assertTrue(calendar.is_trading_hour(aware))

    def test_official_publisher_token_cache_and_errors(self):
        from wechat_official_publisher import WechatOfficialPublisher
        publisher = WechatOfficialPublisher("appid", "secret")
        publisher.access_token = "cached"
        publisher.token_expires_at = 9999999999
        with patch("wechat_official_publisher.time.time", return_value=100):
            self.assertEqual(publisher.get_access_token(), "cached")
        publisher.access_token = None
        with patch("wechat_official_publisher.urllib.request.urlopen",
                   return_value=FakeResponse(json.dumps({"errcode": 401, "errmsg": "invalid ip"}))):
            with self.assertRaises(Exception) as caught:
                publisher.get_access_token()
        self.assertIn("invalid ip", str(caught.exception))

    def test_official_publisher_complete_local_contract(self):
        from wechat_official_publisher import WechatOfficialPublisher
        publisher = WechatOfficialPublisher("appid", "secret")
        publisher.get_access_token = MagicMock(return_value="token")
        responses = [
            FakeResponse(json.dumps({"media_id": "img-1"})),
            FakeResponse(json.dumps({"media_id": "draft-1"})),
            FakeResponse(json.dumps({"publish_id": "pub-1", "msg_data_id": "msg-1"})),
            FakeResponse(json.dumps({"publish_status": "发布状态"})),
        ]
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as image:
            image_path = image.name
        try:
            with patch("wechat_official_publisher.urllib.request.urlopen",
                       side_effect=responses) as urlopen:
                result = publisher.publish_article("标题", "作者", "摘要", "<p>内容</p>", image_path,
                                                   "https://example.invalid/source")
                self.assertEqual(result["publish_id"], "pub-1")
                status = publisher.get_publish_status("pub-1")
            self.assertEqual(status["publish_status"], "发布状态")
            self.assertEqual(urlopen.call_count, 4)
        finally:
            os.unlink(image_path)

    def test_official_publisher_invalid_responses_and_short_circuit(self):
        from wechat_official_publisher import WechatOfficialPublisher
        publisher = WechatOfficialPublisher("appid", "secret")
        publisher.get_access_token = MagicMock(return_value="token")
        with tempfile.NamedTemporaryFile(suffix=".jpg") as image:
            checks = [
                ("upload_news_image", (image.name,), "图片上传异常"),
                ("add_draft", ("t", "a", "d", "c", "thumb"), "草稿创建异常"),
                ("publish_draft", ("draft",), "草稿发布异常"),
                ("get_publish_status", ("publish",), "查询发布状态异常"),
            ]
            for method, args, message in checks:
                with patch("wechat_official_publisher.urllib.request.urlopen",
                           return_value=FakeResponse(json.dumps({"errmsg": "bad"}))):
                    with self.assertRaises(Exception) as caught:
                        getattr(publisher, method)(*args)
                self.assertIn(message, str(caught.exception))

        publisher.upload_news_image = MagicMock(return_value="thumb")
        publisher.add_draft = MagicMock(return_value="draft")
        publisher.publish_draft = MagicMock(return_value={})
        self.assertEqual(publisher.publish_article("t", "a", "d", "c", "cover.jpg"), {})
        publisher.publish_draft.assert_called_once_with("draft")

    def test_official_publisher_convenience_requires_publish_id_and_config(self):
        import builtins
        import wechat_official_publisher as module
        config = json.dumps({"wechat_official": {"enabled": True, "appid": "cfg-app", "appsecret": "cfg-secret"}})
        with patch.object(builtins, "open", return_value=FakeResponse(config)), patch.object(
                module.WechatOfficialPublisher, "publish_article", return_value={}):
            self.assertFalse(module.publish_to_wechat_official("t", "a", "d", "c", "cover.jpg"))
        with patch.object(builtins, "open", side_effect=OSError("no config")):
            self.assertFalse(module.publish_to_wechat_official("t", "a", "d", "c", "cover.jpg"))
        disabled = json.dumps({"wechat_official": {"enabled": False}})
        with patch.object(builtins, "open", return_value=FakeResponse(disabled)):
            self.assertFalse(module.publish_to_wechat_official("t", "a", "d", "c", "cover.jpg"))

    def test_official_publisher_success_with_environment_credentials(self):
        import builtins
        import wechat_official_publisher as module
        config = json.dumps({"wechat_official": {"enabled": False}})
        with patch.object(builtins, "open", return_value=FakeResponse(config)), patch.dict(
                os.environ, {"WECHAT_APPID": "env-app", "WECHAT_APPSECRET": "env-secret"}), patch.object(
                module.WechatOfficialPublisher, "publish_article", return_value={"publish_id": "pub-1"}):
            self.assertTrue(module.publish_to_wechat_official("t", "a", "d", "c", "cover.jpg"))

    def test_history_and_monitor_contracts(self):
        import github_monitor
        monitor = github_monitor.GitHubMonitor("owner/repo", "CI", "token")
        payload = {"workflow_runs": [{"id": 1, "run_number": 2,
                    "event": "schedule", "status": "completed", "conclusion": "success",
                    "created_at": "2026-09-01T00:05:00Z",
                    "run_started_at": "2026-09-01T00:05:30Z",
                    "updated_at": "2026-09-01T00:06:00Z",
                    "html_url": "https://example.invalid/run"}]}
        with patch.object(monitor, "_get_workflow_id", return_value=123), \
                patch.object(monitor, "_http_get", return_value=payload):
            runs = monitor.get_recent_runs(limit=1)
        self.assertEqual(monitor.analyze_delays(runs)["average_delay_seconds"], 3900.0)




class TestOperationsAndPersistence(unittest.TestCase):
    def test_workflow_lock_lifecycle_and_recovery(self):
        import workflow_lock
        with tempfile.TemporaryDirectory() as directory:
            lock_path = os.path.join(directory, "lock")
            with patch.object(workflow_lock, "LOCK_FILE", __import__("pathlib").Path(lock_path)):
                self.assertTrue(workflow_lock.check_lock())
                self.assertFalse(workflow_lock.check_lock())
                workflow_lock.release_lock()
                self.assertFalse(os.path.exists(lock_path))
                with open(lock_path, "w", encoding="utf-8") as stream:
                    stream.write("not-a-date")
                self.assertTrue(workflow_lock.check_lock())
                workflow_lock.release_lock()

    def test_workflow_lock_expired_file_is_replaced(self):
        import workflow_lock
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as directory:
            lock_path = __import__("pathlib").Path(directory) / "lock"
            with patch.object(workflow_lock, "LOCK_FILE", lock_path):
                old = datetime.now(timezone.utc) - timedelta(hours=2)
                lock_path.write_text(old.isoformat(), encoding="utf-8")
                self.assertTrue(workflow_lock.check_lock())
                self.assertNotEqual(lock_path.read_text(encoding="utf-8"), old.isoformat())
                workflow_lock.release_lock()

    def test_push_history_formats_records_and_report(self):
        from push_history_recorder import PushHistoryRecorder, to_beijing, format_beijing_time
        aware = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        self.assertIn("2026-09-01 08:00:00", to_beijing(aware))
        self.assertIn("北京时间", format_beijing_time(aware))
        with tempfile.TemporaryDirectory() as directory:
            history_path = os.path.join(directory, "history.json")
            report_path = os.path.join(directory, "report.html")
            recorder = PushHistoryRecorder(history_path)
            with patch("push_history_recorder.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = datetime(2026, 9, 1, 23, 30, tzinfo=timezone.utc)
                mocked_datetime.combine = datetime.combine
                mocked_datetime.min = datetime.min
                mocked_datetime.fromisoformat = datetime.fromisoformat
                record = recorder.record_push("23:23", "test")
            self.assertEqual(record["task"], "test")
            self.assertEqual(record["schema_version"], 2)
            self.assertEqual(record["delivery_completed_at"], record["timestamp"])
            self.assertEqual(record["scheduled_at"], record["expected_time"])
            self.assertIsNone(record["event_created_at"])
            self.assertIsNone(record["runner_started_at"])
            self.assertEqual(len(recorder.history), 1)
            recorder.generate_report(report_path)
            self.assertTrue(os.path.exists(report_path))
            with open(report_path, encoding="utf-8") as stream:
                html = stream.read()
            self.assertIn("总推送次数", html)
            self.assertIn("delay-low", html)
            self.assertEqual(PushHistoryRecorder(os.path.join(directory, "missing.json")).history, [])
            with open(history_path, "w", encoding="utf-8") as stream:
                stream.write("broken")
            self.assertEqual(PushHistoryRecorder(history_path).history, [])

    def test_push_history_normalizes_milestones_and_rejects_invalid_delays(self):
        from push_history_recorder import PushHistoryRecorder
        with tempfile.TemporaryDirectory() as directory:
            history_path = os.path.join(directory, "history.json")
            payload = {"records": [
                {
                    "task": "legacy",
                    "timestamp": "2026-09-01T23:05:00Z",
                    "expected_time": "2026-09-01T23:00:00Z",
                },
                {
                    "schema_version": "bad",
                    "delivery_completed_at": "2026-09-01T22:59:00Z",
                    "scheduled_at": "2026-09-01T23:00:00Z",
                },
                "malformed",
            ]}
            with open(history_path, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
            recorder = PushHistoryRecorder(history_path)
            self.assertEqual(len(recorder.history), 1)
            self.assertEqual(recorder.history[0]["schema_version"], 1)
            self.assertEqual(recorder.history[0]["delay_seconds"], 300)

            delivery = datetime(2026, 9, 1, 23, 5, tzinfo=timezone.utc)
            event = datetime(2026, 9, 1, 23, 1, tzinfo=timezone.utc)
            runner = datetime(2026, 9, 1, 23, 2)
            pipeline = datetime(2026, 9, 1, 23, 7, tzinfo=timezone.utc)
            record = recorder.record_push(
                "23:00", "milestones", delivery, event, runner, pipeline
            )
            self.assertEqual(record["event_created_at"], event.isoformat())
            self.assertEqual(record["runner_started_at"], runner.replace(
                tzinfo=timezone.utc).isoformat())
            self.assertEqual(record["pipeline_completed_at"], pipeline.isoformat())
            invalid = PushHistoryRecorder._normalize_record({
                "delivery_completed_at": "2026-09-01T22:59:00Z",
                "scheduled_at": "2026-09-01T23:00:00Z",
            })
            self.assertIsNone(invalid)

    def test_delivery_status_requires_all_wecom_successes(self):
        from delivery_status import (
            latest_successful_delivery, load_successful_delivery,
            write_delivery_status,
        )
        with tempfile.TemporaryDirectory() as directory:
            ai_path = os.path.join(directory, "ai.json")
            finance_path = os.path.join(directory, "finance.json")
            ai_time = datetime(2026, 9, 1, 23, 4, tzinfo=timezone.utc)
            finance_time = datetime(2026, 9, 1, 23, 6, tzinfo=timezone.utc)
            payload = write_delivery_status(
                ai_path, "ai", "wecom_webhook", True, True, True, ai_time
            )
            self.assertNotIn("webhook", payload)
            self.assertEqual(load_successful_delivery(ai_path), ai_time)
            write_delivery_status(
                finance_path, "finance", "wecom_webhook", True, True, True,
                finance_time,
            )
            self.assertEqual(
                latest_successful_delivery([ai_path, finance_path]), finance_time
            )

            write_delivery_status(
                finance_path, "finance", "wecom_webhook", True, True, False,
                reason="api_rejected",
            )
            with self.assertRaisesRegex(ValueError, "未成功"):
                latest_successful_delivery([ai_path, finance_path])
            with self.assertRaisesRegex(ValueError, "未配置"):
                load_successful_delivery(
                    self._write_json(directory, "none.json", {
                        "schema_version": 1, "report": "ai", "channel": "none",
                        "configured": False, "attempted": False, "success": False,
                    })
                )
            with self.assertRaisesRegex(ValueError, "未提供"):
                latest_successful_delivery([])

    @staticmethod
    def _write_json(directory, name, payload):
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        return path

    def test_push_history_rollover_save_failure_and_empty_report(self):
        from push_history_recorder import PushHistoryRecorder
        with tempfile.TemporaryDirectory() as directory:
            history_path = os.path.join(directory, "history.json")
            recorder = PushHistoryRecorder(history_path)
            with patch("push_history_recorder.datetime") as mocked_datetime:
                mocked_datetime.now.return_value = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
                mocked_datetime.combine = datetime.combine
                mocked_datetime.min = datetime.min
                record = recorder.record_push("23:23", "before")
            self.assertEqual(record["expected_time"], "2026-08-31T23:23:00+00:00")
            with patch("builtins.open", side_effect=OSError("disk full")):
                with patch("push_history_recorder.datetime") as mocked_datetime:
                    mocked_datetime.now.return_value = datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc)
                    mocked_datetime.combine = datetime.combine
                    mocked_datetime.min = datetime.min
                    recorder.record_push("23:23", "after")
            self.assertEqual(len(recorder.history), 2)
            empty = PushHistoryRecorder(os.path.join(directory, "empty.json"))
            self.assertIsNone(empty.generate_report(os.path.join(directory, "empty.html")))

    def test_push_history_future_rollover_delay_classes_and_cli(self):
        import push_history_recorder
        from push_history_recorder import PushHistoryRecorder, to_beijing
        now = datetime(2026, 9, 1, 23, 0, tzinfo=timezone.utc)
        expected = PushHistoryRecorder._resolve_expected_dt(now, "23:23")
        self.assertEqual(expected.date(), now.date())
        self.assertEqual(
            PushHistoryRecorder._resolve_expected_dt(
                datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc), "23:23"
            ).date(), date(2026, 8, 31)
        )
        self.assertEqual(
            PushHistoryRecorder._resolve_expected_dt(
                datetime(2026, 9, 1, 12, 0, tzinfo=None), "23:23"
            ).tzinfo, timezone.utc
        )
        recorder = PushHistoryRecorder(os.path.join(tempfile.gettempdir(), "unused-history.json"))
        records = []
        for seconds in (100, 301, 601):
            records.append({
                "date": "2026-09-01",
                "timestamp": "2026-09-01T00:00:00+00:00",
                "expected_time": "2026-09-01T00:00:00+00:00",
                "delay_seconds": seconds,
                "delay_minutes": seconds / 60,
            })
        html = recorder._build_html(3, 334, 601, 100, records)
        self.assertIn("delay-low", html)
        self.assertIn("delay-medium", html)
        self.assertIn("delay-high", html)
        with tempfile.TemporaryDirectory() as directory, patch.object(
            push_history_recorder, "PushHistoryRecorder", return_value=recorder
        ):
            old_argv = sys.argv
            try:
                sys.argv = ["push_history_recorder.py", "--no-record",
                            "--report", os.path.join(directory, "report.html")]
                push_history_recorder.main()
            finally:
                sys.argv = old_argv

    def test_wechat_ai_empty_and_populated_paths(self):
        from wechat_content_formatter import format_ai_daily_for_wechat
        empty = format_ai_daily_for_wechat({"meta": {"date": "bad"}})
        self.assertEqual(empty[0], "AI 日报")
        self.assertEqual(empty[2], "今日AI行业要闻")
        populated = format_ai_daily_for_wechat({
            "meta": {"date": "2026-09-01"},
            "highlights": [{"title": "重要事件", "summary": "摘要"}],
            "sections": [{"label": "工具", "items": [{
                "title": "工具标题", "summary": "工具摘要", "source": "来源"
            }]}],
        })
        self.assertIn("AI 日报", populated[1])
        self.assertIn("工具标题", populated[1])
        self.assertIn("1. 重要事件", populated[2])

    def test_wechat_cover_cache_and_download_failure(self):
        from wechat_content_builder import prepare_ai_daily_cover, prepare_finance_daily_cover
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            ai_path = Path(directory) / "ai_daily_cover.jpg"
            ai_path.write_bytes(b"cached")
            with patch("wechat_content_builder.datetime") as mocked_datetime:
                mocked_datetime.now.return_value.date.return_value = __import__("datetime").date.today()
                mocked_datetime.fromtimestamp.return_value.date.return_value = __import__("datetime").date.today()
                self.assertEqual(prepare_ai_daily_cover(directory), str(ai_path))
            with patch("wechat_content_builder.download_cover_image", return_value=False):
                self.assertIsNone(prepare_finance_daily_cover(directory))

    def test_wechat_stale_covers_and_html_builders(self):
        from wechat_content_builder import (prepare_ai_daily_cover,
                                             prepare_finance_daily_cover,
                                             html_to_wechat_article,
                                             html_to_wechat_finance_article)
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            for name in ("ai_daily_cover.jpg", "finance_daily_cover.jpg"):
                path = Path(directory) / name
                path.write_bytes(b"old")
                old = __import__("time").time() - 3 * 86400
                os.utime(path, (old, old))
            with patch("wechat_content_builder.download_cover_image", return_value=True) as download:
                self.assertEqual(prepare_ai_daily_cover(directory),
                                 os.path.join(directory, "ai_daily_cover.jpg"))
                self.assertEqual(prepare_finance_daily_cover(directory),
                                 os.path.join(directory, "finance_daily_cover.jpg"))
            self.assertEqual(download.call_count, 2)
            ai_html = html_to_wechat_article("ignored", "AI <日报>", "https://example.invalid/ai")
            finance_html = html_to_wechat_finance_article("ignored", "财经日报", "https://example.invalid/finance")
            self.assertIn("AI <日报>", ai_html)
            self.assertIn("财经日报", finance_html)
            self.assertIn("投资建议", finance_html)

    def test_wechat_finance_empty_and_populated_paths(self):
        from wechat_content_formatter import format_finance_daily_for_wechat
        empty = format_finance_daily_for_wechat({"meta": {"date": "bad"}})
        self.assertEqual(empty[0], "财经日报")
        populated = format_finance_daily_for_wechat({
            "meta": {"date": "2026-09-01", "domesticCount": 1, "internationalCount": 1},
            "strategy": {"recommendation": "保持谨慎"},
            "domestic": {"sections": [{"items": [{"title": "国内", "summary": "摘要", "source": "源"}]}]},
            "international": {"sections": [{"items": [{"title": "国际", "summary": "摘要", "source": "源"}]}]},
        })
        self.assertIn("今日策略", populated[1])
        self.assertIn("国内", populated[1])
        self.assertIn("国际", populated[1])
        self.assertIn("国内 1 条", populated[2])

    def test_wechat_cover_download_success(self):
        from wechat_content_builder import download_cover_image
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "cover.jpg")
            with patch("wechat_content_builder.urllib.request.urlopen", return_value=FakeResponse(b"image")):
                self.assertTrue(download_cover_image("https://example.invalid/cover", target))
            with open(target, "rb") as stream:
                self.assertEqual(stream.read(), b"image")
            with patch("wechat_content_builder.urllib.request.urlopen", side_effect=RuntimeError("offline")):
                self.assertFalse(download_cover_image("https://example.invalid/cover", target))


class TestAnalyzerModules(unittest.TestCase):
    def test_market_report_formatter_all_cards_and_empty(self):
        from analyzers.market_report_formatter import MarketReportFormatter
        formatter = MarketReportFormatter()
        empty_cards = formatter.format_for_html({})
        self.assertEqual(len(empty_cards), 1)
        self.assertIn("已确认：0 项", empty_cards[0]["content"])
        cards = formatter.format_for_html({
            "news_metrics": {
                "revenue": [{"company": "A", "value": "10"}],
                "funding": [{"company": "B", "amount": "$2M"}],
                "users": [{"company": "C", "metric": "DAU", "value": "3M"}],
                "price_changes": [{"model": "M", "change": "-20%"}],
            },
            "market_trends": {
                "total_models": 4,
                "pricing_summary": {"min_price": 0.1, "max_price": 2, "avg_price": 0.7},
                "top_models_by_price": [
                    {"model": "M1", "price_per_1m_tokens": 0.1},
                    {"model": "M2", "price_per_1m_tokens": 0.2},
                    {"model": "M3", "price_per_1m_tokens": 0.3},
                    {"model": "M4", "price_per_1m_tokens": 0.4},
                ],
            },
            "intelligence_rankings": [{"model": "I", "score": 9}],
            "speed_rankings": [{"model": "S", "tokens_per_sec": 10}],
            "cross_validation": {
                "confirmed": [{"model": "M", "sources": ["news", "api"]}],
                "unconfirmed": [{"model": "U"}],
            },
        })
        self.assertEqual(len(cards), 4)
        self.assertIn("A ARR 10", cards[0]["content"])
        self.assertIn("热门模型 Top 3", cards[1]["content"])
        self.assertIn("智能排名 Top 5", cards[2]["content"])
        self.assertIn("已确认：1 项", cards[3]["content"])
        self.assertEqual(formatter._format_for_html("a\nb"), "a\nb")

    def test_news_metrics_extractor_empty_and_llm_paths(self):
        from analyzers.news_metrics_extractor import NewsMetricsExtractor
        with patch("analyzers.news_metrics_extractor.OpenAIClient", side_effect=RuntimeError("offline")):
            extractor = NewsMetricsExtractor()
        self.assertEqual(extractor.extract_metrics([{"title": "x"}])["revenue"], [])

        extractor = NewsMetricsExtractor.__new__(NewsMetricsExtractor)
        extractor.llm = MagicMock()
        extractor.llm.extract_structured_data.return_value = {
            "revenue": [{"company": "A"}], "funding": [], "users": [],
            "token_usage": [], "price_changes": [], "ignored": [1],
        }
        result = extractor.extract_metrics([{"title": "t", "summary": "s"}])
        self.assertEqual(result["revenue"], [{"company": "A"}])
        self.assertNotIn("ignored", result)
        self.assertEqual(extractor._format_news_for_llm([{"title": "t", "summary": "s"}] * 25).count(". t"), 20)
        self.assertEqual(extractor.extract_metrics([]), extractor._empty_metrics())

    def test_market_aggregator_merge_helpers_and_failures(self):
        from analyzers.market_data_aggregator import MarketDataAggregator
        with patch("analyzers.market_data_aggregator.NewsMetricsExtractor") as extractor_cls:
            extractor_cls.return_value._empty_metrics.return_value = {
                "revenue": [], "funding": [], "users": [], "token_usage": [], "price_changes": []
            }
            aggregator = MarketDataAggregator()
            aggregator.metrics_extractor.extract_metrics.side_effect = RuntimeError("bad metrics")
            with patch("analyzers.market_data_aggregator.fetch_openrouter_data", side_effect=RuntimeError("or")), \
                 patch("analyzers.market_data_aggregator.fetch_aa_data", return_value={"date": "d", "intelligence": [], "speed": [], "cost": []}):
                result = aggregator.aggregate([{"title": "t"}])
            self.assertEqual(result["market_trends"]["total_models"], 0)
            self.assertEqual(result["news_metrics"]["revenue"], [])

        aggregator = MarketDataAggregator.__new__(MarketDataAggregator)
        self.assertEqual(aggregator._deduplicate_rankings([]), [])
        rankings = [{"model": "OpenAI: GPT-4", "score": 1}, {"model": "gpt 4", "score": 1}, {"model": "", "score": 2}]
        self.assertEqual(len(aggregator._deduplicate_rankings(rankings)), 1)
        self.assertEqual(aggregator._summarize_pricing({"pricing": []}), {})
        self.assertEqual(aggregator._summarize_pricing({"pricing": [{"price_per_1m_tokens": 0}]}), {})
        self.assertTrue(aggregator._fuzzy_match_model("GPT-4", "OpenAI: gpt 4"))
        self.assertFalse(aggregator._fuzzy_match_model("", "x"))
        validation = aggregator._cross_validate(
            {"rankings": [{"model": "GPT-4", "price_per_1m_tokens": 1}]},
            {"price_changes": [{"model": "GPT-4"}, {"model": "Unknown"}]},
        )
        self.assertEqual(len(validation["confirmed"]), 1)
        self.assertEqual(len(validation["unconfirmed"]), 1)

    def test_trend_analyzer_historical_and_no_data_paths(self):
        from analyzers.trend_analyzer import TrendAnalyzer
        analyzer = TrendAnalyzer()
        with patch.object(analyzer, "_load_historical_data", return_value=[]):
            self.assertEqual(analyzer.analyze_trends({}), {
                "trends": [], "history_status": "missing", "history_count": 0,
                "note": "无足够历史数据"
            })
        historical = [{"date": "2026-09-01", "data": {"rankings": [
            {"model": "A", "price_per_1m_tokens": 1}, {"model": "B", "price_per_1m_tokens": 2},
        ]}}]
        current = {"market_trends": {"top_models_by_price": [
            {"model": "B", "price_per_1m_tokens": 3}, {"model": "C", "price_per_1m_tokens": 4}
        ]}}
        with patch.object(analyzer, "_load_historical_data", return_value=historical):
            result = analyzer.analyze_trends(current, days_back=1)
        self.assertEqual(result["price_trends"][0]["model"], "B")
        self.assertEqual(result["history_status"], "restored")
        self.assertEqual(result["history_count"], 1)
        self.assertEqual(result["compared_with"], "2026-09-01")
        self.assertEqual(result["ranking_trends"]["entered"], ["C"])
        self.assertEqual(result["ranking_trends"]["exited"], ["A"])
        self.assertEqual(result["ranking_trends"]["moved"][0]["model"], "B")
        self.assertEqual(analyzer._analyze_ranking_trends(current, [{"date": "d", "data": {"rankings": []}}])["compared_with"], "d")
        self.assertIn("note", analyzer._analyze_ranking_trends(current, [{"date": "d", "data": {"rankings": [{"model": "X"}]}}]))


class TestScrapers(unittest.TestCase):
    def test_base_scraper_cache_cleanup_and_retry(self):
        from scrapers.base_scraper import BaseScraper
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as directory:
            scraper = BaseScraper(directory)
            scraper.save_cache("fixture", {"ok": True})
            self.assertEqual(scraper.load_cache("fixture")["ok"], True)
            path = scraper.get_cache_path("old_2020-01-01")
            path.write_text("{}", encoding="utf-8")
            scraper.cleanup_old_cache(days=1)
            self.assertFalse(path.exists())
            bad = scraper.get_cache_path("bad_2020-01-01")
            bad.write_text("{", encoding="utf-8")
            self.assertIsNone(scraper.load_cache("bad_2020-01-01"))
            attempts = iter(["first", "ok"])
            def flaky():
                value = next(attempts)
                if value == "first":
                    raise RuntimeError(value)
                return value
            with patch("scrapers.base_scraper.time.sleep"):
                self.assertEqual(scraper.fetch_with_retry(flaky, retries=2), "ok")
            with self.assertRaises(RuntimeError):
                scraper.fetch_with_retry(lambda: (_ for _ in ()).throw(RuntimeError("fail")), retries=1)

    def test_money_flow_legacy_scraper_and_formatter(self):
        from money_flow_scraper import MoneyFlowScraper, format_money_flow_for_html
        scraper = MoneyFlowScraper()
        north_payload = json.dumps({"data": {"hgt": {"f52": 10000}, "sgt": {"f52": -5000}}})
        industry_payload = json.dumps({"data": {"diff": [
            {"f14": "Tech", "f62": 20000, "f3": 350, "f184": 10000}
        ]}})
        stock_payload = json.dumps({"data": {"diff": [
            {"f12": "000001", "f14": "A", "f62": -10000, "f3": 120,
             "f184": -5000, "f2": 1234}
        ]}})
        with patch("money_flow_scraper.urllib.request.urlopen", side_effect=[
            FakeResponse(north_payload), FakeResponse(industry_payload),
            FakeResponse(stock_payload)
        ]):
            north = scraper.get_north_capital_flow()
            industries = scraper.get_industry_money_flow()
            stocks = scraper.get_stock_money_flow()
        self.assertEqual(north["total"]["net_inflow"], 0.5)
        self.assertEqual(industries[0]["name"], "Tech")
        self.assertEqual(industries[0]["net_inflow"], 2)
        self.assertEqual(stocks[0]["code"], "000001")
        with patch("money_flow_scraper.urllib.request.urlopen", side_effect=RuntimeError("offline")):
            self.assertIsNone(scraper.get_north_capital_flow())
            self.assertEqual(scraper.get_stock_money_flow(), [])
        html = format_money_flow_for_html({"north_capital": north,
            "industries": [{"name": "Tech", "net_inflow": 1, "change_pct": -1}],
            "stocks": [{"code": "1", "name": "A", "net_inflow": -1, "change_pct": 1}]})
        self.assertIn("Tech", html)
        self.assertIn("A", html)
        self.assertEqual(format_money_flow_for_html({}), "")

    def test_money_flow_legacy_empty_errors_aggregate_and_color_paths(self):
        from money_flow_scraper import MoneyFlowScraper, format_money_flow_for_html

        scraper = MoneyFlowScraper()
        empty_payload = json.dumps({"data": {}})
        missing_data_payload = json.dumps({"meta": "fixture"})
        plain_north = json.dumps({"data": {"hgt": {"f52": 20000}}})
        callback_north = "callback(" + json.dumps({
            "data": {"sgt": {"f52": -10000}}
        }) + ");"
        with patch("money_flow_scraper.urllib.request.urlopen", side_effect=[
            FakeResponse(plain_north), FakeResponse(callback_north),
            FakeResponse(missing_data_payload), FakeResponse(empty_payload),
            FakeResponse(empty_payload),
        ]):
            north = scraper.get_north_capital_flow()
            self.assertEqual(north["total"]["net_inflow"], 2)
            callback_result = scraper.get_north_capital_flow()
            self.assertEqual(callback_result["shenzhen"]["net_inflow"], -1)
            missing_result = scraper.get_north_capital_flow()
            self.assertEqual(missing_result["total"]["net_inflow"], 0)
            self.assertEqual(scraper.get_industry_money_flow(), [])
            self.assertEqual(scraper.get_stock_money_flow(), [])

        with patch("money_flow_scraper.urllib.request.urlopen",
                   side_effect=RuntimeError("offline")):
            self.assertEqual(scraper.get_industry_money_flow(), [])

        complete = {
            "north_capital": {
                "total": {"net_inflow": -2},
                "shanghai": {"net_inflow": 0},
                "shenzhen": {"net_inflow": -2},
                "update_time": "fixture",
            },
            "industries": [
                {"name": "Down", "net_inflow": -1, "change_pct": 1},
                {"name": "Flat", "net_inflow": 0, "change_pct": 0},
            ],
            "stocks": [
                {"code": "1", "name": "Up", "net_inflow": 1,
                 "change_pct": -1},
                {"code": "2", "name": "Flat", "net_inflow": 0,
                 "change_pct": 0},
            ],
        }
        html = format_money_flow_for_html(complete)
        self.assertIn("2.00亿", html)
        self.assertIn("↘", html)
        self.assertIn("#9aa4b2", format_money_flow_for_html({
            "north_capital": {
                "total": {"net_inflow": 0},
                "shanghai": {"net_inflow": 0},
                "shenzhen": {"net_inflow": 0},
                "update_time": "fixture",
            }
        }))

        with patch.object(scraper, "get_north_capital_flow",
                          return_value={"total": {"net_inflow": 3}}), \
             patch.object(scraper, "get_industry_money_flow",
                          return_value=[{"name": "Tech"}]), \
             patch.object(scraper, "get_stock_money_flow",
                          return_value=[{"name": "Stock"}]):
            result = scraper.get_all_money_flow_data()
        self.assertEqual(result["north_capital"]["total"]["net_inflow"], 3)
        self.assertEqual(len(result["industries"]), 1)
        self.assertEqual(len(result["stocks"]), 1)

        with patch.object(scraper, "get_north_capital_flow", return_value=None), \
             patch.object(scraper, "get_industry_money_flow", return_value=[]), \
             patch.object(scraper, "get_stock_money_flow", return_value=[]):
            self.assertEqual(scraper.get_all_money_flow_data(), {
                "north_capital": None, "industries": [], "stocks": []
            })

    def test_openrouter_scraper_parses_and_falls_back(self):
        from scrapers.openrouter_scraper import OpenRouterScraper
        scraper = OpenRouterScraper()
        models = {"data": [{"name": "GPT-4", "id": "gpt", "pricing": {"prompt": "0.001", "completion": "0.003"}, "context_length": 100}]}
        with patch("scrapers.openrouter_scraper.urllib.request.urlopen", return_value=FakeResponse(json.dumps(models))):
            parsed = scraper._fetch_models_api()
        self.assertEqual(parsed["total_models"], 1)
        self.assertEqual(parsed["pricing"][0]["price_per_1m_tokens"], 2000.0)
        html = "<html><head><meta name='description' content='desc'></head><body>GPT-4 Claude</body></html>"
        with patch("scrapers.openrouter_scraper.urllib.request.urlopen", return_value=FakeResponse(html)):
            page = scraper._fetch_rankings_page()
        self.assertEqual(page["description"], "desc")
        self.assertIn("GPT-4", page["detected_models"])
        merged = scraper._merge_data(parsed, page)
        self.assertEqual(merged["rankings"][0]["id"], "gpt")
        next_data = {"props": {"pageProps": {"date": "d", "rankings": [{"name": "M", "rank": 1, "tokens": 2, "marketShare": 3}]}}}
        self.assertEqual(scraper._parse_next_data(next_data)["top_models"][0]["name"], "M")
        fallback = scraper._parse_html_fallback(__import__("bs4").BeautifulSoup("Live LLM rankings Usage data through Jan 1, 2026 Claude", "html.parser"))
        self.assertIn("Claude", fallback["detected_models"])
        with patch.object(scraper, "_fetch_models_api", side_effect=RuntimeError("offline")), \
             patch.object(scraper, "load_cache", return_value=None), \
             patch.object(scraper, "_load_fallback_cache", return_value={"is_fallback": True}):
            self.assertTrue(scraper.fetch_rankings()["is_fallback"])

        with tempfile.TemporaryDirectory() as cache_dir:
            fallback_scraper = OpenRouterScraper()
            fallback_scraper.cache_dir = __import__("pathlib").Path(cache_dir)
            with open(fallback_scraper.cache_dir / "openrouter_2026-01-01.json", "w", encoding="utf-8") as handle:
                json.dump({"source": "openrouter", "top_models": [{"name": "cached"}]}, handle)
            cached = fallback_scraper._load_fallback_cache()
            self.assertTrue(cached["is_fallback"])
            self.assertEqual(cached["top_models"][0]["name"], "cached")

        # Exercise cache hit, API/page degradation, malformed model pricing,
        # and the public wrapper without making network requests.
        cached_result = {"source": "openrouter", "top_models": [{"name": "cached"}]}
        with patch.object(scraper, "load_cache", return_value=cached_result):
            self.assertIs(scraper.fetch_rankings(), cached_result)

        with patch("scrapers.openrouter_scraper.urllib.request.urlopen", side_effect=ValueError("bad response")):
            self.assertEqual(scraper._fetch_models_api(), {"total_models": 0, "pricing": []})
            page = scraper._fetch_rankings_page()
            self.assertEqual(page["detected_models"], [])
            self.assertEqual(page["description"], "Live LLM rankings by real-world usage")

        bad_models = {"data": [{"pricing": {"prompt": "invalid", "completion": "0"}}]}
        with patch("scrapers.openrouter_scraper.urllib.request.urlopen", return_value=FakeResponse(json.dumps(bad_models))):
            degraded = scraper._fetch_models_api()
        self.assertEqual(degraded["total_models"], 0)
        self.assertEqual(degraded["pricing"], [])

        empty_next = scraper._parse_next_data({"props": {"pageProps": {"rankings": None}}})
        self.assertEqual(empty_next["top_models"], [])
        malformed_next = scraper._parse_next_data({"props": {"pageProps": {"rankings": [None]}}})
        self.assertEqual(malformed_next["top_models"], [])

        fallback_html = __import__("bs4").BeautifulSoup(
            "Live LLM rankings Usage data through January 1, 2026 GPT-4 Gemini",
            "html.parser",
        )
        fallback = scraper._parse_html_fallback(fallback_html)
        self.assertEqual(fallback["usage_data_through"], "January 1, 2026")
        self.assertIn("GPT-4", fallback["detected_models"])

        with patch("glob.glob", return_value=[]):
            self.assertEqual(scraper._load_fallback_cache()["top_models"], [])

        with tempfile.TemporaryDirectory() as cache_dir:
            cache_scraper = OpenRouterScraper()
            cache_scraper.cache_dir = __import__("pathlib").Path(cache_dir)
            result = {"total_models": 1, "pricing": []}
            with patch.object(cache_scraper, "load_cache", return_value=None), \
                 patch.object(cache_scraper, "_fetch_models_api", return_value=result), \
                 patch.object(cache_scraper, "_fetch_rankings_page", return_value={"description": "d", "detected_models": []}):
                fetched = cache_scraper.fetch_rankings()
            self.assertEqual(fetched["description"], "d")
            self.assertTrue((cache_scraper.cache_dir / f"openrouter_{datetime.now().strftime('%Y-%m-%d')}.json").exists())

        no_meta = __import__("bs4").BeautifulSoup("<html><body>plain</body></html>", "html.parser")
        with patch("scrapers.openrouter_scraper.urllib.request.urlopen", return_value=FakeResponse(str(no_meta))):
            self.assertEqual(scraper._fetch_rankings_page()["description"], "Live LLM rankings by real-world usage")

        self.assertEqual(scraper._parse_next_data({"props": {"pageProps": {"rankings": []}}})["top_models"], [])
        self.assertEqual(scraper._parse_next_data({"props": {"pageProps": {}}})["top_models"], [])
        self.assertEqual(
            scraper._parse_html_fallback(__import__("bs4").BeautifulSoup("Usage data through unknown", "html.parser"))["description"],
            "",
        )
        broken_soup = MagicMock()
        broken_soup.find.side_effect = RuntimeError("broken soup")
        self.assertEqual(scraper._parse_html_fallback(broken_soup)["top_models"], [])

        with tempfile.TemporaryDirectory() as cache_dir:
            bad_cache_scraper = OpenRouterScraper()
            bad_cache_scraper.cache_dir = __import__("pathlib").Path(cache_dir)
            (bad_cache_scraper.cache_dir / "openrouter_2026-01-02.json").write_text("{", encoding="utf-8")
            self.assertEqual(bad_cache_scraper._load_fallback_cache()["top_models"], [])

        with patch("scrapers.openrouter_scraper.OpenRouterScraper") as scraper_type:
            scraper_type.return_value.fetch_rankings.return_value = {"ok": True}
            from scrapers.openrouter_scraper import fetch_openrouter_data
            self.assertEqual(fetch_openrouter_data(), {"ok": True})

    def test_artificial_analysis_parser_paths(self):
        from scrapers.artificial_analysis_scraper import ArtificialAnalysisScraper
        scraper = ArtificialAnalysisScraper()
        html = ("<html><body>Highlights Claude 80 GPT 90"
                '<script type="application/ld+json">{"@type": "Dataset", "name": "Intelligence", "data": ['
                '{"label": "Claude Fable 5.1 (max)", "artificialAnalysisIntelligenceIndex": 53.4},'
                '{"label": "GPT-6 Astra (max)", "artificialAnalysisIntelligenceIndex": 52.8}]}</script>'
                '<script type="application/ld+json">{"@type": "Dataset", "name": "Speed", "data": ['
                '{"label": "Gemini 3.8 Flash (high)", "medianOutputSpeed": 335.5}]}</script>'
                '<script type="application/ld+json">{"@type": "Dataset", "name": "Cost per Task", "data": ['
                '{"label": "GPT-5.6 Luna (max)", "costPerIntelligenceIndexTask": 0.1783}]}</script>'
                "</body></html>")
        with (
            patch("scrapers.artificial_analysis_scraper.urllib.request.urlopen", return_value=FakeResponse(html)),
            patch.object(scraper, "load_cache", return_value=None),
            patch.object(scraper, "save_cache"),
        ):
            result = scraper.fetch_benchmarks()
        self.assertTrue(result["parsed"])
        self.assertEqual(result["datasets_found"], ["Intelligence", "Speed", "Cost per Task"])
        self.assertEqual(result["intelligence"][0]["score"], 53.4)
        self.assertEqual(result["speed"][0]["tokens_per_sec"], 335.5)
        self.assertEqual(result["cost"][0]["cost_per_task"], 0.1783)
        models = " ".join(r["model"] for r in result["intelligence"])
        self.assertNotIn("80", models)
        with (
            patch.object(scraper, "load_cache", return_value=None),
            patch("scrapers.artificial_analysis_scraper.urllib.request.urlopen",
                  return_value=FakeResponse("<html><body>全新改版</body></html>")),
            patch.object(scraper, "_load_fallback_cache", return_value={"is_fallback": True}),
        ):
            self.assertTrue(scraper.fetch_benchmarks()["is_fallback"])
        with (
            patch.object(scraper, "load_cache", return_value=None),
            patch("scrapers.artificial_analysis_scraper.urllib.request.urlopen", side_effect=RuntimeError("offline")),
            patch.object(scraper, "_load_fallback_cache", return_value={"is_fallback": True}),
        ):
            self.assertTrue(scraper.fetch_benchmarks()["is_fallback"])
    def test_artificial_analysis_cache_and_parser_exception_paths(self):
        from scrapers.artificial_analysis_scraper import ArtificialAnalysisScraper
        scraper = ArtificialAnalysisScraper()
        good = {"source": "cache", "parsed": True, "intelligence": [],
                "speed": [], "cost": [{"model": "M", "cost_per_task": 0.5}]}
        with patch.object(scraper, "load_cache", return_value=good):
            self.assertIs(scraper.fetch_benchmarks(), good)
        junk = {"source": "cache",
                "intelligence": [{"model": "Qwen", "score": 3}],
                "speed": [], "cost": []}
        with (
            patch.object(scraper, "load_cache", return_value=junk),
            patch("scrapers.artificial_analysis_scraper.urllib.request.urlopen", side_effect=RuntimeError("offline")),
            patch.object(scraper, "_load_fallback_cache", return_value={"is_fallback": True}),
        ):
            self.assertTrue(scraper.fetch_benchmarks()["is_fallback"])
        self.assertEqual(scraper._extract_datasets("<html>no scripts</html>"), {})
        self.assertEqual(scraper._clean_rows(
            [None, {"label": "", "x": 1}], ("artificialAnalysisIntelligenceIndex",), "intelligence"), [])
        fallback = scraper._load_fallback_cache()
        self.assertEqual(fallback["source"], "artificial_analysis")
    def test_artificial_analysis_scripts_tables_and_fallback_edges(self):
        from scrapers.artificial_analysis_scraper import ArtificialAnalysisScraper
        scraper = ArtificialAnalysisScraper()
        html = ("<html><head>"
                '<script type="application/ld+json">not json</script>'
                '<script type="application/ld+json">{"@type": "Other", "name": "X"}</script>'
                '<script type="application/ld+json">{"@type": "Dataset", "name": "Speed", "data": ['
                '{"label": "Gemini 3.8 Flash (high)", "medianOutputSpeed": 335.5},'
                '{"label": "Gemini 3.8 Flash (high)", "medianOutputSpeed": 335.5},'
                '{"label": "Stalled", "medianOutputSpeed": 0},'
                '{"label": "", "medianOutputSpeed": 400}]}</script>'
                "</head></html>")
        datasets = scraper._extract_datasets(html)
        self.assertEqual(list(datasets), ["Speed"])
        rows = scraper._clean_rows(datasets["Speed"], ("medianOutputSpeed",), "speed")
        self.assertEqual([r["model"] for r in rows], ["Gemini 3.8 Flash (high)"])
        with tempfile.TemporaryDirectory() as directory:
            scraper.cache_dir = __import__("pathlib").Path(directory)
            (scraper.cache_dir / "artificial_analysis_3.json").write_text("{", encoding="utf-8")
            (scraper.cache_dir / "artificial_analysis_2.json").write_text("[]", encoding="utf-8")
            empty = scraper._load_fallback_cache()
            self.assertEqual(empty["intelligence"], [])
            self.assertFalse(empty.get("parsed", False))
    def test_trend_analyzer_cache_loading_and_price_edges(self):
        from analyzers.trend_analyzer import TrendAnalyzer
        with tempfile.TemporaryDirectory() as directory:
            analyzer = TrendAnalyzer(directory)
            yesterday = (datetime.now() - __import__("datetime").timedelta(days=1)).strftime("%Y-%m-%d")
            (analyzer.data_dir / f"openrouter_{yesterday}.json").parent.mkdir(parents=True, exist_ok=True)
            (analyzer.data_dir / f"openrouter_{yesterday}.json").write_text(
                json.dumps({"rankings": [{"model": "A", "price_per_1m_tokens": 2}]}),
                encoding="utf-8"
            )
            (analyzer.data_dir / f"openrouter_{(datetime.now() - __import__('datetime').timedelta(days=2)).strftime('%Y-%m-%d')}.json").write_text("{", encoding="utf-8")
            historical = analyzer._load_historical_data(2)
            self.assertEqual(len(historical), 1)
            trends = analyzer._analyze_price_trends(
                {"market_trends": {"top_models_by_price": [
                    {"model": "A", "price_per_1m_tokens": 3},
                    {"model": "B", "price_per_1m_tokens": 1},
                ]}}, historical)
            self.assertEqual(trends[0]["change_percent"], 50.0)
            self.assertEqual(analyzer._analyze_price_trends({}, []), [])

        from scrapers.artificial_analysis_scraper import ArtificialAnalysisScraper
        from bs4 import BeautifulSoup
        scraper = ArtificialAnalysisScraper()
        parsed_empty = scraper.parse_homepage("<html><body>Claude 0 GPT 100 Qwen 99</body></html>")
        self.assertFalse(parsed_empty["parsed"])
        with tempfile.TemporaryDirectory() as directory:
            scraper.cache_dir = __import__("pathlib").Path(directory)
            (scraper.cache_dir / "artificial_analysis_bad.json").write_text("{", encoding="utf-8")
            good = scraper.cache_dir / "artificial_analysis_good.json"
            good.write_text('{"source": "artificial_analysis", "intelligence": [{"model": "Claude Fable 5.1 (max)", "score": 53.4}], "speed": [], "cost": []}', encoding="utf-8")
            cached = scraper._load_fallback_cache()
            self.assertTrue(cached["is_fallback"])
            self.assertEqual(cached["intelligence"][0]["score"], 53.4)
    def test_money_flow_post_close_and_fallback_shapes(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        target = "2026-09-07"
        parsed = scraper._parse_post_close_kline({"data": {
            "hk2sh": {"dayNetAmtIn": 100000000},
            "hk2sz": {"dayNetAmtIn": -50000000},
        }}, target, "fixture")
        self.assertEqual(parsed["total_flow"], 0.5)
        with self.assertRaises(ValueError):
            scraper._parse_post_close_kline({"data": {"hk2sh": [], "hk2sz": []}}, target, "fixture")
        with self.assertRaises(ValueError):
            scraper._parse_post_close_kline({"data": {
                "hk2sh": {"dayNetAmtIn": 0}, "hk2sz": {"dayNetAmtIn": 0}
            }}, target, "fixture")
        self.assertEqual(scraper._num("-"), 0.0)
        self.assertEqual(scraper._empty_sector_flow()["top_inflow"], [])
        with patch.object(scraper, "_clist", side_effect=RuntimeError("offline")):
            sector = scraper.fetch_sector_flow(2)
            self.assertFalse(sector["available"])
        with patch.object(scraper, "_clist", side_effect=RuntimeError("offline")):
            self.assertEqual(scraper.fetch_stock_flow(2)["top_outflow"], [])
        with patch.object(scraper, "_fetch_eastmoney_post_close", return_value=None), \
             patch.object(scraper, "_fetch_10jqka_post_close", side_effect=RuntimeError("offline")), \
             patch.object(scraper, "_load_cached_north", return_value=None):
            result = scraper.fetch_north_flow(target)
        self.assertFalse(result["available"])

    def test_money_flow_transport_helpers_and_result_shapes(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        calls = []

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": {"diff": [{"f14": "Tech", "f62": 100000000,
                                                  "f3": 4.4, "f184": 2.2, "f12": "1"}]}}

        def fail_then_pass(url, **kwargs):
            calls.append(url)
            if len(calls) == 1:
                raise RuntimeError("first host unavailable")
            return Response()

        with patch("scrapers.money_flow_scraper.requests.get", side_effect=fail_then_pass):
            self.assertEqual(scraper._clist("fixture", 1)[0]["f14"], "Tech")
        self.assertEqual(len(calls), 2)
        with patch.object(scraper, "_get_json", return_value={"data": {}}):
            self.assertEqual(scraper._clist("fixture", 1), [])
        self.assertEqual(scraper._shape_flow({"f14": "Tech", "f62": 100000000,
                                               "f3": 4.4, "f184": 2.2, "f12": "1"}, True),
                         {"name": "Tech", "net_inflow": 1.0, "change_pct": 4.4,
                          "net_ratio": 2.2, "code": "1"})
        self.assertEqual(scraper._optional_num(0), 0.0)
        self.assertIsNone(scraper._optional_num("-"))
        self.assertIsNone(scraper._optional_num(float("nan")))
        valid_zero = {"f14": "Flat", "f62": 0, "f3": 0, "f184": 0}
        valid_nonzero = {"f14": "Tech", "f62": 100, "f3": 0, "f184": 0}
        self.assertEqual(scraper._valid_rank_rows([valid_zero, valid_nonzero]),
                         [valid_zero, valid_nonzero])
        self.assertEqual(scraper._valid_rank_rows([valid_zero]), [])
        self.assertEqual(scraper._valid_rank_rows([
            {"f14": "", "f62": 1, "f3": 1, "f184": 1},
            {"f14": "Bad", "f62": "-", "f3": 1, "f184": 1},
            None,
        ]), [])
        with patch.object(scraper, "_clist", side_effect=[[valid_zero], [valid_zero]]):
            sector = scraper.fetch_sector_flow(1)
        self.assertFalse(sector["available"])
        self.assertIn("占位", sector["reason"])
        with patch.object(scraper, "_clist", side_effect=[[valid_zero], [valid_zero]]):
            stock = scraper.fetch_stock_flow(1)
        self.assertFalse(stock["available"])
        self.assertIn("占位", stock["reason"])
        self.assertFalse(scraper._parse_north_flow({"data": {}})["available"])
        with patch("scrapers.money_flow_scraper.requests.get", return_value=Response()):
            with self.assertRaises(ValueError):
                scraper._fetch_10jqka_post_close("2026-09-07")

    def test_blogger_and_weibo_scraper_contracts(self):
        from scrapers.blogger_scraper import BloggerScraper
        from scrapers.weibo_scraper import WeiboScraper
        from datetime import datetime, timedelta, timezone
        blogger = BloggerScraper(timeout=1, min_interval=0)
        listing = """<div class='articleCell'><span class='atc_title'><a href='//blog.sina.com.cn/a'>直播</a></span><span class='atc_tm'>2026-09-07 08:00</span></div>
        <div class='articleCell'><span class='atc_title'><a href='/b'>普通</a></span><span class='atc_tm'>bad</span></div>"""
        body = "<div id='sina_keyword_ad_area2'>正文\n点击进入\n风险提示：\n有效内容</div>"
        class Resp:
            status_code = 200
            apparent_encoding = "utf-8"
            encoding = "utf-8"
            text = listing
            def raise_for_status(self): pass
        with patch("scrapers.blogger_scraper.requests.get", return_value=Resp()):
            articles = blogger.fetch_article_list("1")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["url"], "https://blog.sina.com.cn/a")
        with patch("scrapers.blogger_scraper.requests.get", return_value=type("R", (), {"status_code": 200, "apparent_encoding": "utf-8", "encoding": "utf-8", "text": body, "raise_for_status": lambda self: None})()):
            self.assertEqual(blogger.fetch_article_body("https://x") , "正文\n有效内容")
        with patch.object(blogger, "fetch_article_list", return_value=[]):
            self.assertFalse(blogger.fetch_recent("1")["available"])
        with patch.object(blogger, "fetch_article_list", side_effect=RuntimeError("offline")):
            self.assertFalse(blogger.fetch_recent("1")["available"])
        with patch.object(blogger, "fetch_recent", return_value={"articles": [1], "available": True}) as recent:
            self.assertEqual(len(blogger.fetch_all([{"uid": "1"}, {"uid": ""} ])), 1)
            recent.assert_called_once()
        xml = "<rss><channel><item><title>T</title><link>u</link><pubDate>2026-09-07T07:00:00+00:00</pubDate><description>&lt;b&gt;C&lt;/b&gt;</description></item></channel></rss>"
        wb = WeiboScraper(rsshub_base="https://fixture", timeout=1)
        response = MagicMock(content=xml.encode())
        response.raise_for_status.return_value = None
        with patch("scrapers.weibo_scraper.requests.get", return_value=response):
            fetched = wb.fetch_weibo_user("42", limit=1)
        self.assertTrue(fetched["available"])
        self.assertEqual(fetched["weibos"][0]["content"], "C")
        with patch("scrapers.weibo_scraper.requests.get", side_effect=RuntimeError("offline")):
            self.assertFalse(wb.fetch_weibo_user("42")["available"])
        with patch.object(wb, "fetch_weibo_user", return_value={"available": True, "weibos": []}):
            self.assertFalse(wb.fetch_recent("42")["available"])

    def test_blogger_24h_window_live_posts_and_retry_paths(self):
        import scrapers.blogger_scraper as blogger_module
        from scrapers.blogger_scraper import BloggerScraper
        now = blogger_module.datetime.now()
        scraper = BloggerScraper(timeout=1, min_interval=0)

        # The default 24-hour window keeps both ordinary posts and a live post
        # whose effective content date is today, while excluding an old post.
        articles = [
            {"title": "策略", "url": "https://example.invalid/strategy",
             "published": now - blogger_module.timedelta(hours=2),
             "effective": now - blogger_module.timedelta(hours=2), "is_live": False},
            {"title": "9月7日盘中即时直播", "url": "https://example.invalid/live",
             "published": now - blogger_module.timedelta(hours=20),
             "effective": now - blogger_module.timedelta(hours=1), "is_live": True},
            {"title": "旧文章", "url": "https://example.invalid/old",
             "published": now - blogger_module.timedelta(hours=30),
             "effective": now - blogger_module.timedelta(hours=30), "is_live": False},
        ]
        with patch.object(scraper, "fetch_article_list", return_value=articles), \
             patch.object(scraper, "fetch_article_body", side_effect=["正文内容", "短"]):
            result = scraper.fetch_recent("1", name="fixture", hours=24)
        self.assertTrue(result["available"])
        self.assertEqual([a["title"] for a in result["articles"]], ["策略"])

        with patch.object(scraper, "fetch_article_list", return_value=articles), \
             patch.object(scraper, "fetch_article_body", return_value="直播正文足够长" * 20):
            result = scraper.fetch_recent("1", name="fixture", hours=24)
        self.assertEqual(len(result["articles"]), 2)
        self.assertTrue(result["articles"][1]["isLive"])
        self.assertEqual(result["articles"][1]["published"],
                         articles[1]["effective"].strftime("%Y-%m-%d %H:%M"))
        self.assertEqual(result["articles"][1]["contentTime"],
                         articles[1]["effective"].strftime("%Y-%m-%d %H:%M"))
        self.assertEqual(result["articles"][1]["shellPublished"],
                         articles[1]["published"].strftime("%Y-%m-%d %H:%M"))

        future_live = [{
            "title": "future live", "url": "u", "published": now,
            "effective": now + blogger_module.timedelta(hours=1), "is_live": True,
        }]
        with patch.object(scraper, "fetch_article_list", return_value=future_live), \
             patch.object(scraper, "fetch_article_body") as body:
            result = scraper.fetch_recent("1", name="future", hours=24)
        self.assertTrue(result["available"])
        self.assertEqual(result["articles"], [])
        body.assert_not_called()
        with patch.object(scraper, "fetch_article_list", return_value=articles), \
             patch.object(scraper, "fetch_article_body") as body:
            result = scraper.fetch_recent("1", name="fixture", hours=24, with_body=False)
        self.assertEqual(len(result["articles"]), 1)
        self.assertEqual(result["articles"][0]["content"], "")
        body.assert_not_called()

        self.assertEqual(scraper._effective_time("普通标题", now), (now, False))
        self.assertEqual(scraper._effective_time("2月30日盘中直播", now), (now, False))
        self.assertEqual(scraper._abs_url("https://example.invalid/a"), "https://example.invalid/a")

        class LimitedResponse:
            status_code = 418
            apparent_encoding = "utf-8"
            encoding = "utf-8"
            text = ""
            def raise_for_status(self):
                raise blogger_module.requests.HTTPError("limited", response=self)

        with patch.object(scraper, "_throttle"), \
             patch.object(blogger_module.time, "sleep"), \
             patch.object(blogger_module.requests, "get", return_value=LimitedResponse()):
            with self.assertRaises(blogger_module.requests.HTTPError):
                scraper._get_soup("https://example.invalid", retries=1)

        with patch.object(scraper, "fetch_article_list", return_value=articles), \
             patch.object(scraper, "fetch_article_body", side_effect=RuntimeError("body offline")):
            result = scraper.fetch_recent("1", hours=24)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["articles"]), 1)

        scraper.min_interval = 1
        scraper._last_request = blogger_module.time.monotonic()
        with patch.object(blogger_module.time, "sleep") as sleep:
            scraper._throttle()
            sleep.assert_called_once()

        malformed_listing = """
        <div class='articleCell'><span class='atc_title'>missing link</span><span class='atc_tm'>2026-09-08 08:00</span></div>
        <div class='articleCell'><span class='atc_title'><a href='/ok'> </a></span><span class='atc_tm'>2026-09-08 08:00</span></div>
        <div class='articleCell'><span class='atc_title'><a href='/ok'>ok</a></span><span class='atc_tm'>2026-09-08 08:00</span></div>
        """
        class ListingResponse:
            status_code = 200
            apparent_encoding = "utf-8"
            encoding = "utf-8"
            text = malformed_listing
            def raise_for_status(self):
                return None
        with patch.object(blogger_module.requests, "get", return_value=ListingResponse()):
            self.assertEqual(len(scraper.fetch_article_list("1")), 1)

        with patch.object(scraper, "_get_soup", return_value=MagicMock(select_one=lambda _: None)):
            self.assertEqual(scraper.fetch_article_body("https://example.invalid/no-body"), "")
        with patch.object(scraper, "_get_soup", side_effect=RuntimeError("body offline")):
            self.assertEqual(scraper.fetch_article_body("https://example.invalid/fail"), "")

        stale = [{"title": "old", "url": "u", "published": now - blogger_module.timedelta(days=31),
                  "effective": now - blogger_module.timedelta(days=31), "is_live": False}]
        with patch.object(scraper, "fetch_article_list", return_value=stale):
            self.assertFalse(scraper.fetch_recent("1", name="stale", hours=24)["available"])
        with patch.object(scraper, "fetch_article_list", return_value=[{
            "title": "today", "url": "u", "published": now,
            "effective": now, "is_live": False}]), \
             patch.object(scraper, "fetch_article_body", side_effect=RuntimeError("body")):
            result = scraper.fetch_recent("1", name="body-fail", hours=24)
            self.assertTrue(result["available"])
            self.assertEqual(result["articles"][0]["content"], "")

        with patch("scrapers.weibo_scraper.fetch_weibo_blogger", return_value={"articles": [1]}):
            collected = scraper.fetch_all([{"uid": "2", "type": "weibo", "name": "微博"}])
            self.assertEqual(len(collected), 1)
        self.assertEqual(scraper.fetch_all([]), [])
        self.assertEqual(scraper._abs_url("/root"), "https://blog.sina.com.cn/root")
        self.assertEqual(scraper._abs_url("//blog.sina.com.cn/proto"), "https://blog.sina.com.cn/proto")
        self.assertEqual(scraper._clean_body(" a \n\n 点击进入 \n微信号：x\n b "), "a\nb")
        self.assertEqual(scraper._effective_time("2月30日盘中直播", now), (now, False))
        self.assertEqual(scraper._effective_time("12月31日盘中直播", datetime(now.year, 1, 1)),
                         (datetime(now.year, 1, 1), False))
        with patch.object(scraper, "fetch_recent", side_effect=RuntimeError("one")):
            self.assertEqual(scraper.fetch_all([{"uid": "3"}]), [])
        with patch.object(scraper, "fetch_recent", return_value={"articles": [], "available": True}):
            self.assertEqual(scraper.fetch_all([{"uid": "4"}]), [])

        recent_but_outside_window = [{
            "title": "recent", "url": "u",
            "published": now - blogger_module.timedelta(days=1),
            "effective": now - blogger_module.timedelta(days=1), "is_live": False,
        }]
        with patch.object(scraper, "fetch_article_list",
                          return_value=recent_but_outside_window), \
             patch("builtins.print") as printer:
            no_update = scraper.fetch_recent("1", name="quiet", hours=1)
        self.assertTrue(no_update["available"])
        self.assertEqual(no_update["articles"], [])
        printer.assert_called_once()

        only_live_shell = [{
            "title": "live", "url": "u", "published": now,
            "effective": now, "is_live": True,
        }]
        with patch.object(scraper, "fetch_article_list",
                          return_value=only_live_shell), \
             patch.object(scraper, "fetch_article_body", return_value="short"), \
             patch("builtins.print") as printer:
            empty_live = scraper.fetch_recent("1", name="live", hours=24)
        self.assertTrue(empty_live["available"])
        self.assertEqual(empty_live["articles"], [])
        printer.assert_called_once()

        demo_article = {
            "title": "demo", "url": "https://example.invalid/demo",
            "published": "2026-09-08 08:00", "content": "body",
        }
        with patch.object(blogger_module.BloggerScraper, "fetch_recent",
                          return_value={"available": True,
                                        "articles": [demo_article]}), \
             patch("builtins.print") as printer:
            blogger_module.test_scraper()
        self.assertGreaterEqual(printer.call_count, 4)

        from scrapers.x_api_scraper import XApiScraper
        import scrapers.x_api_scraper as x_api
        scraper = XApiScraper("token", timeout=1)
        lookup_response = MagicMock()
        lookup_response.json.return_value = {"data": {"id": "7", "username": "fixture"}}
        lookup_response.raise_for_status.return_value = None
        tweets_response = MagicMock()
        tweets_response.json.return_value = {
            "data": [{"id": "99", "text": "fixture post",
                      "author_id": "7", "created_at": "2026-09-08T00:00:00Z"}],
            "includes": {"users": [{"id": "7", "username": "fixture"}]},
            "meta": {},
        }
        tweets_response.raise_for_status.return_value = None
        with patch.object(x_api.requests, "get", side_effect=[lookup_response, lookup_response, tweets_response]):
            self.assertEqual(scraper.lookup_user(" fixture ")["user"]["id"], "7")
            self.assertEqual(scraper.fetch_username_tweets("fixture")["available"], True)
        self.assertFalse(scraper.lookup_user("")["available"])
        malformed = MagicMock()
        malformed.json.return_value = []
        malformed.raise_for_status.return_value = None
        with patch.object(x_api.requests, "get", return_value=malformed):
            self.assertFalse(scraper.lookup_user("fixture")["available"])
        with patch.object(scraper, "lookup_user", return_value={"available": False, "error": "bad"}):
            self.assertFalse(scraper.fetch_username_tweets("fixture")["available"])
        with patch.object(x_api.requests, "get", side_effect=RuntimeError("offline")):
            self.assertFalse(scraper.lookup_user("fixture")["available"])
        self.assertIsNone(scraper._normalize({"text": "x", "created_at": "bad", "id": "1"}, {})["pub_date"])
        with patch.object(scraper, "search_recent", return_value={"tweets": [], "available": True}):
            self.assertTrue(scraper.fetch_finance_comments([" ", ""])["available"] is False)

    def test_x_api_edge_shapes_and_pagination(self):
        from scrapers.x_api_scraper import XApiScraper
        import scrapers.x_api_scraper as x_api

        with patch.dict(os.environ, {}, clear=True):
            unconfigured = XApiScraper()
            self.assertFalse(unconfigured.lookup_user("fixture")["available"])
            self.assertFalse(unconfigured.search_recent("fixture")["available"])
            self.assertFalse(unconfigured.fetch_finance_comments([" "])["available"])

        scraper = XApiScraper("token", timeout=1)
        invalid_response = MagicMock()
        invalid_response.raise_for_status.return_value = None
        invalid_response.json.return_value = []
        with patch.object(x_api.requests, "get", return_value=invalid_response):
            with self.assertRaisesRegex(ValueError, "must be an object"):
                scraper._get("fixture", {})
        self.assertFalse(scraper.lookup_user("")["available"])
        with patch.object(scraper, "_get", return_value={"data": {"username": "fixture"}}):
            self.assertFalse(scraper.lookup_user("fixture")["available"])
        with patch.object(scraper, "_get", return_value={"data": {"id": "7", "username": "fixture"}}):
            self.assertTrue(scraper.lookup_user("fixture")["available"])
        with patch.object(scraper, "_get", return_value={"data": "bad"}):
            self.assertFalse(scraper.lookup_user("fixture")["available"])

        with patch.object(scraper, "_get", return_value={"data": {}, "includes": {}, "meta": {}}):
            result = scraper.fetch_user_tweets("7", limit=0, pagination_token="next")
            self.assertFalse(result["available"])
            self.assertEqual(result["provenance"], "no_content")
        with patch.object(scraper, "_get", return_value={"data": "bad"}):
            self.assertFalse(scraper.fetch_user_tweets("7")["available"])
        with patch.object(scraper, "_get", return_value={"data": {}, "includes": {}, "meta": {}}):
            result = scraper.search_recent("fixture", limit=0, next_token="next")
            self.assertFalse(result["available"])
            self.assertEqual(result["provenance"], "no_content")

        with patch.object(scraper, "_get", return_value={"data": "bad"}):
            self.assertFalse(scraper.search_recent("fixture")["available"])
        normalized = scraper._normalize({"text": "", "id": "1", "author_id": "7",
                                         "created_at": None}, {})
        self.assertEqual(normalized["username"], "7")
        self.assertEqual(normalized["conversation_id"], "")
        self.assertIsNone(
            scraper._normalize({"created_at": "not-a-date"}, {})["pub_date"])

        with patch.object(
                scraper, "lookup_user",
                return_value={"available": False, "error": "missing"}):
            result = scraper.fetch_username_tweets("missing")
        self.assertFalse(result["available"])
        with patch.object(
                scraper, "lookup_user",
                return_value={"available": True, "user": {"id": "7"}}), \
             patch.object(
                 scraper, "fetch_user_tweets",
                 return_value={"available": True, "tweets": []}) as fetch:
            result = scraper.fetch_username_tweets("fixture", limit=3)
        self.assertTrue(result["available"])
        fetch.assert_called_once_with("7", limit=3)

    def test_github_monitor_http_report_and_alert_paths(self):
        import github_monitor
        monitor = github_monitor.GitHubMonitor("owner/repo", "CI", "token")
        with patch.object(monitor, "_http_get", return_value={"workflows": [{"name": "CI", "id": 9}]}):
            self.assertEqual(monitor._get_workflow_id(), 9)
            self.assertEqual(monitor._get_workflow_id(), 9)
        missing_monitor = github_monitor.GitHubMonitor("owner/repo", "CI")
        with patch.object(missing_monitor, "_http_get", return_value={"workflows": [{"name": "Other", "id": 1}]}):
            self.assertIsNone(missing_monitor._get_workflow_id())
        failed_monitor = github_monitor.GitHubMonitor("owner/repo", "CI")
        with patch.object(failed_monitor, "_http_get", side_effect=RuntimeError("offline")):
            self.assertIsNone(failed_monitor._get_workflow_id())
        with patch.object(monitor, "_http_get", side_effect=RuntimeError("offline")):
            self.assertEqual(monitor.get_recent_runs(), [])
        self.assertEqual(monitor.analyze_delays([])["total_runs"], 0)
        runs = [{"id": 1, "run_number": 1, "event": "schedule",
                 "status": "completed", "conclusion": "failure",
                 "created_at": "2026-09-01T23:02:00Z",
                 "run_started_at": "2026-09-01T23:03:00Z",
                 "updated_at": "2026-09-01T23:05:00Z",
                 "html_url": "https://example.invalid/run"},
                {"id": 2, "run_number": 2, "event": "workflow_dispatch",
                 "status": "completed", "conclusion": "success",
                 "created_at": "", "run_started_at": ""}]
        report = monitor.analyze_delays(runs)
        self.assertEqual(report["failure_count"], 1)
        self.assertEqual(report["manual_runs"], 1)
        self.assertEqual(report["average_dispatch_delay_seconds"], 120)
        with patch.object(monitor, "get_recent_runs", return_value=[]):
            evaluation = monitor.evaluate_latest(
                [], 300, datetime(2026, 9, 1, 22, 55, tzinfo=timezone.utc))
            self.assertEqual(evaluation["state"], "waiting")
            self.assertFalse(evaluation["alert"])
        with patch.object(monitor, "get_recent_runs", return_value=[runs[1]]):
            evaluation = monitor.evaluate_latest(
                [runs[1]], 300,
                datetime(2026, 9, 1, 22, 55, tzinfo=timezone.utc))
            self.assertEqual(evaluation["state"], "waiting")
        with patch.object(monitor, "evaluate_latest",
                          return_value={"state": "success", "alert": False}):
            self.assertFalse(monitor.check_and_alert())
        delayed = [{"id": 3, "run_number": 3, "event": "schedule",
                    "status": "completed", "conclusion": "success",
                    "created_at": "2026-09-01T23:10:00Z",
                    "run_started_at": "2026-09-01T23:11:00Z",
                    "updated_at": "2026-09-01T23:20:00Z",
                    "html_url": "u"}]
        with patch.object(monitor, "get_recent_runs", return_value=delayed), \
             patch.object(monitor, "evaluate_latest", return_value={
                 "state": "success", "alert": True, "delay_seconds": 600,
                 "run_number": 3, "scheduled_at": "2026-09-01T23:00:00+00:00",
                 "html_url": "u",
             }), \
             patch("alerting.send_alert") as alert:
            self.assertTrue(monitor.check_and_alert(1))
            alert.assert_called_once()
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "report.html")
            with patch.object(monitor, "get_recent_runs", return_value=delayed):
                monitor.generate_report(output)
            with open(output, encoding="utf-8") as handle:
                report_html = handle.read()
            self.assertIn("delay-high", report_html)

    def test_github_monitor_constructor_http_and_cli_paths(self):
        import github_monitor
        from urllib.error import HTTPError, URLError

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "env/repo", "GITHUB_WORKFLOW": "env-ci", "GITHUB_TOKEN": "env-token"}, clear=True):
            env_monitor = github_monitor.GitHubMonitor()
        self.assertEqual(env_monitor.repo, "env/repo")
        self.assertEqual(env_monitor.headers["Authorization"], "Bearer env-token")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                github_monitor.GitHubMonitor()

        monitor = github_monitor.GitHubMonitor("owner/repo")
        response = FakeResponse('{"ok": true}')
        with patch.object(github_monitor.urllib.request, "urlopen", return_value=response) as opener:
            self.assertEqual(monitor._http_get("https://example.invalid/api"), {"ok": True})
            opener.assert_called_once()
        http_error = HTTPError("u", 503, "unavailable", {}, FakeResponse('{"error": "down"}'))
        with patch.object(github_monitor.urllib.request, "urlopen", side_effect=http_error):
            with self.assertRaisesRegex(Exception, "HTTP 503"):
                monitor._http_get("https://example.invalid/api")
        with patch.object(github_monitor.urllib.request, "urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(Exception, "URL Error: offline"):
                monitor._http_get("https://example.invalid/api")

        normal_run = {
            "run_number": 1, "event": "schedule", "status": "completed",
            "created_at": "2026-09-01T23:00:00Z",
            "run_started_at": "2026-09-01T23:00:01Z",
            "updated_at": "2026-09-01T23:00:02Z",
            "conclusion": "success", "html_url": "u",
        }
        with patch.object(monitor, "get_recent_runs", return_value=[normal_run]), \
             patch.object(monitor, "evaluate_latest",
                          return_value={"state": "success", "alert": False}):
            self.assertFalse(monitor.check_and_alert(300))
        with patch.object(monitor, "evaluate_latest", return_value={
                "state": "success", "alert": True, "delay_seconds": 1,
                "run_number": 1, "scheduled_at": "", "html_url": "u"}), \
             patch("alerting.send_alert", side_effect=ImportError):
            self.assertTrue(monitor.check_and_alert(0))
        with patch.object(github_monitor, "GitHubMonitor", side_effect=RuntimeError("offline")), patch("sys.argv", ["github_monitor.py", "--repo", "owner/repo"]):
            self.assertEqual(github_monitor.main(), 1)
        fake_monitor = MagicMock(repo="owner/repo", workflow_name="CI")
        fake_monitor.get_recent_runs.return_value = []
        fake_monitor.analyze_delays.return_value = {
            "total_runs": 0, "scheduled_runs": 0, "manual_runs": 0,
            "average_dispatch_delay_seconds": 0,
            "average_queue_delay_seconds": 0,
        }
        with patch.object(github_monitor, "GitHubMonitor", return_value=fake_monitor), patch("sys.argv", ["github_monitor.py", "--repo", "owner/repo", "--report", "report.html"]):
            self.assertEqual(github_monitor.main(), 0)

    def test_weibo_scraper_fallback_filter_and_limits(self):
        import scrapers.weibo_scraper as module
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        xml = f"""<rss><channel>
        <item><title>{'T' * 60}</title><link>u1</link><pubDate>{now.isoformat()}</pubDate><description>&lt;b&gt;fresh&lt;/b&gt;</description></item>
        <item><title>old</title><link>u2</link><pubDate>{(now - timedelta(hours=30)).isoformat()}</pubDate><description>old</description></item>
        <item><title>future</title><link>u3</link><pubDate>{(now + timedelta(hours=1)).isoformat()}</pubDate><description>future</description></item>
        </channel></rss>"""
        scraper = module.WeiboScraper(rsshub_base="https://one/", timeout=2)
        response = MagicMock(content=xml.encode())
        response.raise_for_status.return_value = None
        with patch.object(module.requests, "get", return_value=response):
            result = scraper.fetch_recent("42", name="fixture", hours=24, max_articles=1)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["articles"]), 1)
        self.assertTrue(result["articles"][0]["title"].endswith("..."))

        bad_date = "<rss><channel><item><title>x</title><link>u</link><pubDate>bad</pubDate><description>x</description></item></channel></rss>"
        bad_response = MagicMock(content=bad_date.encode())
        bad_response.raise_for_status.return_value = None
        with patch.object(module.requests, "get", return_value=bad_response):
            self.assertFalse(scraper.fetch_recent("42")["articles"])
        malformed = MagicMock(content=b"<rss")
        malformed.raise_for_status.return_value = None
        scraper.rsshub_mirrors = ["https://one", "https://two"]
        scraper.max_mirrors = 2
        with patch.object(module.requests, "get", side_effect=[malformed, response]):
            self.assertTrue(scraper.fetch_weibo_user("42")["available"])
        with patch.object(module.requests, "get", side_effect=RuntimeError("offline")):
            failed = scraper.fetch_recent("42")
        self.assertFalse(failed["available"])
        self.assertIn("offline", failed["error"])
        with patch.object(scraper, "fetch_weibo_user", return_value={"available": True, "weibos": []}):
            empty = scraper.fetch_recent("42")
        self.assertFalse(empty["available"])
        with patch.object(module.WeiboScraper, "fetch_recent", return_value={"available": False, "articles": []}):
            self.assertFalse(module.fetch_weibo_blogger("42", "fixture", hours=1)["available"])

    def test_official_x_api_success_failure_and_comments(self):
        from scrapers.x_api_scraper import XApiScraper
        import scrapers.x_api_scraper as x_api
        payload = {
            "data": [{"id": "9", "text": "$AAPL update", "author_id": "7",
                      "created_at": "2026-09-07T07:00:00Z", "public_metrics": {"like_count": 2}}],
            "includes": {"users": [{"id": "7", "username": "fixture"}]},
            "meta": {"next_token": "next"},
        }
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        scraper = XApiScraper("token", timeout=1,)
        with patch.object(x_api.requests, "get", return_value=response) as get:
            result = scraper.search_recent("$AAPL", limit=1)
            self.assertTrue(result["available"])
            self.assertEqual(result["tweets"][0]["username"], "fixture")
            self.assertEqual(result["next_token"], "next")
            comments = scraper.fetch_finance_comments(["$AAPL"], limit=1)
            self.assertEqual(comments["tweets"][0]["category"], "comments")
            self.assertIn("-is:retweet", get.call_args.kwargs["params"]["query"])
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(XApiScraper().fetch_user_tweets("7")["available"])
        with patch.object(x_api.requests, "get", side_effect=RuntimeError("offline")):
            failed = scraper.fetch_user_tweets("7")
        self.assertFalse(failed["available"])
        self.assertEqual(failed["provenance"], "source_failed")
        for status, state in ((401, "auth_failed"), (403, "auth_failed"),
                              (429, "quota_limited"), (503, "source_failed")):
            exc = x_api.requests.HTTPError("api failure")
            exc.response = MagicMock(status_code=status)
            with patch.object(scraper, "_get", side_effect=exc):
                self.assertEqual(scraper.search_recent("$SPY")["provenance"], state)
        self.assertFalse(scraper.search_recent(" ")["available"])
        self.assertFalse(scraper.fetch_finance_comments([])["available"])

        import scrapers.twitter_scraper as twitter
        import scrapers.x_api_scraper as x_api
        from datetime import datetime, timedelta, timezone
        scraper = twitter.TwitterScraper(rsshub_base="https://fixture", timeout=1)
        xml = "<rss><channel><item><title>T</title><link>u</link><pubDate>2026-09-07T07:00:00+00:00</pubDate><description>C</description></item></channel></rss>"
        response = MagicMock(content=xml.encode())
        response.raise_for_status.return_value = None
        with patch("scrapers.twitter_scraper.requests.get", return_value=response):
            fetched = scraper.fetch_tweets("acct", limit=1)
        self.assertTrue(fetched["available"])
        self.assertEqual(fetched["tweets"][0]["username"], "acct")
        with patch("scrapers.twitter_scraper.requests.get", side_effect=RuntimeError("offline")):
            self.assertFalse(scraper.fetch_tweets("acct")["available"])
        tweet = {"content": "news", "username": "acct", "link": "u",
                 "pub_date": datetime.now(timezone.utc)}
        with patch.object(scraper, "fetch_tweets", side_effect=[
            {"available": True, "tweets": [tweet], "source_url": "m"},
            {"available": False, "tweets": [], "error": "bad"}]):
            combined = scraper.fetch_multiple_accounts(["good", "bad"])
        self.assertTrue(combined["available"])
        self.assertEqual(combined["failed_accounts"], ["bad"])
        with patch.object(scraper, "fetch_tweets", return_value={"available": False, "tweets": [], "error": "bad"}):
            self.assertFalse(scraper.fetch_multiple_accounts(["bad"])["available"])
        llm = MagicMock(return_value={"items": [{"title": "x", "idx": 1}]})
        result = scraper.filter_and_summarize([tweet], llm, category="media")
        self.assertEqual(result[0]["verification"], "confirmed")
        self.assertEqual(result[0]["link"], "u")
        bad_idx = scraper.filter_and_summarize([tweet], MagicMock(return_value=[{"idx": 9}]))
        self.assertEqual(bad_idx[0]["link"], "#")
        self.assertEqual(scraper.filter_and_summarize([], llm), [])
        self.assertEqual(scraper.filter_and_summarize([tweet], MagicMock(side_effect=RuntimeError("llm"))), [])
        with patch.object(twitter.TwitterScraper, "fetch_multiple_accounts", return_value={"available": False, "tweets": [], "error": "offline"}):
            self.assertEqual(twitter.fetch_twitter_rumors(llm, accounts=["x"]), [])
        fetch_results = [
            {"available": True, "tweets": [tweet], "source": "rsshub",
             "provenance": "rsshub", "attempted_sources": ["rsshub"]},
            {"available": False, "tweets": [], "error": "offline",
             "source": "rsshub", "provenance": "source_failed",
             "attempted_sources": ["rsshub"]},
        ]
        with patch("scrapers.twitter_scraper._fetch_official_accounts",
                   return_value={"tweets": [], "available": False,
                                 "provenance": "not_configured",
                                 "attempted_sources": ["official_x_api"],
                                 "error": "not configured"}), \
             patch("scrapers.twitter_scraper._fetch_official_comments",
                   return_value={"tweets": [], "available": False,
                                 "provenance": "not_configured",
                                 "attempted_sources": ["official_x_api"],
                                 "error": "not configured"}), \
             patch.object(twitter.TwitterScraper, "fetch_multiple_accounts", side_effect=fetch_results), \
             patch.object(twitter.TwitterScraper, "filter_and_summarize", return_value=[{"title": "r"}]):
            categorized = twitter.fetch_twitter_categorized(llm)
        self.assertTrue(categorized["available"])
        self.assertIn("media", categorized["errors"])
        self.assertIn("comments", categorized["errors"])
        self.assertEqual(categorized["provenance"]["rumors"]["state"], "rsshub")
        self.assertEqual(categorized["provenance"]["rumors"]["degraded_from"], "not_configured")
        self.assertEqual(categorized["provenance"]["comments"]["state"], "not_configured")

        # Exercise RSS mirror fallback, malformed dates, and request limits.
        malformed_xml = """<rss><channel>
            <item><title>bad date</title><link>u1</link>
                <pubDate>not-a-date</pubDate><description> d </description></item>
            <item><title>second</title><link>u2</link>
                <pubDate></pubDate><description></description></item>
        </channel></rss>"""
        first = MagicMock(content=b"broken", status_code=503)
        first.raise_for_status.side_effect = RuntimeError("503")
        second = MagicMock(content=malformed_xml.encode())
        second.raise_for_status.return_value = None
        mirror_scraper = twitter.TwitterScraper(timeout=1)
        mirror_scraper.rsshub_mirrors = ["https://first", "https://second"]
        mirror_scraper.max_mirrors = 2
        with patch("scrapers.twitter_scraper.requests.get",
                   side_effect=[first, second]) as get:
            result = mirror_scraper.fetch_tweets("acct", limit=2)
        self.assertTrue(result["available"])
        self.assertEqual(len(result["tweets"]), 2)
        self.assertIsNone(result["tweets"][0]["pub_date"])
        self.assertIsNone(result["tweets"][1]["pub_date"])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(result["source_url"], "rsshub")

        # Invalid environment values are surfaced during construction rather
        # than silently changing the mirror policy.
        with patch.dict(os.environ, {"RSSHUB_MAX_MIRRORS": "0"}, clear=False):
            self.assertEqual(twitter.TwitterScraper().max_mirrors, 1)

        # Cover all summarizer categories and its supported response shapes.
        json_tweet = {"content": "market move", "username": "acct",
                      "link": "link", "pub_date": None}
        for category in ("rumors", "comments"):
            response = '[{"title":"x","idx":1}]'
            parsed = scraper.filter_and_summarize(
                [json_tweet], MagicMock(return_value=response), category=category)
            self.assertEqual(parsed[0]["category"], category)
            self.assertEqual(parsed[0]["verification"], "unverified")
        wrapped = scraper.filter_and_summarize(
            [json_tweet], MagicMock(return_value={"items": [{"title": "x"}]}))
        self.assertEqual(wrapped[0]["link"], "#")
        supplied_verification = scraper.filter_and_summarize(
            [json_tweet], MagicMock(return_value=[{
                "title": "x", "idx": 1, "verification": "reviewed",
            }]), category="media")
        self.assertEqual(supplied_verification[0]["verification"], "reviewed")
        self.assertEqual(scraper.filter_and_summarize(
            [json_tweet], MagicMock(return_value={"a": 1, "b": 2})), [])

        with patch.object(scraper, "fetch_tweets", return_value={
                "available": True, "tweets": [json_tweet]}):
            no_source = scraper.fetch_multiple_accounts(["acct"])
        self.assertFalse(no_source["available"])
        with patch.object(scraper, "fetch_tweets", return_value={
                "available": True, "tweets": [], "source_url": "m"}):
            self.assertFalse(scraper.fetch_multiple_accounts(None)["available"])

        with patch.object(twitter.TwitterScraper, "fetch_multiple_accounts",
                          return_value={"available": True,
                                        "tweets": [json_tweet]}), \
             patch.object(twitter.TwitterScraper, "filter_and_summarize",
                          return_value=[{"title": "r"}]):
            self.assertEqual(len(twitter.fetch_twitter_rumors(
                MagicMock(), accounts=["acct"])), 1)

        with patch.object(x_api.XApiScraper, "__init__", return_value=None), \
             patch.object(x_api.XApiScraper, "configured",
                          new=property(lambda _self: False)):
            official_unconfigured = twitter._fetch_official_accounts(
                scraper, ["acct"], 1, 24)
            comments_unconfigured = twitter._fetch_official_comments(["$SPY"], 1)
            self.assertEqual(official_unconfigured["provenance"], "not_configured")
            self.assertEqual(comments_unconfigured["provenance"], "not_configured")

        # Exercise configured official-account success, per-account failure,
        # empty-result degradation, and the Recent Search wrapper.
        recent = {"content": "official", "username": "acct",
                  "pub_date": datetime.now(timezone.utc), "link": "x"}
        with patch.object(x_api.XApiScraper, "configured",
                          new=property(lambda _self: True)), \
             patch.object(x_api.XApiScraper, "fetch_username_tweets",
                          side_effect=[{"available": True, "tweets": [recent]},
                                       {"available": False, "tweets": [],
                                        "error": "missing"}]), \
             patch.object(x_api.XApiScraper, "fetch_finance_comments",
                          return_value={"available": True, "tweets": [recent]}):
            official = twitter._fetch_official_accounts(
                scraper, ["good", "bad"], 2, 24)
            self.assertTrue(official["available"])
            self.assertEqual(official["failed_accounts"], ["bad"])
            comments = twitter._fetch_official_comments(["$SPY"], 2)
            self.assertTrue(comments["available"])

        with patch.object(x_api.XApiScraper, "configured",
                          new=property(lambda _self: True)), \
             patch.object(x_api.XApiScraper, "fetch_username_tweets",
                          return_value={"available": True, "tweets": []}):
            empty_official = twitter._fetch_official_accounts(
                scraper, ["empty"], 2, 24)
            self.assertFalse(empty_official["available"])

        with patch("scrapers.twitter_scraper._fetch_official_accounts",
                   return_value={"tweets": [], "available": False,
                                 "provenance": "not_configured",
                                 "attempted_sources": ["official_x_api"],
                                 "error": "not configured"}), \
             patch("scrapers.twitter_scraper._fetch_official_comments",
                   return_value={"tweets": [], "available": False,
                                 "provenance": "not_configured",
                                 "attempted_sources": ["official_x_api"],
                                 "error": "not configured"}), \
             patch.object(twitter.TwitterScraper, "fetch_multiple_accounts",
                          return_value={"available": False, "tweets": [],
                                        "error": "offline",
                                        "provenance": "source_failed",
                                        "attempted_sources": ["rsshub"]}):
            unavailable = twitter.fetch_twitter_categorized(MagicMock())
        self.assertFalse(unavailable["available"])
        self.assertIn("comments", unavailable["errors"])

        old_comment = {"content": "old", "username": "acct",
                       "pub_date": datetime.now(timezone.utc) - timedelta(hours=48),
                       "link": "https://x.test/old"}
        with patch("scrapers.twitter_scraper._fetch_official_accounts",
                   return_value={"tweets": [], "available": False,
                                 "provenance": "not_configured",
                                 "attempted_sources": ["official_x_api"]}), \
             patch("scrapers.twitter_scraper._fetch_official_comments",
                   return_value={"available": True, "tweets": [old_comment]}), \
             patch.object(twitter.TwitterScraper, "fetch_multiple_accounts",
                          return_value={"available": False, "tweets": [],
                                        "error": "offline"}):
            stale_comments = twitter.fetch_twitter_categorized(MagicMock(), hours=24)
        self.assertFalse(stale_comments["available"])
        self.assertIn("24小时内无新讨论", stale_comments["errors"]["comments"])

    def test_twitter_official_categories_and_comment_metadata(self):
        from scrapers import twitter_scraper as twitter

        now = datetime.now(timezone.utc)
        rumor = {"content": "rumor", "username": "r", "pub_date": now,
                 "link": "https://x.test/r", "id": "1"}
        media = {"content": "report", "username": "m", "pub_date": now,
                 "link": "https://x.test/m", "id": "2"}
        comment = {"content": "$AAPL discussion", "username": "person",
                   "author_id": "7", "id": "3", "conversation_id": "30",
                   "in_reply_to_user_id": "8", "public_metrics": {"like_count": 9},
                   "pub_date": now, "link": "https://x.test/c",
                   "source": "official_x_api", "category": "comments",
                   "verification": "unverified"}
        account_results = [
            {"available": True, "tweets": [rumor], "source": "official_x_api"},
            {"available": True, "tweets": [media], "source": "official_x_api"},
        ]

        def summarize(tweets, _llm, max_rumors=5, category="rumors", analysis_model=None):
            source = tweets[0]
            return [{"title": source["content"], "summary": source["content"],
                     "source": "@" + source["username"], "idx": 1,
                     "link": source["link"], "category": category,
                     "verification": "confirmed" if category == "media" else "unverified",
                     **{key: source[key] for key in ("author_id", "id", "conversation_id",
                                                    "in_reply_to_user_id", "public_metrics")
                        if key in source}}]

        with patch("scrapers.twitter_scraper._fetch_official_accounts", side_effect=account_results), \
             patch("scrapers.twitter_scraper._fetch_official_comments",
                   return_value={"available": True, "tweets": [comment],
                                 "source": "official_x_api",
                                 "provenance": "official_x_api",
                                 "attempted_sources": ["official_x_api"]}), \
             patch.object(twitter.TwitterScraper, "fetch_multiple_accounts") as rss, \
             patch.object(twitter.TwitterScraper, "filter_and_summarize", side_effect=summarize):
            categorized = twitter.fetch_twitter_categorized(MagicMock(), max_per_category=2)

        rss.assert_not_called()
        self.assertTrue(categorized["available"])
        self.assertEqual(categorized["provenance"]["rumors"]["state"], "official_x_api")
        self.assertEqual(categorized["provenance"]["media"]["state"], "official_x_api")
        self.assertEqual(categorized["provenance"]["comments"]["state"], "official_x_api")
        self.assertEqual(categorized["comments"][0]["category"], "comments")
        self.assertEqual(categorized["comments"][0]["verification"], "unverified")
        self.assertEqual(categorized["comments"][0]["conversation_id"], "30")
        self.assertNotIn(categorized["comments"][0], categorized["media"])


class TestArticleTranslator(unittest.TestCase):
    def test_selection_cache_fetch_and_translation_paths(self):
        from article_translator import ArticleTranslator, batch_translate_articles
        translator = ArticleTranslator(cache_dir=tempfile.mkdtemp())
        long_summary = "English summary " * 12
        base = {"region": "international", "importance_score": 8,
                "link": "https://example.invalid/story", "title": "OpenAI news",
                "summary": long_summary}
        self.assertTrue(translator.is_worth_translating(base))
        for item in [
            {**base, "region": "domestic"}, {**base, "importance_score": 4},
            {**base, "link": ""}, {**base, "link": "https://x.test/video/a"},
            {**base, "link": "https://bloomberg.com/story"},
            {**base, "title": "Breaking: update"},
            {**base, "originalTitle": "中文标题"},
            {**base, "summary": "short"},
        ]:
            self.assertFalse(translator.is_worth_translating(item))

        url = base["link"]
        translator.save_translation_cache(url, "original", "translated")
        cached = translator.load_translation_cache(url)
        self.assertEqual(cached["translated_content"], "translated")
        base_copy = dict(base)
        self.assertTrue(translator.translate_news_item(base_copy))
        self.assertEqual(base_copy["original_content"], "original")
        with patch.object(translator, "get_cache_path", return_value=translator.cache_dir / "bad.json"):
            (translator.cache_dir / "bad.json").write_text("broken", encoding="utf-8")
            self.assertIsNone(translator.load_translation_cache(url))

        html = "<html><body><article>" + ("word " * 60) + "</article></body></html>"
        response = MagicMock(content=html.encode(), encoding="utf-8", apparent_encoding="utf-8")
        response.raise_for_status.return_value = None
        with patch("article_translator.requests.get", return_value=response):
            content = translator.fetch_article_content(url)
        self.assertGreater(len(content), 200)
        with patch("article_translator.requests.get", side_effect=RuntimeError("offline")):
            self.assertIsNone(translator.fetch_article_content(url))
        short_response = MagicMock(content=b"<body>short</body>", encoding="utf-8", apparent_encoding="utf-8")
        short_response.raise_for_status.return_value = None
        with patch("article_translator.requests.get", return_value=short_response):
            self.assertIsNone(translator.fetch_article_content(url))

        translator.llm_caller = MagicMock(side_effect=lambda system, user: "译文")
        translated = translator.translate_article("a" * 2001 + "\n\n" + "b" * 2001, "Title")
        self.assertEqual(translated, "译文\n\n译文")
        translator.llm_caller = None
        self.assertIsNone(translator.translate_article("content"))
        translator.llm_caller = MagicMock(side_effect=RuntimeError("llm"))
        with patch("article_translator.time.sleep"):
            self.assertIsNone(translator.translate_article("x" * 4000))

        with tempfile.TemporaryDirectory() as directory:
            translator = ArticleTranslator(cache_dir=directory)
            url = "https://example.invalid/cache"
            stale = translator.get_cache_path(url)
            stale.write_text(json.dumps({
                "timestamp": (datetime.now() - timedelta(days=8)).isoformat(),
                "translated_content": "old",
            }), encoding="utf-8")
            self.assertIsNone(translator.load_translation_cache(url))
            with patch("builtins.open", side_effect=OSError("save offline")):
                translator.save_translation_cache(url, "original", "translated")
            body_response = MagicMock(content=("<body>" + ("word " * 60) + "</body>").encode(),
                                      encoding="iso-8859-1", apparent_encoding="utf-8")
            body_response.raise_for_status.return_value = None
            with patch("article_translator.requests.get", return_value=body_response):
                self.assertGreater(len(translator.fetch_article_content(url)), 200)
            fallback_response = MagicMock(content=("<html>" + ("word " * 60) + "</html>").encode(),
                                          encoding="utf-8", apparent_encoding="utf-8")
            fallback_response.raise_for_status.return_value = None
            with patch("article_translator.requests.get", return_value=fallback_response):
                self.assertIsNone(translator.fetch_article_content(url))

        with patch.dict(os.environ, {"LLM_ARTICLE_ATTEMPTS": "2"}), \
             patch("article_translator.time.sleep"), \
             patch.object(ArticleTranslator, "save_translation_cache"):
            translator = ArticleTranslator(cache_dir=tempfile.mkdtemp(),
                                           llm_caller=MagicMock(side_effect=["", "译文"]))
            self.assertEqual(translator.translate_article("x" * 100), "译文")

    def test_batch_translation_limits_and_failures(self):
        from article_translator import batch_translate_articles
        candidates = [{"region": "international", "importance_score": score,
                       "link": f"https://example.invalid/{score}",
                       "title": f"Model {score}", "summary": "English " * 20}
                      for score in (5, 8, 7)]
        with patch("article_translator.ArticleTranslator.translate_news_item", return_value=True) as translate:
            self.assertEqual(batch_translate_articles(candidates, MagicMock(), max_count=2), 2)
            self.assertEqual(translate.call_count, 2)
        with patch("article_translator.ArticleTranslator.translate_news_item", return_value=False):
            self.assertEqual(batch_translate_articles(candidates, MagicMock(), max_count=1), 0)
        self.assertEqual(batch_translate_articles([{"title": "中文", "link": "x", "summary": "短"}], MagicMock()), 0)


class TestStandaloneAnalyzersAndHolidaySources(unittest.TestCase):
    def test_event_impact_paths_and_merge(self):
        from event_impact_analyzer import EventImpactAnalyzer
        event = {"title": "event", "summary": "summary"}
        empty = EventImpactAnalyzer()
        self.assertEqual(empty.analyze_event_impact(event)["impact_direction"], "中性")
        self.assertEqual(empty.analyze_events_batch([]), [])

        valid = {"impact_level": "重大", "impact_direction": "利好",
                 "beneficiary_sectors": ["芯片"], "damaged_sectors": [],
                 "operation_advice": "关注", "risk_warning": "注意"}
        analyzer = EventImpactAnalyzer(llm_caller=MagicMock(return_value=valid))
        analyzed = analyzer.analyze_events_batch([event])
        self.assertEqual(analyzed[0]["impact"], valid)
        self.assertEqual(analyzer.merge_impacts_for_strategy(analyzed)["major_events_count"], 1)
        self.assertIsNone(analyzer.merge_impacts_for_strategy([{"impact": {"impact_level": "轻微"}}]))
        missing = EventImpactAnalyzer(llm_caller=MagicMock(return_value={}))
        self.assertEqual(missing.analyze_event_impact(event)["impact_level"], "未知")
        failing = EventImpactAnalyzer(llm_caller=MagicMock(side_effect=RuntimeError("offline")))
        self.assertEqual(failing.analyze_event_impact(event)["impact_level"], "未知")

    def test_news_metrics_all_formats_and_helpers(self):
        from news_metrics_extractor import NewsMetricsExtractor, extract_metrics_from_news
        metric = {"company": "A", "metric_type": "ARR", "metric_name": "ARR",
                  "value": 1_000_000_000, "unit": "USD", "confidence": 0.9,
                  "context": "official"}
        calls = []
        def llm(*args, **kwargs):
            calls.append(1)
            return {"metrics": [metric]}
        extractor = NewsMetricsExtractor(llm)
        self.assertEqual(extractor.extract_metrics([{"title": "x", "summary": "y"}])[0], metric)
        grouped = extractor.group_metrics_by_type([metric, {"metric_type": "other"}])
        self.assertEqual(len(grouped["ARR"]), 1)
        self.assertEqual(len(extractor.filter_high_confidence_metrics([metric], 0.95)), 0)
        self.assertIn("$1.0B", extractor.format_metric_display(metric))
        self.assertIn("100.0%", extractor.format_metric_display({"value": 1, "unit": "%"}))
        self.assertIn("1.0T tokens", extractor.format_metric_display({"value": 1e12, "unit": "tokens"}))
        self.assertIn("1 亿美元", extractor.format_metric_display({"value": 1, "unit": "亿美元"}))
        self.assertIn("5 个", extractor.format_metric_display({"value": 5, "unit": "个"}))
        self.assertEqual(NewsMetricsExtractor().extract_metrics([{"title": "x"}]), [])
        bad = NewsMetricsExtractor(MagicMock(return_value={"wrong": 1}))
        self.assertEqual(bad.extract_metrics([{"title": "x"}]), [])
        failed = NewsMetricsExtractor(MagicMock(side_effect=RuntimeError("offline")))
        self.assertEqual(failed.extract_metrics([{"title": "x"}]), [])
        self.assertEqual(extract_metrics_from_news([{"title": "x", "summary": "y"}], llm)["total_count"], 1)

    def test_holiday_sources_success_failure_and_fallback(self):
        import fetch_official_holidays as holidays
        sse = {"days": [{"date": "2026-01-01", "isOffDay": True},
                        {"date": "2026-01-03", "isOffDay": True},
                        {"date": "2026-01-05", "isOffDay": False}]}
        with patch("fetch_official_holidays.urllib.request.urlopen",
                   return_value=FakeResponse(json.dumps(sse))):
            result = holidays.fetch_sse_holidays(2026)
        self.assertEqual([str(d) for d in result], ["2026-01-01"])
        timor = {"code": 0, "holiday": {"2026-01-01": {"holiday": True},
                                           "2026-01-03": {"holiday": True}}}
        with patch("fetch_official_holidays.urllib.request.urlopen",
                   return_value=FakeResponse(json.dumps(timor))):
            self.assertEqual(len(holidays.fetch_timor_holidays(2026)), 1)
        with patch("fetch_official_holidays.urllib.request.urlopen", side_effect=RuntimeError("offline")):
            self.assertEqual(holidays.fetch_sse_holidays(2026), [])
            self.assertEqual(holidays.fetch_timor_holidays(2026), [])
        with patch.object(holidays, "fetch_timor_holidays", return_value=[]), \
             patch.object(holidays, "fetch_sse_holidays", return_value=["fixture"]):
            self.assertEqual(holidays.fetch_official_holidays(2026), ["fixture"])
        self.assertEqual(holidays.fetch_official_holidays(2026, market="HK"), [])


class TestOperationsAndClients(unittest.TestCase):
    def test_monitor_metrics_health_persistence_and_tracker(self):
        import monitoring
        monitor = monitoring.MonitorMetrics()
        with patch.object(monitor, "_persist_alert"), \
             patch.object(monitor, "_send_immediate_notification"):
            monitor.record_run("ai_daily", True, 2.0, items_count=3)
            monitor.record_run("ai_daily", False, 1.0, items_count=0, error="bad")
            monitor.record_data_quality(2, 4)
            monitor.alert(monitoring.AlertLevel.INFO, "info", "message")
        self.assertEqual(monitor.metrics["ai_daily"]["success_count"], 1)
        self.assertEqual(monitor.metrics["ai_daily"]["failure_count"], 1)
        self.assertGreaterEqual(len(monitor.alerts), 3)
        self.assertIn(monitor.get_health_status()["status"], {"healthy", "degraded", "unhealthy"})
        monitor.metrics["finance_daily"]["failure_count"] = 3
        monitor.metrics["finance_daily"]["success_count"] = 1
        self.assertEqual(monitor.get_health_status()["status"], "unhealthy")
        monitor.metrics["ai_daily"]["last_run"] = "2000-01-01T00:00:00"
        self.assertTrue(any("48小时" in issue for issue in monitor.get_health_status()["issues"]))
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "metrics.json")
            monitor.export_metrics(output)
            with open(output, encoding="utf-8") as metrics_file:
                self.assertIn("metrics", json.load(metrics_file))

        tracker = monitoring.PerformanceTracker()
        tracker.start("task")
        tracker.end("task")
        tracker.end("missing")
        self.assertIn("task", tracker.get_summary())
        tracker.log_summary()
        self.assertIs(monitoring.get_monitor(), monitoring.get_monitor())
        self.assertIs(monitoring.get_perf_tracker(), monitoring.get_perf_tracker())

    def test_monitor_decorators_success_and_failure(self):
        import monitor_decorator
        import monitoring
        import logger
        monitor = MagicMock()
        logger_instance = MagicMock()
        logger_instance.start_trace.return_value = "trace"
        with patch.object(monitoring, "get_monitor", return_value=monitor), \
             patch.object(logger.LoggerFactory, "get_logger", return_value=logger_instance):
            @monitor_decorator.monitor_task("fixture")
            def success():
                return {"items_count": 2}
            self.assertEqual(success()["items_count"], 2)
            monitor.record_run.assert_called()
            monitor.export_metrics.assert_called()

            @monitor_decorator.monitor_task("fixture-error")
            def failure():
                raise ValueError("boom")
            with self.assertRaises(ValueError):
                failure()
            monitor.alert.assert_called()

        with patch.object(monitoring, "get_monitor", side_effect=ImportError("disabled")):
            @monitor_decorator.monitor_task("unavailable")
            def plain():
                return "ok"
            self.assertEqual(plain(), "ok")

    def test_monitoring_remaining_branches(self):
        import monitoring
        monitor = monitoring.MonitorMetrics()
        monitor.record_run("unknown", True, 1.0)
        monitor.record_run("ai_daily", True, 1.0, items_count=1)
        monitor.record_run("ai_daily", True, 3.0, items_count=1)
        monitor.record_data_quality(5, 10)
        monitor.metrics["ai_daily"]["failure_count"] = 1
        monitor.metrics["ai_daily"]["success_count"] = 4
        monitor.metrics["finance_daily"]["failure_count"] = 1
        monitor.metrics["finance_daily"]["success_count"] = 4
        monitor.metrics["data_quality"]["empty_runs"] = 4
        status = monitor.get_health_status()
        self.assertEqual(status["status"], "degraded")
        self.assertTrue(status["issues"])
        with patch("monitoring.datetime.date", side_effect=RuntimeError("disk")):
            with patch("builtins.open", side_effect=OSError("disk")):
                with self.assertRaises(OSError):
                    monitor._persist_alert({"level": "error"})

        with patch("monitoring.datetime.date", side_effect=RuntimeError("disabled")), \
             patch("monitoring.os.makedirs", side_effect=OSError("disabled")):
            with self.assertRaises(OSError):
                monitor._persist_alert({"level": "error"})

        tracker = monitoring.PerformanceTracker()
        tracker.start("list")
        tracker.end("list")
        self.assertIsInstance(tracker.get_summary()["list"], float)

        @monitoring.monitor_function("ai_daily")
        def list_result():
            return [1, 2]

        @monitoring.monitor_function("ai_daily")
        def tuple_result():
            return (1,)

        @monitoring.monitor_function("ai_daily")
        def dict_result():
            return {"items": [1, 2, 3]}

        self.assertEqual(list_result(), [1, 2])
        self.assertEqual(tuple_result(), (1,))
        self.assertEqual(len(dict_result()["items"]), 3)

    def test_openai_client_success_and_error_contracts(self):
        import types
        fake_client = MagicMock()
        fake_module = types.SimpleNamespace(OpenAI=MagicMock(return_value=fake_client))
        response = MagicMock()
        response.choices = [MagicMock(message=MagicMock(content='{"ok": true}'))]
        fake_client.chat.completions.create.return_value = response
        with patch.dict(sys.modules, {"openai": fake_module}), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "sk-fixture"}):
            from llm.openai_client import OpenAIClient
            client = OpenAIClient()
            self.assertEqual(client.extract_structured_data("prompt", "system"), {"ok": True})
            response.choices[0].message.content = " summary "
            self.assertEqual(client.summarize("text"), "summary")
            fake_client.chat.completions.create.side_effect = RuntimeError("offline")
            self.assertEqual(client.extract_structured_data("prompt"), {})
            self.assertEqual(client.summarize("text"), "")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                OpenAIClient()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-fixture"}), \
             patch.dict(sys.modules, {"openai": None}):
            with self.assertRaises(ImportError):
                OpenAIClient()

    def test_openai_client_cli_test_function(self):
        import llm.openai_client as module
        fake_client = MagicMock()
        fake_client.extract_structured_data.return_value = {"test": "value"}
        fake_client.summarize.return_value = "摘要"
        with patch.object(module, "OpenAIClient", return_value=fake_client), patch("builtins.print"):
            module.test_client()
        with patch.object(module, "OpenAIClient", side_effect=RuntimeError("offline")), patch("builtins.print"):
            module.test_client()


class TestAlerting(unittest.TestCase):
    def test_channels_payloads_http_and_global_helpers(self):
        import alerting
        env = {
            "ALERT_WECOM_WEBHOOK": "https://wecom.invalid",
            "ALERT_DINGTALK_WEBHOOK": "https://ding.invalid",
            "ALERT_DINGTALK_SECRET": "secret-fixture",
            "ALERT_FEISHU_WEBHOOK": "https://feishu.invalid",
            "ALERT_WEBHOOK": "https://custom.invalid",
        }
        with patch.dict(os.environ, env, clear=True):
            notifier = alerting.AlertNotifier()
        self.assertEqual(len(notifier.channels), 4)
        sent = []

        def fake_post(url, payload, timeout=10):
            sent.append((url, payload, timeout))
            return {"ok": True}

        with patch.object(notifier, "_http_post", side_effect=fake_post):
            self.assertTrue(notifier.send_alert(
                "ERROR", "fixture", "message", {"key": "value"}))
        self.assertEqual(len(sent), 4)
        self.assertEqual(sum(item[1].get("msgtype") == "markdown"
                             for item in sent), 2)
        self.assertEqual(sum(item[1].get("msg_type") == "text"
                             for item in sent), 1)
        self.assertEqual(sum("level" in item[1] for item in sent), 1)
        self.assertEqual(alerting.AlertNotifier()._get_emoji("UNKNOWN"), "📢")

        with patch.object(notifier, "_http_post", side_effect=RuntimeError("offline")):
            self.assertFalse(notifier.send_alert("WARNING", "x", "y"))
        with patch.dict(os.environ, {}, clear=True):
            empty = alerting.AlertNotifier()
            self.assertFalse(empty.send_alert("INFO", "x", "y"))

        response = FakeResponse('{"errcode": 0}')
        with patch("alerting.urllib.request.urlopen", return_value=response) as opener:
            self.assertEqual(notifier._http_post("https://fixture", {"x": 1}),
                             {"errcode": 0})
            self.assertEqual(opener.call_args.kwargs["timeout"], 10)
        with patch("alerting.urllib.request.urlopen", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                notifier._http_post("https://fixture", {})
        with patch.object(alerting, "get_notifier", return_value=notifier):
            with patch.object(notifier, "send_alert", return_value=True):
                self.assertTrue(alerting.send_alert("INFO", "x", "y"))

    def test_dingtalk_signing_and_unsigned_urls(self):
        import alerting
        notifier = alerting.AlertNotifier()
        sent = []
        notifier._http_post = lambda url, payload: sent.append((url, payload))
        config = {
            "webhook": "https://ding.invalid/robot/send",
            "secret": "secret-fixture",
        }

        with patch("alerting.time.time", return_value=1_700_000_000.125):
            notifier._send_dingtalk("ERROR", "fixture", "message", None, config)
        timestamp = "1700000000125"
        signature = alerting.base64.b64encode(alerting.hmac.new(
            b"secret-fixture", f"{timestamp}\nsecret-fixture".encode("utf-8"),
            alerting.hashlib.sha256,
        ).digest()).decode("utf-8")
        expected_query = alerting.urllib.parse.urlencode({
            "timestamp": timestamp,
            "sign": signature,
        })
        self.assertEqual(
            sent[0][0],
            f"https://ding.invalid/robot/send?{expected_query}",
        )
        self.assertEqual(sent[0][1]["markdown"]["title"], "fixture")

        config["webhook"] = "https://ding.invalid/robot/send?access_token=fixture"
        with patch("alerting.time.time", return_value=1_700_000_000.125):
            notifier._send_dingtalk("WARNING", "fixture", "message", {}, config)
        self.assertEqual(
            sent[1][0],
            f"https://ding.invalid/robot/send?access_token=fixture&{expected_query}",
        )

        config = {"webhook": "https://ding.invalid/robot/send", "secret": ""}
        notifier._send_dingtalk("INFO", "fixture", "message", None, config)
        self.assertEqual(sent[2][0], "https://ding.invalid/robot/send")


class TestEnterpriseAudit(unittest.TestCase):
    def test_audit_checks_and_main(self):
        import enterprise_audit as m
        with tempfile.TemporaryDirectory() as directory:
            original = os.getcwd()
            try:
                os.chdir(directory)
                for name in ("push_config.json", ".env", "config.json"):
                    open(name, "w", encoding="utf-8").close()
                os.makedirs("logs")
                with open(os.path.join("logs", "app.log"), "w", encoding="utf-8") as stream:
                    stream.write("sk-" + "a" * 32)
                with open(".gitignore", "w", encoding="utf-8") as stream:
                    stream.write("push_config.json\n*.log\n.env\n__pycache__\n*.pyc\nmetrics.json\n.cache\n")
                with open("requirements.txt", "w", encoding="utf-8") as stream:
                    stream.write("requests==1\n")
                for name in ("ai_daily_push.py", "finance_daily_push.py"):
                    with open(name, "w", encoding="utf-8") as stream:
                        stream.write("urlopen(foo)\nexcept:\n.open(x)\n")
                with open("concurrent_fetcher.py", "w", encoding="utf-8") as stream:
                    stream.write("retry")
                with open("logger.py", "w", encoding="utf-8") as stream:
                    stream.write("DEBUG INFO WARNING ERROR CRITICAL")
                with open("monitoring.py", "w", encoding="utf-8") as stream:
                    stream.write("duration success alert email health trace")
                with open("README.md", "w", encoding="utf-8") as stream:
                    stream.write("安装 配置 使用")
                os.makedirs(".github/workflows")
                with open("LICENSE", "w", encoding="utf-8") as stream:
                    stream.write("license")
                issues = []
                for check in (m.check_security_issues, m.check_reliability_issues,
                              m.check_observability_issues, m.check_maintainability_issues,
                              m.check_performance_issues, m.check_compliance_issues):
                    issues.extend(check())
                self.assertTrue(issues)
                self.assertFalse(m.main())
            finally:
                os.chdir(original)

    def test_audit_sparse_project_reports_missing_controls(self):
        import enterprise_audit as m
        with tempfile.TemporaryDirectory() as directory:
            original = os.getcwd()
            try:
                os.chdir(directory)
                for name in ("ai_daily_push.py", "finance_daily_push.py"):
                    with open(name, "w", encoding="utf-8") as stream:
                        stream.write('"""module"""\nfor item in urls:\n    http(item)\n')
                with open("logger.py", "w", encoding="utf-8") as stream:
                    stream.write('"""module"""\nINFO\n')
                with open("monitoring.py", "w", encoding="utf-8") as stream:
                    stream.write('"""module"""\n')
                issues = (m.check_security_issues() + m.check_reliability_issues()
                          + m.check_observability_issues() + m.check_maintainability_issues()
                          + m.check_performance_issues() + m.check_compliance_issues())
                joined = "\n".join(issues)
                self.assertIn("缺少 .gitignore", joined)
                self.assertIn("缺少 requirements.txt", joined)
                self.assertIn("缺少重试机制", joined)
                self.assertIn("缺少数据验证", joined)
                self.assertIn("缺少级别", joined)
                self.assertIn("未记录执行时间", joined)
                self.assertIn("未记录成功率", joined)
                self.assertIn("缺少告警机制", joined)
                self.assertIn("未集成通知渠道", joined)
                self.assertIn("缺少健康检查", joined)
                self.assertIn("缺少 Trace ID", joined)
                self.assertIn("缺少版本号", joined)
                self.assertIn("测试文件较少", joined)
                self.assertIn("缺少 CI/CD", joined)
                self.assertIn("缺少并发抓取", joined)
                self.assertIn("未发现缓存", joined)
                self.assertIn("缺少 LICENSE", joined)
                self.assertIn("缺少 README", joined)
            finally:
                os.chdir(original)

    def test_audit_clean_paths(self):
        import enterprise_audit as m
        with tempfile.TemporaryDirectory() as directory:
            original = os.getcwd()
            try:
                os.chdir(directory)
                os.makedirs(".github/workflows")
                for name in ("ai_daily_push.py", "finance_daily_push.py"):
                    with open(name, "w", encoding="utf-8") as stream:
                        stream.write('"""module"""\nvalidate()\n')
                with open("monitoring.py", "w", encoding="utf-8") as stream:
                    stream.write('"""module"""\nduration success alert email health\n')
                with open("logger.py", "w", encoding="utf-8") as stream:
                    stream.write('"""module"""\nDEBUG INFO WARNING ERROR CRITICAL trace\n')
                with open("concurrent_fetcher.py", "w", encoding="utf-8") as stream:
                    stream.write("retry")
                with open("cache.json", "w", encoding="utf-8") as stream:
                    stream.write("{}")
                with open(".gitignore", "w", encoding="utf-8") as stream:
                    stream.write("push_config.json *.log .env __pycache__ *.pyc metrics.json .cache")
                with open("requirements.txt", "w", encoding="utf-8") as stream:
                    stream.write("requests==1")
                with open("README.md", "w", encoding="utf-8") as stream:
                    stream.write("安装 配置 使用")
                with open("LICENSE", "w", encoding="utf-8") as stream:
                    stream.write("license")
                with open("setup.py", "w", encoding="utf-8") as stream:
                    stream.write("version = '1.0'\n")
                for index in range(3):
                    with open("test_%d.py" % index, "w", encoding="utf-8") as stream:
                        stream.write("# test\n")
                self.assertEqual(m.check_security_issues(), [])
                self.assertEqual(m.check_reliability_issues(), [])
                self.assertEqual(m.check_observability_issues(), [])
                self.assertEqual(m.check_maintainability_issues(), [])
                self.assertEqual(m.check_performance_issues(), [])
                self.assertTrue(m.check_compliance_issues())
            finally:
                os.chdir(original)


class TestUtilityModules(unittest.TestCase):
    def test_translation_service_batches_and_normalizes_results(self):
        import translation_service
        calls = []

        def call(system, user, model=None, retries=1):
            calls.append((user, model, retries))
            if len(calls) == 1:
                return {"translation": "第一段"}
            if len(calls) == 2:
                return '{"text": "第二段"}'
            return "```json\n第三段\n```"

        with patch.dict(os.environ, {"OPENAI_MODEL_TRANSLATE": "fixture-model"}):
            result = translation_service.translate_article_llm(
                " a " + "x" * 8 + "\n\n b " + "y" * 8 + "\n\n c ",
                call, max_chars_per_batch=10)
        self.assertEqual(result, "第一段\n\n第二段\n\n第三段")
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(call[1:] == ("fixture-model", 2) for call in calls))

        self.assertEqual(translation_service.translate_article_llm(" \n\n", call), "")
        self.assertEqual(translation_service._translate_batch("原文", MagicMock(side_effect=RuntimeError("offline"))), "原文")
        self.assertEqual(translation_service._translate_batch("x", lambda *args, **kwargs: {"content": " c "}), "c")
        self.assertEqual(translation_service._translate_batch("x", lambda *args, **kwargs: {"other": 1}), "{'other': 1}")
        self.assertEqual(translation_service._translate_batch("x", lambda *args, **kwargs: 123), "123")

    def test_cover_generator_success_cache_and_failures(self):
        import cover_generator
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "cover.jpg")
            self.assertTrue(cover_generator.generate_cover_image("t", "2026-09-01T00:00:00Z", output))
            self.assertTrue(os.path.exists(output))
            self.assertTrue(cover_generator.generate_cover_image("t", "bad-date", output, "finance"))
            self.assertTrue(cover_generator.get_or_create_cover("2026-09-01", "ai").endswith("ai_daily_20260901.jpg"))
        with patch.object(cover_generator, "PIL_AVAILABLE", False):
            self.assertFalse(cover_generator.generate_cover_image("t", "d", "x"))
            self.assertIsNone(cover_generator.create_default_cover())
        with patch.object(cover_generator, "generate_cover_image", return_value=False), \
             patch.object(cover_generator.os, "makedirs"), \
             patch.object(cover_generator.os.path, "exists", return_value=False):
            self.assertIsNone(cover_generator.get_or_create_cover("2026-09-01"))
        with patch.object(cover_generator.Image, "new", side_effect=RuntimeError("image")):
            self.assertIsNone(cover_generator.create_default_cover("finance"))

    def test_cover_generator_font_default_and_default_cover_cache(self):
        import cover_generator
        image = MagicMock()
        draw = MagicMock()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(cover_generator.os.path, "exists", return_value=False), \
             patch.object(cover_generator.Image, "new", return_value=image), \
             patch.object(cover_generator.ImageDraw, "Draw", return_value=draw), \
             patch.object(cover_generator.ImageFont, "load_default", return_value=MagicMock()):
            self.assertTrue(cover_generator.generate_cover_image(
                "title", "bad-date", os.path.join(directory, "cover.jpg"), "finance"))
            image.save.assert_called_once()
        with patch.object(cover_generator.os.path, "exists", side_effect=lambda path: path.endswith("_default.jpg")):
            self.assertTrue(cover_generator.create_default_cover("ai").endswith("ai_default.jpg"))
        with patch.object(cover_generator.os.path, "exists", return_value=False), \
             patch.object(cover_generator.Image, "new", return_value=image):
            image.reset_mock()
            self.assertTrue(cover_generator.create_default_cover("finance").endswith("finance_default.jpg"))
            image.save.assert_called_once()

    def test_config_validator_paths_without_network(self):
        import config_validator
        validator = config_validator.ConfigValidator()
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(validator, "_validate_network"):
            passed, errors, warnings = validator.validate_all()
        self.assertFalse(passed)
        self.assertTrue(errors)
        self.assertTrue(warnings)
        with patch.dict(os.environ, {"PUSHPLUS_TOKEN": "token", "OPENAI_API_KEY": "sk-test"}, clear=True), \
             patch.object(validator, "_validate_network"):
            passed, errors, warnings = validator.validate_all()
        self.assertTrue(passed)
        self.assertFalse(errors)
        with tempfile.TemporaryDirectory() as directory:
            missing = os.path.join(directory, "missing.json")
            self.assertTrue(validator.validate_config_file(missing))
            valid = os.path.join(directory, "valid.json")
            with open(valid, "w", encoding="utf-8") as stream:
                json.dump({"pushplus_token": "x"}, stream)
            self.assertTrue(validator.validate_config_file(valid))
            with open(valid, "w", encoding="utf-8") as stream:
                stream.write("{")
            self.assertFalse(validator.validate_config_file(valid))
        import urllib.request
        with patch.object(urllib.request, "urlopen", side_effect=Exception("offline")):
            validator._validate_network()
        validator.print_report()

    def test_config_validator_push_channels_and_key_warning_branches(self):
        import config_validator
        validator = config_validator.ConfigValidator()
        env = {
            "WECOM_CORPID": "corp", "WECOM_CORPSECRET": "secret", "WECOM_AGENTID": "agent",
            "PUSHPLUS_TOKEN": "push", "DINGTALK_WEBHOOK": "ding", "FEISHU_WEBHOOK": "feishu",
            "OPENAI_API_KEY": "not-sk", "OPENAI_BASE_URL": "https://llm.invalid/v1",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(validator, "_validate_network"):
            passed, errors, warnings = validator.validate_all()
        self.assertTrue(passed)
        self.assertFalse(errors)
        self.assertTrue(any("sk-" in warning for warning in warnings))
        with patch.dict(os.environ, {"DINGTALK_WEBHOOK": "ding"}, clear=True):
            validator._validate_push_config()
        self.assertFalse(validator.errors)

    def test_config_validator_permission_network_and_file_error_branches(self):
        import config_validator
        validator = config_validator.ConfigValidator()
        with patch("builtins.open", side_effect=OSError("read-only")), \
             patch.object(os.path, "exists", return_value=False), \
             patch.object(os, "makedirs", side_effect=OSError("mkdir failed")):
            validator._validate_file_permissions()
        self.assertTrue(any("不可写" in error for error in validator.errors))
        self.assertTrue(any("无法创建目录" in error for error in validator.errors))

        validator.errors.clear()
        with tempfile.TemporaryDirectory() as directory:
            original_cwd = os.getcwd()
            try:
                os.chdir(directory)
                validator._validate_file_permissions()
            finally:
                os.chdir(original_cwd)
        self.assertFalse(validator.errors)

        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("unreachable")):
            validator._validate_network()
        self.assertEqual(len(validator.warnings), 2)
        validator.warnings.clear()
        with patch("urllib.request.urlopen", side_effect=[object(), Exception("broken")]):
            validator._validate_network()
        self.assertTrue(any("GitHub 连接测试失败" in warning for warning in validator.warnings))

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"other": True}, stream)
            self.assertTrue(validator.validate_config_file(path))
            self.assertTrue(any("缺少推送配置" in warning for warning in validator.warnings))
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("[]")
            self.assertTrue(validator.validate_config_file(path))
            with patch("builtins.open", side_effect=OSError("denied")):
                self.assertFalse(validator.validate_config_file(path))
        self.assertTrue(any("读取配置文件失败" in error for error in validator.errors))

    def test_config_validator_report_and_environment_entrypoint(self):
        import config_validator
        validator = config_validator.ConfigValidator()
        validator.print_report()
        validator.errors = ["bad"]
        validator.warnings = ["careful"]
        validator.print_report()
        with patch.object(config_validator.ConfigValidator, "validate_config_file", return_value=True), \
             patch.object(config_validator.ConfigValidator, "validate_all", return_value=(False, ["bad"], [])), \
             patch.object(config_validator.ConfigValidator, "print_report"):
            self.assertFalse(config_validator.validate_environment())
        with patch.object(config_validator.ConfigValidator, "validate_config_file", return_value=True), \
             patch.object(config_validator.ConfigValidator, "validate_all", return_value=(True, [], ["careful"])), \
             patch.object(config_validator.ConfigValidator, "print_report"):
            self.assertTrue(config_validator.validate_environment())
        with patch.object(config_validator.ConfigValidator, "validate_config_file", return_value=True), \
             patch.object(config_validator.ConfigValidator, "validate_all", return_value=(True, [], [])), \
             patch.object(config_validator.ConfigValidator, "print_report"):
            self.assertTrue(config_validator.validate_environment())


class TestCalendarUpdaterAndUiEnhancer(unittest.TestCase):
    def test_trading_calendar_updater_generation_and_year_branches(self):
        import trading_calendar_updater as updater_module
        updater = updater_module.TradingCalendarUpdater()
        fixed = updater._get_fixed_holidays(2026)
        self.assertEqual(len(fixed), 15)
        self.assertEqual(len(updater._get_lunar_holidays(2026)), 16)
        self.assertEqual(updater._get_lunar_holidays(2099), [
            updater_module.datetime.date(2099, 4, day) for day in (5, 6, 7)
        ])
        self.assertEqual(updater._expand_holiday(2026, 1, 1, 3), [
            updater_module.datetime.date(2026, 1, day) for day in (1, 2, 3)
        ])
        china = updater.fetch_china_holidays(2026)
        hk = updater.fetch_hk_holidays(2026)
        self.assertEqual(china, sorted(set(china)))
        self.assertEqual(hk, sorted(set(hk)))
        self.assertIn(updater_module.datetime.date(2026, 2, 17), hk)
        self.assertEqual(updater.fetch_hk_holidays(2099), [
            updater_module.datetime.date(2099, month, day)
            for month, day in ((1, 1), (5, 1), (7, 1), (10, 1), (12, 25), (12, 26))
        ])
        code = updater.update_trading_calendar_file([2026, 2099])
        self.assertIn("A_STOCK_HOLIDAYS_2026", code)
        self.assertIn("HK_STOCK_HOLIDAYS_2099", code)
        self.assertIn("datetime.date(2026, 2, 17)", code)
        with patch.object(updater_module.datetime, "date") as mocked_date:
            mocked_date.today.return_value.year = 2026
            default_code = updater.update_trading_calendar_file()
        self.assertIn("A_STOCK_HOLIDAYS_2027", default_code)

    def test_trading_calendar_updater_invalid_holiday_dates_are_ignored(self):
        import trading_calendar_updater as updater_module
        updater = updater_module.TradingCalendarUpdater()
        real_date = updater_module.datetime.date

        class DateWithInvalidHoliday(real_date):
            @classmethod
            def today(cls):
                return real_date(2026, 1, 1)

            def __new__(cls, year, month, day):
                if year == 2026 and month == 5:
                    raise ValueError("fixture invalid date")
                return real_date(year, month, day)

        with patch.object(updater_module.datetime, "date", DateWithInvalidHoliday):
            self.assertNotIn(real_date(2026, 5, 1), updater.fetch_hk_holidays(2026))

    def test_ui_enhancer_transforms_fixture_and_writes_output(self):
        import enhance_ui_f5
        html = ('<html><style>html{scroll-behavior:smooth}</style>'
                '  @media (max-width:560px){.hero{padding:22px 0 12px}.grid{grid-template-columns:1fr}}'
                '<nav class="nav"><div class="wrap" id="navLinks"></div></nav>'
                '<div class="block emergency"><h2>🚨 突发事件</h2></div>'
                '<footer><div class="wrap">footer</div></footer>'
                '<script>old</script></html>')
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "finance_dashboard.html")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(html)
            with patch.object(enhance_ui_f5, "open", side_effect=lambda name, mode="r", encoding=None: open(
                    path, mode, encoding=encoding)):
                enhance_ui_f5.enhance_html()
            with open(path, encoding="utf-8") as stream:
                result = stream.read()
        self.assertIn("scroll-padding-top:120px", result)
        self.assertIn('id="navSub"', result)
        self.assertIn('id="backToTop"', result)
        self.assertIn('id="breaking-section"', result)


class TestRenderingAndEntrypoints(unittest.TestCase):
    def test_cloudfunction_handler_monitoring_outcomes(self):
        import cloudfunction_handler as cloud
        monitor = MagicMock()
        env = {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_WORKFLOW": "daily",
            "EXPECTED_RUN_TIME": "23:00",
            "DELAY_THRESHOLD": "600",
        }
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(cloud.main_handler({}, None)["statusCode"], 400)
        with patch.dict(os.environ, env, clear=True), \
             patch("github_monitor.GitHubMonitor", return_value=monitor) as factory, \
             patch.object(cloud, "send_alert") as alert:
            monitor.get_recent_runs.return_value = [{"id": 1}]
            monitor.evaluate_latest.return_value = {
                "state": "waiting", "alert": False,
                "scheduled_at": "2026-09-01T23:00:00+00:00",
                "delay_seconds": 300,
            }
            result = cloud.main_handler({}, None)
            self.assertEqual(result["statusCode"], 200)
            self.assertIn('"waiting"', result["body"])
            factory.assert_called_with(
                repo="owner/repo", workflow_name="daily", token="",
                expected_time="23:00",
            )
            alert.assert_not_called()

            for state, level in (("missing", "ERROR"), ("queued", "WARNING"),
                                 ("in_progress", "WARNING"), ("failed", "ERROR"),
                                 ("success", "WARNING")):
                monitor.evaluate_latest.return_value = {
                    "state": state, "alert": True, "delay_seconds": 901,
                    "scheduled_at": "2026-09-01T23:00:00+00:00",
                    "run_number": 7, "html_url": "https://example.invalid/run",
                }
                result = cloud.main_handler({}, None)
                self.assertEqual(result["statusCode"], 503)
                self.assertIn(f'"{state}"', result["body"])
                self.assertEqual(alert.call_args.args[0], level)

        local_env = {**env, "EXPECTED_RUN_TIME": "07:00",
                     "EXPECTED_TIMEZONE": "Asia/Shanghai"}
        with patch.dict(os.environ, local_env, clear=True), \
             patch("github_monitor.GitHubMonitor", return_value=monitor) as factory:
            monitor.evaluate_latest.return_value = {
                "state": "success", "alert": False, "delay_seconds": 1,
            }
            cloud.main_handler({}, None)
            self.assertEqual(factory.call_args.kwargs["expected_time"], "23:00")
        bad_tz_env = {**env, "EXPECTED_TIMEZONE": "Invalid/Zone"}
        with patch.dict(os.environ, bad_tz_env, clear=True), \
             patch("github_monitor.GitHubMonitor", return_value=monitor) as factory:
            cloud.main_handler({}, None)
            self.assertEqual(factory.call_args.kwargs["expected_time"], "23:00")
        with patch.dict(os.environ, env, clear=True), \
             patch("github_monitor.GitHubMonitor", side_effect=RuntimeError("offline")):
            self.assertEqual(cloud.main_handler({}, None)["statusCode"], 500)
        with patch.object(cloud, "main_handler", return_value={"ok": True}):
            self.assertTrue(cloud.handler(b"{}", None)["ok"])
            self.assertTrue(cloud.handler(b"", None)["ok"])
        with patch("alerting.send_alert", side_effect=RuntimeError("offline")):
            cloud.send_alert("ERROR", "title", "message", {"k": "v"})
        self.assertIn("北京时间", cloud.format_beijing_time(datetime(2026, 1, 1)))

    def test_local_monitor_configuration_and_outcomes(self):
        import local_monitor
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(local_monitor, "__file__", os.path.join(directory, "local_monitor.py")), \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "env/repo"}, clear=True):
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                json.dump({"github_repository": "file/repo"}, stream)
            self.assertEqual(local_monitor.load_config()["github_repository"], "env/repo")
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(local_monitor.check_github_actions())
        run_time = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        run = {"created_at": run_time.isoformat(),
               "run_started_at": run_time.isoformat(),
               "conclusion": "success", "run_number": 1, "html_url": "u"}
        monitor = MagicMock()
        env = {"GITHUB_REPOSITORY": "owner/repo", "EXPECTED_RUN_TIME": run_time.strftime("%H:%M"), "DELAY_THRESHOLD": "600"}
        with patch.dict(os.environ, env, clear=True), patch.object(local_monitor, "GitHubMonitor", return_value=monitor), patch.object(local_monitor, "send_alert"):
            monitor.get_recent_runs.return_value = []
            self.assertFalse(local_monitor.check_github_actions())
            monitor.get_recent_runs.return_value = [run]
            self.assertTrue(local_monitor.check_github_actions())
            monitor.get_recent_runs.return_value = [{**run, "conclusion": "failure"}]
            self.assertFalse(local_monitor.check_github_actions())
        with patch.dict(os.environ, env, clear=True), patch.object(local_monitor, "GitHubMonitor", side_effect=RuntimeError("offline")):
            self.assertFalse(local_monitor.check_github_actions())
        with patch.object(local_monitor, "check_github_actions", return_value=True), patch("sys.argv", ["local_monitor.py", "--test"]):
            self.assertEqual(local_monitor.main(), 0)

    def test_static_translation_page_escapes(self):
        import static_page_generator
        with tempfile.TemporaryDirectory() as directory:
            path = static_page_generator.generate_translation_page(
                {"url": "https://example.invalid/a", "title": "<T>", "source": "S"},
                "A & B", directory)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as stream:
                self.assertIn("&lt;T&gt;", stream.read())
            self.assertEqual(
                static_page_generator.generate_translation_page(
                    {"url": "https://example.invalid/a", "title": "<T>", "source": "S"},
                    "changed", directory),
                path,
            )

            rich = static_page_generator.generate_translation_page(
                {"url": "https://example.invalid/rich", "title": '"T"',
                 "source": "S & S", "author": "A <B>", "date": "2026-09-08"},
                "first\n\n  \nsecond <x>", directory)
            with open(rich, encoding="utf-8") as stream:
                html = stream.read()
            self.assertIn("作者：A &lt;B&gt;", html)
            self.assertIn("S &amp; S", html)
            self.assertIn("2026-09-08", html)
            self.assertIn("second &lt;x&gt;", html)

            minimal = static_page_generator.generate_translation_page(
                {"url": "https://example.invalid/minimal"}, "body", directory)
            with open(minimal, encoding="utf-8") as stream:
                html = stream.read()
            self.assertNotIn("{{#author}}", html)
            self.assertNotIn("{{#date}}", html)

        self.assertEqual(static_page_generator._escape_html(None), "")
        self.assertEqual(static_page_generator._escape_html(123), "123")
        import wechat_content_builder
        ai = wechat_content_builder.html_to_wechat_article(
            "ignored", "AI 日报", "https://example.invalid")
        finance = wechat_content_builder.html_to_wechat_finance_article(
            "ignored", "财经日报", "https://example.invalid")
        self.assertIn("AI 日报", ai)
        self.assertIn("财经日报", finance)

    def test_wechat_publish_wrapper_handles_success_and_failures(self):
        import wechat_official
        publisher = MagicMock()
        publisher.publish_article.return_value = {"publish_id": "pub-1"}
        with patch.object(wechat_official, "WechatOfficialPublisher", return_value=publisher):
            self.assertEqual(wechat_official.publish_to_wechat(
                "id", "secret", "title", "body", "author", "digest", "url", "cover"), "pub-1")
        publisher.publish_article.return_value = {}
        with patch.object(wechat_official, "WechatOfficialPublisher", return_value=publisher):
            self.assertIsNone(wechat_official.publish_to_wechat(
                "id", "secret", "title", "body", "author", "digest", "url", "cover"))
        with patch.object(wechat_official, "WechatOfficialPublisher", side_effect=RuntimeError("offline")):
            self.assertIsNone(wechat_official.publish_to_wechat(
                "id", "secret", "title", "body", "author", "digest", "url", "cover"))

    def test_version_is_current_release(self):
        import __version__
        self.assertEqual(__version__.__version__, "4.0.2")
        self.assertEqual(__version__.__version_info__, (4, 0, 2))
        self.assertIn("稳定版本", __version__.VERSION_HISTORY[__version__.__version__])


class TestAIDailyWhiteBoxPaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ai_daily_push
        cls.module = ai_daily_push

    def test_http_errors_daily_fallback_and_empty_index(self):
        m = self.module
        from urllib.error import HTTPError
        not_found = HTTPError("u", 404, "missing", {}, None)
        with patch.object(m, "http_get", side_effect=not_found):
            self.assertIsNone(m.http_get_or_none("https://example.invalid/missing"))
        server_error = HTTPError("u", 500, "bad", {}, None)
        with patch.object(m, "http_get", side_effect=server_error):
            with self.assertRaises(HTTPError):
                m.http_get_or_none("https://example.invalid/error")
        with patch.object(m, "http_get_or_none", return_value=None), \
             patch.object(m, "http_get", side_effect=[{"items": [{"date": "2026-09-02"}]}, {"date": "2026-09-02"}]):
            self.assertEqual(m.fetch_daily("2026-09-03")[1:], ("2026-09-02", True))
        with patch.object(m, "http_get_or_none", return_value=None), \
             patch.object(m, "http_get", return_value={"items": []}):
            with self.assertRaises(RuntimeError):
                m.fetch_daily("2026-09-03")

    def test_rss_atom_and_malformed_xml(self):
        m = self.module
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Atom</title><summary>&lt;b&gt;Summary&lt;/b&gt;</summary><content>&lt;p&gt;Content fallback&lt;/p&gt;</content><link href="https://example.invalid/a"/><updated>today</updated></entry></feed>'''
        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(atom)):
            rows = m.fetch_rss("Fixture", "https://example.invalid/feed", limit=1)
        self.assertEqual(rows[0]["title"], "Atom")
        self.assertEqual(rows[0]["summary"], "Summary")
        self.assertEqual(rows[0]["summary_status"], "available")
        self.assertEqual(rows[0]["link"], "https://example.invalid/a")
        self.assertEqual(rows[0]["source"], "Fixture")

        atom_content = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Content</title><content>&lt;p&gt;Body &amp;amp; details&lt;/p&gt;</content><link href="https://example.invalid/content"/></entry><entry><title>Empty</title><link href="https://example.invalid/empty"/></entry></feed>'''
        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(atom_content)):
            rows = m.fetch_rss("Fixture", "https://example.invalid/feed", limit=2)
        self.assertEqual(rows[0]["summary"], "Body & details")
        self.assertEqual(rows[0]["summary_status"], "available")
        self.assertEqual(rows[1]["summary"], "")
        self.assertEqual(rows[1]["summary_status"], "source_empty")

        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(b"<broken")):
            with self.assertRaises(Exception):
                m.fetch_rss("Fixture", "https://example.invalid/feed")

    def test_aggregate_sources_deduplicates_partial_failures_and_history(self):
        m = self.module
        primary = {"date": "2026-09-03", "sections": [{"items": [{"title": "Same", "summary": "x"}]}]}
        feeds = [("Good", "u1"), ("Bad", "u2")]
        with patch.object(m, "RSS_FEEDS", feeds), \
             patch.object(m, "fetch_rss", side_effect=[[{"title": "Same", "summary": "dup", "link": "u", "source": "Good"}], RuntimeError("offline")]), \
             patch.object(m.os.path, "exists", return_value=False):
            result = m.aggregate_sources(primary)
        self.assertEqual(sum(len(s["items"]) for s in result["sections"]), 1)
        self.assertTrue(result["windowEnd"])
        with tempfile.TemporaryDirectory() as directory:
            history = os.path.join(directory, "push_history.json")
            with open(history, "w", encoding="utf-8") as stream:
                json.dump({"lastPushTime": "2026-09-01T00:00:00+00:00"}, stream)
            with patch.object(m, "HERE", directory), patch.object(m, "RSS_FEEDS", []):
                result = m.aggregate_sources({"sections": []})
            self.assertEqual(result["windowStart"], "2026-09-01T00:00:00+00:00")

        boundary = datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc)
        records = [
            {"delivery_completed_at": "2026-09-08T23:05:00Z"},
            {"timestamp": "2026-09-07T23:10:00+00:00"},
            {"pipeline_completed_at": "2026-09-10T00:00:00Z"},
            {"timestamp": "malformed"},
            "bad-record",
        ]
        self.assertEqual(
            m._latest_history_boundary(records, boundary),
            datetime(2026, 9, 8, 23, 5, tzinfo=timezone.utc),
        )
        self.assertEqual(
            m._latest_history_boundary({"records": records}, boundary),
            datetime(2026, 9, 8, 23, 5, tzinfo=timezone.utc),
        )
        self.assertIsNone(m._latest_history_boundary("bad-schema", boundary))
        self.assertIsNone(m._parse_history_time("not-a-date"))
        self.assertEqual(
            m._parse_history_time("2026-09-08T23:05:00"),
            datetime(2026, 9, 8, 23, 5, tzinfo=timezone.utc),
        )

    def test_term_protection_translation_and_retry(self):
        m = self.module
        protected, terms = m._protect_terms("OpenAI and Google DeepMind", ["DeepMind", "Google DeepMind"])
        self.assertIn("OpenAI", protected)
        self.assertNotIn("Google DeepMind", protected)
        self.assertEqual(m._restore_terms("QQZ1ZQQ QQZ0ZQQ", terms), "QQZ1ZQQ Google DeepMind")
        self.assertTrue(m._has_leftover_placeholder("QQZ 4 ZQQ"))
        self.assertFalse(m._has_leftover_placeholder("translated"))
        self.assertEqual(m.translate_text("中文"), "中文")
        payload = {"responseStatus": 200, "responseData": {"translatedText": "OpenAI translated"}}
        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps(payload))), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.translate_text("OpenAI news", retries=1), "OpenAI translated")
        bad = {"responseStatus": 500, "responseData": {"translatedText": ""}}
        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps(bad))), \
             patch.object(m.time, "sleep"):
            with self.assertRaises(ValueError):
                m.translate_text("English", retries=1)

    def test_llm_json_batch_and_translation_fallback(self):
        m = self.module
        with patch.object(m, "_ai_llm_config", return_value=("", "https://gateway", "model")):
            with self.assertRaises(RuntimeError):
                m.call_ai_llm_json("s", "u", retries=0)
        body = {"choices": [{"message": {"content": "```json\n{\"ok\": true}\n```"}}]}
        with patch.object(m, "_ai_llm_config", return_value=("key", "https://gateway", "model")), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps(body))):
            self.assertEqual(m.call_ai_llm_json("s", "u", retries=0)["ok"], True)
        pairs = [(0, "One", "Summary"), (1, "Two", "")]
        response = {"items": [{"id": "0", "title": "一", "summary": "摘要"}, {"id": 1, "title": "二", "summary": ""}, {"id": None}]}
        with patch.object(m, "call_ai_llm_json", return_value=response):
            result = m.translate_batch_llm_ai(pairs)
        self.assertEqual(result[0], ("一", "摘要"))
        self.assertEqual(result[1], ("二", ""))
        with patch.object(m, "call_ai_llm_json", side_effect=RuntimeError("gateway")):
            self.assertEqual(m.translate_batch_llm_ai(pairs), {})

    def test_translate_items_disabled_partial_llm_and_free_fallback(self):
        m = self.module
        report = {"sections": [{"items": [{"title": "English title", "summary": "English summary"}]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "0"}, clear=False):
            result = m.translate_items(report)
        self.assertEqual(result["sections"][0]["items"][0]["originalTitle"], "English title")
        report = {"sections": [{"items": [{"title": "English title", "summary": "English summary"}]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}, clear=False), \
             patch.object(m, "_ai_llm_config", return_value=("key", "gateway", "model")), \
             patch.object(m, "translate_batch_llm_ai", side_effect=[{0: ("中文标题", "")}, {0: ("", "中文摘要")}]), \
             patch.object(m, "translate_text", side_effect=lambda text: "免费"), \
             patch.object(m.time, "sleep"):
            m.translate_items(report)
        item = report["sections"][0]["items"][0]
        self.assertEqual(item["title"], "中文标题")
        self.assertEqual(item["summary"], "中文摘要")
        report = {"sections": [{"items": [{"title": "English title", "summary": ""}]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}, clear=False), \
             patch.object(m, "_ai_llm_config", return_value=("key", "gateway", "model")), \
             patch.object(m, "translate_batch_llm_ai", side_effect=[{0: ("中文标题", "")}, {0: ("中文标题", "")}]), \
             patch.object(m, "translate_text") as free_translate, \
             patch("builtins.print") as output:
            m.translate_items(report)
        free_translate.assert_not_called()
        self.assertTrue(any("LLM 翻译完成：1/1 条" in str(call) for call in output.call_args_list))

        report = {"sections": [{"items": [{"title": "English", "summary": "Summary"}]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}, clear=False), \
             patch.object(m, "_ai_llm_config", return_value=("", "gateway", "model")), \
             patch.object(m, "translate_text", side_effect=RuntimeError("limited")), \
             patch.object(m.time, "sleep"):
            m.translate_items(report, give_up_after=1)
        self.assertEqual(report["sections"][0]["items"][0]["title"], "English")

    def test_insights_trends_shape_and_markdown_branches(self):
        m = self.module
        insights = {"highlights": {"official_announcements": [{"text": "ARR", "source": "A"}], "market_usage": [{"text": "usage"}], "performance_benchmarks": [{"text": "speed"}]}}
        section = m.create_market_insights_section(insights)
        self.assertEqual(len(section["items"]), 3)
        self.assertIsNone(m.create_market_insights_section({}))
        trends = {"price_trends": [{"model": "M", "change_percent": 4, "from_date": "d", "old_price": 1, "new_price": 2}], "ranking_trends": {"compared_with": "d", "entered": ["N"], "exited": ["X"], "moved": [{"model": "M", "delta": -1, "from_rank": 1, "to_rank": 2}]}}
        cards = m._format_trend_cards(trends, 4)
        self.assertEqual(cards[0]["idx"], 4)
        self.assertGreaterEqual(len(cards), 4)
        shaped = m.shape({"date": "2026-09-01", "sections": []}, market_insights=[{"title": "M", "summary": "S", "source": "X", "link": "#"}], news_metrics={})
        md = m.build_markdown(shaped, "https://example.invalid/dashboard")
        self.assertIn("查看完整仪表盘", md)
        self.assertIn("市场数据与趋势", m.build_html(shaped))

    def test_full_page_translation_and_push_payloads(self):
        m = self.module
        html = "<html><article><p>" + ("Long paragraph content. " * 10) + "</p></article></html>"
        response = MagicMock(content=html.encode(), status_code=200)
        response.raise_for_status.return_value = None
        response.json.return_value = {"choices": [{"message": {"content": "译文"}}]}
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "__file__", os.path.join(directory, "ai_daily_push.py")), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "key", "OPENAI_BASE_URL": "https://gateway"}, clear=False), \
             patch("requests.get", return_value=response), patch("requests.post", return_value=response), \
             patch.object(m, "_ai_llm_config", return_value=("key", "https://gateway", "model")):
            self.assertTrue(m.translate_page_with_llm("https://example.invalid/a", "Title"))
        self.assertEqual(m.translate_page_url("javascript:bad"), "")
        with patch.object(m, "http_post_json", return_value={"errcode": 0}) as post:
            result = m.push_wecom_webhook("hook", "md", "https://example.invalid/dashboard")
            self.assertEqual(result, [{"errcode": 0}])
            payload = post.call_args.args[1]
            self.assertEqual(payload["msgtype"], "news")
        with patch.object(m, "http_post_json", return_value={"StatusCode": 0}) as post:
            result = m.push_feishu("hook", "title", "md", "https://example.invalid/dashboard")
            self.assertEqual(result["StatusCode"], 0)
            self.assertEqual(post.call_args.args[1]["msg_type"], "interactive")
        with patch.object(m, "http_get", return_value={"access_token": "tok"}), \
             patch.object(m, "http_post_json", return_value={"errcode": 0}) as post:
            self.assertEqual(m.push_wecom("id", "secret", "1", "@all", "md")["errcode"], 0)
            self.assertIn("access_token=tok", post.call_args.args[0])
        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse('{"code":200}')):
            self.assertEqual(m.push_pushplus("token", "md", "title")["code"], 200)
    def test_ai_classification_config_scores_and_edge_helpers(self):
        m = self.module
        sections = m.classify_ai_items([
            {"title": "", "summary": "research benchmark"},
            {"title": "unmatched", "summary": ""},
        ])
        self.assertEqual([s["label"] for s in sections], ["🔬 学术研究", "其他资讯"])
        self.assertEqual(m.calculate_similarity("", "title"), 0.0)
        self.assertEqual(m.calculate_similarity("title", ""), 0.0)
        ranked = m.pick_highlights([
            ({"idx": 1, "title": "OpenAI 发布突破", "source": "A"}, "AI"),
            ({"idx": 2, "title": "OpenAI 发布突破细节", "source": "B"}, "AI"),
        ], top_n=5)
        self.assertEqual(len(ranked), 2)
        self.assertGreater(m._score_importance("OpenAI 发布", "AI"), 0)
        self.assertEqual(m.safe_md_url("javascript:bad"), "#")
        self.assertEqual(m.fmt_cst("not-a-date", "%Y"), "not-a-date")

        with patch.object(m, "_BASE_URL_WARNED", False, create=True):
            m._BASE_URL_WARNED = False
            m._warn_if_default_base_url("https://api.openai.com/v1", "key")
            self.assertTrue(m._BASE_URL_WARNED)
            m._warn_if_default_base_url("https://gateway", "")
        with tempfile.TemporaryDirectory() as directory:
            config_path = os.path.join(directory, "push_config.json")
            with open(config_path, "w", encoding="utf-8") as stream:
                json.dump({"openai_api_key": "file-key", "openai_base_url": "https://file-gateway/",
                           "openai_model_translate": "file-model"}, stream)
            with patch.object(m, "HERE", directory), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(m._ai_llm_config(), ("file-key", "https://file-gateway", "file-model"))
            with open(config_path, "w", encoding="utf-8") as stream:
                stream.write("{")
            with patch.object(m, "HERE", directory), patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}, clear=True):
                self.assertEqual(m._ai_llm_config()[0], "env-key")

    def test_ai_remaining_network_and_window_branches(self):
        m = self.module
        payload = {"date": "2026-09-03", "sections": []}
        with patch.object(m, "http_get_or_none", return_value=payload):
            self.assertEqual(m.fetch_daily("2026-09-03"), (payload, "2026-09-03", False))
        rss = b"<rss><channel><item><title>T</title><link>L</link></item></channel></rss>"
        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(rss)):
            row = m.fetch_rss("Fixture", "https://example.invalid/feed")[0]
        self.assertEqual(row["summary"], "")
        with patch.object(m, "RSS_FEEDS", [("Good", "u")]), \
             patch.object(m, "fetch_rss", return_value=[{"title": "Unique", "summary": "x", "link": "u", "source": "Good"}]), \
             patch.dict(os.environ, {"CRON_HOUR": "23", "CRON_MINUTE": "23"}, clear=False):
            result = m.aggregate_sources({"date": "d", "sections": []})
        self.assertEqual(sum(len(s["items"]) for s in result["sections"]), 1)
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "push_history.json"), "w", encoding="utf-8") as stream:
                stream.write("not-json")
            with patch.object(m, "HERE", directory), patch.object(m, "RSS_FEEDS", []):
                self.assertTrue(m.aggregate_sources({"sections": []})["windowStart"])
        with patch.object(m, "_protect_terms", return_value=("x", {"QQZ0ZQQ": "OpenAI"})), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps({
                 "responseStatus": 200, "responseData": {"translatedText": "QQZ 0 ZQQ"}}))), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.translate_text("OpenAI news"), "OpenAI")
        with patch.object(m, "_protect_terms", return_value=("x", {"QQZ0ZQQ": "OpenAI"})), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps({
                 "responseStatus": 200, "responseData": {"translatedText": "QQZ9ZQQ"}}))), \
             patch.object(m.time, "sleep"):
            with self.assertRaises(ValueError):
                m.translate_text("OpenAI news", retries=1)

    def test_ai_full_translation_cache_and_rendering_edges(self):
        m = self.module
        response = MagicMock(content=b"<html><body><p>short</p></body></html>", status_code=200)
        response.raise_for_status.return_value = None
        with patch("requests.get", return_value=response):
            self.assertIsNone(m.translate_page_with_llm("https://example.invalid/short", "Title"))
        response.status_code = 503
        with patch("requests.get", return_value=response):
            self.assertIsNone(m.translate_page_with_llm("https://example.invalid/error", "Title"))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "translated_abc.html")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("ok")
            with patch.object(m, "__file__", os.path.join(directory, "ai_daily_push.py")):
                self.assertEqual(m.translate_page_url("https://example.invalid/abc"), "")
                expected = "translated_" + __import__("hashlib").md5("https://example.invalid/abc".encode()).hexdigest()[:12] + ".html"
                with open(os.path.join(directory, expected), "w", encoding="utf-8") as stream:
                    stream.write("ok")
                self.assertEqual(m.translate_page_url("https://example.invalid/abc"), expected)
        self.assertEqual(m._format_trend_cards({"ranking_trends": {}}), [])
        self.assertEqual(m.build_markdown({"meta": {"date": "2026-09-01", "total": 0,
            "windowStart": "bad", "windowEnd": "bad", "dailyUrl": "javascript:bad"},
            "sections": [], "highlights": []}, ""),
            "# AI 日报 · 2026年09月01日 星期二\n> 总条数 **0** · 收录窗口 bad–bad（北京时间）\n\n[📊 AI HOT 日报主页](#)")
    def test_ai_full_translation_cache_and_rendering_edges(self):
        m = self.module
        response = MagicMock(content=b"<html><body><p>short</p></body></html>", status_code=200)
        response.raise_for_status.return_value = None
        with patch("requests.get", return_value=response):
            self.assertIsNone(m.translate_page_with_llm("https://example.invalid/short", "Title"))
        response.status_code = 503
        with patch("requests.get", return_value=response):
            self.assertIsNone(m.translate_page_with_llm("https://example.invalid/error", "Title"))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "translated_abc.html")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("ok")
            with patch.object(m, "__file__", os.path.join(directory, "ai_daily_push.py")):
                self.assertEqual(m.translate_page_url("https://example.invalid/abc"), "")
                expected = "translated_" + __import__("hashlib").md5("https://example.invalid/abc".encode()).hexdigest()[:12] + ".html"
                with open(os.path.join(directory, expected), "w", encoding="utf-8") as stream:
                    stream.write("ok")
                self.assertEqual(m.translate_page_url("https://example.invalid/abc"), expected)
        self.assertEqual(m._format_trend_cards({"ranking_trends": {}}), [])
        self.assertEqual(m.build_markdown({"meta": {"date": "2026-09-01", "total": 0,
            "windowStart": "bad", "windowEnd": "bad", "dailyUrl": "javascript:bad"},
            "sections": [], "highlights": []}, ""),
            "# AI 日报 · 2026年09月01日 星期二\n> 总条数 **0** · 收录窗口 bad–bad（北京时间）\n\n[📊 AI HOT 日报主页](#)")
        self.assertEqual(m.truncate_bytes("abc", 3), "abc")
        self.assertEqual(m.truncate_bytes("中文", 1), "")

    def test_ai_main_no_push_and_disabled_market_paths(self):
        m = self.module
        args = ["ai_daily_push.py", "--no-push", "--date", "2026-09-08"]
        raw = {"report": {"sections": [{"label": "AI", "items":
            [{"title": "Fixture", "summary": "Summary", "source": {"name": "Fixture"}, "link": "u"}]}]}}
        with patch("sys.argv", args), patch.object(m, "fetch_daily", return_value=(raw, "2026-09-08", False)), \
             patch.object(m, "aggregate_sources", return_value=raw["report"]), \
             patch.object(m, "translate_items", return_value=raw["report"]), \
             patch.object(m, "MARKET_DATA_AVAILABLE", False), \
             patch.object(m, "HERE", tempfile.gettempdir()):
            m.main()

    def test_ai_main_market_fallback_and_empty_news(self):
        m = self.module
        args = ["ai_daily_push.py", "--no-push"]
        raw = {"report": {"sections": []}}
        with patch("sys.argv", args), patch.object(m, "fetch_daily", return_value=(raw, "2026-09-08", True)), \
             patch.object(m, "aggregate_sources", return_value=raw["report"]), \
             patch.object(m, "translate_items", return_value=raw["report"]), \
             patch.object(m, "MARKET_DATA_AVAILABLE", True), \
             patch.object(m, "MarketDataAggregator", side_effect=RuntimeError("offline")), \
             patch.object(m, "HERE", tempfile.gettempdir()):
            m.main()

    def test_ai_main_market_success_trend_and_metrics_failure(self):
        m = self.module
        args = ["ai_daily_push.py", "--no-push", "--date", "2026-09-08"]
        raw = {"report": {"sections": [{"label": "AI", "items":
            [{"title": "Fixture", "summary": "Summary", "source": {"name": "Fixture"}, "link": "u"}]}]}}
        aggregator = MagicMock()
        aggregator.aggregate.return_value = {"models": [{"name": "Claude", "count": 1}]}
        formatter = MagicMock()
        formatter.format_for_html.return_value = [{"title": "Metric", "content": "Value", "source": "Fixture"}]
        trend = {"ranking_trends": {"Claude": {"direction": "up", "change": 1}}}
        with patch("sys.argv", args), patch.object(m, "fetch_daily", return_value=(raw, "2026-09-08", False)), \
             patch.object(m, "aggregate_sources", return_value=raw["report"]), \
             patch.object(m, "translate_items", return_value=raw["report"]), \
             patch.object(m, "MARKET_DATA_AVAILABLE", True), \
             patch.object(m, "MarketDataAggregator", return_value=aggregator), \
             patch.object(m, "MarketReportFormatter", return_value=formatter), \
             patch("analyzers.trend_analyzer.TrendAnalyzer.analyze_trends", return_value=trend), \
             patch("news_metrics_extractor.extract_metrics_from_news", side_effect=RuntimeError("metrics")), \
             patch.object(m, "HERE", tempfile.gettempdir()):
            m.main()

    def _run_ai_main(self, directory, config=None, env=None):
        m = self.module
        if config is not None:
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                json.dump(config, stream)
        raw = {"report": {"date": "2026-09-08", "sections": []}}
        with patch("sys.argv", ["ai_daily_push.py", "--date", "2026-09-08"]), \
             patch.dict(os.environ, env or {}, clear=True), \
             patch.object(m, "HERE", directory), \
             patch.object(m, "fetch_daily", return_value=(raw, "2026-09-08", False)), \
             patch.object(m, "aggregate_sources", return_value=raw["report"]), \
             patch.object(m, "translate_items", return_value=raw["report"]), \
             patch.object(m, "MARKET_DATA_AVAILABLE", False):
            m.main()

    def test_ai_main_push_channel_routes_and_failures(self):
        m = self.module
        scenarios = [
            ({"WECOM_WEBHOOK": "hook"}, "push_wecom_webhook", [{"errcode": 1}]),
            ({"WECOM_WEBHOOK": "hook"}, "push_wecom_webhook", RuntimeError("wecom")),
            ({"FEISHU_WEBHOOK": "hook"}, "push_feishu", {"StatusCode": 1, "msg": "failed"}),
            ({"FEISHU_WEBHOOK": "hook"}, "push_feishu", RuntimeError("feishu")),
            ({"WECOM_CORPID": "id", "WECOM_CORPSECRET": "secret", "WECOM_AGENTID": "1"},
             "push_wecom", {"errcode": 1, "errmsg": "failed"}),
            ({"WECOM_CORPID": "id", "WECOM_CORPSECRET": "secret", "WECOM_AGENTID": "1"},
             "push_wecom", RuntimeError("app")),
            ({"PUSHPLUS_TOKEN": "token", "PUSHPLUS_TOPIC": "topic"},
             "push_pushplus", {"code": 500}),
        ]
        for env, target, result in scenarios:
            with self.subTest(target=target, result=type(result).__name__), tempfile.TemporaryDirectory() as directory:
                kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                with patch.object(m, target, **kwargs) as sender:
                    self._run_ai_main(directory, env=env)
                sender.assert_called_once()
        with tempfile.TemporaryDirectory() as directory:
            self._run_ai_main(directory)

    def test_ai_main_wechat_publish_cover_and_error_paths(self):
        import cover_generator
        import wechat_content_formatter
        import wechat_official

        config = {"wechat_official": {"enabled": True, "appid": "app", "appsecret": "secret"}}
        with tempfile.TemporaryDirectory() as directory:
            cover = os.path.join(directory, "cover.jpg")
            with open(cover, "wb") as stream:
                stream.write(b"image")
            with patch.object(wechat_content_formatter, "format_ai_daily_for_wechat", return_value=("T", "C", "D")), \
                 patch.object(cover_generator, "get_or_create_cover", return_value=cover), \
                 patch.object(wechat_official, "publish_to_wechat", return_value="pub-1") as publish:
                self._run_ai_main(directory, config=config)
            publish.assert_called_once()

        with tempfile.TemporaryDirectory() as directory:
            fallback = os.path.join(directory, "fallback.jpg")
            with open(fallback, "wb") as stream:
                stream.write(b"image")
            with patch.object(wechat_content_formatter, "format_ai_daily_for_wechat", return_value=("T", "C", "D")), \
                 patch.object(cover_generator, "get_or_create_cover", return_value=""), \
                 patch.object(cover_generator, "create_default_cover", return_value=fallback), \
                 patch.object(wechat_official, "publish_to_wechat", return_value=None):
                self._run_ai_main(directory, config=config)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(wechat_content_formatter, "format_ai_daily_for_wechat", return_value=("T", "C", "D")), \
                 patch.object(cover_generator, "get_or_create_cover", return_value=""), \
                 patch.object(cover_generator, "create_default_cover", return_value=""):
                self._run_ai_main(directory, config=config)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(wechat_content_formatter, "format_ai_daily_for_wechat", side_effect=RuntimeError("format")):
                self._run_ai_main(directory, config=config)

        with tempfile.TemporaryDirectory() as directory:
            self._run_ai_main(directory, config={"wechat_official": {"enabled": True}})

    def test_ai_main_empty_market_and_trend_failure(self):
        m = self.module
        aggregator = MagicMock()
        aggregator.aggregate.return_value = {}
        formatter = MagicMock()
        formatter.format_for_html.return_value = []
        args = ["ai_daily_push.py", "--no-push", "--date", "2026-09-08"]
        raw = {"report": {"sections": []}}
        with tempfile.TemporaryDirectory() as directory, patch("sys.argv", args), \
             patch.object(m, "fetch_daily", return_value=(raw, "2026-09-08", False)), \
             patch.object(m, "aggregate_sources", return_value=raw["report"]), \
             patch.object(m, "translate_items", return_value=raw["report"]), \
             patch.object(m, "MARKET_DATA_AVAILABLE", True), \
             patch.object(m, "MarketDataAggregator", return_value=aggregator), \
             patch.object(m, "MarketReportFormatter", return_value=formatter), \
             patch("analyzers.trend_analyzer.TrendAnalyzer.analyze_trends", side_effect=RuntimeError("trend")), \
             patch.object(m, "HERE", directory):
            m.main()


class TestFinanceEntrypointWhiteBox(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import finance_daily_push
        cls.module = finance_daily_push

    @staticmethod
    def _status(days=1):
        return {
            "market_status": "trading", "last_trading_day": date(2026, 9, 7),
            "is_post_holiday": False, "days_since_last_trading": days,
        }

    @staticmethod
    def _items():
        domestic = {"title": "A股政策", "summary": "央行发布政策", "link": "d",
                    "source": "Fixture", "published": "2026-09-08T00:00:00+00:00"}
        international = {"title": "Federal Reserve news", "summary": "Global market update",
                         "link": "i", "source": "Fixture", "isEnglish": True,
                         "published": "2026-09-08T00:00:00+00:00"}
        return {"domestic": [domestic], "international": [international]}

    @staticmethod
    def _copy_template(directory):
        source_path = os.path.join(os.path.dirname(__file__), "finance_dashboard_template.html")
        target_path = os.path.join(directory, "finance_dashboard_template.html")
        with open(source_path, "r", encoding="utf-8") as source, open(target_path, "w", encoding="utf-8") as target:
            target.write(source.read())

    def test_finance_main_no_push_success(self):
        m = self.module
        flow = MagicMock()
        flow.fetch_north_flow.return_value = {"available": True, "total_flow": 2.5}
        flow.fetch_sector_flow.return_value = {"top_inflow": [{"name": "科技", "net_inflow": 3}]}
        flow.fetch_stock_flow.return_value = {"top_inflow": [{"name": "公司", "net_inflow": 4}]}
        analysis = {"summary": "总结", "macro": "宏观", "sector": "行业", "emergencyEvents": []}
        strategy = {"aShare": "A股策略", "hkShare": "港股策略", "risk": "风险"}
        twitter = {"rumors": [], "media": [], "comments": [], "available": True, "errors": {}}
        with tempfile.TemporaryDirectory() as directory, patch("sys.argv", ["finance_daily_push.py", "--no-push"]), \
             patch.object(m, "HERE", directory), patch.object(m, "get_trading_status", return_value=self._status(3)), \
             patch.object(m, "fetch_quotes", return_value=[{"name": "上证", "price": 1, "pct": 2}]), \
             patch("scrapers.money_flow_scraper.MoneyFlowScraper", return_value=flow), \
             patch.object(m, "collect_blogger_views", return_value=[{"name": "博主", "articles": []}]), \
             patch("scrapers.twitter_scraper.fetch_twitter_categorized", return_value=twitter), \
             patch.object(m, "fetch_finance_items", return_value=self._items()), \
             patch.object(m, "translate_finance_items"), patch.object(m, "identify_breaking_news", return_value=[]), \
             patch.object(m, "generate_analysis", return_value=analysis), \
             patch.object(m, "generate_strategy", return_value=strategy):
            self._copy_template(directory)
            m.main()
            self.assertTrue(os.path.exists(os.path.join(directory, "finance_dashboard.html")))

    def test_finance_main_empty_news_and_collection_failures(self):
        m = self.module
        with tempfile.TemporaryDirectory() as directory, \
             patch("sys.argv", ["finance_daily_push.py", "--hours", "24"]), patch.object(m, "HERE", directory), \
             patch.object(m, "get_trading_status", return_value=self._status()), \
             patch.object(m, "fetch_quotes", side_effect=RuntimeError("quotes offline")), \
             patch("scrapers.money_flow_scraper.MoneyFlowScraper", side_effect=RuntimeError("flow offline")), \
             patch.object(m, "collect_blogger_views", side_effect=RuntimeError("blog offline")), \
             patch("scrapers.twitter_scraper.fetch_twitter_categorized", side_effect=RuntimeError("x offline")), \
             patch.object(m, "fetch_finance_items", return_value={"domestic": [], "international": []}):
            self.assertIsNone(m.main())

    def test_finance_main_mocked_push_and_wechat(self):
        m = self.module
        cfg = {"finance_dashboard_url": "https://example.invalid/finance",
               "wechat_official": {"enabled": True, "appid": "app", "appsecret": "secret"}}
        flow = MagicMock()
        flow.fetch_north_flow.side_effect = RuntimeError("north")
        flow.fetch_sector_flow.side_effect = RuntimeError("sector")
        flow.fetch_stock_flow.side_effect = RuntimeError("stock")
        analysis = {"summary": "总结", "macro": "宏观", "sector": "行业", "emergencyEvents": []}
        twitter = {"rumors": [], "media": [], "comments": [], "available": False, "errors": {}}
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                json.dump(cfg, stream)
            cover = os.path.join(directory, "cover.jpg")
            with open(cover, "wb") as stream:
                stream.write(b"image")
            env = {"WECOM_WEBHOOK": "wecom", "FEISHU_WEBHOOK": "feishu"}
            with patch("sys.argv", ["finance_daily_push.py", "--hours", "24"]), \
                 patch.dict(os.environ, env, clear=False), patch.object(m, "HERE", directory), \
                 patch.object(m, "get_trading_status", return_value={**self._status(), "is_post_holiday": True}), \
                 patch.object(m, "fetch_quotes", return_value=[]), \
                 patch("scrapers.money_flow_scraper.MoneyFlowScraper", return_value=flow), \
                 patch.object(m, "collect_blogger_views", return_value=[]), \
                 patch("scrapers.twitter_scraper.fetch_twitter_categorized", return_value=twitter), \
                 patch.object(m, "fetch_finance_items", return_value={"domestic": self._items()["domestic"], "international": []}), \
                 patch.object(m, "identify_breaking_news", return_value=[]), \
                 patch.object(m, "generate_analysis", return_value=analysis), \
                 patch.object(m, "generate_strategy", side_effect=RuntimeError("strategy")), \
                 patch.object(m, "push_wecom_news_card", return_value={"errcode": 1}), \
                 patch.object(m, "push_feishu_markdown", return_value={"code": 0}), \
                 patch("wechat_content_formatter.format_finance_daily_for_wechat", return_value=("T", "C", "D")), \
                 patch("cover_generator.get_or_create_cover", return_value=cover), \
                 patch("wechat_official.publish_to_wechat", return_value="pub-1"):
                self._copy_template(directory)
                m.main()

    def test_finance_main_auto_window_analysis_fallback_and_all_push_paths(self):
        m = self.module
        analysis = {"summary": "总结", "macro": "宏观", "sector": "行业", "emergencyEvents": []}
        items = self._items()
        flow = MagicMock()
        flow.fetch_north_flow.return_value = {"available": False}
        flow.fetch_sector_flow.return_value = {"top_inflow": []}
        flow.fetch_stock_flow.return_value = {"top_inflow": []}
        base = {
            "fetch_quotes": lambda: [],
            "collect_blogger_views": lambda *args, **kwargs: [],
            "fetch_finance_items": lambda hours=24: items,
        }
        for days in (2, 1):
            with self.subTest(days=days), tempfile.TemporaryDirectory() as directory:
                with patch("sys.argv", ["finance_daily_push.py"]), patch.object(m, "HERE", directory), \
                     patch.object(m, "get_trading_status", return_value=self._status(days)), \
                     patch.object(m, "fetch_quotes", return_value=[]), \
                     patch("scrapers.money_flow_scraper.MoneyFlowScraper", return_value=flow), \
                     patch.object(m, "collect_blogger_views", return_value=[]), \
                     patch("scrapers.twitter_scraper.fetch_twitter_categorized", return_value={"rumors": [], "media": [], "comments": [], "available": True, "errors": {}}), \
                     patch.object(m, "fetch_finance_items", return_value=items), \
                     patch.object(m, "translate_finance_items"), patch.object(m, "identify_breaking_news", return_value=[]), \
                     patch.object(m, "generate_analysis", side_effect=RuntimeError("analysis")), \
                     patch.object(m, "generate_strategy", side_effect=RuntimeError("strategy")):
                    self._copy_template(directory)
                    m.main()
                    self.assertTrue(os.path.exists(os.path.join(directory, "finance_dashboard.html")))

        for target, env in (("push_markdown", {"WECOM_WEBHOOK": "hook"}),
                            ("push_feishu_markdown", {"FEISHU_WEBHOOK": "hook"})):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                with patch("sys.argv", ["finance_daily_push.py", "--hours", "24"]), \
                     patch.dict(os.environ, env, clear=True), patch.object(m, "HERE", directory), \
                     patch.object(m, "get_trading_status", return_value=self._status()), \
                     patch.object(m, "fetch_quotes", return_value=[]), \
                     patch("scrapers.money_flow_scraper.MoneyFlowScraper", return_value=flow), \
                     patch.object(m, "collect_blogger_views", return_value=[]), \
                     patch("scrapers.twitter_scraper.fetch_twitter_categorized", return_value={"rumors": [], "media": [], "comments": [], "available": True, "errors": {}}), \
                     patch.object(m, "fetch_finance_items", return_value=items), patch.object(m, "translate_finance_items"), \
                     patch.object(m, "identify_breaking_news", return_value=[]), patch.object(m, "generate_analysis", return_value=analysis), \
                     patch.object(m, "generate_strategy", return_value={"aShare": "A", "hkShare": "H", "risk": "R"}), \
                     patch.object(m, target, return_value={"errcode": 0}) as sender:
                    self._copy_template(directory)
                    m.main()
                    sender.assert_called_once()

        with tempfile.TemporaryDirectory() as directory:
            with patch("sys.argv", ["finance_daily_push.py", "--hours", "24"]), \
                 patch.dict(os.environ, {"WECOM_WEBHOOK": "hook"}, clear=True), patch.object(m, "HERE", directory), \
                 patch.object(m, "get_trading_status", return_value=self._status()), patch.object(m, "fetch_quotes", return_value=[]), \
                 patch("scrapers.money_flow_scraper.MoneyFlowScraper", return_value=flow), patch.object(m, "collect_blogger_views", return_value=[]), \
                 patch("scrapers.twitter_scraper.fetch_twitter_categorized", return_value={"rumors": [], "media": [], "comments": [], "available": True, "errors": {}}), \
                 patch.object(m, "fetch_finance_items", return_value=items), patch.object(m, "translate_finance_items"), \
                 patch.object(m, "identify_breaking_news", return_value=[]), patch.object(m, "generate_analysis", return_value=analysis), \
                 patch.object(m, "generate_strategy", return_value={"aShare": "A", "hkShare": "H", "risk": "R"}), \
                 patch.object(m, "push_wecom_news_card", side_effect=RuntimeError("push")):
                self._copy_template(directory)
                m.main()

    def test_finance_main_wechat_missing_cover_and_format_errors(self):
        m = self.module
        config = {"wechat_official": {"enabled": True, "appid": "app", "appsecret": "secret"}}
        items = self._items()
        flow = MagicMock()
        flow.fetch_north_flow.return_value = {"available": False}
        flow.fetch_sector_flow.return_value = {"top_inflow": []}
        flow.fetch_stock_flow.return_value = {"top_inflow": []}
        def run(directory, formatter=None, cover=None, default=None):
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                json.dump(config, stream)
            with patch("sys.argv", ["finance_daily_push.py", "--hours", "24"]), patch.object(m, "HERE", directory), \
                 patch.dict(os.environ, {}, clear=True), patch.object(m, "get_trading_status", return_value=self._status()), \
                 patch.object(m, "fetch_quotes", return_value=[]), patch("scrapers.money_flow_scraper.MoneyFlowScraper", return_value=flow), \
                 patch.object(m, "collect_blogger_views", return_value=[]), patch("scrapers.twitter_scraper.fetch_twitter_categorized", return_value={"rumors": [], "media": [], "comments": [], "available": True, "errors": {}}), \
                 patch.object(m, "fetch_finance_items", return_value=items), patch.object(m, "translate_finance_items"), \
                 patch.object(m, "identify_breaking_news", return_value=[]), patch.object(m, "generate_analysis", return_value={"summary": "s", "macro": "m", "sector": "s", "emergencyEvents": []}), \
                 patch.object(m, "generate_strategy", return_value={"aShare": "A", "hkShare": "H", "risk": "R"}), \
                 patch("wechat_content_formatter.format_finance_daily_for_wechat", side_effect=formatter or RuntimeError("format")), \
                 patch("cover_generator.get_or_create_cover", return_value=cover or ""), \
                 patch("cover_generator.create_default_cover", return_value=default or ""), \
                 patch("wechat_official.publish_to_wechat", return_value=None):
                self._copy_template(directory)
                m.main()
        with tempfile.TemporaryDirectory() as directory:
            run(directory, formatter=RuntimeError("format"))
        with tempfile.TemporaryDirectory() as directory:
            run(directory, formatter=("T", "C", "D"), cover="", default="")

