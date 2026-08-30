# Phase A3: Artificial Analysis 爬虫增强 - 实施计划

## 📊 当前状态分析

### 已有实现（172行）
✅ **ArtificialAnalysisScraper 类**
- 基础 URL：https://artificialanalysis.ai
- 主方法：`fetch_benchmarks()`
- 数据解析：`_parse_highlights()` + `_parse_from_scripts()`
- 缓存机制：日期缓存 + 历史降级

### 当前数据结构（实际输出）
```json
{
  "source": "artificial_analysis",
  "intelligence": [
    {"model": "Mistral", "score": 4},
    {"model": "Llama", "score": 29}
  ],
  "speed": [],
  "cost": []
}
```

### 目标数据结构（完整计划要求）
```json
{
  "date": "2026-08-30",
  "intelligence": [
    {"model": "Claude Opus 5", "score": 63},
    {"model": "GPT-4", "score": 62}
  ],
  "speed": [
    {"model": "Gemini 2.5 Flash", "tokens_per_sec": 324}
  ],
  "cost": [
    {"model": "Llama 3.3 70B", "cost_per_task": 0.05}
  ]
}
```

---

## 🎯 Phase A3 目标

### 任务清单
- [x] 开发 artificial_analysis_scraper.py（已存在，需增强）
- [ ] 增强首页抓取（Intelligence/Speed/Cost 图表）
- [ ] 抓取 /leaderboards 页面（如果有）
- [ ] 数据解析增强
- [ ] 单元测试更新

---

## 🔍 问题分析

### 问题 1: API 不可用
**现象**：/api/models 返回 404 错误页面

**原因**：Artificial Analysis 没有公开 API

**解决方案**：继续使用网页抓取，但需增强解析逻辑

### 问题 2: 数据不完整
**现象**：
- intelligence 有数据，但模型名称不完整（"Mistral"、"Llama"）
- speed 为空数组
- cost 为空数组

**原因**：
- 当前解析逻辑不够完善
- 可能需要解析不同的页面元素或脚本

### 问题 3: Next.js 客户端渲染
**现象**：页面使用 Next.js 框架，数据可能动态加载

**原因**：数据在客户端 JavaScript 中渲染

---

## 🔧 实施方案

### 方案 A: 增强 HTML 解析（推荐）
**策略**：
1. 手动访问 https://artificialanalysis.ai
2. 检查页面源码和 Network 请求
3. 找到数据源（可能在 `__NEXT_DATA__` 或其他脚本中）
4. 更新解析逻辑

**优势**：
- ✅ 保持轻量级
- ✅ 无需额外依赖

**劣势**：
- ⚠️ 依赖页面结构

### 方案 B: 使用 Playwright（备选）
**策略**：
1. 安装 Playwright
2. 启动无头浏览器
3. 等待页面渲染完成
4. 提取 DOM 数据

**优势**：
- ✅ 支持完全动态页面
- ✅ 可以等待 JavaScript 执行

**劣势**：
- ❌ 需要安装 Chromium
- ❌ 执行时间增加

---

## 📋 实施步骤（方案 A）

### 步骤 1: 手动检查 Artificial Analysis 页面（30分钟）
```bash
# 下载页面源码
curl -A "Mozilla/5.0" https://artificialanalysis.ai > artificial_analysis.html

# 查找 Next.js 数据
grep -o "__NEXT_DATA__.*" artificial_analysis.html | head -1

# 查找图表数据
grep -i "intelligence\|speed\|cost" artificial_analysis.html
```

### 步骤 2: 增强数据解析（60分钟）
根据步骤 1 的发现，更新解析逻辑：

```python
def fetch_benchmarks(self):
    """抓取性能基准数据（增强版）"""
    print("  抓取 Artificial Analysis 数据...")
    
    cached = self.load_cache("artificial_analysis")
    if cached:
        return cached
    
    try:
        # 1. 抓取主页
        html = self._fetch_page(self.base_url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # 2. 尝试多种解析策略
        result = self._parse_next_data(soup)
        
        if not any([result['intelligence'], result['speed'], result['cost']]):
            result = self._parse_highlights(soup)
        
        if not any([result['intelligence'], result['speed'], result['cost']]):
            result = self._parse_tables(soup)
        
        # 3. 添加日期
        result['date'] = datetime.now().strftime("%Y-%m-%d")
        
        # 保存缓存
        self.save_cache("artificial_analysis", result)
        return result
    
    except Exception as e:
        print(f"     [WARN] 抓取失败：{e}")
        return self._load_fallback_cache()
```

### 步骤 3: 添加新的解析方法（60分钟）

```python
def _parse_next_data(self, soup):
    """解析 Next.js 数据"""
    result = {
        "source": "artificial_analysis",
        "intelligence": [],
        "speed": [],
        "cost": []
    }
    
    try:
        script = soup.find('script', id='__NEXT_DATA__')
        if script:
            data = json.loads(script.string)
            
            # 提取路径（需根据实际结构调整）
            page_props = data.get("props", {}).get("pageProps", {})
            
            # Intelligence
            if "intelligenceData" in page_props:
                for item in page_props["intelligenceData"]:
                    result["intelligence"].append({
                        "model": item.get("model", "Unknown"),
                        "score": item.get("score", 0)
                    })
            
            # Speed
            if "speedData" in page_props:
                for item in page_props["speedData"]:
                    result["speed"].append({
                        "model": item.get("model", "Unknown"),
                        "tokens_per_sec": item.get("tokensPerSec", 0)
                    })
            
            # Cost
            if "costData" in page_props:
                for item in page_props["costData"]:
                    result["cost"].append({
                        "model": item.get("model", "Unknown"),
                        "cost_per_task": item.get("costPerTask", 0)
                    })
    
    except Exception as e:
        print(f"     [WARN] Next.js 数据解析失败：{e}")
    
    return result

def _parse_tables(self, soup):
    """解析表格数据（降级方案）"""
    result = {
        "source": "artificial_analysis",
        "intelligence": [],
        "speed": [],
        "cost": []
    }
    
    try:
        # 查找表格
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows[1:]:  # 跳过表头
                cells = row.find_all(['td', 'th'])
                
                if len(cells) >= 2:
                    model_name = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    
                    # 尝试解析数值
                    try:
                        numeric_value = float(re.sub(r'[^\d.]', '', value))
                        
                        # 根据值的范围推断类型
                        if numeric_value > 100:  # 可能是 tokens/sec
                            result["speed"].append({
                                "model": model_name,
                                "tokens_per_sec": numeric_value
                            })
                        elif numeric_value < 1:  # 可能是成本
                            result["cost"].append({
                                "model": model_name,
                                "cost_per_task": numeric_value
                            })
                        else:  # 可能是分数
                            result["intelligence"].append({
                                "model": model_name,
                                "score": numeric_value
                            })
                    except:
                        pass
    
    except Exception as e:
        print(f"     [WARN] 表格解析失败：{e}")
    
    return result
```

### 步骤 4: 更新单元测试（20分钟）

```python
def test_aa_enhanced(self):
    """测试增强后的 Artificial Analysis 数据"""
    data = fetch_aa_data()
    
    # 基础字段验证
    self.assertIn('source', data)
    self.assertEqual(data['source'], 'artificial_analysis')
    
    # 数据结构验证
    self.assertIn('intelligence', data)
    self.assertIn('speed', data)
    self.assertIn('cost', data)
    self.assertIn('date', data)
    
    # 验证数据质量
    if len(data.get('intelligence', [])) > 0:
        intel = data['intelligence'][0]
        self.assertIn('model', intel)
        self.assertIn('score', intel)
    
    print(f"[OK] Artificial Analysis enhanced test passed")
    print(f"  - Date: {data.get('date')}")
    print(f"  - Intelligence: {len(data['intelligence'])} items")
    print(f"  - Speed: {len(data['speed'])} items")
    print(f"  - Cost: {len(data['cost'])} items")
```

### 步骤 5: 本地测试（20分钟）

```bash
# 清除旧缓存
rm data/market_data/artificial_analysis_*.json

# 测试爬虫
python -m scrapers.artificial_analysis_scraper

# 检查输出
cat data/market_data/artificial_analysis_2026-08-30.json | python -m json.tool

# 运行单元测试
python -m unittest tests.test_scrapers -k test_aa
```

---

## 🧪 测试计划

### 测试场景
1. **完整数据** - intelligence + speed + cost 都有数据
2. **部分数据** - 只有部分维度有数据
3. **缓存命中** - 第二次调用读缓存
4. **降级机制** - 网络失败，使用历史缓存

### 验收标准
- [ ] date 字段正确（当前日期）
- [ ] intelligence 字段非空（至少 3 个模型）
- [ ] speed 字段有数据（至少 1 个模型）
- [ ] cost 字段有数据（至少 1 个模型）
- [ ] 模型名称完整（不是片段）
- [ ] 数值类型正确
- [ ] 单元测试通过

---

## ⚠️ 风险与缓解

### 风险 1: 数据完全客户端渲染
- **可能性**: 高
- **影响**: 无法获取完整数据
- **缓解**: 
  - 升级到 Playwright（方案 B）
  - 或者只抓取部分可用数据

### 风险 2: 页面结构复杂
- **可能性**: 中
- **影响**: 解析困难
- **缓解**:
  - 多种解析策略（Next.js + 表格 + Highlights）
  - 降级到历史缓存

### 风险 3: 数据格式不一致
- **可能性**: 中
- **影响**: 解析错误
- **缓解**:
  - 容错解析（try-except）
  - 类型验证

---

## 📝 待办清单

- [ ] 1. 手动检查 Artificial Analysis 页面
- [ ] 2. 定位数据源
- [ ] 3. 增强 _parse_next_data() 方法
- [ ] 4. 添加 _parse_tables() 方法
- [ ] 5. 更新 fetch_benchmarks() 流程
- [ ] 6. 更新单元测试
- [ ] 7. 本地测试验证
- [ ] 8. 提交代码
- [ ] 9. 更新完整计划文档

---

## 🚀 准备退出计划模式

等待用户批准后开始实施。如果方案 A 无法获取足够数据，将升级到方案 B（Playwright）。
