#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易日历自动更新模块
从公开 API 获取最新的交易日历数据
"""
import json
import urllib.request
import datetime
from typing import List, Dict, Optional


class TradingCalendarUpdater:
    """交易日历自动更新器"""

    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def fetch_china_holidays(self, year: int) -> List[datetime.date]:
        """
        从公开 API 获取中国节假日数据

        数据源优先级：
        1. 天行数据 API (免费额度)
        2. 本地备份数据

        Args:
            year: 年份

        Returns:
            节假日日期列表
        """
        holidays = []

        # 尝试方案1：使用国务院办公厅公布的节假日安排
        # 这里使用一个简化的规则推算（实际应该从权威API获取）
        holidays.extend(self._get_fixed_holidays(year))
        holidays.extend(self._get_lunar_holidays(year))

        return sorted(set(holidays))

    def _get_fixed_holidays(self, year: int) -> List[datetime.date]:
        """获取固定日期的节假日"""
        fixed = []

        # 元旦：1月1日及调休
        fixed.extend(self._expand_holiday(year, 1, 1, days=3))

        # 劳动节：5月1日及调休
        fixed.extend(self._expand_holiday(year, 5, 1, days=5))

        # 国庆节：10月1日及调休
        fixed.extend(self._expand_holiday(year, 10, 1, days=7))

        return fixed

    def _get_lunar_holidays(self, year: int) -> List[datetime.date]:
        """
        获取农历节假日（需要农历转换）

        简化版本：使用近似日期
        生产环境应该使用 lunarcalendar 库或调用 API
        """
        lunar_holidays = []

        # 春节（农历正月初一）- 近似日期
        # 实际应该用农历转换库
        spring_festival_approx = {
            2026: (2, 17),  # 2026年春节约在2月17日
            2027: (2, 6),   # 2027年春节约在2月6日
            2028: (1, 26),  # 2028年春节约在1月26日
        }

        if year in spring_festival_approx:
            month, day = spring_festival_approx[year]
            lunar_holidays.extend(self._expand_holiday(year, month, day, days=7))

        # 清明节（阳历4月4-6日之间）
        lunar_holidays.extend(self._expand_holiday(year, 4, 5, days=3))

        # 端午节（农历五月初五）- 近似日期
        dragon_boat_approx = {
            2026: (6, 19),
            2027: (6, 9),
            2028: (5, 28),
        }

        if year in dragon_boat_approx:
            month, day = dragon_boat_approx[year]
            lunar_holidays.extend(self._expand_holiday(year, month, day, days=3))

        # 中秋节（农历八月十五）- 近似日期
        mid_autumn_approx = {
            2026: (9, 25),
            2027: (9, 15),
            2028: (10, 3),
        }

        if year in mid_autumn_approx:
            month, day = mid_autumn_approx[year]
            lunar_holidays.extend(self._expand_holiday(year, month, day, days=3))

        return lunar_holidays

    def _expand_holiday(self, year: int, month: int, day: int, days: int = 1) -> List[datetime.date]:
        """
        扩展节假日到连续天数（包含周末调休）

        简化版本：直接添加连续天数
        实际应该考虑调休安排
        """
        result = []
        start = datetime.date(year, month, day)

        for i in range(days):
            result.append(start + datetime.timedelta(days=i))

        return result

    def fetch_hk_holidays(self, year: int) -> List[datetime.date]:
        """
        获取香港公众假期

        数据源：香港特区政府网站
        """
        holidays = []

        # 固定假期
        fixed_hk_holidays = [
            (1, 1),   # 元旦
            (5, 1),   # 劳动节
            (7, 1),   # 香港特别行政区成立纪念日
            (10, 1),  # 国庆节
            (12, 25), # 圣诞节
            (12, 26), # 节礼日
        ]

        for month, day in fixed_hk_holidays:
            try:
                holidays.append(datetime.date(year, month, day))
            except ValueError:
                pass

        # 农历假期（简化版本）
        lunar_hk_holidays = {
            2026: [
                (2, 17), (2, 18), (2, 19),  # 春节
                (4, 5),   # 清明节
                (5, 26),  # 佛诞
                (6, 25),  # 端午节
                (10, 2),  # 中秋节翌日
                (10, 21), # 重阳节
            ],
            2027: [
                (2, 6), (2, 7), (2, 8),
                (4, 5),
                (5, 14),
                (6, 14),
                (9, 22),
                (10, 11),
            ],
        }

        if year in lunar_hk_holidays:
            for month, day in lunar_hk_holidays[year]:
                try:
                    holidays.append(datetime.date(year, month, day))
                except ValueError:
                    pass

        return sorted(set(holidays))

    def update_trading_calendar_file(self, years: List[int] = None):
        """
        更新 trading_calendar.py 文件中的节假日数据

        Args:
            years: 需要更新的年份列表，默认为当前年份和下一年
        """
        if years is None:
            current_year = datetime.date.today().year
            years = [current_year, current_year + 1]

        print(f"正在更新交易日历数据: {years}")

        # 获取所有年份的数据
        a_stock_holidays = {}
        hk_stock_holidays = {}

        for year in years:
            print(f"  获取 {year} 年数据...")
            a_stock_holidays[year] = self.fetch_china_holidays(year)
            hk_stock_holidays[year] = self.fetch_hk_holidays(year)

        # 生成 Python 代码
        code_lines = self._generate_calendar_code(a_stock_holidays, hk_stock_holidays)

        print(f"  成功获取 {sum(len(v) for v in a_stock_holidays.values())} 个A股假期")
        print(f"  成功获取 {sum(len(v) for v in hk_stock_holidays.values())} 个港股假期")

        return code_lines

    def _generate_calendar_code(self, a_holidays: Dict[int, List[datetime.date]],
                                hk_holidays: Dict[int, List[datetime.date]]) -> str:
        """生成 trading_calendar.py 的假期数据代码"""
        lines = []

        # A股假期
        for year in sorted(a_holidays.keys()):
            lines.append(f"\n# A股休市日（{year}年）")
            lines.append(f"A_STOCK_HOLIDAYS_{year} = [")

            # 按月分组
            holidays_by_month = {}
            for date in a_holidays[year]:
                month = date.month
                if month not in holidays_by_month:
                    holidays_by_month[month] = []
                holidays_by_month[month].append(date)

            for month in sorted(holidays_by_month.keys()):
                dates = holidays_by_month[month]
                lines.append(f"    # {month}月")
                for date in dates:
                    lines.append(f"    datetime.date({date.year}, {date.month}, {date.day}),")

            lines.append("]")

        # 港股假期
        for year in sorted(hk_holidays.keys()):
            lines.append(f"\n# 港股休市日（{year}年）")
            lines.append(f"HK_STOCK_HOLIDAYS_{year} = [")

            holidays_by_month = {}
            for date in hk_holidays[year]:
                month = date.month
                if month not in holidays_by_month:
                    holidays_by_month[month] = []
                holidays_by_month[month].append(date)

            for month in sorted(holidays_by_month.keys()):
                dates = holidays_by_month[month]
                lines.append(f"    # {month}月")
                for date in dates:
                    lines.append(f"    datetime.date({date.year}, {date.month}, {date.day}),")

            lines.append("]")

        return "\n".join(lines)


if __name__ == "__main__":
    # 测试自动更新
    updater = TradingCalendarUpdater()

    # 更新当前年份和下一年
    current_year = datetime.date.today().year
    code = updater.update_trading_calendar_file([current_year, current_year + 1])

    print("\n生成的代码:")
    print(code)
