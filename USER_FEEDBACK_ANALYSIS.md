# v3.0.1 用户反馈问题分析

**反馈时间**: 2026-08-31 11:30推送后  
**版本**: v3.0.1

---

## 问题清单

### 问题1: 只收到AI日报，没有财经日报 ⚠️

**现象**:
- 11:30 UTC (19:30北京时间) 只收到AI日报推送
- 财经日报未推送

**原因分析**:

查看workflow配置：
```yaml
# .github/workflows/daily.yml
- name: 第二条：财经日报（markdown + 财经网页）
  continue-on-error: true  # ← 关键：失败不影响整体
```

**`continue-on-error: true`** 意味着：
- ✅ 财经日报失败不会让整个workflow标红
- ❌ 但也意味着失败被静默忽略，用户收不到

**可能的失败原因**:
1. 数据源访问超时（akshare/新浪财经）
2. LLM API调用失败或超时
3. 行情数据解析错误
4. 运行时间超过GitHub Actions限制

**验证方法**:
```bash
# 查看最新运行日志
gh run view <run-id> --log | grep -A 20 "第二条：财经日报"
```

**当前状态**: 运行ID 33358370799 还在进行中，无法查看完整日志

---

### 问题2: 翻译全文链接存在但可能不好用 ⚠️

**现象**:
- 页面有"翻译全文 ↗"链接
- 可能用户体验不好

**代码检查**:

从HTML源码看，翻译链接**确实存在**：
```javascript
// ai_daily_dashboard.html Line 226
const tp=safeUrl(it.translatedPage||'');
'<a class="orig" href="'+esc(tp)+'" target="_blank">翻译全文 ↗</a>'
```

**实际链接示例**:
```
https://translate.google.com/translate?sl=auto&tl=zh-CN&u=https%3A%2F%2Fventurebeat.com%2Fai%2F...
```

**潜在问题**:
1. ✅ Google Translate在国内可能无法访问
2. ✅ 翻译质量可能不如机器翻译（MyMemory）
3. ✅ 用户期望的可能是"中文全文"而非Google翻译页面

**改进建议**:
- 方案A: 使用国内可访问的翻译服务
- 方案B: 直接显示翻译后的全文摘要（扩展summary长度）
- 方案C: 移除"翻译全文"链接，只保留"阅读原文"

---

### 问题3: 缺少ARR、Token数、费用统计和分类 ❌

**现象**:
- 页面中看不到ARR、Token、费用等统计数据
- 分类（category）缺失

#### 3.1 ARR/Token数据问题

**代码中有渲染逻辑**:
```javascript
// ai_daily_push.py Line 648-668
if(newsMetrics.ARR&&newsMetrics.ARR.length>0){
  main+='<div class="block"><h2>💰 ARR / 营收数据</h2><ul>...';
}
```

**实际数据检查**:
```bash
# 检查生成的HTML中是否有ARR数据
grep '"ARR":\[' ai_daily_dashboard.html
# 结果：(无输出)
```

**结论**: 
- ✅ 渲染代码存在
- ❌ **数据为空** `newsMetrics.ARR` 是空数组 `[]`

**根本原因**: 从新闻中提取指标的函数未能提取到数据

```python
# ai_daily_push.py Line 1011
print("[1.6/4] 从新闻提取关键指标（ARR/Token/用户数等）...")
news_metrics = extract_news_metrics(report)
```

**可能的原因**:
1. 提取逻辑不够准确（关键词匹配失败）
2. LLM提取功能未启用或失败
3. 今日新闻中确实没有ARR/Token相关内容
4. 提取后的数据格式不正确

#### 3.2 分类（category）问题

**代码检查**:
```bash
grep '"category"' ai_daily_dashboard.html
# 结果：(无输出)
```

**数据结构**:
```javascript
// 当前数据结构
{
  "idx": 1,
  "title": "...",
  "summary": "...",
  "source": "...",
  // ❌ 缺少 "category" 字段
}
```

**原因**: 数据生成时**没有添加category字段**

**应该有的字段**:
```python
item = {
    "idx": idx,
    "title": title,
    "summary": summary,
    "category": "产品发布",  # ← 缺失
    "source": source,
    ...
}
```

---

## 问题优先级分析

| 问题 | 严重性 | 影响 | 优先级 |
|------|--------|------|--------|
| 财经日报未推送 | High | 用户只收到一半内容 | **P0** |
| 缺少ARR/Token统计 | Medium | 功能不完整 | **P1** |
| 缺少分类信息 | Medium | 信息组织不清晰 | **P1** |
| 翻译全文体验差 | Low | 有替代方案（原文） | P2 |

---

## 修复建议

### P0 - 财经日报未推送（立即修复）

#### 方案1: 添加失败通知（推荐）
```yaml
# .github/workflows/daily.yml
- name: 第二条：财经日报
  id: finance_daily
  continue-on-error: true
  run: python finance_daily_push.py

- name: 财经日报失败通知
  if: steps.finance_daily.outcome == 'failure'
  run: |
    python -c "
    from alerting import send_alert
    send_alert('WARNING', '财经日报生成失败', 
               '请查看GitHub Actions日志排查问题')
    "
```

#### 方案2: 增加超时和重试
```python
# finance_daily_push.py
@retry(max_attempts=3, delay=5)
def fetch_market_data():
    # 增加超时设置
    # 失败时重试
```

#### 方案3: 降级方案
```python
# 如果LLM失败，仍然推送基础行情数据
if llm_analysis_failed:
    # 只推送行情表格，不推送分析
    push_basic_quotes()
```

---

### P1 - 添加ARR/Token统计数据

**问题定位**:
```python
# ai_daily_push.py
def extract_news_metrics(report):
    """从新闻中提取关键指标"""
    # 当前实现可能过于简单
    # 需要增强提取逻辑
```

**修复方案**:

#### 方案A: 增强关键词匹配
```python
def extract_news_metrics(report):
    metrics = {
        "ARR": [],
        "用户数": [],
        "Token数": [],
        "融资": [],
        "市场份额": []
    }
    
    # 扩展关键词列表
    arr_patterns = [
        r'(\$[\d.]+[BMK]?)\s*(ARR|annual recurring revenue)',
        r'(\d+亿美元)\s*(年度经常性收入|ARR)',
        r'revenue.*?(\$[\d.]+[BMK]?)',
    ]
    
    token_patterns = [
        r'([\d.]+[BMT]?)\s*tokens?',
        r'(\d+亿)\s*tokens?',
    ]
    
    for section in report.get("sections", []):
        for item in section.get("items", []):
            text = f"{item['title']} {item['summary']}"
            
            # 匹配ARR
            for pattern in arr_patterns:
                matches = re.findall(pattern, text, re.I)
                if matches:
                    metrics["ARR"].append({
                        "company": extract_company(text),
                        "value": parse_value(matches[0]),
                        "source": item["title"]
                    })
    
    return metrics
```

#### 方案B: 使用LLM提取（更准确）
```python
def extract_metrics_with_llm(report):
    """使用LLM提取结构化指标"""
    prompt = """
从以下新闻中提取关键指标，以JSON格式返回：
{
  "ARR": [{"company": "公司名", "value": 数值, "unit": "USD", "context": "上下文"}],
  "Token数": [{"company": "公司名", "value": 数值, "unit": "tokens"}],
  "用户数": [{"company": "公司名", "value": 数值, "unit": "人"}]
}

新闻内容：
{news_text}
"""
    
    response = call_llm(prompt)
    return json.loads(response)
```

---

### P1 - 添加分类信息（category）

**修复方案**:

#### 步骤1: 定义分类规则
```python
# ai_daily_push.py
CATEGORY_KEYWORDS = {
    "产品发布": ["launch", "release", "introduce", "unveil", "发布", "推出"],
    "融资消息": ["funding", "investment", "raise", "Series", "融资", "投资"],
    "技术突破": ["breakthrough", "research", "paper", "model", "突破", "研究"],
    "行业动态": ["partnership", "acquisition", "merge", "合作", "收购"],
    "政策法规": ["regulation", "policy", "law", "compliance", "政策", "法规"],
}

def classify_item(item):
    """为新闻条目分类"""
    text = f"{item['title']} {item.get('summary', '')}".lower()
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            return category
    
    return "其他"
```

#### 步骤2: 在生成数据时添加category
```python
# ai_daily_push.py Line 480-490
for idx, (item, sec) in enumerate(sorted_items, start=1):
    result["sections"][sec_map[sec]]["items"].append({
        "idx": idx,
        "title": item.get("title", ""),
        "summary": item.get("summary", ""),
        "category": classify_item(item),  # ← 添加这行
        "source": item.get("source", ""),
        ...
    })
```

#### 步骤3: 在HTML中显示分类
```javascript
// ai_daily_dashboard.html
main+='<article class="card">';
main+='<div class="top">';
main+='<span class="category">'+esc(it.category)+'</span>';  // 显示分类
main+='<span class="idx">'+it.idx+'</span>';
main+='</div>';
```

---

## 测试验证清单

修复后需要验证：

- [ ] **财经日报推送**
  - [ ] 本地运行：`python finance_daily_push.py`
  - [ ] 检查是否生成 finance_dashboard.html
  - [ ] 检查是否推送到企业微信
  - [ ] 添加失败通知机制

- [ ] **ARR/Token统计**
  - [ ] 找一条包含ARR的新闻测试
  - [ ] 验证extract_news_metrics()能正确提取
  - [ ] 检查HTML中是否渲染"💰 ARR / 营收数据"板块
  - [ ] 至少显示1-2条数据

- [ ] **分类信息**
  - [ ] 验证每条新闻都有category字段
  - [ ] 检查HTML中显示分类标签
  - [ ] 分类颜色/样式符合设计

- [ ] **翻译全文**
  - [ ] 决定是否保留Google Translate链接
  - [ ] 如果保留，添加说明（可能需要VPN）
  - [ ] 如果移除，更新HTML渲染逻辑

---

## 时间估算

| 任务 | 预计时间 | 优先级 |
|------|---------|--------|
| 修复财经日报推送 | 2-3小时 | P0 |
| 增强指标提取 | 3-4小时 | P1 |
| 添加分类功能 | 2小时 | P1 |
| 优化翻译链接 | 1小时 | P2 |
| **总计** | **8-10小时** | - |

---

## 立即行动

1. **查看最新运行日志**（确认财经日报失败原因）
   ```bash
   gh run view 33358370799 --log > latest_run.log
   grep -A 50 "第二条：财经日报" latest_run.log
   ```

2. **本地测试财经日报**
   ```bash
   python finance_daily_push.py --no-push
   ```

3. **检查今日数据中是否有ARR相关新闻**
   ```bash
   grep -i "ARR\|revenue\|funding" ai_daily_dashboard.html
   ```

---

**结论**: 这三个问题都是**功能不完整**导致的，不是bug。需要补充实现：
1. ❌ 财经日报失败监控
2. ❌ 指标提取功能
3. ❌ 分类功能

这些都在原始需求中，但v3.0.1只修复了bug，未完成全部功能开发。
