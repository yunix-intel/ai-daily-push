#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交易日状态与节后判据：固定日期回归。

锁死 2026-09-14（周一）→ days_since_last_trading == 3 → 走节后分支；
2026-09-16（周三）→ == 1 → 常规分支。防止判据被改回纯 flag
（flag 在普通周一只数 2 天，会把周一误判成常规交易日，假期回顾消失）。
"""
import datetime
import unittest

from finance_daily_push import generate_strategy, is_post_holiday_session
from trading_calendar import get_trading_status

MONDAY = datetime.date(2026, 9, 14)
WEDNESDAY = datetime.date(2026, 9, 16)


class TestTradingStatusFixedDates(unittest.TestCase):
    def test_monday_gap_is_three_days(self):
        st = get_trading_status(MONDAY, market='A')
        self.assertTrue(st['is_trading_day'])
        self.assertEqual(st['days_since_last_trading'], 3)
        self.assertFalse(st['is_post_holiday'])  # 日历 flag 周一只数 2 天

    def test_midweek_gap_is_one_day(self):
        st = get_trading_status(WEDNESDAY, market='A')
        self.assertTrue(st['is_trading_day'])
        self.assertEqual(st['days_since_last_trading'], 1)

    def test_monday_counts_as_post_holiday_session(self):
        self.assertTrue(is_post_holiday_session(get_trading_status(MONDAY, market='A')))

    def test_midweek_is_regular_session(self):
        self.assertFalse(is_post_holiday_session(get_trading_status(WEDNESDAY, market='A')))

    def test_weekend_strategy_needs_no_llm(self):
        saturday = datetime.date(2026, 9, 12)
        st = get_trading_status(saturday, market='A')
        self.assertEqual(st['market_status'], 'weekend')
        strategy = generate_strategy({"emergencyEvents": []}, {"A股": []}, st)
        self.assertFalse(strategy['is_trading_day'])
        self.assertIn('休市', strategy['aShare'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
