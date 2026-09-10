#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""End-to-end contract tests for the repaired AI and finance dashboard paths."""
import json
from pathlib import Path

from ai_daily_push import build_html, shape
from finance_daily_push import build_finance_html, shape_finance, build_finance_markdown
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


def test_ai_source_empty_contract():
    report = {
        "sections": [{
            "label": "Research",
            "items": [{
                "title": "Source without excerpt",
                "summary": "",
                "summaryStatus": "source_empty",
                "source": {"name": "Example"},
                "links": {"original": "https://example.com/empty"},
            }],
        }]
    }
    data = shape(report, market_insights=[])
    assert_true(data["meta"]["sourceEmptyCount"] == 1,
                "source-empty count was not preserved")
    assert_true(data["sections"][0]["items"][0]["summaryStatus"] == "source_empty",
                "source-empty status was not preserved")
    html = build_html(data)
    assert_true("上游未提供摘要，请查看原文。" in html,
                "source-empty state is not visible in the dashboard")
    print("[PASS] Source-empty status reaches AI dashboard metadata and UI")


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


def test_finance_money_flow_degraded_contract():
    money_flow = {
        "north_flow": {
            "available": True, "stale": True, "trade_date": "2026-09-04",
            "sh_flow": 1.0, "sz_flow": -0.2, "total_flow": 0.8,
            "reason": "实时数据不可用，显示最近有效交易日 2026-09-04 的缓存",
        },
        "sector_flow": {"top_inflow": [], "top_outflow": [],
                        "available": False, "reason": "行业数据暂不可用"},
        "stock_flow": {"top_inflow": [], "top_outflow": [],
                        "available": False, "reason": "个股数据暂不可用"},
    }
    data = shape_finance([], [], {}, {}, {}, {}, money_flow_data=money_flow)
    html = build_finance_html(data)
    body, _ = build_finance_markdown(data, "")
    assert_true("2026-09-04" in html and "缓存" in html,
                "stale northbound provenance is missing from HTML")
    assert_true("行业数据暂不可用" in html and "个股数据暂不可用" in html,
                "sector/stock unavailable reasons are missing from HTML")
    assert_true("行业资金：行业数据暂不可用" in body and
                "个股资金：个股数据暂不可用" in body,
                "money-flow unavailable reasons are missing from Markdown body")
    print("[PASS] Money-flow stale and unavailable states reach HTML and Markdown")

def test_scraper_status_contracts():
    from scrapers.twitter_scraper import TwitterScraper
    from scrapers.weibo_scraper import WeiboScraper

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
        test_ai_source_empty_contract,
        test_ai_market_fallback_contract,
        test_finance_twitter_contract,
        test_finance_twitter_failure_contract,
        test_finance_money_flow_degraded_contract,
        test_scraper_status_contracts,
    ]
    for test in tests:
        test()
    print(f"[PASS] {len(tests)}/{len(tests)} end-to-end contract tests passed")


if __name__ == "__main__":
    main()
