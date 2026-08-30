#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向数据抓取模块 - 抓取北向资金、行业资金流向、个股资金流向
"""
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta


class MoneyFlowScraper:
    """资金流向数据抓取器"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    def get_north_capital_flow(self):
        """
        获取北向资金流向数据

        Returns:
            dict: {
                'shanghai': {'net_inflow': 123.45, 'total_inflow': 456.78, 'total_outflow': 333.33},
                'shenzhen': {...},
                'total': {...},
                'update_time': '2024-08-30 15:00:00'
            }
        """
        try:
            # 使用东方财富网 API（示例）
            url = "http://push2.eastmoney.com/api/qt/kamt.rtmin/get"
            params = {
                'fields1': 'f1,f2,f3,f4',
                'fields2': 'f51,f52,f53,f54,f55,f56',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
                'cb': 'callback'
            }

            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(full_url, headers=self.headers)

            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')

            # 去除 callback 包装
            if content.startswith('callback('):
                content = content[9:-2]

            data = json.loads(content)

            # 解析数据
            result = {
                'shanghai': {'net_inflow': 0, 'total_inflow': 0, 'total_outflow': 0},
                'shenzhen': {'net_inflow': 0, 'total_inflow': 0, 'total_outflow': 0},
                'total': {'net_inflow': 0, 'total_inflow': 0, 'total_outflow': 0},
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            if data and 'data' in data:
                flows = data['data']

                # 沪股通
                if 'hgt' in flows:
                    result['shanghai']['net_inflow'] = flows['hgt'].get('f52', 0) / 10000  # 转为亿

                # 深股通
                if 'sgt' in flows:
                    result['shenzhen']['net_inflow'] = flows['sgt'].get('f52', 0) / 10000  # 转为亿

                # 总计
                result['total']['net_inflow'] = result['shanghai']['net_inflow'] + result['shenzhen']['net_inflow']

            return result

        except Exception as e:
            print(f"  [WARN] 北向资金数据抓取失败: {e}")
            return None

    def get_industry_money_flow(self, top_n=10):
        """
        获取行业资金流向 Top N

        Args:
            top_n: 返回前 N 个行业

        Returns:
            list: [
                {'name': '电子', 'net_inflow': 12.34, 'change_pct': 2.5},
                ...
            ]
        """
        try:
            # 使用东方财富网行业资金流向 API（示例）
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'fid': 'f62',
                'po': '1',
                'pz': str(top_n),
                'pn': '1',
                'np': '1',
                'fltt': '2',
                'invt': '2',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
                'fs': 'm:90+t:2',
                'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13'
            }

            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(full_url, headers=self.headers)

            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')

            data = json.loads(content)

            industries = []
            if data and 'data' in data and 'diff' in data['data']:
                for item in data['data']['diff'][:top_n]:
                    industries.append({
                        'name': item.get('f14', '未知'),
                        'net_inflow': item.get('f62', 0) / 10000,  # 转为亿
                        'change_pct': item.get('f3', 0) / 100,  # 转为百分比
                        'main_net_inflow': item.get('f184', 0) / 10000,  # 主力净流入
                    })

            return industries

        except Exception as e:
            print(f"  [WARN] 行业资金流向数据抓取失败: {e}")
            return []

    def get_stock_money_flow(self, top_n=10):
        """
        获取个股资金流向 Top N

        Args:
            top_n: 返回前 N 只股票

        Returns:
            list: [
                {'code': '000001', 'name': '平安银行', 'net_inflow': 1.23, 'change_pct': 3.2},
                ...
            ]
        """
        try:
            # 使用东方财富网个股资金流向 API（示例）
            url = "http://push2.eastmoney.com/api/qt/clist/get"
            params = {
                'fid': 'f62',
                'po': '1',
                'pz': str(top_n),
                'pn': '1',
                'np': '1',
                'fltt': '2',
                'invt': '2',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
                'fs': 'm:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,m:1+t:2+f:!2,m:1+t:23+f:!2',
                'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13'
            }

            full_url = f"{url}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(full_url, headers=self.headers)

            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8')

            data = json.loads(content)

            stocks = []
            if data and 'data' in data and 'diff' in data['data']:
                for item in data['data']['diff'][:top_n]:
                    stocks.append({
                        'code': item.get('f12', ''),
                        'name': item.get('f14', '未知'),
                        'net_inflow': item.get('f62', 0) / 10000,  # 转为亿
                        'change_pct': item.get('f3', 0) / 100,  # 转为百分比
                        'main_net_inflow': item.get('f184', 0) / 10000,  # 主力净流入
                        'price': item.get('f2', 0) / 100,  # 最新价
                    })

            return stocks

        except Exception as e:
            print(f"  [WARN] 个股资金流向数据抓取失败: {e}")
            return []

    def get_all_money_flow_data(self):
        """
        获取所有资金流向数据

        Returns:
            dict: {
                'north_capital': {...},
                'industries': [...],
                'stocks': [...]
            }
        """
        print("  抓取资金流向数据...")

        result = {
            'north_capital': None,
            'industries': [],
            'stocks': []
        }

        # 北向资金
        print("    [1/3] 北向资金...")
        north_capital = self.get_north_capital_flow()
        if north_capital:
            result['north_capital'] = north_capital
            print(f"      ✓ 北向资金净流入: {north_capital['total']['net_inflow']:.2f}亿")

        # 行业资金流向
        print("    [2/3] 行业资金流向 Top 10...")
        industries = self.get_industry_money_flow(top_n=10)
        if industries:
            result['industries'] = industries
            print(f"      ✓ 获取到 {len(industries)} 个行业数据")

        # 个股资金流向
        print("    [3/3] 个股资金流向 Top 10...")
        stocks = self.get_stock_money_flow(top_n=10)
        if stocks:
            result['stocks'] = stocks
            print(f"      ✓ 获取到 {len(stocks)} 只个股数据")

        return result


def format_money_flow_for_html(money_flow_data):
    """
    格式化资金流向数据为 HTML 展示格式

    Args:
        money_flow_data: get_all_money_flow_data() 返回的数据

    Returns:
        str: HTML 字符串
    """
    html_parts = []

    # 北向资金
    if money_flow_data.get('north_capital'):
        nc = money_flow_data['north_capital']
        total_flow = nc['total']['net_inflow']
        flow_direction = "↗" if total_flow > 0 else "↘" if total_flow < 0 else "→"
        flow_color = "#37e0b0" if total_flow > 0 else "#ff4757" if total_flow < 0 else "#9aa4b2"

        html_parts.append(f"""
<div class="money-flow-card">
<h3>💰 北向资金</h3>
<div class="flow-total" style="color:{flow_color}">
<span class="flow-amount">{abs(total_flow):.2f}亿</span> {flow_direction}
</div>
<div class="flow-detail">
<div>沪股通: <span style="color:{'#37e0b0' if nc['shanghai']['net_inflow'] > 0 else '#ff4757'}">{nc['shanghai']['net_inflow']:.2f}亿</span></div>
<div>深股通: <span style="color:{'#37e0b0' if nc['shenzhen']['net_inflow'] > 0 else '#ff4757'}">{nc['shenzhen']['net_inflow']:.2f}亿</span></div>
</div>
<div class="update-time">更新时间: {nc['update_time']}</div>
</div>
""")

    # 行业资金流向
    if money_flow_data.get('industries'):
        html_parts.append('<div class="money-flow-card"><h3>📊 行业资金流向 Top 10</h3><table class="flow-table">')
        html_parts.append('<tr><th>行业</th><th>净流入</th><th>涨跌幅</th></tr>')

        for ind in money_flow_data['industries']:
            flow_color = "#37e0b0" if ind['net_inflow'] > 0 else "#ff4757"
            change_color = "#37e0b0" if ind['change_pct'] > 0 else "#ff4757"
            html_parts.append(f"""
<tr>
<td>{ind['name']}</td>
<td style="color:{flow_color}">{ind['net_inflow']:.2f}亿</td>
<td style="color:{change_color}">{ind['change_pct']:.2f}%</td>
</tr>
""")

        html_parts.append('</table></div>')

    # 个股资金流向
    if money_flow_data.get('stocks'):
        html_parts.append('<div class="money-flow-card"><h3>📈 个股资金流向 Top 10</h3><table class="flow-table">')
        html_parts.append('<tr><th>代码</th><th>名称</th><th>净流入</th><th>涨跌幅</th></tr>')

        for stock in money_flow_data['stocks']:
            flow_color = "#37e0b0" if stock['net_inflow'] > 0 else "#ff4757"
            change_color = "#37e0b0" if stock['change_pct'] > 0 else "#ff4757"
            html_parts.append(f"""
<tr>
<td>{stock['code']}</td>
<td>{stock['name']}</td>
<td style="color:{flow_color}">{stock['net_inflow']:.2f}亿</td>
<td style="color:{change_color}">{stock['change_pct']:.2f}%</td>
</tr>
""")

        html_parts.append('</table></div>')

    return ''.join(html_parts)


# 测试函数
if __name__ == "__main__":
    print("测试资金流向数据抓取...")

    scraper = MoneyFlowScraper()
    data = scraper.get_all_money_flow_data()

    print("\n=== 抓取结果 ===")
    print(json.dumps(data, ensure_ascii=False, indent=2))
