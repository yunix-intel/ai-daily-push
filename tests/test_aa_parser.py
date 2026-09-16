#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AA 解析回归：只认 ld+json Dataset，正文数字一律不算分。

锁死旧 bug（正文 "Qwen … 3" 被当成 Qwen 3 分）不再出现，以及
超范围值、重复 label、改版空页面时的行为。
"""
import json
import unittest

from scrapers.artificial_analysis_scraper import ArtificialAnalysisScraper

FIXTURE = """
<html><body>
<p>Qwen 发布了 3 款新模型，GPT 拿下 6 个奖项，会议共 7 天</p>
<script type="application/ld+json">%s</script>
<script type="application/ld+json">%s</script>
</body></html>
"""

INTEL = {"@type": "Dataset", "name": "Intelligence", "data": [
    {"label": "Claude Fable 5.1 (max with fallback)",
     "artificialAnalysisIntelligenceIndex": 53.37, "detailsUrl": "/models/x"},
    {"label": "Claude Fable 5.1 (max with fallback)",
     "artificialAnalysisIntelligenceIndex": 53.37, "detailsUrl": "/models/x"},
    {"label": "Qwen Fake", "artificialAnalysisIntelligenceIndex": 999.0,
     "detailsUrl": "/models/y"},
    {"label": "GPT-6 Astra (max)",
     "artificialAnalysisIntelligenceIndex": 52.81, "detailsUrl": "/models/z"},
    {"label": "", "artificialAnalysisIntelligenceIndex": 40.0,
     "detailsUrl": "/models/w"},
]}

SPEED = {"@type": "Dataset", "name": "Speed", "data": [
    {"label": "Gemini 3.8 Flash (high)", "medianOutputSpeed": 335.5,
     "detailsUrl": "/models/a"},
    {"label": "Broken Model", "medianOutputSpeed": "fast",
     "detailsUrl": "/models/b"},
]}


class TestAAParser(unittest.TestCase):
    def setUp(self):
        self.scraper = ArtificialAnalysisScraper()

    def test_datasets_beat_body_text(self):
        html = FIXTURE % (json.dumps(INTEL), json.dumps(SPEED))
        r = self.scraper.parse_homepage(html)
        self.assertTrue(r["parsed"])
        models = [x["model"] for x in r["intelligence"]]
        # 正文里的 Qwen/GPT/数字一个都不许进榜
        self.assertNotIn("Qwen", " ".join(models))
        self.assertEqual(models.count("Claude Fable 5.1 (max with fallback)"), 1)
        # 超范围 999 与空 label 被丢掉，只剩 2 条
        self.assertEqual(len(r["intelligence"]), 2)
        self.assertEqual(r["intelligence"][0]["score"], 53.4)
        # 速度榜只认数值，非数值丢掉
        self.assertEqual(len(r["speed"]), 1)
        self.assertEqual(r["speed"][0]["tokens_per_sec"], 335.5)
        # Cost 块缺席 → 空榜，不编造
        self.assertEqual(r["cost"], [])

    def test_redesigned_page_hides(self):
        r = self.scraper.parse_homepage("<html><body>全新改版，无数据</body></html>")
        self.assertFalse(r["parsed"])
        self.assertEqual(r["intelligence"], [])
        self.assertEqual(r["speed"], [])
        self.assertEqual(r["cost"], [])

    def test_junk_cache_is_unusable(self):
        junk = {"intelligence": [{"model": "Qwen", "score": 3},
                                 {"model": "GPT", "score": 6}],
                "speed": [], "cost": []}
        self.assertFalse(ArtificialAnalysisScraper._is_usable_cache(junk))
        real = {"parsed": True, "intelligence": [], "speed": [],
                "cost": [{"model": "GPT-5.6 Luna (max)", "cost_per_task": 0.1783}]}
        self.assertTrue(ArtificialAnalysisScraper._is_usable_cache(real))

    def test_sane_rows_keeps_real_drops_junk(self):
        rows = [{"model": "Claude Fable 5.1 (max with fallback)", "score": 53.4},
                {"model": "Qwen", "score": 3},
                {"model": "", "score": 45.0},
                "not-a-dict"]
        sane = ArtificialAnalysisScraper._sane_rows(rows, "intelligence")
        self.assertEqual([r["model"] for r in sane],
                         ["Claude Fable 5.1 (max with fallback)"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
