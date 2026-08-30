#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
静态翻译页面生成器
生成独立的 HTML 文章翻译页面
"""

import os
import hashlib
import re


def generate_translation_page(article_data, translated_text, output_dir='translations'):
    """
    生成静态翻译页面

    Args:
        article_data: 原文数据 {title, url, source, author, date}
        translated_text: 翻译后的文本
        output_dir: 输出目录

    Returns:
        生成的HTML文件路径（相对路径），用于 GitHub Pages
    """
    os.makedirs(output_dir, exist_ok=True)

    # 使用 URL hash 作为文件名（去重）
    url_hash = hashlib.md5(article_data['url'].encode()).hexdigest()[:12]
    filename = f"{url_hash}.html"
    filepath = os.path.join(output_dir, filename)

    # 如果已存在，直接返回（缓存）
    if os.path.exists(filepath):
        print(f"     翻译页面已缓存：{filename}")
        return f"{output_dir}/{filename}"

    # 将纯文本转换为HTML段落
    paragraphs = translated_text.split('\n\n')
    content_html = '\n'.join(f'            <p>{_escape_html(para)}</p>' for para in paragraphs if para.strip())

    # 填充模板
    html = TRANSLATION_TEMPLATE
    html = html.replace('{{title}}', _escape_html(article_data.get('title', '')))
    html = html.replace('{{source}}', _escape_html(article_data.get('source', '')))
    html = html.replace('{{original_url}}', article_data.get('url', ''))

    # 可选字段：作者
    author = article_data.get('author', '')
    if author:
        html = html.replace('{{#author}}', '').replace('{{/author}}', '')
        html = html.replace('{{author}}', _escape_html(author))
    else:
        html = re.sub(r'{{#author}}.*?{{/author}}', '', html, flags=re.DOTALL)

    # 可选字段：日期
    date = article_data.get('date', '')
    if date:
        html = html.replace('{{#date}}', '').replace('{{/date}}', '')
        html = html.replace('{{date}}', _escape_html(date))
    else:
        html = re.sub(r'{{#date}}.*?{{/date}}', '', html, flags=re.DOTALL)

    html = html.replace('{{content}}', content_html)

    # 写入文件
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"     翻译页面生成：{filename}")
    return f"{output_dir}/{filename}"


def _escape_html(text):
    """HTML 转义"""
    if not text:
        return ''
    text = str(text)
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#39;')
    return text


TRANSLATION_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}} - 财经日报全文翻译</title>
    <style>
        :root {
            --bg: #0e1014;
            --card: #171c26;
            --text: #e8ecf3;
            --muted: #9aa4b2;
            --accent: #5b9eff;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
            line-height: 1.8;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background: var(--card);
            border-radius: 12px;
            padding: 40px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3);
        }
        .header {
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }
        h1 {
            font-size: 28px;
            margin-bottom: 12px;
            color: var(--accent);
            line-height: 1.3;
        }
        .meta {
            font-size: 14px;
            color: var(--muted);
            line-height: 1.6;
        }
        .meta a {
            color: var(--accent);
            text-decoration: none;
        }
        .meta a:hover {
            text-decoration: underline;
        }
        .content {
            font-size: 16px;
            line-height: 1.8;
        }
        .content p {
            margin-bottom: 16px;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            font-size: 13px;
            color: var(--muted);
            text-align: center;
        }
        .footer a {
            color: var(--accent);
            text-decoration: none;
        }
        .footer a:hover {
            text-decoration: underline;
        }
        @media (max-width: 768px) {
            body { padding: 12px; }
            .container { padding: 24px; }
            h1 { font-size: 22px; }
            .content { font-size: 15px; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{title}}</h1>
            <div class="meta">
                <span>来源：{{source}}</span>
                {{#author}}<span> | 作者：{{author}}</span>{{/author}}
                {{#date}}<span> | {{date}}</span>{{/date}}
                <br>
                <a href="{{original_url}}" target="_blank">📄 阅读英文原文 ↗</a>
            </div>
        </div>
        <div class="content">
{{content}}
        </div>
        <div class="footer">
            本文由 LLM 自动翻译 | <a href="https://yunix-intel.github.io/ai-daily-push/finance.html">返回财经日报</a>
        </div>
    </div>
</body>
</html>
"""


if __name__ == '__main__':
    # 测试
    test_article = {
        'title': 'Test Article Title',
        'url': 'https://example.com/article',
        'source': 'Bloomberg',
        'author': 'John Doe',
        'date': '2026-08-30'
    }

    test_text = """这是第一段测试内容。

这是第二段测试内容，包含更多信息。

这是第三段。"""

    result = generate_translation_page(test_article, test_text, output_dir='test_translations')
    print(f"\n生成的页面路径: {result}")
