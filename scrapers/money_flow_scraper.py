#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向数据爬虫 - 东方财富数据源
"""
import requests
import json
import re
from datetime import datetime


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

    def fetch_north_flow(self):
        """
        获取北向资金数据（沪股通+深股通）

        注意：沪深交易所自 2024 年 8 月起不再披露北向资金盘中净流入，
        接口只剩占位值，因此这里会把 available 标为 False，由展示层决定是否隐藏，
        避免把「+0.00 亿元」当成真实数据展示。

        Returns:
            dict: 北向资金数据
        """
        params = {'fields1': 'f1,f2,f3,f4', 'fields2': 'f51,f52,f54,f56', 'ut': self.UT}

        try:
            data = self._get_json("/api/qt/kamt/get", params)
            return self._parse_north_flow(data)
        except Exception as e:
            print(f"     [WARN] 北向资金获取失败: {e}")
            return self._empty_north_flow()

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
            "sh_flow": 0,
            "sz_flow": 0,
            "total_flow": 0,
            "available": False,
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
