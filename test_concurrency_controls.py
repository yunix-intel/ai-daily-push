#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import threading
import unittest
from unittest.mock import patch


class TestConcurrentFetcherBudgets(unittest.TestCase):
    def test_rss_deadline_returns_without_waiting_for_hung_task(self):
        from concurrent_fetcher import ConcurrentFetcher

        def fetch(name, url, limit):
            if name == "slow":
                time.sleep(2)
            return [{"title": name}]

        start = time.monotonic()
        result = ConcurrentFetcher(max_workers=2, timeout=1, max_retries=1, deadline=0.2).fetch_rss_concurrent(
            [("slow", "u1"), ("fast", "u2")], fetch
        )
        self.assertLess(time.monotonic() - start, 1.2)
        self.assertEqual(result, [])

    def test_url_results_preserve_input_keys_after_deadline(self):
        from concurrent_fetcher import ConcurrentFetcher

        def fetch(url):
            if url == "slow":
                time.sleep(2)
            return {"ok": url}

        result = ConcurrentFetcher(max_workers=2, timeout=1, max_retries=1, deadline=0.2).fetch_urls_concurrent(
            ["slow", "fast"], fetch
        )
        self.assertEqual(list(result), ["slow", "fast"])
        self.assertIn("error", result["slow"])


class TestLLMModelRouting(unittest.TestCase):
    def test_llm_helpers_uses_analysis_semaphore_for_analysis_model(self):
        import importlib
        import llm_helpers
        llm_helpers = importlib.reload(llm_helpers)
        calls = []

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                payload = {"choices": [{"message": {"content": '{"ok": true}'}}]}
                import json
                return json.dumps(payload).encode("utf-8")

        class Marker:
            def __init__(self, name):
                self.name = name
            def __enter__(self):
                calls.append(self.name)
            def __exit__(self, *args):
                return False

        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "k",
            "OPENAI_BASE_URL": "https://example.invalid/v1",
            "OPENAI_MODEL_TRANSLATE": "deepseek-v4-flash",
            "OPENAI_MODEL_ANALYSIS": "gpt-5.6-sol",
        }, clear=False), \
             patch.object(llm_helpers, "_DEEPSEEK_SEMAPHORE", Marker("deepseek")), \
             patch.object(llm_helpers, "_ANALYSIS_SEMAPHORE", Marker("analysis")), \
             patch("urllib.request.urlopen", return_value=FakeResponse()):
            self.assertEqual(llm_helpers.call_llm_json("s", "u", model="gpt-5.6-sol"), {"ok": True})
            self.assertEqual(llm_helpers.call_llm_json("s", "u", model="deepseek-v4-flash"), {"ok": True})

        self.assertEqual(calls, ["analysis", "deepseek"])


class TestBreakingNewsHeuristic(unittest.TestCase):
    def test_none_callback_uses_heuristic_without_calling_llm(self):
        from news_classifier import identify_breaking_news
        result = identify_breaking_news([{"title": "突发：重要公司违约", "summary": "市场承压"}], None)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["direction"], "待确认")


if __name__ == "__main__":
    unittest.main(verbosity=2)
