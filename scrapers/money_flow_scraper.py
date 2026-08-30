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

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'http://data.eastmoney.com/'
        }
        self.timeout = 10

    def fetch_north_flow(self):
        """
        获取北向资金数据（沪股通+深股通）

        Returns:
            dict: 北向资金数据
        """
        url = "http://push2.eastmoney.com/api/qt/kamt.rtmin/get"
        params = {
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f56',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
            'cb': 'jQuery'
        }

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()

            # 移除 JSONP 包装
            text = response.text
            json_match = re.search(r'jQuery\d+_\d+\((.*)\)', text)
            if json_match:
                data = json.loads(json_match.group(1))
                return self._parse_north_flow(data)
            else:
                print(f"     [WARN] 北向资金数据格式异常")
                return self._empty_north_flow()

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
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': '1',
            'pz': '50',
            'po': '1',
            'np': '1',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
            'fltt': '2',
            'invt': '2',
            'fid': 'f62',
            'fs': 'm:90+t:2',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124'
        }

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return self._parse_sector_flow(data, top_n)

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
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': '1',
            'pz': str(top_n * 2),
            'po': '1',
            'np': '1',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
            'fltt': '2',
            'invt': '2',
            'fid': 'f62',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124'
        }

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return self._parse_stock_flow(data, top_n)

        except Exception as e:
            print(f"     [WARN] 个股资金流向获取失败: {e}")
            return self._empty_stock_flow()

    def _parse_north_flow(self, data):
        """解析北向资金数据"""
        try:
            if not data or 'data' not in data:
                return self._empty_north_flow()

            flow_data = data['data']

            # f51: 沪股通净流入（元）
            # f52: 深股通净流入（元）
            sh_flow = flow_data.get('f51', 0) / 100000000  # 转换为亿元
            sz_flow = flow_data.get('f52', 0) / 100000000
            total_flow = sh_flow + sz_flow

            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "sh_flow": round(sh_flow, 2),
                "sz_flow": round(sz_flow, 2),
                "total_flow": round(total_flow, 2)
            }

        except Exception as e:
            print(f"     [WARN] 北向资金数据解析失败: {e}")
            return self._empty_north_flow()

    def _parse_sector_flow(self, data, top_n):
        """解析行业资金流向"""
        try:
            if not data or 'data' not in data or 'diff' not in data['data']:
                return self._empty_sector_flow()

            items = data['data']['diff']

            # 按主力净流入排序
            sorted_items = sorted(items, key=lambda x: x.get('f62', 0), reverse=True)

            top_inflow = []
            top_outflow = []

            # Top N 流入
            for item in sorted_items[:top_n]:
                top_inflow.append({
                    "name": item.get('f14', ''),
                    "net_inflow": round(item.get('f62', 0) / 100000000, 2),  # 亿元
                    "change_pct": round(item.get('f3', 0) / 100, 2)  # 涨跌幅
                })

            # Top N 流出
            for item in sorted_items[-top_n:]:
                top_outflow.append({
                    "name": item.get('f14', ''),
                    "net_inflow": round(item.get('f62', 0) / 100000000, 2),
                    "change_pct": round(item.get('f3', 0) / 100, 2)
                })

            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "top_inflow": top_inflow,
                "top_outflow": list(reversed(top_outflow))
            }

        except Exception as e:
            print(f"     [WARN] 行业资金流向数据解析失败: {e}")
            return self._empty_sector_flow()

    def _parse_stock_flow(self, data, top_n):
        """解析个股资金流向"""
        try:
            if not data or 'data' not in data or 'diff' not in data['data']:
                return self._empty_stock_flow()

            items = data['data']['diff']

            # 按主力净流入排序
            sorted_items = sorted(items, key=lambda x: x.get('f62', 0), reverse=True)

            top_inflow = []
            top_outflow = []

            # Top N 流入
            for item in sorted_items[:top_n]:
                top_inflow.append({
                    "code": item.get('f12', ''),
                    "name": item.get('f14', ''),
                    "net_inflow": round(item.get('f62', 0) / 100000000, 2),  # 亿元
                    "change_pct": round(item.get('f3', 0) / 100, 2)  # 涨跌幅
                })

            # Top N 流出
            for item in sorted_items[-top_n:]:
                top_outflow.append({
                    "code": item.get('f12', ''),
                    "name": item.get('f14', ''),
                    "net_inflow": round(item.get('f62', 0) / 100000000, 2),
                    "change_pct": round(item.get('f3', 0) / 100, 2)
                })

            return {
                "date": datetime.now().strftime("%Y-%m-%d"),
                "top_inflow": top_inflow,
                "top_outflow": list(reversed(top_outflow))
            }

        except Exception as e:
            print(f"     [WARN] 个股资金流向数据解析失败: {e}")
            return self._empty_stock_flow()

    def _empty_north_flow(self):
        """返回空的北向资金数据"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "sh_flow": 0,
            "sz_flow": 0,
            "total_flow": 0
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
