#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公众号内容格式化模块 - 将日报数据转换为适合公众号的 HTML 格式
"""
from datetime import datetime, timedelta


def format_ai_daily_for_wechat(data):
    """
    将 AI 日报数据格式化为微信公众号文章

    Args:
        data: AI 日报数据结构

    Returns:
        tuple: (title, content_html, digest)
    """
    meta = data.get('meta', {})
    sections = data.get('sections', [])
    highlights = data.get('highlights', [])

    # 生成标题
    date_str = meta.get('date', '')
    try:
        dt = datetime.fromisoformat(date_str + 'T00:00:00+08:00')
        title = f"AI 日报 · {dt.month}月{dt.day}日"
    except:
        title = "AI 日报"

    # 生成摘要（前3条要闻）
    digest_items = []
    for i, hl in enumerate(highlights[:3]):
        digest_items.append(f"{i+1}. {hl.get('title', '')[:30]}...")
    digest = " | ".join(digest_items) if digest_items else "今日AI行业要闻"

    # 生成 HTML 内容
    html_parts = []

    # 头部
    html_parts.append(f"""
<section style="margin:0;padding:20px;background:#f8f9fa;font-family:system-ui,-apple-system,sans-serif">
<h1 style="font-size:24px;color:#1a1a1a;margin:0 0 10px">🤖 AI 日报</h1>
<p style="color:#666;font-size:14px;margin:0">{date_str}</p>
</section>
""")

    # 今日要闻
    if highlights:
        html_parts.append('<section style="padding:20px"><h2 style="font-size:20px;color:#1a1a1a;border-left:4px solid #5b9dff;padding-left:12px;margin:0 0 15px">⭐ 今日要闻</h2>')
        for i, item in enumerate(highlights[:5]):
            html_parts.append(f"""
<div style="margin-bottom:15px;padding:15px;background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)">
<h3 style="font-size:16px;color:#1a1a1a;margin:0 0 8px">{i+1}. {item.get('title', '')}</h3>
<p style="font-size:14px;color:#666;line-height:1.6;margin:0">{item.get('summary', '')[:150]}...</p>
</div>
""")
        html_parts.append('</section>')

    # 各板块新闻
    for section in sections:
        label = section.get('label', '')
        items = section.get('items', [])

        if not items:
            continue

        html_parts.append(f'<section style="padding:20px"><h2 style="font-size:20px;color:#1a1a1a;border-left:4px solid #5b9dff;padding-left:12px;margin:0 0 15px">{label}</h2>')

        for item in items[:10]:  # 每个板块最多10条
            title = item.get('title', '')
            summary = item.get('summary', '')
            source = item.get('source', '')

            html_parts.append(f"""
<div style="margin-bottom:15px;padding:12px;background:#f8f9fa;border-radius:6px">
<h4 style="font-size:15px;color:#1a1a1a;margin:0 0 6px">{title}</h4>
<p style="font-size:13px;color:#666;line-height:1.5;margin:0 0 6px">{summary[:120]}...</p>
<p style="font-size:12px;color:#999;margin:0">来源：{source}</p>
</div>
""")

        html_parts.append('</section>')

    # 底部
    html_parts.append("""
<section style="margin:20px;padding:15px;background:#f0f0f0;border-radius:8px;text-align:center">
<p style="font-size:13px;color:#666;margin:0">更多详情请查看完整版日报</p>
</section>
""")

    content_html = ''.join(html_parts)

    return title, content_html, digest


def format_finance_daily_for_wechat(data):
    """
    将财经日报数据格式化为微信公众号文章

    Args:
        data: 财经日报数据结构

    Returns:
        tuple: (title, content_html, digest)
    """
    meta = data.get('meta', {})
    domestic = data.get('domestic', {})
    international = data.get('international', {})

    # 生成标题
    date_str = meta.get('date', '')
    try:
        dt = datetime.fromisoformat(date_str)
        title = f"财经日报 · {dt.month}月{dt.day}日"
    except:
        title = "财经日报"

    # 生成摘要
    digest = f"国内 {meta.get('domesticCount', 0)} 条 | 国际 {meta.get('internationalCount', 0)} 条"

    # 生成 HTML 内容
    html_parts = []

    # 头部
    html_parts.append(f"""
<section style="margin:0;padding:20px;background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);font-family:system-ui,-apple-system,sans-serif">
<h1 style="font-size:24px;color:#fff;margin:0 0 10px">📊 财经日报</h1>
<p style="color:#fff;opacity:0.9;font-size:14px;margin:0">{date_str}</p>
</section>
""")

    # 策略建议
    strategy = data.get('strategy', {})
    if strategy.get('recommendation'):
        html_parts.append(f"""
<section style="padding:20px;background:#fff8e1">
<h2 style="font-size:18px;color:#f57c00;margin:0 0 10px">🎯 今日策略</h2>
<p style="font-size:14px;color:#333;line-height:1.6;margin:0">{strategy.get('recommendation', '')}</p>
</section>
""")

    # 国内要闻
    if domestic.get('sections'):
        html_parts.append('<section style="padding:20px"><h2 style="font-size:20px;color:#1a1a1a;border-left:4px solid #f0b429;padding-left:12px;margin:0 0 15px">🇨🇳 国内要闻</h2>')

        for section in domestic['sections'][:2]:  # 前2个分类
            items = section.get('items', [])
            for item in items[:5]:  # 每个分类最多5条
                title = item.get('title', '')
                summary = item.get('summary', '')
                source = item.get('source', '')

                html_parts.append(f"""
<div style="margin-bottom:15px;padding:12px;background:#f8f9fa;border-radius:6px">
<h4 style="font-size:15px;color:#1a1a1a;margin:0 0 6px">{title}</h4>
<p style="font-size:13px;color:#666;line-height:1.5;margin:0 0 6px">{summary[:120]}...</p>
<p style="font-size:12px;color:#999;margin:0">来源：{source}</p>
</div>
""")

        html_parts.append('</section>')

    # 国际要闻
    if international.get('sections'):
        html_parts.append('<section style="padding:20px"><h2 style="font-size:20px;color:#1a1a1a;border-left:4px solid #37e0b0;padding-left:12px;margin:0 0 15px">🌍 国际要闻</h2>')

        for section in international['sections'][:2]:  # 前2个分类
            items = section.get('items', [])
            for item in items[:5]:  # 每个分类最多5条
                title = item.get('title', '')
                summary = item.get('summary', '')
                source = item.get('source', '')

                html_parts.append(f"""
<div style="margin-bottom:15px;padding:12px;background:#f8f9fa;border-radius:6px">
<h4 style="font-size:15px;color:#1a1a1a;margin:0 0 6px">{title}</h4>
<p style="font-size:13px;color:#666;line-height:1.5;margin:0 0 6px">{summary[:120]}...</p>
<p style="font-size:12px;color:#999;margin:0">来源：{source}</p>
</div>
""")

        html_parts.append('</section>')

    # 底部
    html_parts.append("""
<section style="margin:20px;padding:15px;background:#f0f0f0;border-radius:8px;text-align:center">
<p style="font-size:13px;color:#666;margin:0">更多详情请查看完整版日报</p>
</section>
""")

    content_html = ''.join(html_parts)

    return title, content_html, digest
