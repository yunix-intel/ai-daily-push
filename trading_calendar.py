# -*- coding: utf-8 -*-
"""
交易日历模块
支持 A股和港股的交易日判断

节假日数据会自动从在线 API 获取并缓存
缓存失效或获取失败时，回退到本地预设数据
"""
import datetime
import json
import os
import urllib.request
from typing import Optional, Literal, List

# 缓存目录
CACHE_DIR = os.path.join(os.path.dirname(__file__), '.cache')
CACHE_FILE = os.path.join(CACHE_DIR, 'trading_calendar_cache.json')
CACHE_EXPIRY_DAYS = 30  # 缓存30天


def _ensure_cache_dir():
    """确保缓存目录存在"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)


def _load_cache() -> dict:
    """加载缓存的交易日历数据"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            # 检查缓存是否过期
            cache_time = datetime.datetime.fromisoformat(cache.get('update_time', '2000-01-01'))
            if datetime.datetime.now() - cache_time < datetime.timedelta(days=CACHE_EXPIRY_DAYS):
                return cache
    except Exception:
        pass
    return {}


def _save_cache(cache: dict):
    """保存交易日历数据到缓存"""
    try:
        _ensure_cache_dir()
        cache['update_time'] = datetime.datetime.now().isoformat()
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _fetch_official_holidays_from_github(year: int) -> List[datetime.date]:
    """
    从 GitHub holiday-cn 获取官方节假日数据

    数据来源：https://github.com/NateScarlet/holiday-cn
    这是根据国务院办公厅每年发布的节假日安排整理的开源数据
    """
    try:
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
                    date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    # 只保留工作日的节假日（排除普通周末）
                    if date_obj.weekday() < 5:
                        holidays.append(date_obj)

        return sorted(holidays)

    except Exception as e:
        return []


def _fetch_online_holidays(year: int, market: str = 'A') -> tuple[List[datetime.date], Optional[datetime.date]]:
    """
    从在线数据源获取交易日历数据

    数据源优先级：
    1. GitHub holiday-cn（官方数据，最可靠）
    2. 东方财富网 API（实时数据，用于验证）

    Returns:
        (节假日列表, API数据的最后日期)
    """
    if market != 'A':
        # 港股暂时使用原有逻辑
        return [], None

    # 优先使用 GitHub holiday-cn（官方数据）
    github_holidays = _fetch_official_holidays_from_github(year)

    if github_holidays:
        # 成功获取官方数据，返回完整年份的数据
        return github_holidays, datetime.date(year, 12, 31)

    # 降级：使用东方财富网 API
    try:
        if market == 'A':
            # 使用东方财富网交易日历 API
            url = f"http://push2his.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55,f56,f57,f58&klt=101&fqt=0&beg={year}0101&end={year}1231"

            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            if data and 'data' in data and 'klines' in data['data']:
                trading_days = set()
                last_trading_date = None

                for kline in data['data']['klines']:
                    date_str = kline.split(',')[0]  # YYYY-MM-DD
                    date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                    trading_days.add(date_obj)

                    # 记录最后一个交易日
                    if last_trading_date is None or date_obj > last_trading_date:
                        last_trading_date = date_obj

                # 计算节假日：工作日（周一到周五）且不在交易日列表中的日期
                # 只计算到 API 数据覆盖的日期范围
                holidays = []
                start = datetime.date(year, 1, 1)
                # 只统计到 API 数据的最后日期，避免误判未来的交易日
                end = last_trading_date if last_trading_date else datetime.date(year, 12, 31)
                current = start

                while current <= end:
                    # 是工作日（不是周末），但不是交易日 = 节假日
                    if current.weekday() < 5 and current not in trading_days:
                        holidays.append(current)
                    current += datetime.timedelta(days=1)

                return holidays, last_trading_date
    except Exception as e:
        print(f"  [WARN] 在线获取交易日历失败: {e}")

    return [], None


def _get_holidays_for_year(year: int, market: Literal['A', 'HK'] = 'A') -> List[datetime.date]:
    """
    获取指定年份的节假日列表（自动缓存）

    优先级：
    1. 缓存数据（30天内有效）
    2. 在线 API 获取 + 本地预设数据补充
    3. 纯本地预设数据（2026年）
    """
    # 尝试从缓存加载
    cache = _load_cache()
    cache_key = f"{market}_{year}"

    if cache_key in cache:
        try:
            return [datetime.datetime.strptime(d, '%Y-%m-%d').date() for d in cache[cache_key]]
        except Exception:
            pass

    # 尝试在线获取
    online_holidays, last_date = _fetch_online_holidays(year, market)

    # 获取本地预设数据
    local_holidays = []
    if year == 2026:
        if market == 'A':
            local_holidays = A_STOCK_HOLIDAYS_2026
        else:
            local_holidays = HK_STOCK_HOLIDAYS_2026

    if online_holidays and last_date:
        # 合并策略：
        # - API 数据覆盖范围内：使用 API 数据
        # - API 数据之后：使用本地预设数据
        merged_holidays = set(online_holidays)

        # 添加 API 数据之后的本地预设节假日
        for holiday in local_holidays:
            if holiday > last_date:
                merged_holidays.add(holiday)

        final_holidays = sorted(merged_holidays)

        # 保存到缓存
        cache[cache_key] = [d.isoformat() for d in final_holidays]
        cache[f"{cache_key}_last_date"] = last_date.isoformat()
        _save_cache(cache)

        return final_holidays

    # 回退到纯本地预设数据
    if local_holidays:
        return local_holidays

    # 如果没有数据，返回空列表（只依赖周末判断）
    return []


def _get_last_api_date(year: int, market: Literal['A', 'HK'] = 'A') -> Optional[datetime.date]:
    """获取 API 数据的最后日期（从缓存读取）"""
    cache = _load_cache()
    cache_key = f"{market}_{year}_last_date"

    if cache_key in cache:
        try:
            return datetime.datetime.strptime(cache[cache_key], '%Y-%m-%d').date()
        except Exception:
            pass

    return None


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
    判断是否为交易日（自动从在线 API 获取最新数据）

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

    # 获取该年份的节假日列表（自动缓存）
    year = date.year
    holidays = _get_holidays_for_year(year, market)

    # 检查是否为节假日
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


# ==================== 交易时间判断（盘中信息过滤） ====================

# 北京时间 UTC+8
BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))

# A股交易时段
A_SHARE_SESSIONS = [
    (datetime.time(9, 30), datetime.time(11, 30)),   # 上午
    (datetime.time(13, 0), datetime.time(15, 0)),    # 下午
]


def is_trading_hour(dt=None, market='A'):
    """
    判断是否为交易时间

    Args:
        dt: 日期时间对象，默认为当前时间
        market: 市场代码，默认'A'（A股）

    Returns:
        bool: 是否在交易时段
    """
    if dt is None:
        dt = datetime.datetime.now(BEIJING_TZ)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING_TZ)
    else:
        dt = dt.astimezone(BEIJING_TZ)

    # 检查是否为交易日
    if not is_trading_day(dt.date(), market):
        return False

    # 检查是否在交易时段
    current_time = dt.time()

    if market == 'A':
        sessions = A_SHARE_SESSIONS
    else:
        return False  # 暂不支持其他市场

    for start, end in sessions:
        if start <= current_time <= end:
            return True

    return False


def is_intraday_news(title, summary, pub_time=None):
    """
    判断是否为盘中实时新闻

    Args:
        title: 新闻标题
        summary: 新闻摘要
        pub_time: 发布时间（可选）

    Returns:
        bool: 是否为盘中新闻
    """
    content = title + ' ' + summary

    # 盘中关键词
    intraday_keywords = [
        '盘中', '尾盘', '开盘', '盘前', '午盘',
        '涨停', '跌停', '炸板', '封板',
        '直线拉升', '快速拉升', '急跌', '跳水',
        '异动', '盘面', '盘口'
    ]

    # 如果包含盘中关键词
    if any(kw in content for kw in intraday_keywords):
        # 如果有发布时间，检查是否为交易时间
        if pub_time:
            return is_trading_hour(pub_time)
        else:
            # 没有发布时间，保守判断为盘中新闻
            return True

    return False

