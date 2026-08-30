# -*- coding: utf-8 -*-
"""
交易日历模块
支持 A股和港股的交易日判断
"""
import datetime
from typing import Optional, Literal

# A股休市日（2026年，需要每年更新）
# 数据来源：上交所/深交所公告
A_STOCK_HOLIDAYS_2026 = [
    # 元旦：1月1日-3日
    datetime.date(2026, 1, 1),
    datetime.date(2026, 1, 2),
    datetime.date(2026, 1, 3),
    # 春节：2月16日-22日
    datetime.date(2026, 2, 16),
    datetime.date(2026, 2, 17),
    datetime.date(2026, 2, 18),
    datetime.date(2026, 2, 19),
    datetime.date(2026, 2, 20),
    datetime.date(2026, 2, 21),
    datetime.date(2026, 2, 22),
    # 清明节：4月5日-7日
    datetime.date(2026, 4, 5),
    datetime.date(2026, 4, 6),
    datetime.date(2026, 4, 7),
    # 劳动节：5月1日-5日
    datetime.date(2026, 5, 1),
    datetime.date(2026, 5, 2),
    datetime.date(2026, 5, 3),
    datetime.date(2026, 5, 4),
    datetime.date(2026, 5, 5),
    # 端午节：6月25日-27日
    datetime.date(2026, 6, 25),
    datetime.date(2026, 6, 26),
    datetime.date(2026, 6, 27),
    # 国庆节+中秋节：10月1日-8日
    datetime.date(2026, 10, 1),
    datetime.date(2026, 10, 2),
    datetime.date(2026, 10, 3),
    datetime.date(2026, 10, 4),
    datetime.date(2026, 10, 5),
    datetime.date(2026, 10, 6),
    datetime.date(2026, 10, 7),
    datetime.date(2026, 10, 8),
]

# 港股休市日（2026年，需要每年更新）
# 数据来源：港交所公告
HK_STOCK_HOLIDAYS_2026 = [
    # 元旦：1月1日
    datetime.date(2026, 1, 1),
    # 春节：2月17日-19日
    datetime.date(2026, 2, 17),
    datetime.date(2026, 2, 18),
    datetime.date(2026, 2, 19),
    # 清明节：4月6日
    datetime.date(2026, 4, 6),
    # 耶稣受难日：4月10日
    datetime.date(2026, 4, 10),
    # 复活节翌日：4月13日
    datetime.date(2026, 4, 13),
    # 劳动节：5月1日
    datetime.date(2026, 5, 1),
    # 佛诞：5月26日
    datetime.date(2026, 5, 26),
    # 端午节：6月25日
    datetime.date(2026, 6, 25),
    # 香港特别行政区成立纪念日：7月1日
    datetime.date(2026, 7, 1),
    # 中秋节翌日：10月2日
    datetime.date(2026, 10, 2),
    # 国庆节：10月1日
    datetime.date(2026, 10, 1),
    # 重阳节：10月21日
    datetime.date(2026, 10, 21),
    # 圣诞节：12月25日
    datetime.date(2026, 12, 25),
    # 节礼日：12月26日
    datetime.date(2026, 12, 26),
]


def is_weekend(date: datetime.date) -> bool:
    """判断是否为周末（周六、周日）"""
    return date.weekday() in (5, 6)


def is_trading_day(date: datetime.date, market: Literal['A', 'HK'] = 'A') -> bool:
    """
    判断是否为交易日

    Args:
        date: 日期
        market: 市场类型，'A' (A股) 或 'HK' (港股)

    Returns:
        True: 交易日
        False: 非交易日（周末或节假日）
    """
    # 周末不交易
    if is_weekend(date):
        return False

    # 检查是否为节假日
    holidays = A_STOCK_HOLIDAYS_2026 if market == 'A' else HK_STOCK_HOLIDAYS_2026
    if date in holidays:
        return False

    return True


def get_last_trading_day(date: datetime.date, market: Literal['A', 'HK'] = 'A') -> datetime.date:
    """
    获取上一个交易日

    Args:
        date: 基准日期
        market: 市场类型

    Returns:
        上一个交易日
    """
    current = date - datetime.timedelta(days=1)

    # 向前查找，最多回溯30天
    for _ in range(30):
        if is_trading_day(current, market):
            return current
        current -= datetime.timedelta(days=1)

    # 如果30天内找不到交易日，返回当前日期（异常情况）
    return date


def count_non_trading_days(start_date: datetime.date, end_date: datetime.date,
                          market: Literal['A', 'HK'] = 'A') -> int:
    """
    计算两个日期之间的非交易日天数（不包括start_date，包括end_date）

    Args:
        start_date: 开始日期（上一个交易日）
        end_date: 结束日期（当前日期）
        market: 市场类型

    Returns:
        非交易日天数
    """
    count = 0
    current = start_date + datetime.timedelta(days=1)

    while current <= end_date:
        if not is_trading_day(current, market):
            count += 1
        current += datetime.timedelta(days=1)

    return count


def is_post_holiday_first_day(date: datetime.date, market: Literal['A', 'HK'] = 'A',
                              threshold: int = 3) -> bool:
    """
    判断是否为节后首个交易日（连续休市天数 >= threshold）

    Args:
        date: 日期
        market: 市场类型
        threshold: 连续休市天数阈值，默认3天

    Returns:
        True: 节后首个交易日
        False: 不是节后首日或常规周末后
    """
    # 如果当天不是交易日，不是节后首日
    if not is_trading_day(date, market):
        return False

    # 获取上一个交易日
    last_trading = get_last_trading_day(date, market)

    # 计算连续休市天数
    non_trading_days = count_non_trading_days(last_trading, date - datetime.timedelta(days=1), market)

    return non_trading_days >= threshold


def get_trading_status(date: datetime.date, market: Literal['A', 'HK'] = 'A') -> dict:
    """
    获取交易日状态（综合信息）

    Args:
        date: 日期
        market: 市场类型

    Returns:
        {
            'is_trading_day': bool,
            'last_trading_day': datetime.date,
            'days_since_last_trading': int,
            'is_post_holiday': bool,
            'market_status': str  # 'trading' | 'weekend' | 'holiday' | 'post_holiday'
        }
    """
    is_trading = is_trading_day(date, market)
    last_trading = get_last_trading_day(date, market)
    days_since = (date - last_trading).days
    is_post_holiday = is_post_holiday_first_day(date, market)

    # 确定市场状态
    if is_post_holiday:
        market_status = 'post_holiday'
    elif is_trading:
        market_status = 'trading'
    elif is_weekend(date):
        market_status = 'weekend'
    else:
        market_status = 'holiday'

    return {
        'is_trading_day': is_trading,
        'last_trading_day': last_trading,
        'days_since_last_trading': days_since,
        'is_post_holiday': is_post_holiday,
        'market_status': market_status
    }


def format_date_cn(date: datetime.date) -> str:
    """格式化日期为中文"""
    return date.strftime('%Y年%m月%d日')


if __name__ == '__main__':
    # 测试代码
    import sys

    # 测试日期
    test_dates = [
        datetime.date(2026, 8, 28),  # 假设是周五（交易日）
        datetime.date(2026, 8, 29),  # 假设是周六（周末）
        datetime.date(2026, 10, 1),  # 国庆节
        datetime.date(2026, 10, 9),  # 国庆后首个交易日
    ]

    print("=" * 60)
    print("交易日历模块测试")
    print("=" * 60)

    for test_date in test_dates:
        status = get_trading_status(test_date, market='A')
        print(f"\n日期：{format_date_cn(test_date)}")
        print(f"  是否交易日：{status['is_trading_day']}")
        print(f"  上一交易日：{format_date_cn(status['last_trading_day'])}")
        print(f"  距上次交易：{status['days_since_last_trading']}天")
        print(f"  是否节后首日：{status['is_post_holiday']}")
        print(f"  市场状态：{status['market_status']}")
