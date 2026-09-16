#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""End-to-end contract tests for the repaired AI and finance dashboard paths."""
import json
from pathlib import Path
from unittest.mock import patch

from ai_daily_push import build_html, shape, build_markdown, push_wecom_webhook
from finance_daily_push import (
    build_finance_html, shape_finance, build_finance_markdown,
    push_wecom_news_card,
)
from scrapers.twitter_scraper import TwitterScraper
from scrapers.weibo_scraper import WeiboScraper
from wechat_content_formatter import format_ai_daily_for_wechat, format_finance_daily_for_wechat
from wechat_official import publish_to_wechat
from wechat_official_publisher import _standalone_article_html


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


def test_finance_money_flow_no_north_contract():
    """北向已砍：payload 不得含 north_flow；行业数字进 HTML 和微信正文，缺数原因直显。"""
    money_flow = {
        "sector_flow": {
            "top_inflow": [{"name": "银行", "net_inflow": 12.34, "change_pct": 1.2, "net_ratio": 0.5}],
            "top_outflow": [{"name": "医药", "net_inflow": -5.0, "change_pct": -0.8, "net_ratio": -0.3}],
            "available": True, "reason": "",
        },
        "stock_flow": {"top_inflow": [], "top_outflow": [],
                        "available": False, "reason": "东方财富返回盘前占位或无效个股资金数据"},
    }
    data = shape_finance([], [], {}, {}, {}, {}, money_flow_data=money_flow)
    assert_true("north_flow" not in (data.get("moneyFlow") or {}),
                "northbound flow was not removed from finance payload")
    html = build_finance_html(data)
    assert_true("银行" in html and "12.34" in html,
                "sector inflow numbers are missing from finance HTML")
    assert_true("盘前占位" in html,
                "stock unavailable reason is missing from finance HTML")
    body, _ = build_finance_markdown(data, "")
    assert_true("银行" in body and "12.34" in body,
                "sector inflow numbers are missing from Markdown body")
    assert_true("个股资金" in body and "盘前占位" in body,
                "stock unavailable reason is missing from Markdown body")
    print("[PASS] Money-flow (no northbound) numbers and reasons reach HTML and Markdown")

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


def test_site_navigation_delivery_boundary():
    ai_data = shape({"date": "2026-09-10", "sections": []}, market_insights=[])
    finance_data = shape_finance([], [], [], {}, {}, {})

    ai_page = build_html(ai_data)
    finance_page = build_finance_html(finance_data)
    for page in (ai_page, finance_page):
        assert_true('class="global-nav"' in page,
                    "GitHub Pages dashboard lost its global navigation")
        assert_true('href="index.html"' in page and 'href="finance.html"' in page and
                    'href="monitor.html"' in page,
                    "GitHub Pages dashboard is missing a site navigation link")

    ai_markdown = build_markdown(ai_data, "https://example.invalid/index.html")
    finance_body, finance_tail = build_finance_markdown(
        finance_data, "https://example.invalid/finance.html"
    )
    for outbound in (ai_markdown, finance_body + finance_tail):
        assert_true('global-nav' not in outbound,
                    "notification Markdown contains dashboard navigation markup")
        assert_true('推送监控' not in outbound,
                    "notification Markdown contains the monitor navigation item")

    ai_article = format_ai_daily_for_wechat(ai_data)[1]
    finance_article = format_finance_daily_for_wechat(finance_data)[1]
    dashboard_fragment = '''
    <style>.global-nav{position:fixed}.article{color:#333}</style>
    <nav class="global-nav"><a href="index.html">AI 日报</a><a href="finance.html">财经日报</a><a href="monitor.html">推送监控</a></nav>
    <article class="article">应保留正文</article>
    '''
    cleaned_legacy_article = _standalone_article_html(dashboard_fragment)
    for article in (ai_article, finance_article, cleaned_legacy_article):
        assert_true('global-nav' not in article,
                    "WeChat article contains dashboard navigation markup or CSS")
        assert_true('href="index.html"' not in article and
                    'href="finance.html"' not in article and
                    'href="monitor.html"' not in article,
                    "WeChat article contains site navigation links")
    assert_true("应保留正文" in cleaned_legacy_article,
                "navigation sanitizer removed article content")

    with patch("wechat_official.WechatOfficialPublisher") as publisher_type:
        publisher_type.return_value.publish_article.return_value = {"publish_id": "fixture-id"}
        publish_id = publish_to_wechat(
            "fixture-app", "fixture-secret", "测试日报", dashboard_fragment,
            "AI Daily Push", "测试摘要", "https://example.invalid/index.html",
            "fixture-cover.jpg",
        )
    published_content = publisher_type.return_value.publish_article.call_args.kwargs["content"]
    assert_true(publish_id == "fixture-id" and "应保留正文" in published_content,
                "WeChat wrapper did not publish the sanitized article")
    assert_true("global-nav" not in published_content and "推送监控" not in published_content,
                "WeChat wrapper forwarded site navigation to the publisher")

    import ai_daily_push
    import finance_daily_push
    captured = []
    with patch.object(ai_daily_push, "http_post_json",
                      side_effect=lambda url, payload: captured.append(payload) or {"errcode": 0}), \
         patch.object(finance_daily_push, "http_post_json",
                      side_effect=lambda url, payload: captured.append(payload) or {"errcode": 0}):
        push_wecom_webhook("https://example.invalid/ai-hook", ai_markdown,
                           "https://example.invalid/index.html", "AI 日报 · 9月10日")
        push_wecom_news_card("https://example.invalid/finance-hook",
                             "https://example.invalid/finance.html", "财经日报 · 9月10日")

    assert_true(len(captured) == 2, "expected one news card per daily notification")
    for payload in captured:
        articles = payload.get("news", {}).get("articles", [])
        assert_true(payload.get("msgtype") == "news" and len(articles) == 1,
                    "WeCom notification is not a single news card")
        visible = articles[0].get("title", "") + articles[0].get("description", "")
        assert_true('推送监控' not in visible and 'global-nav' not in visible,
                    "WeCom news card exposes site navigation")
    print("[PASS] Site navigation is retained on Pages and excluded at delivery boundaries")


def test_ai_token_usage_contract():
    """直抓 Token 用量（非新闻抽取）必须完整穿过 shape()，供页面 Token/份额块渲染。"""
    payload = {
        "total_weekly_tokens": 80.92e12,
        "list": [{"model": "GPT-5.6 Luna", "weekly_tokens_display": "17.4T",
                  "weekly_tokens": 17.4e12, "market_share": 21.5,
                  "wow_direction": "positive", "wow_change": "21%"}],
        "note": "OpenRouter 网关口径",
    }
    data = shape({"sections": []}, token_usage=payload)
    tu = data.get("tokenUsage") or {}
    assert_true(tu.get("total_weekly_tokens") == 80.92e12,
                "tokenUsage total was dropped by shape()")
    assert_true((tu.get("list") or [{}])[0].get("market_share") == 21.5,
                "tokenUsage shares were dropped by shape()")
    assert_true("网关" in (tu.get("note") or ""),
                "tokenUsage caliber note was dropped by shape()")
    html = build_html(data)
    # JS 按 tokenUsage.list 长度决定整块显隐：有数渲染、无数隐藏。
    # 合约锁的是 payload 必须带齐渲染所需的全部键（页面行为由浏览器执行，单测覆盖数据侧）。
    row = (tu.get("list") or [{}])[0]
    for key in ("model", "weekly_tokens_display", "market_share",
                "wow_direction", "wow_change"):
        assert_true(key in row, f"tokenUsage row is missing {key} for rendering")
    assert_true("GPT-5.6 Luna" in html and "OpenRouter 网关口径" in html,
                "tokenUsage payload is absent from dashboard HTML")
    empty_tu = (shape({"sections": []}, token_usage={}).get("tokenUsage") or {})
    assert_true((empty_tu.get("list") or []) == [],
                "empty tokenUsage must carry an empty list so the block hides")
    print("[PASS] Direct-captured token usage reaches shaped AI data")


def test_finance_strategy_fallback_contract():
    """空分析/空策略必须是机器可判读的，且交易日字段要穿透到页面 payload。"""
    from finance_daily_push import ANALYSIS_FALLBACK, STRATEGY_FALLBACK
    assert_true(ANALYSIS_FALLBACK.get("ok") is False,
                "ANALYSIS_FALLBACK lacks machine-readable ok:false")
    assert_true(STRATEGY_FALLBACK.get("ok") is False,
                "STRATEGY_FALLBACK lacks machine-readable ok:false")
    strategy = dict(STRATEGY_FALLBACK)
    strategy["last_trading_day"] = "9月12日"
    strategy["is_trading_day"] = True
    data = shape_finance([], [], [], {}, {}, strategy)
    sg = data.get("strategy") or {}
    assert_true(sg.get("lastTradingDay") == "9月12日",
                "strategy lastTradingDay was dropped by shape_finance()")
    assert_true(sg.get("isTradingDay") is True,
                "strategy isTradingDay was dropped by shape_finance()")
    print("[PASS] Strategy fallback is machine-readable and preserves trading-day fields")


def test_push_standalone_contract():
    """推送落地页无导航、Pages 版保留导航，卡片外链必须指向无导航版。"""
    from ai_daily_push import derive_push_dashboard_url
    assert_true(derive_push_dashboard_url(
        "https://example.pages.dev/ai_daily_dashboard.html")
        == "https://example.pages.dev/ai_push_standalone.html",
        "AI push URL derivation is wrong")
    assert_true(derive_push_dashboard_url(
        "https://example.pages.dev/finance_dashboard.html")
        == "https://example.pages.dev/finance_push_standalone.html",
        "finance push URL derivation is wrong")
    assert_true(derive_push_dashboard_url("") == "",
                "empty dashboard URL must stay empty")
    assert_true(derive_push_dashboard_url("https://example.pages.dev/x.html")
                == "https://example.pages.dev/x_push_standalone.html",
                "generic .html derivation is wrong")

    pages_html = build_html(shape({"sections": []}))
    push_html = build_html(shape({"sections": []}), standalone=True)
    assert_true("<nav" in pages_html, "Pages AI dashboard lost its navigation")
    assert_true("<nav" not in push_html,
                "push landing page still contains navigation")
    fin_pages = build_finance_html(shape_finance([], [], [], {}, {}, {}))
    fin_push = build_finance_html(shape_finance([], [], [], {}, {}, {}),
                                  standalone=True)
    assert_true("<nav" in fin_pages, "Pages finance dashboard lost its navigation")
    assert_true("<nav" not in fin_push,
                "finance push landing page still contains navigation")

    captured = []
    push_url = derive_push_dashboard_url("https://example.pages.dev/index.html")
    import ai_daily_push
    with patch.object(ai_daily_push, "http_post_json",
                      side_effect=lambda url, payload: captured.append(payload) or {"errcode": 0}):
        push_wecom_webhook("https://example.invalid/hook", "md", push_url, "AI 日报")
    assert_true(captured[0]["news"]["articles"][0]["url"].endswith(
        "index_push_standalone.html"),
        "WeCom card does not point at the navigation-free landing page")
    print("[PASS] Push landing pages are navigation-free and card-linked")


def main():
    tests = [
        test_ai_translation_contract,
        test_ai_source_empty_contract,
        test_ai_market_fallback_contract,
        test_finance_twitter_contract,
        test_finance_twitter_failure_contract,
        test_finance_money_flow_no_north_contract,
        test_ai_token_usage_contract,
        test_finance_strategy_fallback_contract,
        test_scraper_status_contracts,
        test_site_navigation_delivery_boundary,
        test_push_standalone_contract,
    ]
    for test in tests:
        test()
    print(f"[PASS] {len(tests)}/{len(tests)} end-to-end contract tests passed")


if __name__ == "__main__":
    main()
