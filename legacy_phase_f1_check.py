#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试财经日报交易日历功能
"""
import sys
import datetime

# 修复 Windows 编码问题
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except:
            pass

sys.path.insert(0, '.')

from trading_calendar import get_trading_status, format_date_cn

print("=" * 60)
print("Phase F1 测试：交易日历与节假日处理")
print("=" * 60)

# 测试场景
test_cases = [
    {
        "date": datetime.date(2026, 8, 28),  # 周五（交易日）
        "expected_status": "trading",
        "desc": "常规交易日"
    },
    {
        "date": datetime.date(2026, 8, 30),  # 周日（周末）
        "expected_status": "weekend",
        "desc": "周末"
    },
    {
        "date": datetime.date(2026, 10, 1),  # 国庆节
        "expected_status": "holiday",
        "desc": "节假日"
    },
    {
        "date": datetime.date(2026, 10, 9),  # 国庆后首个交易日
        "expected_status": "post_holiday",
        "desc": "节后首个交易日"
    },
]

all_passed = True

for i, tc in enumerate(test_cases, 1):
    status = get_trading_status(tc['date'], market='A')

    print(f"\n测试 {i}: {tc['desc']}")
    print(f"  日期: {format_date_cn(tc['date'])}")
    print(f"  预期状态: {tc['expected_status']}")
    print(f"  实际状态: {status['market_status']}")
    print(f"  上一交易日: {format_date_cn(status['last_trading_day'])}")

    if tc['expected_status'] == 'post_holiday':
        passed = status['is_post_holiday']
        print(f"  连续休市: {status['days_since_last_trading']}天")
    else:
        passed = status['market_status'] == tc['expected_status']

    if passed:
        print("  ✓ PASS")
    else:
        print("  ✗ FAIL")
        all_passed = False

print("\n" + "=" * 60)
if all_passed:
    print("✓ Phase F1 所有测试通过")
else:
    print("✗ Phase F1 部分测试失败")
print("=" * 60)

# 测试策略生成逻辑
print("\n" + "=" * 60)
print("测试策略生成函数调用")
print("=" * 60)

from finance_daily_push import generate_strategy

# 模拟数据
mock_analysis = {
    "summary": "市场整体震荡，成交量放大",
    "macro": "央行维持利率不变",
    "sector": "科技板块领涨",
    "emergencyEvents": []
}

mock_quotes = [
    {"name": "上证指数", "price": "3850.25", "change": 32.5, "pct": 0.85},
    {"name": "深证成指", "price": "12345.67", "change": 145.2, "pct": 1.2},
]

# 测试三种情况
for tc in test_cases:
    status = get_trading_status(tc['date'], market='A')
    try:
        strategy = generate_strategy(mock_analysis, mock_quotes, status)
        print(f"\n{tc['desc']} ({format_date_cn(tc['date'])})")
        print(f"  A股策略: {strategy.get('aShare', '')[:50]}...")
        print(f"  策略类型: {'节后首日' if strategy.get('is_post_holiday') else ('休市' if strategy.get('is_trading_day') == False else '常规')}")
        print("  ✓ 策略生成成功")
    except Exception as e:
        print(f"\n{tc['desc']} 策略生成失败: {e}")
        print("  ✗ 策略生成失败")

print("\n" + "=" * 60)
print("Phase F1 测试完成")
print("=" * 60)
