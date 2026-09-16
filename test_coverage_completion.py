#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic tests for production branches not reached by the core suite."""

import json
import os
import sys
import tempfile
import unittest
import builtins
import importlib.util
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch


class FakeResponse:
    def __init__(self, payload, encoding="utf-8"):
        self.body = payload if isinstance(payload, bytes) else payload.encode(encoding)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class TestFinanceCoverageCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import finance_daily_push
        cls.m = finance_daily_push

    def setUp(self):
        self.env = {
            name: os.environ.pop(name, None)
            for name in (
                "OPENAI_API_KEY", "OPENAI_BASE_URL", "TRANSLATION_ENABLED",
                "CRON_HOUR", "CRON_MINUTE", "WECOM_WEBHOOK", "FEISHU_WEBHOOK",
                "WECHAT_APPID", "WECHAT_APPSECRET",
            )
        }

    def tearDown(self):
        for name, value in self.env.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value

    def test_quote_realtime_fallback_and_malformed_chunks(self):
        m = self.m
        closed = [{"name": "上证", "price": 1, "change": 0, "pct": 0, "as_of": "2026-09-08"}]
        with patch.object(m, "is_trading_hour", return_value=False), \
             patch.object(m, "_fetch_last_close_quotes", return_value=closed):
            self.assertIs(m.fetch_quotes(), closed)

        valid = ["x", "", "x", "100"] + ["x"] * 27 + ["2", "3"]
        invalid = ["x", "坏数据", "x", "not-number"] + ["x"] * 27 + ["2", "3"]
        text = ";".join((
            "without equals",
            'v_short="x~y"',
            'v_bad="' + "~".join(invalid) + '"',
            'v_sh000001="' + "~".join(valid) + '"',
        ))
        with patch.object(m, "is_trading_hour", side_effect=RuntimeError("clock")), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(text)):
            quotes = m.fetch_quotes()
        self.assertEqual(quotes[0]["name"], "上证指数")
        self.assertEqual(quotes[0]["pct"], 3.0)

    def test_dates_category_scoring_and_source_shapes(self):
        m = self.m
        with patch.object(m, "parsedate_to_datetime", return_value=None):
            self.assertIsNone(m._published_dt("date"))
        naive = datetime(2026, 9, 8, 1, 2)
        with patch.object(m, "parsedate_to_datetime", return_value=naive):
            self.assertEqual(m._published_dt("date").tzinfo, timezone.utc)

        self.assertEqual(m.classify_news_category({
            "title": "国内市场", "summary": "美国背景", "source": "Other"
        }), "domestic")
        self.assertEqual(m.classify_news_category({
            "title": "普通消息", "summary": "", "source": {"name": "财新"}
        }), "domestic")
        self.assertEqual(m.classify_news_category({
            "title": "普通消息", "summary": "", "source": "Other"
        }), "international")
        self.assertFalse(m._looks_english(""))

    def test_collection_source_failure_and_intraday_combinations(self):
        m = self.m
        feeds_zh = [("失败源", "/bad"), ("国内源", "/dom")]
        feeds_en = [("国际源", "https://fixture/en")]
        payloads = {
            "国内源": [
                {"title": "A股政策", "summary": "摘要", "published": ""},
                {"title": "国内盘中", "summary": "摘要", "published": ""},
            ],
            "国际源": [
                {"title": "Federal Reserve decision", "summary": "Global news", "published": ""},
                {"title": "International live", "summary": "Market news", "published": ""},
            ],
        }

        def fetch(source, path, limit=20):
            if source == "失败源":
                raise RuntimeError("offline")
            return payloads[source]

        def intraday(title, summary):
            return title in ("国内盘中", "International live")

        with patch.object(m, "FINANCE_FEEDS_ZH", feeds_zh), \
             patch.object(m, "FINANCE_FEEDS_EN", feeds_en), \
             patch.object(m, "_fetch_rss_with_mirrors", side_effect=fetch), \
             patch("trading_calendar.is_trading_hour", return_value=False), \
             patch("trading_calendar.is_intraday_news", side_effect=intraday):
            result = m.fetch_finance_items(hours=24)
        self.assertEqual(len(result["domestic"]), 1)
        self.assertEqual(len(result["international"]), 1)

    def test_translation_retry_success_summary_only_and_still_english(self):
        m = self.m
        item = {
            "title": "Federal Reserve policy", "summary": "English market summary",
            "isEnglish": True,
        }
        with patch.object(m, "translate_batch_llm", side_effect=[
            {0: ("", "中文摘要")}, {0: ("美联储政策", "中文摘要")}
        ]):
            translated = m.translate_finance_items([item])
        self.assertEqual(translated[0]["title"], "美联储政策")

        item = {
            "title": "Federal Reserve policy", "summary": "English market summary",
            "isEnglish": True,
        }
        with patch.object(m, "translate_batch_llm", side_effect=[
            {0: ("中文标题", "")}, {}
        ]):
            translated = m.translate_finance_items([item])
        self.assertEqual(translated[0]["summary"], "English market summary")

        rows = [{"title": "old", "summary": "old"}]
        self.assertEqual(m._apply_translation(rows, [0], {0: ("", "新摘要")}), set())
        self.assertEqual(rows[0]["summary"], "新摘要")

    def test_llm_json_missing_key_retry_and_text_success(self):
        m = self.m
        with patch.object(m, "_llm_config", return_value=("", "url", "translate", "analysis")):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                m.call_llm_json("system", "user", retries=0)

        config = ("sk-fixture", "https://llm.invalid/v1", "translate", "analysis")
        body = {"choices": [{"message": {"content": " done "}}]}
        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(json.dumps(body))):
            self.assertEqual(m.call_llm_text("system", "user", retries=0), "done")

        with patch.object(m, "_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", side_effect=RuntimeError("down")), \
             patch.object(m.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "down"):
                m.call_llm_json("system", "user", retries=1)
            sleep.assert_called_once_with(3)

    def test_config_reporting_and_translation_rows(self):
        m = self.m
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(m, "HERE", directory), \
             patch.object(m, "_LLM_CONFIG_PRINTED", False), \
             patch.dict(os.environ, {
                 "OPENAI_API_KEY": "fixture-key",
                 "OPENAI_BASE_URL": "https://api.openai.com/v1",
             }, clear=False):
            self.assertEqual(m._llm_config()[0], "fixture-key")

        pairs = [(0, "English title", "English summary")]
        response = {"items": [
            {"id": None, "title": "ignored"},
            {"id": "0", "title": " 中文 ", "summary": " 摘要 "},
        ]}
        with patch.object(m, "call_llm_json", return_value=response):
            self.assertEqual(m.translate_batch_llm(pairs)[0], ("中文", "摘要"))

    def test_strategy_disclaimer_and_blogger_success(self):
        m = self.m
        status = {
            "market_status": "trading", "last_trading_day": date(2026, 9, 4),
            "is_post_holiday": True, "days_since_last_trading": 4,
        }
        with patch.object(m, "_llm_config", return_value=("key", "url", "tr", "analysis")), \
             patch.object(m, "call_llm_json", return_value={
                 "aShare": "A", "hkShare": "H", "risk": "风险"
             }):
            strategy = m.generate_strategy({}, [], status)
        self.assertIn(m.DISCLAIMER, strategy["risk"])

        blogger = {
            "name": "博客用户", "uid": "2",
            "articles": [{"title": "T", "url": "u", "published": "p", "isLive": False}],
        }
        with patch("scrapers.blogger_scraper.BloggerScraper") as scraper_cls, \
             patch.object(m, "generate_blogger_digest", return_value={
                 "viewpoint": " 观点 ", "focus": [" 芯片 ", "", "利率"], "tone": " 中性 "
             }):
            scraper_cls.return_value.fetch_all.return_value = [blogger]
            result = m.collect_blogger_views([{"uid": "2"}])
        self.assertEqual(result[0]["platform"], "blog")
        self.assertEqual(result[0]["viewpoint"], "观点")
        self.assertEqual(result[0]["focus"], ["芯片", "利率"])

    def test_shape_history_formats_must_read_and_window_boundaries(self):
        m = self.m

        class BeforeCron(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 8, 1, 0, tzinfo=timezone.utc)

        must_read = [
            {"title": "", "source": "x"},
            {"title": "重要", "source": "x", "link": "u", "importance_score": 9},
        ]
        with tempfile.TemporaryDirectory() as directory:
            history = os.path.join(directory, "push_history.json")
            with open(history, "w", encoding="utf-8") as stream:
                json.dump({"lastPushTime": "2026-09-01T00:00:00+00:00"}, stream)
            with patch.object(m, "HERE", directory), patch.object(m, "datetime", BeforeCron), \
                 patch.dict(os.environ, {"CRON_HOUR": "23", "CRON_MINUTE": "23"}):
                data = m.shape_finance([], [], [], {}, {}, {}, must_read_domestic=must_read)
            self.assertEqual(data["domestic"]["mustRead"][0]["title"], "重要")
            self.assertIn("2026-09-01", data["meta"]["windowStart"])

            with open(history, "w", encoding="utf-8") as stream:
                json.dump({"unexpected": True}, stream)
            with patch.object(m, "HERE", directory), patch.object(m, "datetime", BeforeCron):
                self.assertEqual(m.shape_finance([], [], [], {}, {}, {}, window_hours=6)["meta"]["total"], 0)

            with open(history, "w", encoding="utf-8") as stream:
                json.dump("bad-format", stream)
            with patch.object(m, "HERE", directory), patch.object(m, "datetime", BeforeCron):
                m.shape_finance([], [], [], {}, {}, {})

            with open(history, "w", encoding="utf-8") as stream:
                stream.write("not-json")
            with patch.object(m, "HERE", directory), patch.object(m, "datetime", BeforeCron):
                m.shape_finance([], [], [], {}, {}, {})

    def test_sparse_markdown_optional_branches(self):
        m = self.m
        base = {
            "meta": {"date": "2026-09-08", "domesticCount": 0, "internationalCount": 0},
            "quotes": [], "domestic": {"sections": []}, "international": {"sections": []},
        }
        holiday = {**base, "strategy": {
            "aShare": "A", "is_post_holiday": True, "holiday_summary": ""
        }}
        body, tail = m.build_finance_markdown(holiday, "")
        self.assertIn("A 股", body)
        self.assertNotIn("港股", body)
        self.assertNotIn("查看财经日报", tail)

        holiday_hk = {**base, "strategy": {
            "hkShare": "H", "is_post_holiday": True, "holiday_summary": ""
        }}
        self.assertIn("港股", m.build_finance_markdown(holiday_hk, "")[0])
        ordinary = {**base, "strategy": {"aShare": "A", "is_trading_day": True}}
        self.assertIn("A 股", m.build_finance_markdown(ordinary, "")[0])
        ordinary_hk = {**base, "strategy": {"hkShare": "H", "is_trading_day": True}}
        self.assertIn("港股", m.build_finance_markdown(ordinary_hk, "")[0])
        no_strategy = {**base, "strategy": {"risk": "R"}}
        self.assertIn("R", m.build_finance_markdown(no_strategy, "")[1])
        self.assertEqual(m._quotes_digest([{"name": "I", "price": 1, "change": 0, "pct": 0}]),
                         "- I：1（+0.00，+0.00%）")


class TestArticleTranslatorCoverageCompletion(unittest.TestCase):
    def test_uncached_failure_and_successful_translation(self):
        from article_translator import ArticleTranslator
        with tempfile.TemporaryDirectory() as directory:
            translator = ArticleTranslator(cache_dir=directory, llm_caller=MagicMock(return_value="译文"))
            self.assertIsNone(translator.load_translation_cache("https://fixture/missing"))
            self.assertFalse(translator.translate_news_item({"title": "missing"}))

            item = {"title": "Article", "link": "https://fixture/article"}
            with patch.object(translator, "fetch_article_content", return_value=None):
                self.assertFalse(translator.translate_news_item(item))
            with patch.object(translator, "fetch_article_content", return_value="original" * 50), \
                 patch.object(translator, "save_translation_cache") as save:
                self.assertTrue(translator.translate_news_item(item))
            self.assertEqual(item["translated_content"], "译文")
            save.assert_called_once()

    def test_html_cleanup_and_partial_chunk_failure(self):
        from article_translator import ArticleTranslator
        with tempfile.TemporaryDirectory() as directory:
            translator = ArticleTranslator(cache_dir=directory)
            html = "<body><script>bad</script><article>" + ("word " * 60) + "</article></body>"
            response = MagicMock(content=html.encode(), encoding="utf-8", apparent_encoding="utf-8")
            response.raise_for_status.return_value = None
            with patch("article_translator.requests.get", return_value=response):
                content = translator.fetch_article_content("https://fixture/article")
            self.assertNotIn("bad", content)

            translator.llm_caller = MagicMock(side_effect=[RuntimeError("first"), "译文二"])
            with patch.dict(os.environ, {"LLM_ARTICLE_ATTEMPTS": "1"}), \
                 patch("article_translator.time.sleep"):
                translated = translator.translate_article("a" * 1000 + "\n\n" + "b" * 2500)
            self.assertEqual(translated, "a" * 1000 + "\n\n译文二")

    def test_batch_limits_attempts_and_success(self):
        from article_translator import ArticleTranslator, batch_translate_articles
        candidates = [
            {"title": f"English article {i}", "summary": "long summary " * 12,
             "link": f"https://example.org/{i}", "region": "international",
             "importance_score": 10 - i}
            for i in range(5)
        ]
        with patch.object(ArticleTranslator, "translate_news_item", side_effect=[False, False, True, True]):
            self.assertEqual(batch_translate_articles(candidates, MagicMock(), max_count=1), 1)
        with patch.object(ArticleTranslator, "translate_news_item", side_effect=[True, True]):
            self.assertEqual(batch_translate_articles(candidates, MagicMock(), max_count=2), 2)


class TestEnterpriseAuditCoverageCompletion(unittest.TestCase):
    def _write(self, directory, name, content):
        path = os.path.join(directory, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(content)

    def test_audit_issue_positive_paths(self):
        import enterprise_audit as audit
        with tempfile.TemporaryDirectory() as directory:
            self._write(directory, ".gitignore", "push_config.json\n")
            self._write(directory, "requirements.txt", "requests==1\n")
            self._write(directory, "concurrent_fetcher.py", "retry = True\n")
            self._write(directory, "ai_daily_push.py", '"""doc"""\nurl="https://fixture"\nx.open()\nx.read()\ntraceback\nvalidate\n')
            self._write(directory, "finance_daily_push.py", '"""doc"""\nfor x in http:\n    pass\n')
            self._write(directory, "logger.py", "DEBUG INFO WARNING ERROR CRITICAL trace\n")
            self._write(directory, "monitoring.py", "duration success alert webhook health\n")
            self._write(directory, "README.md", "安装 配置 使用\n")
            self._write(directory, "LICENSE", "license\n")
            self._write(directory, "__version__.py", "VERSION='1'\n")
            os.makedirs(os.path.join(directory, ".github", "workflows"))
            os.makedirs(os.path.join(directory, "logs"))
            self._write(directory, "logs/app.log", "sk-" + "a" * 32)
            self._write(directory, "test_one.py", "")
            self._write(directory, "test_two.py", "")
            self._write(directory, "test_three.py", "")
            self._write(directory, "cache.py", "")

            original = os.getcwd()
            os.chdir(directory)
            try:
                security = audit.check_security_issues()
                reliability = audit.check_reliability_issues()
                audit.check_maintainability_issues()
                performance = audit.check_performance_issues()
                compliance = audit.check_compliance_issues()
            finally:
                os.chdir(original)
        self.assertTrue(any("API Key" in issue for issue in security))
        self.assertTrue(any("资源泄露" in issue for issue in reliability))
        self.assertTrue(any("一次性读取" in issue for issue in performance))
        self.assertTrue(any("错误堆栈" in issue for issue in compliance))

    def test_audit_clean_summary_and_critical_count(self):
        import enterprise_audit as audit
        checks = (
            "check_security_issues", "check_reliability_issues",
            "check_observability_issues", "check_maintainability_issues",
            "check_performance_issues", "check_compliance_issues",
        )
        patches = [patch.object(audit, name, return_value=[]) for name in checks]
        entered = [item.start() for item in patches]
        try:
            self.assertTrue(audit.main())
        finally:
            for item in reversed(patches):
                item.stop()

        patches = [patch.object(audit, name, return_value=["❌ critical"] if i == 0 else [])
                   for i, name in enumerate(checks)]
        for item in patches:
            item.start()
        try:
            self.assertFalse(audit.main())
        finally:
            for item in reversed(patches):
                item.stop()


class TestCoverGeneratorCoverageCompletion(unittest.TestCase):
    def test_generation_fallbacks_and_default_types(self):
        import cover_generator as cover
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "cover.jpg")
            with patch.object(cover.os.path, "exists", return_value=True), \
                 patch.object(cover.ImageFont, "truetype", side_effect=OSError("font")), \
                 patch.object(cover.ImageFont, "load_default", return_value=MagicMock()), \
                 patch.object(cover.Image, "new") as image_new, \
                 patch.object(cover.ImageDraw, "Draw") as draw:
                image_new.return_value.save.side_effect = OSError("save")
                self.assertFalse(cover.generate_cover_image("T", "2026-09-08", output))
                self.assertTrue(draw.called)

            with patch.object(cover.Image, "new") as image_new, \
                 patch.object(cover.os.path, "dirname", return_value=directory), \
                 patch.object(cover.os.path, "exists", return_value=False):
                image_new.return_value.save.return_value = None
                result = cover.create_default_cover("ai")
                self.assertTrue(result.endswith("ai_default.jpg"))
                self.assertEqual(image_new.call_args.args[2], (91, 157, 255))

            with patch.object(cover.Image, "new", side_effect=OSError("image")), \
                 patch.object(cover.os.path, "dirname", return_value=directory), \
                 patch.object(cover.os.path, "exists", return_value=False):
                self.assertIsNone(cover.create_default_cover("finance"))

    def test_get_or_create_cover_success_return(self):
        import cover_generator as cover
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(cover.os.path, "dirname", return_value=directory), \
             patch.object(cover.os.path, "exists", return_value=False), \
             patch.object(cover, "generate_cover_image", return_value=True):
            self.assertTrue(cover.get_or_create_cover("2026-09-08", "ai").endswith("ai_daily_20260908.jpg"))


class TestConcurrencyAndMonitorCoverageCompletion(unittest.TestCase):
    def test_concurrent_retries_timeout_and_deadline_defaults(self):
        import concurrent_fetcher as module
        from concurrent.futures import TimeoutError
        from urllib.error import HTTPError, URLError

        fetcher = module.ConcurrentFetcher(max_workers=1, timeout=1, max_retries=1, deadline=1)
        with patch.object(module.time, "sleep") as sleep:
            recoverable = MagicMock(side_effect=[HTTPError("u", 500, "server", {}, None), ["ok"]])
            self.assertEqual(fetcher._fetch_with_retry(recoverable, "n", "u"), ["ok"])
            generic = MagicMock(side_effect=[RuntimeError("one"), "ok"])
            self.assertEqual(fetcher._fetch_with_retry_generic(generic, "u"), "ok")
            self.assertEqual(sleep.call_count, 2)

        with patch.object(fetcher, "_fetch_with_retry_generic", side_effect=TimeoutError):
            result = fetcher.fetch_urls_concurrent(["u1", "u2"], lambda url: url)
        self.assertIn("error", result["u1"])
        self.assertIn("error", result["u2"])

        with patch.object(fetcher, "_fetch_with_retry", side_effect=TimeoutError):
            self.assertEqual(fetcher.fetch_rss_concurrent([("n", "u")], lambda *args: []), [])
        with patch.object(fetcher, "_fetch_with_retry", side_effect=TimeoutError), \
             patch.object(module.time, "monotonic", side_effect=[0, 0]):
            self.assertEqual(fetcher.fetch_rss_concurrent([("n", "u")], lambda *args: [], deadline=1), [])

    def test_local_monitor_delay_missing_timestamps_config_error_and_alert_fallback(self):
        import local_monitor
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(local_monitor, "__file__", os.path.join(directory, "local_monitor.py")):
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                stream.write("not-json")
            self.assertEqual(local_monitor.load_config(), {})

        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        env = {
            "GITHUB_REPOSITORY": "owner/repo", "EXPECTED_RUN_TIME": "00:00",
            "DELAY_THRESHOLD": "0",
        }
        monitor = MagicMock()
        monitor.get_recent_runs.return_value = [{
            "created_at": now.isoformat(), "run_started_at": now.isoformat(),
            "conclusion": "success", "run_number": 1, "html_url": "u",
        }]
        with patch.dict(os.environ, env, clear=True), \
             patch.object(local_monitor, "GitHubMonitor", return_value=monitor), \
             patch.object(local_monitor, "send_alert") as alert:
            self.assertFalse(local_monitor.check_github_actions())
            alert.assert_called_once()

        monitor.get_recent_runs.return_value = [{"created_at": now.isoformat(), "conclusion": "success"}]
        with patch.dict(os.environ, {**env, "DELAY_THRESHOLD": "999999"}, clear=True), \
             patch.object(local_monitor, "GitHubMonitor", return_value=monitor):
            self.assertIsNone(local_monitor.check_github_actions())

        with patch.dict(sys.modules, {"alerting": None}):
            local_monitor.send_alert("WARN", "title", "message", {"key": "value"})
        with patch.object(local_monitor, "check_github_actions", return_value=False), \
             patch("sys.argv", ["local_monitor.py"]):
            self.assertEqual(local_monitor.main(), 1)


class TestAnalyzerCoverageCompletion(unittest.TestCase):
    def test_market_aggregator_success_merge_and_fallbacks(self):
        from analyzers.market_data_aggregator import MarketDataAggregator
        aggregator = MarketDataAggregator()
        metrics = {"revenue": [], "funding": [], "users": [], "token_usage": [], "price_changes": []}
        aggregator.metrics_extractor.extract_metrics = MagicMock(return_value=metrics)
        with patch("analyzers.market_data_aggregator.fetch_openrouter_data", return_value={
                "date": "d", "total_models": 2,
                "rankings": [{"model": "M", "price_per_1m_tokens": 1}],
                "pricing": [{"price_per_1m_tokens": 1}, {"price_per_1m_tokens": 3}],
             }), patch("analyzers.market_data_aggregator.fetch_aa_data", return_value={
                "date": "d", "intelligence": [], "speed": [], "cost": []}):
            result = aggregator.aggregate([{"title": "news"}])
        self.assertEqual(result["market_trends"]["pricing_summary"]["avg_price"], 2.0)

        with patch.object(aggregator, "_merge_data", side_effect=RuntimeError("merge")), \
             patch("analyzers.market_data_aggregator.fetch_openrouter_data", return_value={}), \
             patch("analyzers.market_data_aggregator.fetch_aa_data", return_value={}):
            self.assertEqual(aggregator.aggregate()["market_trends"]["total_models"], 0)

        with patch.object(aggregator, "_cross_validate", side_effect=RuntimeError("cross")), \
             patch("analyzers.market_data_aggregator.fetch_openrouter_data", return_value={}), \
             patch("analyzers.market_data_aggregator.fetch_aa_data", return_value={}):
            self.assertEqual(aggregator.aggregate()["cross_validation"], {"confirmed": [], "unconfirmed": []})
        self.assertTrue(aggregator._fuzzy_match_model("GPT4", "GPT5", threshold=0.5))

    def test_market_formatter_individual_empty_paths(self):
        from analyzers.market_report_formatter import MarketReportFormatter
        formatter = MarketReportFormatter()
        self.assertIsNone(formatter._format_news_metrics({}))
        self.assertIsNone(formatter._format_market_trends({}))
        self.assertIsNone(formatter._format_performance({}))
        self.assertIsNotNone(formatter._format_cross_validation({}))


class TestFinanceEntrypointCoverageCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import finance_daily_push
        cls.m = finance_daily_push

    def test_import_fallbacks_and_stdout_reconfigure_failure(self):
        source = os.path.join(os.path.dirname(__file__), "finance_daily_push.py")
        real_import = builtins.__import__

        class Stream:
            def reconfigure(self, **kwargs):
                raise RuntimeError("encoding")

        def blocked(name, globals=None, locals=None, fromlist=(), level=0):
            if name in ("monitor_decorator", "monitoring", "logger"):
                raise ImportError("fixture")
            return real_import(name, globals, locals, fromlist, level)

        spec = importlib.util.spec_from_file_location("finance_daily_import_fallback_fixture", source)
        module = importlib.util.module_from_spec(spec)
        with patch("builtins.__import__", side_effect=blocked), \
             patch.object(sys, "stdout", Stream()), patch.object(sys, "stderr", Stream()):
            spec.loader.exec_module(module)
        self.assertFalse(module.MONITORING_AVAILABLE)
        self.assertEqual(module.monitor_task("x")(lambda: 1)(), 1)

    def test_quote_config_blogger_and_pretranslation_paths(self):
        m = self.m
        fields = ["x", "", "x", "bad"] + ["x"] * 27 + ["bad", "bad"]
        payload = 'v_sh000001="' + "~".join(fields) + '";'
        with patch.object(m, "is_trading_hour", return_value=True), \
             patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(payload)):
            self.assertEqual(m.fetch_quotes(), [])

        with patch("article_translator.batch_translate_articles") as batch, \
             patch.object(m, "_llm_config", return_value=("k", "u", "t", "analysis")), \
             patch.object(m, "call_llm_text", return_value="translated"):
            batch.side_effect = lambda items, llm_caller, max_count: (
                1 if llm_caller("s", "u") == "translated" else 0
            )
            m.pre_translate_articles([{"title": "T"}])
        batch.assert_called_once()
        with patch("article_translator.batch_translate_articles", side_effect=RuntimeError("bad")):
            m.pre_translate_articles([])

        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                stream.write("bad-json")
            with patch.object(m, "HERE", directory), patch.object(m, "_LLM_CONFIG_PRINTED", True), \
                 patch.dict(os.environ, {}, clear=True):
                self.assertEqual(m._llm_config()[0], "")
        self.assertEqual(m.collect_blogger_views([]), [])

    def _run_main(self, directory, env=None, config=None, dashboard=False, twitter_driver=None):
        m = self.m
        if config is not None:
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                json.dump(config, stream)
        template = os.path.join(directory, "finance_dashboard_template.html")
        with open(template, "w", encoding="utf-8") as stream:
            stream.write("<script>const DATA=__DATA_PLACEHOLDER__;</script>")
        domestic = {"title": "A股政策", "summary": "摘要", "link": "u", "source": "F"}
        argv = ["finance_daily_push.py", "--hours", "24"]
        if dashboard:
            argv += ["--dashboard-url", "https://fixture.invalid/finance"]
        twitter_driver = twitter_driver or (lambda caller: {"available": True})

        def twitter_fetch(caller, **kwargs):
            return twitter_driver(caller)

        status = {"market_status": "trading", "last_trading_day": date(2026, 9, 8),
                  "is_post_holiday": False, "days_since_last_trading": 1}
        analysis = {"summary": "分析", "macro": "", "sector": "", "emergencyEvents": []}
        with patch("sys.argv", argv), patch.dict(os.environ, env or {}, clear=True), \
             patch.object(m, "HERE", directory), patch.object(m, "fetch_quotes", return_value=[]), \
             patch.object(m, "collect_blogger_views", return_value=[]), \
             patch.object(m, "fetch_finance_items", return_value={"domestic": [domestic], "international": []}), \
             patch.object(m, "identify_breaking_news", return_value=[]), \
             patch.object(m, "generate_analysis", return_value=analysis), \
             patch.object(m, "generate_strategy", return_value={"risk": "risk"}), \
             patch.object(m, "get_trading_status", return_value=status), \
             patch.object(m, "format_date_cn", return_value="2026-09-08"), \
             patch.object(m, "_llm_config", return_value=("k", "u", "t", "a")), \
             patch("scrapers.money_flow_scraper.MoneyFlowScraper", side_effect=ImportError("fixture")), \
             patch("scrapers.twitter_scraper.fetch_twitter_categorized", side_effect=twitter_fetch):
            m.main()

    def test_main_import_twitter_no_push_and_delivery_branches(self):
        m = self.m
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m, "push_feishu_markdown", side_effect=RuntimeError("feishu")):
                self._run_main(directory, env={"FEISHU_WEBHOOK": "hook"}, dashboard=True,
                               twitter_driver=lambda caller: {"rumors": [caller("s", "u")], "available": True})

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m, "call_llm_json", return_value={"ok": True}):
                self._run_main(directory, env={"FEISHU_WEBHOOK": "hook"}, dashboard=True,
                               twitter_driver=lambda caller: {"media": [caller("s", "u")], "available": True})

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m, "call_llm_json", return_value="text"):
                self._run_main(directory, env={"FEISHU_WEBHOOK": "hook"}, dashboard=True,
                               twitter_driver=lambda caller: {"comments": [caller("s", "u")], "available": True})

        with tempfile.TemporaryDirectory() as directory:
            self._run_main(directory, twitter_driver=lambda caller: {
                "media": [caller("s", "u")], "available": True
            })

        with tempfile.TemporaryDirectory() as directory:
            self._run_main(directory, twitter_driver=lambda caller: {
                "comments": [caller("s", "u")], "available": True
            })

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(m, "call_llm_json", side_effect=RuntimeError("llm")):
                self._run_main(directory, twitter_driver=lambda caller: {
                    "comments": [caller("s", "u")], "available": True
                })

    def test_main_wechat_default_cover_unavailable_and_missing_credentials(self):
        m = self.m
        import cover_generator
        import wechat_content_formatter
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(wechat_content_formatter, "format_finance_daily_for_wechat", return_value=("T", "C", "D")), \
             patch.object(cover_generator, "get_or_create_cover", return_value=""), \
             patch.object(cover_generator, "create_default_cover", return_value=""):
            self._run_main(directory, config={"wechat_official": {
                "enabled": True, "appid": "app", "appsecret": "secret"
            }})
        with tempfile.TemporaryDirectory() as directory:
            self._run_main(directory, config={"wechat_official": {"enabled": True}})


class TestAIDailyCoverageCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ai_daily_push
        cls.m = ai_daily_push

    def test_llm_translation_control_flow_and_helpers(self):
        m = self.m
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "push_config.json"), "w", encoding="utf-8") as stream:
                stream.write("not-json")
            with patch.object(m, "HERE", directory), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(m._ai_llm_config()[0], "")

        config = ("key", "https://fixture.invalid/v1", "model")
        body = {"choices": [{"message": {"content": "{}"}}]}
        with patch.object(m, "_ai_llm_config", return_value=config), \
             patch.object(m.urllib.request, "urlopen", side_effect=[RuntimeError("once"), FakeResponse(json.dumps(body))]), \
             patch.object(m.time, "sleep") as sleep:
            self.assertEqual(m.call_ai_llm_json("s", "u", retries=1), {})
        sleep.assert_called_once_with(3)

        report = {"sections": [{"items": [{"title": "中文", "summary": "摘要"}]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}), \
             patch.object(m, "_ai_llm_config", return_value=("", "u", "m")):
            self.assertIs(m.translate_items(report), report)

        report = {"sections": [{"items": [
            {"title": "English one", "summary": "English summary"},
            {"title": "English two", "summary": "English summary"},
        ]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}), \
             patch.object(m, "_ai_llm_config", return_value=("key", "u", "m")), \
             patch.object(m, "translate_batch_llm_ai", side_effect=[
                 {99: ("ignored", "ignored"), 0: ("", "中文摘要")},
                 {0: ("中文标题", ""), 1: ("中文标题二", "中文摘要二")},
             ]):
            m.translate_items(report)
        self.assertEqual(report["sections"][0]["items"][0]["title"], "中文标题")

        report = {"sections": [{"items": [
            {"title": "English one", "summary": "English summary"},
            {"title": "English two", "summary": "English summary"},
        ]}]}
        responses = iter(["标题一", "摘要一", RuntimeError("title"), RuntimeError("summary")])

        def translate(value):
            result = next(responses)
            if isinstance(result, Exception):
                raise result
            return result

        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}), \
             patch.object(m, "_ai_llm_config", return_value=("", "u", "m")), \
             patch.object(m, "translate_text", side_effect=translate), patch.object(m.time, "sleep"):
            m.translate_items(report, give_up_after=1)
        self.assertEqual(report["sections"][0]["items"][0]["title"], "标题一")
        self.assertEqual(m._truncate_by_bytes("abc", 0), "")
        self.assertEqual(m.truncate_bytes("abcdef", 100), "abcdef")
        self.assertTrue(m.truncate_bytes("abcdef", 5))

    def test_shape_page_translation_and_remaining_format_branches(self):
        m = self.m
        report = {"date": "2026-09-08", "sections": [{"label": "AI", "items": [
            {"title": "中文标题", "originalTitle": "English title", "summary": "摘要",
             "source": {"name": "Fixture"}, "links": {"original": "https://fixture.invalid/article"}},
            {"title": "中文二", "originalTitle": "English two", "summary": "摘要二",
             "source": {"name": "Fixture"}, "links": {"original": "https://fixture.invalid/two"}},
        ]}]}
        with patch.dict(os.environ, {"FULL_TEXT_TRANSLATION_ENABLED": "1"}), \
             patch.object(m, "translate_page_with_llm", side_effect=["translated.html", RuntimeError("bad")]):
            shaped = m.shape(report)
        self.assertEqual(shaped["sections"][0]["items"][0]["translatedPage"], "translated.html")
        self.assertEqual(shaped["sections"][0]["items"][1]["translatedPage"], "")
        self.assertIn("English:", m.build_markdown(shaped, ""))

        page = MagicMock(content=b"<html></html>")
        page.raise_for_status.return_value = None
        with patch("requests.get", return_value=page):
            self.assertIsNone(m.translate_page_with_llm("https://fixture.invalid/no-body", "T"))
        page.content = ("<body><p>" + "long paragraph " * 20 + "</p></body>").encode()
        with patch("requests.get", return_value=page), patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(m.translate_page_with_llm("https://fixture.invalid/no-key", "T"))
        page.content = ("<body><script>x</script><p>" + "long paragraph " * 20 + "</p></body>").encode()
        posted = MagicMock(status_code=503)
        with patch("requests.get", return_value=page), patch("requests.post", return_value=posted), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "key"}, clear=True), \
             patch.object(m.time, "monotonic", side_effect=[0, 0, 0]), patch.object(m.time, "sleep"):
            self.assertIsNone(m.translate_page_with_llm("https://fixture.invalid/non-200", "T"))

        self.assertEqual(m._format_trend_cards({"ranking_trends": []}), [])
        self.assertEqual(m._score_importance("nothing", ""), 0)
        picked = m.pick_highlights([
            ({"idx": 1, "title": "same title", "source": "x"}, ""),
            ({"idx": 2, "title": "same title", "source": "x"}, ""),
            ({"idx": 3, "title": "different", "source": "x"}, ""),
        ], top_n=1)
        self.assertEqual(len(picked), 1)

    def test_ai_remaining_exception_and_loop_paths(self):
        m = self.m

        class Stream:
            def reconfigure(self, **kwargs):
                raise RuntimeError("encoding")

        source = os.path.join(os.path.dirname(__file__), "ai_daily_push.py")
        spec = importlib.util.spec_from_file_location("ai_daily_push_stream_fixture", source)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "stdout", Stream()), patch.object(sys, "stderr", Stream()):
            spec.loader.exec_module(module)

        with patch.object(m, "_ai_llm_config", return_value=("key", "https://fixture.invalid", "model")), \
             patch.object(m.urllib.request, "urlopen", side_effect=RuntimeError("all")):
            with self.assertRaisesRegex(RuntimeError, "all"):
                m.call_ai_llm_json("s", "u", retries=0)

        report = {"sections": [{"items": [{"title": "English", "summary": "Summary"}]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}), \
             patch.object(m, "_ai_llm_config", return_value=("key", "u", "m")), \
             patch.object(m, "translate_batch_llm_ai", return_value={}), \
             patch.object(m, "translate_text", return_value="中文"), patch.object(m.time, "sleep"):
            m.translate_items(report)

        report = {"sections": [{"items": [
            {"title": "English one", "summary": "Summary one"},
            {"title": "English two", "summary": "Summary two"},
        ]}]}
        with patch.dict(os.environ, {"TRANSLATION_ENABLED": "1"}), \
             patch.object(m, "_ai_llm_config", return_value=("", "u", "m")), \
             patch.object(m, "translate_text", side_effect=RuntimeError("limited")), \
             patch.object(m.time, "sleep"):
            m.translate_items(report, give_up_after=1)

        ranked = m.pick_highlights([
            ({"idx": 1, "title": "same title", "source": "x"}, ""),
            ({"idx": 2, "title": "same title", "source": "x"}, ""),
            ({"idx": 3, "title": "different news", "source": "x"}, ""),
        ], top_n=5)
        self.assertEqual(len(ranked), 2)
        self.assertIn("完整版", m.truncate_bytes("a" * 100, 40))

        page = MagicMock(content=("<body><p>" + "long paragraph " * 20 + "</p></body>").encode())
        page.raise_for_status.side_effect = RuntimeError("network")
        with patch("requests.get", return_value=page):
            self.assertIsNone(m.translate_page_with_llm("https://fixture.invalid/fail", "T"))

    def test_push_payload_optional_branches_and_errors(self):
        m = self.m
        with patch.object(m, "http_post_json", return_value={}) as post:
            m.push_wecom_webhook("hook", "markdown")
            self.assertEqual(post.call_args.args[1]["msgtype"], "markdown")
        with patch.object(m, "http_post_json", return_value={}) as post:
            m.push_feishu("hook", "title", "markdown")
            self.assertEqual(len(post.call_args.args[1]["card"]["elements"]), 2)
        with patch.object(m, "http_get", return_value={}):
            with self.assertRaises(RuntimeError):
                m.push_wecom("id", "secret", "1", "user", "md")
        with patch.object(m.urllib.request, "urlopen", return_value=FakeResponse("{}")) as opened:
            m.push_pushplus("token", "md", "title", topic="topic")
            payload = json.loads(opened.call_args.args[0].data.decode())
            self.assertEqual(payload["topic"], "topic")

    def test_optional_import_fallbacks_in_isolated_module(self):
        source = os.path.join(os.path.dirname(__file__), "ai_daily_push.py")
        real_import = builtins.__import__

        def blocked(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "monitor_decorator" or name.startswith("analyzers.market_data"):
                raise ImportError("fixture")
            return real_import(name, globals, locals, fromlist, level)

        spec = importlib.util.spec_from_file_location("ai_daily_push_import_fallback_fixture", source)
        module = importlib.util.module_from_spec(spec)
        with patch("builtins.__import__", side_effect=blocked):
            spec.loader.exec_module(module)
        self.assertFalse(module.MONITORING_AVAILABLE)
        self.assertFalse(module.MARKET_DATA_AVAILABLE)
        self.assertEqual(module.monitor_task("x")(lambda: 1)(), 1)


class TestArtificialAnalysisCoverageCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from scrapers.artificial_analysis_scraper import ArtificialAnalysisScraper
        cls.scraper_class = ArtificialAnalysisScraper

    def test_fetch_parser_fallback_chain_and_public_entrypoint(self):
        module_name = "scrapers.artificial_analysis_scraper"
        scraper = self.scraper_class()
        html = ("<html><body>"
                '<script type="application/ld+json">{"@type": "Dataset", "name": "Speed", "data": ['
                '{"label": "Fast Model (max)", "medianOutputSpeed": 250}]}</script>'
                "</body></html>")
        with (
            patch.object(scraper, "load_cache", return_value=None),
            patch.object(scraper, "save_cache") as save,
            patch(module_name + ".urllib.request.urlopen", return_value=FakeResponse(html)),
        ):
            result = scraper.fetch_benchmarks()
        self.assertEqual(result["speed"][0]["tokens_per_sec"], 250)
        save.assert_called_once()

        with patch(module_name + ".ArtificialAnalysisScraper") as scraper_type:
            scraper_type.return_value.fetch_benchmarks.return_value = {"source": "fixture"}
            from scrapers.artificial_analysis_scraper import fetch_aa_data
            self.assertEqual(fetch_aa_data(), {"source": "fixture"})
    def test_highlight_script_and_table_edge_paths(self):
        scraper = self.scraper_class()
        html = ("<html><head>"
                '<script type="application/ld+json">{"@type": "Dataset", "name": "Intelligence", "data": ['
                '{"label": "Claude Fable 5.1 (max)", "artificialAnalysisIntelligenceIndex": 53.4},'
                '{"label": "Claude Fable 5.1 (max)", "artificialAnalysisIntelligenceIndex": 53.4},'
                '{"label": "Qwen", "artificialAnalysisIntelligenceIndex": 999},'
                '{"label": "Bad", "artificialAnalysisIntelligenceIndex": "high"}'
                "]}</script></head>"
                "<body>Qwen 3 GPT 6</body></html>")
        result = scraper.parse_homepage(html)
        self.assertTrue(result["parsed"])
        self.assertEqual([r["model"] for r in result["intelligence"]],
                         ["Claude Fable 5.1 (max)"])
        self.assertEqual(scraper.parse_homepage("<html></html>")["parsed"], False)
        self.assertFalse(type(scraper)._is_usable_cache({}))
class TestPushHistoryCoverageCompletion(unittest.TestCase):
    def test_history_normalization_and_time_edges(self):
        import push_history_recorder as recorder_module

        self.assertIn("北京时间", recorder_module.format_beijing_time(
            datetime(2026, 9, 8, 1, 2, tzinfo=timezone.utc)))
        self.assertIn("2026-09-08", recorder_module.to_beijing(
            datetime(2026, 9, 8, 1, 2)))
        self.assertIsNone(recorder_module.PushHistoryRecorder._parse_time(None))
        self.assertIsNone(recorder_module.PushHistoryRecorder._parse_time("bad"))
        self.assertEqual(
            recorder_module.PushHistoryRecorder._parse_time("2026-09-08T01:02:03").tzinfo,
            timezone.utc,
        )
        self.assertIsNone(recorder_module.PushHistoryRecorder._normalize_record("bad"))
        self.assertIsNone(recorder_module.PushHistoryRecorder._normalize_record({
            "timestamp": "2026-09-08T00:00:00Z",
            "expected_time": "2026-09-08T01:00:00Z",
        }))
        normalized = recorder_module.PushHistoryRecorder._normalize_record({
            "lastPushTime": "2026-09-08T01:10:00Z",
            "expected_time": "2026-09-08T01:00:00Z",
        })
        self.assertEqual(normalized["schema_version"], 1)
        self.assertEqual(normalized["delay_minutes"], 10.0)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "history.json")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"records": ["bad", normalized]}, stream)
            recorder = recorder_module.PushHistoryRecorder(path)
            self.assertEqual(len(recorder.history), 1)
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"unexpected": True}, stream)
            self.assertEqual(recorder_module.PushHistoryRecorder(path).history, [])
            with open(path, "w", encoding="utf-8") as stream:
                json.dump("bad", stream)
            self.assertEqual(recorder_module.PushHistoryRecorder(path).history, [])
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("not-json")
            self.assertEqual(recorder_module.PushHistoryRecorder(path).history, [])

    def test_record_rollover_save_failure_report_and_main_modes(self):
        import push_history_recorder as recorder_module

        base = datetime(2026, 9, 8, 0, 30, tzinfo=timezone.utc)
        previous = recorder_module.PushHistoryRecorder._resolve_expected_dt(base, "23:00")
        following = recorder_module.PushHistoryRecorder._resolve_expected_dt(
            datetime(2026, 9, 9, 13, 0, tzinfo=timezone.utc), "00:00")
        self.assertEqual(previous.date().isoformat(), "2026-09-07")
        self.assertEqual(following.date().isoformat(), "2026-09-10")

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "history.json")
            recorder = recorder_module.PushHistoryRecorder(path)
            record = recorder.record_push(
                expected_time="23:00", task_name="fixture",
                delivery_completed_at=datetime(2026, 9, 8, 23, 10),
                event_created_at=datetime(2026, 9, 8, 23, 1),
                runner_started_at=datetime(2026, 9, 8, 23, 2),
                pipeline_completed_at=datetime(2026, 9, 8, 23, 11),
            )
            self.assertEqual(record["schema_version"], 2)
            recorder.history = [{**record, "delay_seconds": 601, "delay_minutes": 10.0},
                                {**record, "delay_seconds": 301, "delay_minutes": 5.0},
                                record]
            recorder._build_html(3, 401, 601, 1, recorder.history)
            with patch("builtins.open", side_effect=OSError("fixture")):
                recorder._save_history()
            recorder.history = []
            recorder.generate_report(os.path.join(directory, "empty.html"))
            recorder.history = [record]
            output = os.path.join(directory, "report.html")
            recorder.generate_report(output)
            self.assertTrue(os.path.exists(output))

        with patch("sys.argv", ["push_history_recorder.py", "--no-record", "--report", "fixture.html"]):
            with patch.object(recorder_module, "PushHistoryRecorder") as cls:
                cls.return_value.history = []
                recorder_module.main()
                cls.return_value.generate_report.assert_called_once_with(output_file="fixture.html")

        instance = MagicMock()
        instance._parse_time.return_value = None
        with patch("push_history_recorder.PushHistoryRecorder", return_value=instance), \
             patch("sys.argv", ["push_history_recorder.py", "--report", "fixture.html"]):
            recorder_module.main()
        instance.record_push.assert_called_once()


class TestGitHubMonitorCoverageCompletion(unittest.TestCase):
    def test_parse_resolve_states_and_report_rows(self):
        import github_monitor as module

        self.assertIsNone(module.parse_github_time(None))
        self.assertIsNone(module.parse_github_time("invalid"))
        self.assertEqual(module.parse_github_time("2026-09-08T01:02:03").tzinfo, timezone.utc)
        self.assertEqual(
            module.resolve_expected_utc(datetime(2026, 9, 9, 22, 59), "23:00").hour,
            23,
        )
        self.assertEqual(
            module.resolve_expected_utc(datetime(2026, 9, 9, 23, 20), "23:00").date(),
            date(2026, 9, 9),
        )
        self.assertIsNone(module._duration(None, datetime.now(timezone.utc)))
        self.assertIsNone(module._duration(
            datetime(2026, 9, 8, tzinfo=timezone.utc),
            datetime(2026, 9, 9, tzinfo=timezone.utc),
        ))

        monitor = module.GitHubMonitor(repo="owner/repo", workflow_name="Daily")
        with patch.object(monitor, "_http_get", return_value={"workflows": []}):
            self.assertEqual(monitor.get_recent_runs(), [])
        unnamed = module.GitHubMonitor(repo="owner/repo")
        with patch.object(unnamed, "_http_get", return_value={"workflow_runs": {}}):
            self.assertEqual(unnamed.get_recent_runs(), [])

        runs = [
            {"run_number": 1, "event": "schedule", "status": "queued",
             "created_at": "2026-09-08T23:01:00Z"},
            {"run_number": 2, "event": "schedule", "status": "in_progress",
             "created_at": "2026-09-08T23:02:00Z", "run_started_at": "2026-09-08T23:03:00Z"},
            {"run_number": 3, "event": "schedule", "status": "mystery",
             "created_at": "2026-09-08T23:03:00Z"},
            {"run_number": 4, "event": "workflow_dispatch", "status": "completed",
             "created_at": "2026-09-08T23:04:00Z"},
        ]
        states = [monitor._run_timing(run)["state"] for run in runs]
        self.assertEqual(states, ["queued", "in_progress", "mystery", "manual"])
        report = monitor.analyze_delays(runs)
        self.assertEqual(report["queued_count"], 1)
        self.assertEqual(report["in_progress_count"], 1)
        self.assertEqual(report["manual_runs"], 1)
        self.assertEqual(monitor.analyze_delays()["total_runs"], 0)

        html = monitor._build_html_report({
            "scheduled_runs": 1, "manual_runs": 0,
            "average_dispatch_delay_seconds": 0,
            "average_queue_delay_seconds": 0,
            "delays": [{"run_number": 1, "scheduled_at": "", "created_at": "",
                        "dispatch_delay_seconds": None, "queue_delay_seconds": None,
                        "runtime_seconds": None, "state": "queued", "html_url": "u"}],
        })
        self.assertIn("不可用", html)
        self.assertIn("进行中", html)

    def test_evaluate_latest_all_states_and_cli_check(self):
        import github_monitor as module
        monitor = module.GitHubMonitor(repo="owner/repo", workflow_name="Daily")
        before = datetime(2026, 9, 8, 22, 55, tzinfo=timezone.utc)
        self.assertEqual(monitor.evaluate_latest([], 300, before)["state"], "waiting")
        after = datetime(2026, 9, 8, 23, 10, tzinfo=timezone.utc)
        self.assertEqual(monitor.evaluate_latest([], 300, after)["state"], "missing")
        base = "2026-09-08T23:01:00Z"
        def run(status, conclusion=None, number=1):
            return {"run_number": number, "event": "schedule", "status": status,
                    "conclusion": conclusion, "created_at": base,
                    "run_started_at": base, "updated_at": base}
        self.assertTrue(monitor.evaluate_latest([run("completed", "failure")], 300, after)["alert"])
        self.assertEqual(monitor.evaluate_latest([run("queued")], 300, before)["state"], "queued")
        self.assertTrue(monitor.evaluate_latest([run("queued")], 1, after)["alert"])
        self.assertTrue(monitor.evaluate_latest([run("in_progress")], 1, after)["alert"])
        success = monitor.evaluate_latest([run("completed", "success")], 0, after)
        self.assertTrue(success["alert"])

        with patch.object(monitor, "get_recent_runs", return_value=[]), \
             patch.object(monitor, "evaluate_latest", return_value={"state": "missing", "alert": True, "delay_seconds": 1}), \
             patch("alerting.send_alert", side_effect=ImportError):
            self.assertTrue(monitor.check_and_alert(0))
            evaluation = monitor.check_and_alert(0, return_evaluation=True)
            self.assertEqual(evaluation["state"], "missing")
            self.assertTrue(evaluation["alert"])
        with patch.object(monitor, "get_recent_runs", return_value=[]), \
             patch.object(monitor, "evaluate_latest", return_value={"state": "success", "alert": False, "delay_seconds": 0}):
            evaluation = monitor.check_and_alert(0, return_evaluation=True)
            self.assertEqual(evaluation["state"], "success")
            self.assertFalse(evaluation["alert"])
        fake = MagicMock(repo="owner/repo", workflow_name="Daily")
        fake.check_and_alert.return_value = {
            "state": "success", "alert": True, "delay_seconds": 600,
        }
        with patch.object(module, "GitHubMonitor", return_value=fake), \
             patch("sys.argv", ["github_monitor.py", "--repo", "owner/repo", "--check-delay"]):
            self.assertEqual(module.main(), 0)
        fake.check_and_alert.return_value = {
            "state": "missing", "alert": True, "delay_seconds": 600,
        }
        with patch.object(module, "GitHubMonitor", return_value=fake), \
             patch("sys.argv", ["github_monitor.py", "--repo", "owner/repo", "--check-delay"]):
            self.assertEqual(module.main(), 1)
        fake.check_and_alert.return_value = {
            "state": "success", "alert": False, "delay_seconds": 0,
        }
        with patch.object(module, "GitHubMonitor", return_value=fake), \
             patch("sys.argv", ["github_monitor.py", "--repo", "owner/repo", "--check-delay"]):
            self.assertEqual(module.main(), 0)


class TestDeliveryStatusRemainingCoverage(unittest.TestCase):
    def test_default_timestamp_parent_and_non_mapping(self):
        import delivery_status as status
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "status.json")
            with patch.object(status, "datetime") as clock:
                clock.now.return_value = datetime(2026, 9, 8, tzinfo=timezone.utc)
                clock.side_effect = datetime
                payload = status.write_delivery_status(
                    path, "ai", "wecom_webhook", True, True, True)
            self.assertEqual(payload["delivery_completed_at"], "2026-09-08T00:00:00+00:00")
            with open(path, "w", encoding="utf-8") as stream:
                json.dump([], stream)
            with self.assertRaisesRegex(ValueError, "格式无效"):
                status.load_successful_delivery(path)
            payload = status.write_delivery_status(
                path, "ai", "wecom_webhook", True, True, True,
                completed_at="2026-09-08T00:00:00Z")
            self.assertTrue(payload["success"])


class TestBloggerAndMoneyFlowCoverageCompletion(unittest.TestCase):
    def test_blogger_retry_exhaustion_and_empty_body_paths(self):
        from scrapers.blogger_scraper import BloggerScraper
        import scrapers.blogger_scraper as blogger_module

        scraper = BloggerScraper(min_interval=0)
        response = MagicMock(status_code=418)
        error = blogger_module.requests.HTTPError("rate limited", response=response)
        with patch.object(scraper, "_throttle"), \
             patch.object(blogger_module.requests, "get", side_effect=error) as get, \
             patch.object(blogger_module.time, "sleep") as sleep:
            with self.assertRaises(blogger_module.requests.HTTPError):
                scraper._get_soup("https://fixture.invalid", retries=2)
        self.assertEqual(get.call_count, 3)
        sleep.assert_any_call(5)
        sleep.assert_any_call(10)
        with patch.object(scraper, "_get_soup", return_value=MagicMock(select_one=MagicMock(return_value=None))):
            self.assertEqual(scraper.fetch_article_body("https://fixture.invalid"), "")

    def test_money_flow_cache_validation_and_write_failures(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        with tempfile.TemporaryDirectory() as directory:
            scraper = MoneyFlowScraper()
            scraper.cache_path = __import__("pathlib").Path(directory) / "north.json"
            scraper.cache_path.write_text(json.dumps([
                {"available": False, "trade_date": "2026-09-08"},
                {"available": True, "trade_date": "bad-date"},
                {"available": True, "trade_date": "2026-09-10"},
                {"available": True, "trade_date": "2026-09-04", "total_flow": 1},
                {"available": True, "trade_date": "2026-09-08", "total_flow": 2},
            ]), encoding="utf-8")
            cached = scraper._load_cached_north("2026-09-08")
            self.assertEqual(cached["trade_date"], "2026-09-08")
            self.assertTrue(cached["stale"])

            scraper._save_cached_north(None)
            scraper._save_cached_north({"available": False, "trade_date": "2026-09-08"})
            with patch.object(type(scraper.cache_path), "write_text", side_effect=OSError("read-only")):
                scraper._save_cached_north({"available": True, "trade_date": "2026-09-09", "total_flow": 3})

            scraper.cache_path.write_text("not-json", encoding="utf-8")
            scraper._save_cached_north({"available": True, "trade_date": "2026-09-09", "total_flow": 3})
            self.assertIn("2026-09-09", scraper.cache_path.read_text(encoding="utf-8"))

    def test_money_flow_nonfinite_and_parse_error_paths(self):
        from scrapers.money_flow_scraper import MoneyFlowScraper
        scraper = MoneyFlowScraper()
        self.assertEqual(scraper._valid_rank_rows([
            {"f14": "", "f62": "1", "f3": "1", "f184": "1"},
            {"f14": "A", "f62": "NaN", "f3": "1", "f184": "1"},
        ]), [])
        with patch("scrapers.money_flow_scraper.requests.get") as get:
            response = get.return_value
            response.json.return_value = {"data": {"zhuri": {
                "date": ["2026-09-08"], "h": ["NaN"], "total": ["1"]
            }}}
            with self.assertRaisesRegex(ValueError, "有限数值"):
                scraper._fetch_10jqka_post_close("2026-09-08")
        self.assertFalse(scraper._parse_north_flow([])["available"])


class TestAlertingAndMonitoringCoverage(unittest.TestCase):
    def test_alerting_channels_signing_and_http_errors(self):
        import alerting

        with patch.dict(os.environ, {
            "ALERT_WECOM_WEBHOOK": "https://fixture.invalid/wecom",
            "ALERT_DINGTALK_WEBHOOK": "https://fixture.invalid/ding",
            "ALERT_DINGTALK_SECRET": "secret",
            "ALERT_FEISHU_WEBHOOK": "https://fixture.invalid/feishu",
            "ALERT_WEBHOOK": "https://fixture.invalid/custom",
        }, clear=True):
            notifier = alerting.AlertNotifier()
        with patch.object(notifier, "_http_post") as post, \
             patch.object(alerting.time, "time", return_value=1700000000.123):
            self.assertTrue(notifier.send_alert("INFO", "Title", "Message", {"k": "v"}))
            urls = [call.args[0] for call in post.call_args_list]
            self.assertTrue(any("timestamp=1700000000123" in url and "sign=" in url for url in urls))
        disabled = alerting.AlertNotifier()
        disabled.channels = {alerting.NotificationChannel.WECOM: {"enabled": False}}
        self.assertFalse(disabled.send_alert("INFO", "T", "M"))
        empty = alerting.AlertNotifier()
        empty.channels = {}
        self.assertFalse(empty.send_alert("INFO", "T", "M"))
        self.assertEqual(empty._get_emoji("OTHER"), "📢")

        body = __import__("io").BytesIO(b"bad")
        http_error = alerting.urllib.error.HTTPError(
            "https://fixture.invalid", 500, "error", {}, body)
        try:
            with patch.object(alerting.urllib.request, "urlopen", side_effect=http_error):
                with self.assertRaisesRegex(Exception, "HTTP 500"):
                    empty._http_post("https://fixture.invalid", {})
        finally:
            http_error.close()
            body.close()
        with patch.object(alerting.urllib.request, "urlopen",
                          side_effect=alerting.urllib.error.URLError("offline")):
            with self.assertRaisesRegex(Exception, "URL Error"):
                empty._http_post("https://fixture.invalid", {})

        with patch.object(alerting, "_notifier", None), patch.dict(os.environ, {}, clear=True):
            first = alerting.get_notifier()
            self.assertIs(first, alerting.get_notifier())

    def test_monitoring_health_export_and_decorator_paths(self):
        import monitoring

        monitor = monitoring.MonitorMetrics()
        monitor._persist_alert = MagicMock()
        monitor._send_immediate_notification = MagicMock()
        monitor.record_run("unknown", True, 1)
        monitor.record_run("ai_daily", True, 2, items_count=3)
        monitor.record_run("ai_daily", True, 4, items_count=2)
        monitor.record_run("ai_daily", False, 1, error="boom")
        monitor.record_run("finance_daily", False, 1, error="failed")
        monitor.record_data_quality(1, 1)
        monitor.metrics["ai_daily"]["last_run"] = "2020-01-01T00:00:00"
        monitor.metrics["finance_daily"]["last_run"] = "2020-01-01T00:00:00"
        health = monitor.get_health_status()
        self.assertEqual(health["status"], "unhealthy")
        self.assertTrue(health["issues"])
        monitor._send_immediate_notification.assert_called()
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "metrics.json")
            monitor.export_metrics(output)
            with open(output, encoding="utf-8") as stream:
                self.assertIn("metrics", json.load(stream))

        with patch.dict(sys.modules, {"alerting": None}), patch("builtins.print"):
            fallback = monitoring.MonitorMetrics()
            fallback._persist_alert = MagicMock()
            fallback.record_run("ai_daily", False, 1, error="x")
            fallback._send_immediate_notification(fallback.alerts[-1])

        original_monitor = monitoring._monitor
        try:
            monitoring._monitor = monitor
            @monitoring.monitor_function("ai_daily")
            def list_result():
                return [1, 2]
            @monitoring.monitor_function("finance_daily")
            def dict_result():
                return {"items": [1]}
            @monitoring.monitor_function("ai_daily")
            def bad_result():
                raise ValueError("bad")
            self.assertEqual(list_result(), [1, 2])
            self.assertEqual(dict_result()["items"], [1])
            with self.assertRaises(ValueError):
                bad_result()
        finally:
            monitoring._monitor = original_monitor


class TestSmallModuleCoverageCompletion(unittest.TestCase):
    def test_version_accessors_and_module_entrypoint(self):
        import runpy
        import __version__ as version

        self.assertEqual(version.get_version(), version.__version__)
        info = version.get_version_info()
        self.assertEqual(info["version"], version.__version__)
        self.assertEqual(info["version_info"], version.__version_info__)
        self.assertIn("稳定版本", info["description"])
        with patch("builtins.print") as output:
            runpy.run_module("__version__", run_name="__main__")
        self.assertTrue(output.called)

    def test_delivery_status_success_and_validation_errors(self):
        import delivery_status as status

        self.assertIsNone(status._parse_utc(None))
        self.assertIsNone(status._parse_utc("invalid"))
        self.assertEqual(status._parse_utc("2026-09-08T01:02:03").tzinfo, timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "nested", "status.json")
            payload = status.write_delivery_status(
                path, "finance", "wecom_webhook", True, True, True,
                completed_at="2026-09-08T01:02:03Z", reason="fixture",
            )
            self.assertEqual(status.load_successful_delivery(path).year, 2026)
            self.assertEqual(status.latest_successful_delivery([path]),
                             status.load_successful_delivery(path))
            self.assertEqual(payload["reason"], "fixture")

            with self.assertRaisesRegex(ValueError, "未提供推送状态文件"):
                status.latest_successful_delivery([])
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("not-json")
            with self.assertRaisesRegex(ValueError, "不可读"):
                status.load_successful_delivery(path)

            cases = [
                {},
                {"schema_version": 99},
                {"schema_version": 1, "channel": "other"},
                {"schema_version": 1, "channel": "wecom_webhook", "reason": "failed"},
                {"schema_version": 1, "channel": "wecom_webhook", "configured": True,
                 "attempted": True, "success": True},
            ]
            for case in cases:
                with open(path, "w", encoding="utf-8") as stream:
                    json.dump(case, stream)
                with self.assertRaises(ValueError):
                    status.load_successful_delivery(path)

            with open(path, "w", encoding="utf-8") as stream:
                json.dump({"schema_version": 1, "channel": "wecom_webhook",
                           "configured": True, "attempted": True, "success": True,
                           "delivery_completed_at": "2026-09-08T01:02:03Z"}, stream)
            self.assertIsNotNone(status.load_successful_delivery(path))

    def test_delivery_status_defaults_and_unsuccessful_write(self):
        import delivery_status as status

        self.assertIsNone(status.write_delivery_status("", "ai", "wecom_webhook", True, True, True))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "status.json")
            payload = status.write_delivery_status(path, "ai", "wecom_webhook", True, False, False)
            self.assertIsNone(payload["delivery_completed_at"])
            self.assertFalse(payload["success"])
            with self.assertRaisesRegex(ValueError, "未成功"):
                status.load_successful_delivery(path)

    def test_cover_date_and_font_fallback_branches(self):
        import cover_generator as cover

        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "cover.jpg")
            image = MagicMock()
            draw = MagicMock()
            with patch.object(cover.Image, "new", return_value=image), \
                 patch.object(cover.ImageDraw, "Draw", return_value=draw), \
                 patch.object(cover.os.path, "exists", return_value=False), \
                 patch.object(cover.ImageFont, "load_default", return_value=MagicMock()):
                self.assertTrue(cover.generate_cover_image("T", "bad-date", output, "finance"))
                self.assertTrue(cover.generate_cover_image("T", "2026-09-08T00:00:00Z", output, "ai"))
            self.assertEqual(image.save.call_count, 2)


if __name__ == "__main__":
    unittest.main()
