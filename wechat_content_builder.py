#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号内容构建模块
功能：将日报 HTML 转换为适合公众号发布的格式
"""

import os
import urllib.request
from datetime import datetime


def download_cover_image(url, save_path):
    """下载封面图片到本地。

    Args:
        url: 图片 URL
        save_path: 保存路径

    Returns:
        成功返回 True，失败返回 False
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            with open(save_path, "wb") as f:
                f.write(resp.read())
        return True
    except Exception as e:
        print(f"     [!] 下载封面图片失败：{e!r}")
        return False


def prepare_ai_daily_cover(output_dir):
    """准备 AI 日报封面图。

    Args:
        output_dir: 输出目录

    Returns:
        封面图片路径，失败返回 None
    """
    cover_path = os.path.join(output_dir, "ai_daily_cover.jpg")

    # 如果已存在且是今天下载的，直接使用
    if os.path.exists(cover_path):
        mtime = os.path.getmtime(cover_path)
        if datetime.now().date() == datetime.fromtimestamp(mtime).date():
            return cover_path

    # 下载 AI 主题封面图（使用 picsum.photos 随机图片）
    # AI 日报使用科技感的图片 ID
    cover_url = "https://picsum.photos/id/0/1200/630"  # 16:9 比例，适合公众号封面

    if download_cover_image(cover_url, cover_path):
        return cover_path
    return None


def prepare_finance_daily_cover(output_dir):
    """准备财经日报封面图。

    Args:
        output_dir: 输出目录

    Returns:
        封面图片路径，失败返回 None
    """
    cover_path = os.path.join(output_dir, "finance_daily_cover.jpg")

    # 如果已存在且是今天下载的，直接使用
    if os.path.exists(cover_path):
        mtime = os.path.getmtime(cover_path)
        if datetime.now().date() == datetime.fromtimestamp(mtime).date():
            return cover_path

    # 下载财经主题封面图
    # 财经日报使用金融/商务感的图片 ID
    cover_url = "https://picsum.photos/id/1067/1200/630"  # 16:9 比例

    if download_cover_image(cover_url, cover_path):
        return cover_path
    return None


def html_to_wechat_article(html_content, title, dashboard_url=""):
    """将日报 HTML 内容转换为适合公众号的格式。

    公众号编辑器支持有限的 HTML 标签和样式，需要：
    1. 移除复杂的 CSS 和 JS
    2. 简化布局，使用公众号支持的标签
    3. 保留核心内容和链接

    Args:
        html_content: 原始 HTML 内容
        title: 文章标题
        dashboard_url: 日报网页链接

    Returns:
        转换后的 HTML 字符串
    """
    # 简化策略：提取核心内容，重新用公众号支持的样式包装
    # 公众号支持的标签：p, br, strong, em, span, h1-h6, blockquote, ul, ol, li, a, img

    # 这里采用简单策略：引导用户点击"阅读原文"查看完整网页版
    date_str = datetime.now().strftime("%Y年%m月%d日")

    wechat_html = f"""
<section style="font-size: 16px; color: #333; line-height: 1.8;">
    <h2 style="text-align: center; font-size: 24px; color: #2c3e50; margin: 20px 0;">
        {title}
    </h2>

    <p style="text-align: center; color: #7f8c8d; font-size: 14px; margin-bottom: 30px;">
        {date_str}
    </p>

    <section style="background: #f8f9fa; border-left: 4px solid #3498db; padding: 15px; margin: 20px 0;">
        <p style="margin: 0; color: #555;">
            📱 <strong>完整日报已发布到网页版</strong>
        </p>
        <p style="margin: 10px 0 0 0; color: #777; font-size: 14px;">
            点击文末「阅读原文」查看完整交互式日报，包含所有新闻详情、来源链接和实时数据。
        </p>
    </section>

    <section style="margin: 30px 0;">
        <h3 style="font-size: 18px; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
            📊 今日要点
        </h3>
        <p style="color: #555; margin-top: 15px;">
            本期日报已收录最新资讯，包含：
        </p>
        <ul style="color: #555; line-height: 2;">
            <li>AI 行业动态与技术突破</li>
            <li>重要公司新闻与产品发布</li>
            <li>行业分析与市场趋势</li>
            <li>开源项目与开发者工具</li>
        </ul>
    </section>

    <section style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 10px; padding: 20px; margin: 30px 0; text-align: center;">
        <p style="color: white; font-size: 16px; margin: 0;">
            💡 <strong>查看完整内容</strong>
        </p>
        <p style="color: rgba(255,255,255,0.9); font-size: 14px; margin: 10px 0 0 0;">
            点击下方「阅读原文」打开交互式日报网页
        </p>
    </section>

    <section style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
        <p style="color: #999; font-size: 13px; text-align: center;">
            每日 7:23 自动更新 | 多来源聚合 | AI 精选推荐
        </p>
    </section>
</section>
"""

    return wechat_html.strip()


def html_to_wechat_finance_article(html_content, title, dashboard_url=""):
    """将财经日报 HTML 内容转换为适合公众号的格式。

    Args:
        html_content: 原始 HTML 内容
        title: 文章标题
        dashboard_url: 日报网页链接

    Returns:
        转换后的 HTML 字符串
    """
    date_str = datetime.now().strftime("%Y年%m月%d日")

    wechat_html = f"""
<section style="font-size: 16px; color: #333; line-height: 1.8;">
    <h2 style="text-align: center; font-size: 24px; color: #2c3e50; margin: 20px 0;">
        {title}
    </h2>

    <p style="text-align: center; color: #7f8c8d; font-size: 14px; margin-bottom: 30px;">
        {date_str}
    </p>

    <section style="background: #fff9e6; border-left: 4px solid #f0b429; padding: 15px; margin: 20px 0;">
        <p style="margin: 0; color: #555;">
            📈 <strong>完整财经日报已发布到网页版</strong>
        </p>
        <p style="margin: 10px 0 0 0; color: #777; font-size: 14px;">
            点击文末「阅读原文」查看完整交互式日报，包含指数行情、市场分析、策略建议和所有快讯详情。
        </p>
    </section>

    <section style="margin: 30px 0;">
        <h3 style="font-size: 18px; color: #2c3e50; border-bottom: 2px solid #f0b429; padding-bottom: 10px;">
            💹 今日概览
        </h3>
        <p style="color: #555; margin-top: 15px;">
            本期财经日报已收录：
        </p>
        <ul style="color: #555; line-height: 2;">
            <li>实时股市指数（沪深港美）</li>
            <li>过去 24 小时财经快讯</li>
            <li>突发事件与市场分析</li>
            <li>A股/港股策略建议</li>
        </ul>
    </section>

    <section style="background: linear-gradient(135deg, #f0b429 0%, #c98f10 100%);
                    border-radius: 10px; padding: 20px; margin: 30px 0; text-align: center;">
        <p style="color: white; font-size: 16px; margin: 0;">
            💡 <strong>查看完整内容</strong>
        </p>
        <p style="color: rgba(255,255,255,0.9); font-size: 14px; margin: 10px 0 0 0;">
            点击下方「阅读原文」打开完整财经仪表盘
        </p>
    </section>

    <section style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0;">
        <p style="color: #999; font-size: 13px; text-align: center;">
            每日 7:23 自动更新 | 多来源聚合 | LLM 智能分析
        </p>
        <p style="color: #999; font-size: 12px; text-align: center; margin-top: 5px;">
            ⚠️ 本内容仅供参考，不构成投资建议
        </p>
    </section>
</section>
"""

    return wechat_html.strip()


if __name__ == "__main__":
    # 测试代码
    import tempfile

    output_dir = tempfile.gettempdir()

    print("测试下载 AI 日报封面...")
    ai_cover = prepare_ai_daily_cover(output_dir)
    if ai_cover:
        print(f"✓ AI 日报封面已保存：{ai_cover}")
    else:
        print("✗ AI 日报封面下载失败")

    print("\n测试下载财经日报封面...")
    finance_cover = prepare_finance_daily_cover(output_dir)
    if finance_cover:
        print(f"✓ 财经日报封面已保存：{finance_cover}")
    else:
        print("✗ 财经日报封面下载失败")

    print("\n测试生成公众号文章内容...")
    ai_content = html_to_wechat_article("", "AI 日报", "https://example.com")
    print(f"✓ AI 日报内容已生成（{len(ai_content)} 字符）")

    finance_content = html_to_wechat_finance_article("", "财经日报", "https://example.com")
    print(f"✓ 财经日报内容已生成（{len(finance_content)} 字符）")
