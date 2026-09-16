#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Token 多日序列：只收有效快照，空总量/坏文件静默跳过。"""
import json
import tempfile
import unittest
from pathlib import Path

from analyzers.market_data_aggregator import build_token_history


def snap(date, total, top):
    return {"date": date, "total_weekly_tokens": total,
            "token_usage": [{"model": m, "market_share": s} for m, s in top]}


class TestTokenHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "openrouter_2026-09-14.json").write_text(
            json.dumps(snap("2026-09-14", 70e12, [("A", 30.0), ("B", 20.0)])),
            encoding="utf-8")
        (d / "openrouter_2026-09-15.json").write_text(
            json.dumps(snap("2026-09-15", 0, [])), encoding="utf-8")  # 空快照
        (d / "openrouter_2026-09-16.json").write_text(
            json.dumps(snap("2026-09-16", 80.92e12, [("A", 29.5), ("B", 21.0)])),
            encoding="utf-8")
        (d / "openrouter_2026-09-17.json").write_text("{broken", encoding="utf-8")
        self.dir = d

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_valid_points(self):
        hist = build_token_history(data_dir=self.dir, days=7)
        self.assertEqual([p["date"] for p in hist], ["2026-09-14", "2026-09-16"])
        self.assertEqual(hist[-1]["total_weekly_tokens"], 80.92e12)
        self.assertEqual(hist[-1]["top"][0],
                         {"model": "A", "market_share": 29.5})

    def test_missing_dir_is_empty(self):
        self.assertEqual(
            build_token_history(data_dir=self.dir / "nope", days=7), [])


class TestOpenRouterStaleCache(unittest.TestCase):
    """回归：旧代码快照（无 token 用量）不得直接沿用，必须重抓。

    2026-09-16 线上实证：actions/cache 恢复了凌晨旧代码跑的当日快照，
    fetch 直接返回，Token 块整天隐藏。
    """
    def test_stale_snapshot_triggers_refetch(self):
        from unittest.mock import patch
        from scrapers.openrouter_scraper import OpenRouterScraper
        scraper = OpenRouterScraper()
        stale = {"source": "openrouter", "token_usage": [],
                 "total_weekly_tokens": 0}
        fresh = {"source": "openrouter", "token_usage": [{"model": "M"}],
                 "total_weekly_tokens": 5}
        with (patch.object(scraper, "load_cache", return_value=stale),
              patch.object(scraper, "_fetch_models_api", return_value={}),
              patch.object(scraper, "_fetch_rankings_page", return_value={}),
              patch.object(scraper, "_merge_data", return_value=fresh),
              patch.object(scraper, "save_cache") as save):
            result = scraper.fetch_rankings()
        self.assertIs(result, fresh)
        save.assert_called_once()

    def test_fresh_cache_still_used(self):
        from unittest.mock import patch
        from scrapers.openrouter_scraper import OpenRouterScraper
        scraper = OpenRouterScraper()
        good = {"source": "openrouter",
                "token_usage": [{"model": "M"}], "total_weekly_tokens": 5}
        with (patch.object(scraper, "load_cache", return_value=good),
              patch.object(scraper, "_fetch_models_api",
                           side_effect=AssertionError("must not refetch"))):
            self.assertIs(scraper.fetch_rankings(), good)


if __name__ == "__main__":
    unittest.main(verbosity=2)
