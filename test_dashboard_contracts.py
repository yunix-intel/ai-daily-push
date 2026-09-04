#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""End-to-end contract tests for the repaired AI and finance dashboard paths."""
import json
from pathlib import Path

from ai_daily_push import build_html, shape
from finance_daily_push import build_finance_html, shape_finance
from scrapers.twitter_scraper import TwitterScraper
from scrapers.weibo_scraper import WeiboScraper


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def test_ai_translation_contract():
    report = {
        "sections": [{
            "label": "International",
            "items": [{
                "title": "Translated headline",
                "originalTitle": "Original English headline",
                "summary": "Chinese summary",
                "originalSummary": "An English source summary that is long enough to represent an article.",
                "source": {"name": "Example"},
                "links": {"original": "https://example.com/article"},
                "translated_content": "This is the translated full article.",
            }],
        }]
    }
    data = shape(report, market_insights=[])
    item = data["sections"][0]["items"][0]
    assert_true(item["translated_content"] == "This is the translated full article.",
                "shape() dropped translated_content")
    html = build_html(data)
    assert_true("翻译全文" in html, "AI dashboard is missing the translation button")
    assert_true("This is the translated full article." in html,
                "translated_content is absent from AI dashboard payload")
    print("[PASS] AI translated_content reaches dashboard HTML")


def test_ai_market_fallback_contract():
    report = {"sections": []}
    fallback = [{
        "title": "市场数据暂不可用",
        "summary": "OpenRouter API unavailable",
        "source": "System",
        "link": "#",
    }]
    data = shape(report, market_insights=fallback)
    serialized = json.dumps(data, ensure_ascii=False)
    assert_true("市场数据暂不可用" in serialized,
                "market fallback was not included in shaped data")
    html = build_html(data)
    assert_true("市场数据暂不可用" in html,
                "market fallback was not included in AI dashboard HTML")
    print("[PASS] Market-data fallback reaches dashboard HTML")


def test_finance_twitter_contract():
    twitter = {
        "rumors": [{
            "title": "Unverified event",
            "summary": "A rumor summary",
            "source": "@rumor",
            "link": "https://x.com/rumor/status/1",
            "verification": "unverified",
            "category": "rumors",
        }],
        "media": [{
            "title": "Confirmed media report",
            "summary": "A media summary",
            "source": "@Reuters",
            "link": "https://x.com/Reuters/status/2",
            "verification": "confirmed",
            "category": "media",
        }],
        "available": True,
        "errors": {},
    }
    data = shape_finance([], [], {}, {}, {}, {}, blogger_views=[], twitter_content=twitter)
    assert_true(data["twitter"]["available"] is True, "twitter availability was dropped")
    assert_true(data["twitter"]["rumors"][0]["verification"] == "unverified",
                "rumor verification was dropped")
    html = build_finance_html(data)
    assert_true("未经证实" in html, "finance template is missing unverified-rumor warning")
    assert_true("Twitter 财经观察" in html, "finance template is missing Twitter section")
    print("[PASS] Twitter rumor/media data reaches finance dashboard HTML")


def test_finance_twitter_failure_contract():
    twitter = {
        "rumors": [],
        "media": [],
        "available": False,
        "errors": {"rumors": "RSSHub unavailable"},
    }
    data = shape_finance([], [], {}, {}, {}, {}, blogger_views=[], twitter_content=twitter)
    assert_true(data["twitter"]["available"] is False, "twitter failure state was dropped")
    assert_true(data["twitter"]["errors"]["rumors"] == "RSSHub unavailable",
                "twitter failure error was dropped")
    html = build_finance_html(data)
    assert_true("RSSHub unavailable" in html, "RSSHub error missing from finance dashboard payload")
    print("[PASS] Twitter source failure reaches finance dashboard HTML")


def test_scraper_status_contracts():
    weibo = WeiboScraper(rsshub_base="https://invalid.example", timeout=1)
    weibo_result = weibo.fetch_weibo_user("1", limit=1)
    assert_true(set(("weibos", "available", "source_url")).issubset(weibo_result),
                "Weibo result is not structured")
    assert_true(weibo_result["available"] is False, "invalid Weibo endpoint unexpectedly succeeded")

    twitter = TwitterScraper(rsshub_base="https://invalid.example", timeout=1)
    twitter_result = twitter.fetch_tweets("example", limit=1)
    assert_true(set(("tweets", "available", "source_url")).issubset(twitter_result),
                "Twitter result is not structured")
    assert_true(twitter_result["available"] is False, "invalid Twitter endpoint unexpectedly succeeded")
    print("[PASS] RSSHub failures return structured scraper statuses")


def main():
    tests = [
        test_ai_translation_contract,
        test_ai_market_fallback_contract,
        test_finance_twitter_contract,
        test_finance_twitter_failure_contract,
        test_scraper_status_contracts,
    ]
    for test in tests:
        test()
    print(f"[PASS] {len(tests)}/{len(tests)} end-to-end contract tests passed")


if __name__ == "__main__":
    main()
