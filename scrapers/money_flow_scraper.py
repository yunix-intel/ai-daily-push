#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向数据爬虫 - 东方财富数据源
"""
import requests
import json
import re
from datetime import datetime, date
import math
import os


class MoneyFlowScraper:
    """资金流向爬虫"""

    # 东财主站对 http:// 直接回 502，且单个 host 经常抽风，按序做故障转移。
    API_HOSTS = [
        "https://push2delay.eastmoney.com",
        "https://push2.eastmoney.com",
        "https://82.push2.eastmoney.com",
    ]
    UT = 'b2884a393a59ad64002292a3e90d46a5'

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://data.eastmoney.com/'
        }
        self.timeout = 15

    def _get_json(self, path, params):
        """按 host 列表依次尝试，第一个成功返回 JSON 的即用。全挂则抛最后一个异常。"""
        last_exc = None
        for host in self.API_HOSTS:
            try:
                response = requests.get(f"{host}{path}", params=params,
                                        headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_exc = exc
                continue
        raise last_exc

    def _clist(self, fs, page_size, ascending=False):
        """拉取资金流排行。ascending=True 取净流出榜。

        必须单独请求一次升序：接口本身按 fid 降序返回，
        在降序结果的尾部取「流出」拿到的其实还是净流入的条目。
        """
        params = {
            'pn': '1',
            'pz': str(page_size),
            'po': '0' if ascending else '1',
            'np': '1',
            'ut': self.UT,
            'fltt': '2',
            'invt': '2',
            'fid': 'f62',
            'fs': fs,
            'fields': 'f12,f14,f2,f3,f62,f184',
        }
        data = self._get_json("/api/qt/clist/get", params)
        if not data or not data.get('data') or not data['data'].get('diff'):
            return []
        return data['data']['diff']

    def fetch_north_flow(self, target_date=None):
        """获取最近已收盘交易日的北向资金日数据。"""
        target = self._resolve_target_date(target_date)
        errors = []
        for source, fetcher in (("eastmoney", self._fetch_eastmoney_post_close),
                                ("10jqka", self._fetch_10jqka_post_close)):
            try:
                result = fetcher(target)
                if result and result.get("available"):
                    result["attempted_sources"] = [source]
                    return result
                errors.append(f"{source}:未返回有效盘后数据")
            except Exception as exc:
                errors.append(f"{source}:{type(exc).__name__}")
        return self._empty_north_flow(
            "；".join(errors) or "东方财富和同花顺均未返回有效盘后数据"
        )

    def _resolve_target_date(self, target_date=None):
        if target_date:
            return target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
        current = datetime.now().date()
        try:
            from trading_calendar import get_last_trading_day
            # 日报在北京时间 07:00 运行，当日市场尚未收盘；该函数会从
            # 基准日的前一天开始回溯，因此直接传入今天即可得到最近已收盘交易日。
            return get_last_trading_day(current).isoformat()
        except Exception:
            return current.isoformat()

    def _fetch_eastmoney_post_close(self, target_date):
        params = {'fields1': 'f1,f2,f3,f4', 'fields2': 'f51,f52,f53,f54,f55,f56',
                  'klt': '101', 'lmt': '30', 'ut': self.UT}
        data = self._get_json("/api/qt/kamt.kline/get", params)
        return self._parse_post_close_kline(data, target_date, "eastmoney")

    def _fetch_10jqka_post_close(self, target_date):
        """读取同花顺公开的北向资金日线接口。"""
        url = "https://data.10jqka.com.cn/hsgt/history/type/north/date/day/"
        response = requests.get(url, headers={**self.headers, "Referer": "https://data.10jqka.com.cn/hsgt/"},
                                timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        daily = ((payload.get("data") or {}).get("zhuri") or {})
        dates = daily.get("date") or []
        index = next((i for i, value in enumerate(dates) if str(value) == target_date), None)
        if index is None:
            raise ValueError("同花顺盘后记录日期不匹配")
        sh = self._num((daily.get("h") or [])[index]) / 100000000
        total = self._num((daily.get("total") or [])[index]) / 100000000
        sz = total - sh
        if not all(math.isfinite(value) for value in (sh, sz, total)):
            raise ValueError("同花顺盘后数据不是有限数值")
        return {"date": target_date, "trade_date": target_date,
                "sh_flow": round(sh, 2), "sz_flow": round(sz, 2),
                "total_flow": round(total, 2), "available": True,
                "collection_mode": "post_close", "source": "10jqka",
                "reason": "", "stale": False}

    def _parse_post_close_kline(self, data, target_date, source):
        rows = (data or {}).get("data", {}).get("hk2sh", [])
        sz_rows = (data or {}).get("data", {}).get("hk2sz", [])
        if isinstance(rows, dict):
            rows = [f"{target_date},{rows.get('dayNetAmtIn', 0)},0,0"]
        if isinstance(sz_rows, dict):
            sz_rows = [f"{target_date},{sz_rows.get('dayNetAmtIn', 0)},0,0"]
        sh = next((row for row in rows if str(row).split(",", 1)[0] == target_date), None)
        sz = next((row for row in sz_rows if str(row).split(",", 1)[0] == target_date), None)
        if not sh or not sz:
            raise ValueError("盘后数据日期不匹配")
        sh_value = self._num(str(sh).split(",")[1]) / 100000000
        sz_value = self._num(str(sz).split(",")[1]) / 100000000
        if sh_value == 0 and sz_value == 0:
            raise ValueError("东方财富仅返回北向占位零值")
        return {"date": target_date, "trade_date": target_date,
                "sh_flow": round(sh_value, 2), "sz_flow": round(sz_value, 2),
                "total_flow": round(sh_value + sz_value, 2), "available": True,
                "collection_mode": "post_close", "source": source,
                "reason": "", "stale": False}

    def fetch_sector_flow(self, top_n=5):
        """
        获取行业资金流向

        Args:
            top_n: 返回前 N 个行业

        Returns:
            dict: 行业资金流向数据
        """
        try:
            inflow = self._clist('m:90+t:2', top_n)
            outflow = self._clist('m:90+t:2', top_n, ascending=True)
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "top_inflow": [self._shape_flow(x) for x in inflow[:top_n]],
                "top_outflow": [self._shape_flow(x) for x in outflow[:top_n]],
            }
        except Exception as e:
            print(f"     [WARN] 行业资金流向获取失败: {e}")
            return self._empty_sector_flow()

    def fetch_stock_flow(self, top_n=10):
        """
        获取个股资金流向

        Args:
            top_n: 返回前 N 个个股

        Returns:
            dict: 个股资金流向数据
        """
        fs = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
        try:
            inflow = self._clist(fs, top_n)
            outflow = self._clist(fs, top_n, ascending=True)
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "top_inflow": [self._shape_flow(x, with_code=True) for x in inflow[:top_n]],
                "top_outflow": [self._shape_flow(x, with_code=True) for x in outflow[:top_n]],
            }
        except Exception as e:
            print(f"     [WARN] 个股资金流向获取失败: {e}")
            return self._empty_stock_flow()

    @staticmethod
    def _num(value):
        """东财在停牌/无数据时会返回 '-'，统一转成 0。"""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _shape_flow(self, item, with_code=False):
        """整形单条资金流记录。

        f62 主力净流入（元）→ 亿元；f184 主力净占比（%）；
        f3 涨跌幅在 fltt=2 下已经是百分数，再除 100 会把 +4.4% 变成 +0.04%。
        """
        shaped = {
            "name": item.get('f14', ''),
            "net_inflow": round(self._num(item.get('f62')) / 100000000, 2),
            "change_pct": round(self._num(item.get('f3')), 2),
            "net_ratio": round(self._num(item.get('f184')), 2),
        }
        if with_code:
            shaped["code"] = item.get('f12', '')
        return shaped

    def _parse_north_flow(self, data):
        """解析北向资金数据"""
        try:
            flow_data = (data or {}).get('data') or {}

            # 新版接口按通道拆开：hk2sh / hk2sz 才是「北向」（外资买入 A 股）。
            # dayNetAmtIn 单位为元。
            sh_flow = self._num((flow_data.get('hk2sh') or {}).get('dayNetAmtIn')) / 100000000
            sz_flow = self._num((flow_data.get('hk2sz') or {}).get('dayNetAmtIn')) / 100000000
            total_flow = sh_flow + sz_flow

            # 两个通道都是 0 基本可以断定是停止披露后的占位值，不是「刚好零流入」
            available = bool(sh_flow or sz_flow)
            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "sh_flow": round(sh_flow, 2),
                "sz_flow": round(sz_flow, 2),
                "total_flow": round(total_flow, 2),
                "available": available,
                # 带上原因，展示层才能说明「为什么没有」，而不是整块静默消失
                "reason": "" if available else "沪深交易所已停止披露北向资金盘中净流入",
            }

        except Exception as e:
            print(f"     [WARN] 北向资金数据解析失败: {e}")
            return self._empty_north_flow()

    def _empty_north_flow(self, reason="北向资金数据暂不可用"):
        """返回空的北向资金数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "trade_date": None,
            "sh_flow": 0,
            "sz_flow": 0,
            "total_flow": 0,
            "available": False,
            "collection_mode": "post_close",
            "source": "none",
            "stale": False,
            "reason": reason,
        }

    def _empty_sector_flow(self):
        """返回空的行业资金流向数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "top_inflow": [],
            "top_outflow": []
        }

    def _empty_stock_flow(self):
        """返回空的个股资金流向数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "top_inflow": [],
            "top_outflow": []
        }


# 测试函数
def test_scraper():
    """测试爬虫功能"""
    print("=== 资金流向数据测试 ===\n")

    scraper = MoneyFlowScraper()

    print("1. 测试北向资金...")
    north = scraper.fetch_north_flow()
    print(f"   日期: {north['date']}")
    print(f"   沪股通: {north['sh_flow']} 亿元")
    print(f"   深股通: {north['sz_flow']} 亿元")
    print(f"   合计: {north['total_flow']} 亿元\n")

    print("2. 测试行业资金流向（Top 5）...")
    sector = scraper.fetch_sector_flow(top_n=5)
    print(f"   日期: {sector['date']}")
    print(f"   Top 流入: {len(sector['top_inflow'])} 个行业")
    print(f"   Top 流出: {len(sector['top_outflow'])} 个行业")
    if sector['top_inflow']:
        print(f"   最大流入: {sector['top_inflow'][0]['name']} ({sector['top_inflow'][0]['net_inflow']} 亿)\n")

    print("3. 测试个股资金流向（Top 10）...")
    stock = scraper.fetch_stock_flow(top_n=10)
    print(f"   日期: {stock['date']}")
    print(f"   Top 流入: {len(stock['top_inflow'])} 只个股")
    print(f"   Top 流出: {len(stock['top_outflow'])} 只个股")
    if stock['top_inflow']:
        print(f"   最大流入: {stock['top_inflow'][0]['name']} ({stock['top_inflow'][0]['net_inflow']} 亿)")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    test_scraper()
