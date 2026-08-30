#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从官方来源获取交易所休市安排
"""
import json
import urllib.request
import datetime
from typing import List, Optional
import re


def fetch_sse_holidays(year: int) -> List[datetime.date]:
    """
    从上海证券交易所获取休市安排

    数据源：上交所官网 / 或使用第三方整理的数据
    """
    # 方案1: 使用 Tushare / AkShare 等开源数据接口
    # 方案2: 爬取上交所官网公告
    # 方案3: 使用第三方整理的 JSON 数据源

    try:
        # 使用开源的中国节假日数据 API
        # https://github.com/NateScarlet/holiday-cn
        url = f"https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        holidays = []
        for item in data.get('days', []):
            # 只获取非工作日（isOffDay = true）
            if item.get('isOffDay'):
                date_str = item.get('date')
                if date_str:
                    holidays.append(datetime.datetime.strptime(date_str, '%Y-%m-%d').date())

        # 过滤出只有工作日的节假日（排除普通周末）
        filtered = []
        for date in holidays:
            # 如果是工作日（周一到周五）但是休市，才算节假日
            if date.weekday() < 5:
                filtered.append(date)

        return sorted(filtered)

    except Exception as e:
        print(f"从 GitHub 获取节假日数据失败: {e}")
        return []


def fetch_timor_holidays(year: int) -> List[datetime.date]:
    """
    从 Timor API 获取中国节假日数据

    免费API，无需注册
    """
    try:
        url = f"https://timor.tech/api/holiday/year/{year}"

        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))

        holidays = []

        if data.get('code') == 0:
            holiday_data = data.get('holiday', {})

            for date_str, info in holiday_data.items():
                # info: {"holiday": true, "name": "元旦", "wage": 3, "date": "2026-01-01"}
                if info.get('holiday'):
                    date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    # 只保留工作日的节假日
                    if date.weekday() < 5:
                        holidays.append(date)

        return sorted(holidays)

    except Exception as e:
        print(f"从 Timor API 获取节假日数据失败: {e}")
        return []


def fetch_official_holidays(year: int, market: str = 'A') -> List[datetime.date]:
    """
    从官方来源获取节假日数据（多个来源尝试）

    Args:
        year: 年份
        market: 'A' (A股) 或 'HK' (港股)

    Returns:
        节假日列表
    """
    if market == 'A':
        # 尝试多个数据源
        sources = [
            ('Timor API', fetch_timor_holidays),
            ('GitHub holiday-cn', fetch_sse_holidays),
        ]

        for source_name, fetch_func in sources:
            try:
                holidays = fetch_func(year)
                if holidays:
                    print(f"  成功从 {source_name} 获取 {len(holidays)} 个节假日")
                    return holidays
            except Exception as e:
                print(f"  {source_name} 失败: {e}")
                continue

    return []


if __name__ == "__main__":
    # 测试
    print("测试从官方来源获取节假日数据\n")

    for year in [2024, 2025, 2026]:
        print(f"=== {year} 年 ===")
        holidays = fetch_official_holidays(year, 'A')
        print(f"共 {len(holidays)} 个节假日:")
        for h in holidays[:10]:
            print(f"  {h}")
        if len(holidays) > 10:
            print(f"  ... 还有 {len(holidays) - 10} 个")
        print()
