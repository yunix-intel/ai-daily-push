# Phase F6: 资金流向数据 - 实施计划

## 📊 当前状态分析

### 已完成的财经日报功能（Phase F1-F5, F7）
✅ **Phase F1**: 交易日历与节假日处理
✅ **Phase F2**: 新闻分类优化  
✅ **Phase F3**: 国际要闻翻译
✅ **Phase F4**: 全文翻译优化
✅ **Phase F5**: UI/UX 优化
✅ **Phase F7**: 测试与优化

### Phase F6 目标
添加资金流向数据，展示市场资金流动情况：
- 北向资金（沪股通+深股通）
- 南向资金（港股通）
- 行业资金流向
- 个股资金流向 Top 10

---

## 🎯 Phase F6 目标

### 核心功能
1. **北向资金数据**
   - 沪股通净流入
   - 深股通净流入
   - 合计净流入
   - 历史对比

2. **南向资金数据**
   - 港股通净流入
   - 趋势分析

3. **行业资金流向**
   - 资金净流入 Top 5 行业
   - 资金净流出 Top 5 行业

4. **个股资金流向**
   - 主力净流入 Top 10
   - 主力净流出 Top 10

---

## 📋 数据源选择

### 选项 1: 东方财富 API（推荐）
**优点**：
- 数据全面（北向/南向/行业/个股）
- 更新及时
- 免费公开 API

**API 端点**：
```python
# 北向资金
URL_NORTH_FLOW = "http://push2.eastmoney.com/api/qt/kamt.rtmin/get"

# 南向资金  
URL_SOUTH_FLOW = "http://push2.eastmoney.com/api/qt/kamt.rtmin/get"

# 行业资金流向
URL_SECTOR_FLOW = "http://push2.eastmoney.com/api/qt/clist/get"

# 个股资金流向
URL_STOCK_FLOW = "http://push2.eastmoney.com/api/qt/clist/get"
```

### 选项 2: 新浪财经
**优点**：
- 简单易用
- 稳定性好

**缺点**：
- 数据不如东方财富全面

### 选项 3: 雪球 API
**优点**：
- 社区数据丰富

**缺点**：
- 需要认证
- 可能有反爬

---

## 🔧 实施步骤

### 步骤 1: 创建资金流向爬虫（1.5小时）

**文件**：`scrapers/money_flow_scraper.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
资金流向数据爬虫
"""
import requests
import json
from datetime import datetime


class MoneyFlowScraper:
    """资金流向爬虫"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def fetch_north_flow(self):
        """获取北向资金数据"""
        url = "http://push2.eastmoney.com/api/qt/kamt.rtmin/get"
        params = {
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f56',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
            'cb': 'jQuery'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            # 解析返回数据
            return self._parse_north_flow(response.text)
        except Exception as e:
            print(f"     [WARN] 北向资金获取失败: {e}")
            return None
    
    def fetch_sector_flow(self, top_n=5):
        """获取行业资金流向"""
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': '1',
            'pz': str(top_n * 2),  # 获取流入和流出各 top_n
            'po': '1',
            'np': '1',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13',
            'fid': 'f62',
            'ut': 'b2884a393a59ad64002292a3e90d46a5'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            return self._parse_sector_flow(response.text, top_n)
        except Exception as e:
            print(f"     [WARN] 行业资金流向获取失败: {e}")
            return None
    
    def fetch_stock_flow(self, top_n=10):
        """获取个股资金流向"""
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': '1',
            'pz': str(top_n * 2),
            'po': '1',
            'np': '1',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124,f1,f13',
            'fid': 'f62',
            'ut': 'b2884a393a59ad64002292a3e90d46a5'
        }
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            return self._parse_stock_flow(response.text, top_n)
        except Exception as e:
            print(f"     [WARN] 个股资金流向获取失败: {e}")
            return None
    
    def _parse_north_flow(self, text):
        """解析北向资金数据"""
        # 实现解析逻辑
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "sh_flow": 0,  # 沪股通净流入（亿元）
            "sz_flow": 0,  # 深股通净流入（亿元）
            "total_flow": 0  # 合计净流入（亿元）
        }
    
    def _parse_sector_flow(self, text, top_n):
        """解析行业资金流向"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "top_inflow": [],  # Top N 流入行业
            "top_outflow": []  # Top N 流出行业
        }
    
    def _parse_stock_flow(self, text, top_n):
        """解析个股资金流向"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "top_inflow": [],  # Top N 流入个股
            "top_outflow": []  # Top N 流出个股
        }


# 测试函数
def test_scraper():
    scraper = MoneyFlowScraper()
    
    print("=== 资金流向数据测试 ===\n")
    
    print("1. 北向资金...")
    north = scraper.fetch_north_flow()
    print(f"   {north}\n")
    
    print("2. 行业资金流向...")
    sector = scraper.fetch_sector_flow(top_n=5)
    print(f"   {sector}\n")
    
    print("3. 个股资金流向...")
    stock = scraper.fetch_stock_flow(top_n=10)
    print(f"   {stock}\n")


if __name__ == "__main__":
    test_scraper()
```

### 步骤 2: 集成到财经日报主流程（1小时）

**修改 finance_daily_push.py**：

```python
# 在主流程中添加
def fetch_money_flow_data():
    """获取资金流向数据"""
    from scrapers.money_flow_scraper import MoneyFlowScraper
    
    scraper = MoneyFlowScraper()
    
    return {
        "north_flow": scraper.fetch_north_flow(),
        "sector_flow": scraper.fetch_sector_flow(top_n=5),
        "stock_flow": scraper.fetch_stock_flow(top_n=10)
    }
```

### 步骤 3: 更新 HTML 模板（1小时）

添加新的板块显示资金流向数据：

```html
<!-- 资金流向板块 -->
<div class="section">
    <h2>💰 资金流向</h2>
    
    <!-- 北向资金 -->
    <div class="money-flow-card">
        <h3>北向资金</h3>
        <div class="flow-stats">
            <div class="flow-item">
                <span>沪股通</span>
                <span class="flow-value positive">+15.2亿</span>
            </div>
            <div class="flow-item">
                <span>深股通</span>
                <span class="flow-value positive">+8.6亿</span>
            </div>
            <div class="flow-item total">
                <span>合计</span>
                <span class="flow-value positive">+23.8亿</span>
            </div>
        </div>
    </div>
    
    <!-- 行业资金流向 -->
    <div class="money-flow-card">
        <h3>行业资金流向</h3>
        <table>
            <thead>
                <tr>
                    <th>行业</th>
                    <th>净流入</th>
                    <th>涨跌幅</th>
                </tr>
            </thead>
            <tbody>
                <!-- 数据行 -->
            </tbody>
        </table>
    </div>
</div>
```

### 步骤 4: 添加 CSS 样式（30分钟）

```css
/* 资金流向样式 */
.money-flow-card {
    background: #f8f9fa;
    padding: 15px;
    border-radius: 8px;
    margin-bottom: 15px;
}

.flow-stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
}

.flow-item {
    text-align: center;
    padding: 10px;
    background: white;
    border-radius: 5px;
}

.flow-value {
    display: block;
    font-size: 18px;
    font-weight: bold;
    margin-top: 5px;
}

.flow-value.positive {
    color: #e74c3c;  /* 红色 */
}

.flow-value.negative {
    color: #27ae60;  /* 绿色 */
}

.flow-item.total {
    grid-column: span 3;
}
```

### 步骤 5: 测试与优化（1小时）

- 数据准确性验证
- 样式调整
- 错误处理
- 缓存机制

---

## 📝 待办清单

- [ ] 1. 创建 money_flow_scraper.py
- [ ] 2. 实现北向资金爬虫
- [ ] 3. 实现行业资金流向爬虫
- [ ] 4. 实现个股资金流向爬虫
- [ ] 5. 集成到主流程
- [ ] 6. 更新 HTML 模板
- [ ] 7. 添加 CSS 样式
- [ ] 8. 测试数据准确性
- [ ] 9. 添加缓存机制
- [ ] 10. 提交代码

---

## ⚠️ 注意事项

### 数据源稳定性
- 东方财富 API 可能会变化
- 需要添加错误处理和降级策略
- 建议添加缓存机制

### 数据更新时间
- 北向资金：交易日实时更新
- 行业/个股：收盘后更新
- 非交易日：显示最近交易日数据

### 显示逻辑
- 正值：红色（流入）
- 负值：绿色（流出）
- 金额单位：亿元
- 保留2位小数

---

## 🚀 预计时间

总计：5-6 小时

准备开始实施。
