#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
封面图生成模块 - 为微信公众号文章生成封面图
"""
import os
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def generate_cover_image(title, date_str, output_path, cover_type="ai"):
    """
    生成微信公众号封面图

    Args:
        title: 标题
        date_str: 日期字符串
        output_path: 输出路径
        cover_type: 封面类型 ("ai" 或 "finance")

    Returns:
        bool: 是否生成成功
    """
    if not PIL_AVAILABLE:
        print("  [WARN] PIL/Pillow 未安装，无法生成封面图")
        return False

    try:
        # 微信公众号封面图尺寸：900x500 (推荐)
        width, height = 900, 500

        # 背景颜色
        if cover_type == "ai":
            bg_color = (14, 16, 20)  # 深色背景
            accent_color = (91, 157, 255)  # 蓝色
            title_text = "AI 日报"
        else:
            bg_color = (23, 28, 38)  # 深色背景
            accent_color = (240, 180, 41)  # 金色
            title_text = "财经日报"

        # 创建图像
        image = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(image)

        # 尝试加载字体（如果系统有）
        try:
            # Windows 字体路径
            font_path = "C:/Windows/Fonts/msyh.ttc"
            if os.path.exists(font_path):
                title_font = ImageFont.truetype(font_path, 72)
                date_font = ImageFont.truetype(font_path, 36)
                subtitle_font = ImageFont.truetype(font_path, 28)
            else:
                # 使用默认字体
                title_font = ImageFont.load_default()
                date_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
        except:
            title_font = ImageFont.load_default()
            date_font = ImageFont.load_default()
            subtitle_font = ImageFont.load_default()

        # 绘制装饰线条
        draw.rectangle([50, 50, 850, 54], fill=accent_color)

        # 绘制标题
        draw.text((50, 100), title_text, fill=(232, 236, 243), font=title_font)

        # 绘制日期
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            date_display = dt.strftime('%Y年%m月%d日')
        except:
            date_display = date_str

        draw.text((50, 220), date_display, fill=accent_color, font=date_font)

        # 绘制副标题
        subtitle = "每日精选 · 智能聚合"
        draw.text((50, 300), subtitle, fill=(154, 164, 178), font=subtitle_font)

        # 绘制底部装饰
        draw.rectangle([50, 446, 850, 450], fill=accent_color)

        # 保存图像
        image.save(output_path, 'JPEG', quality=95)
        print(f"  封面图已生成: {output_path}")
        return True

    except Exception as e:
        print(f"  [WARN] 封面图生成失败: {e}")
        return False


def get_or_create_cover(date_str, cover_type="ai"):
    """
    获取或创建封面图

    Args:
        date_str: 日期字符串
        cover_type: 封面类型 ("ai" 或 "finance")

    Returns:
        str: 封面图路径，失败返回 None
    """
    here = os.path.dirname(os.path.abspath(__file__))
    covers_dir = os.path.join(here, "covers")

    # 确保目录存在
    os.makedirs(covers_dir, exist_ok=True)

    # 生成文件名
    cover_filename = f"{cover_type}_daily_{date_str.replace('-', '')}.jpg"
    cover_path = os.path.join(covers_dir, cover_filename)

    # 如果已存在，直接返回
    if os.path.exists(cover_path):
        return cover_path

    # 生成新封面
    if generate_cover_image(
        title=f"{cover_type.upper()} 日报",
        date_str=date_str,
        output_path=cover_path,
        cover_type=cover_type
    ):
        return cover_path

    return None


def create_default_cover(cover_type="ai"):
    """
    创建默认封面图（纯色背景）

    Args:
        cover_type: 封面类型 ("ai" 或 "finance")

    Returns:
        str: 封面图路径，失败返回 None
    """
    if not PIL_AVAILABLE:
        print("  [WARN] PIL/Pillow 未安装，无法生成默认封面")
        return None

    here = os.path.dirname(os.path.abspath(__file__))
    covers_dir = os.path.join(here, "covers")
    os.makedirs(covers_dir, exist_ok=True)

    cover_path = os.path.join(covers_dir, f"{cover_type}_default.jpg")

    # 如果已存在，直接返回
    if os.path.exists(cover_path):
        return cover_path

    try:
        # 微信公众号封面图尺寸：900x500
        width, height = 900, 500

        # 背景颜色
        if cover_type == "ai":
            bg_color = (91, 157, 255)  # 蓝色
        else:
            bg_color = (240, 180, 41)  # 金色

        # 创建纯色图像
        image = Image.new('RGB', (width, height), bg_color)

        # 保存
        image.save(cover_path, 'JPEG', quality=95)
        print(f"  默认封面已生成: {cover_path}")
        return cover_path

    except Exception as e:
        print(f"  [WARN] 默认封面生成失败: {e}")
        return None


# 测试函数
if __name__ == "__main__":
    print("测试封面图生成...")

    # 测试 AI 日报封面
    ai_cover = get_or_create_cover("2024-01-15", cover_type="ai")
    print(f"AI 日报封面: {ai_cover}")

    # 测试财经日报封面
    finance_cover = get_or_create_cover("2024-01-15", cover_type="finance")
    print(f"财经日报封面: {finance_cover}")

    # 测试默认封面
    default_cover = create_default_cover(cover_type="ai")
    print(f"默认封面: {default_cover}")
