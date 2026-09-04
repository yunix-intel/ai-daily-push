# AI Daily Push 问题修复计划
# 生成时间：2026-09-02 16:00 北京时间

## 目录
1. [问题1：推送次数和时间异常](#问题1)
2. [问题2：AI日报收录窗口显示错误](#问题2)
3. [问题3：AI日报没有两端对齐](#问题3)
4. [问题4：行业数据洞察缺失](#问题4)
5. [问题5：AI日报翻译按钮消失](#问题5)
6. [问题6：财经日报指数显示0.00%](#问题6)
7. [问题7：财经日报收录窗口错误](#问题7)
8. [问题8：Node.js 20弃用警告](#问题8)
9. [问题9：GitHub Pages缺少导航](#问题9)
10. [问题10：财经日报无资金流向](#问题10)
11. [问题11：财经日报无分类tab](#问题11)
12. [问题12：突发事件分类错误](#问题12)
13. [问题13：盘中信息未过滤](#问题13)
14. [问题14：财经日报无翻译按钮](#问题14)
15. [问题15：新闻分类逻辑错误](#问题15)
16. [问题16：统一触发时间为北京7:00](#问题16)

---

<a name="问题1"></a>
## 问题1：推送次数和时间异常

### 根本原因
1. 手动触发(08:34北京) + 定时触发(09:04北京) 叠加
2. GitHub Actions 延迟101分钟（23:23 UTC → 01:04 UTC）
3. 无互斥锁机制

### 修复计划

#### 步骤1.1：添加互斥锁机制
**文件：** `.github/workflows/daily.yml`

```yaml
# 在 jobs.build-and-push 最前面添加
concurrency:
  group: daily-push-${{ github.ref }}
  cancel-in-progress: true  # 如果有运行中的，取消它
```

**作用：** 同一时间只允许一个 workflow 运行

#### 步骤1.2：添加运行时间检查
**新文件：** `workflow_lock.py`

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Workflow 互斥锁检查
防止手动触发和定时触发同时运行
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOCK_FILE = Path(__file__).parent / ".workflow_lock"
LOCK_TIMEOUT = 3600  # 1小时超时

def check_lock():
    """检查是否有其他实例正在运行"""
    if LOCK_FILE.exists():
        # 读取锁文件
        lock_time_str = LOCK_FILE.read_text().strip()
        try:
            lock_time = datetime.fromisoformat(lock_time_str)
            elapsed = (datetime.now(timezone.utc) - lock_time).total_seconds()
            
            if elapsed < LOCK_TIMEOUT:
                print(f"⚠️ 检测到另一个实例正在运行（{int(elapsed/60)}分钟前开始）")
                print(f"为避免重复推送，本次运行终止")
                return False
            else:
                print(f"⚠️ 发现过期锁文件（{int(elapsed/3600)}小时前），清除")
                LOCK_FILE.unlink()
        except Exception as e:
            print(f"⚠️ 锁文件格式错误，清除：{e}")
            LOCK_FILE.unlink()
    
    # 创建锁文件
    LOCK_FILE.write_text(datetime.now(timezone.utc).isoformat())
    return True

def release_lock():
    """释放锁"""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "release":
        release_lock()
        print("✓ 锁已释放")
    else:
        if check_lock():
            print("✓ 锁已获取，可以继续")
            sys.exit(0)
        else:
            sys.exit(1)
```

#### 步骤1.3：修改 workflow 调用锁检查
**文件：** `.github/workflows/daily.yml`

```yaml
jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - name: 检出代码
        uses: actions/checkout@v7

      - name: 配置 Python
        uses: actions/setup-python@v7
        with:
          python-version: '3.11'

      # 新增：检查互斥锁
      - name: 检查是否有重复运行
        id: lock_check
        run: |
          python workflow_lock.py
          echo "lock_acquired=true" >> $GITHUB_OUTPUT

      - name: 清除 Python 缓存
        if: steps.lock_check.outputs.lock_acquired == 'true'
        run: |
          # ... 原有内容
      
      # ... 其他步骤保持不变

      # 最后添加：释放锁
      - name: 释放互斥锁
        if: always()
        run: python workflow_lock.py release
```

#### 步骤1.4：添加延迟监控
**文件：** `push_history_recorder.py`

在记录推送时间时添加延迟告警：

```python
def record_push(expected_time, actual_time):
    # ... 现有代码
    
    # 新增：延迟告警
    if delay_minutes > 30:
        print(f"⚠️ 推送延迟超过30分钟：{delay_minutes:.1f}分钟")
        # 发送告警到企业微信
        try:
            from alerting import send_wecom_text
            webhook = os.getenv('WECOM_WEBHOOK')
            if webhook:
                send_wecom_text(
                    webhook,
                    f"⚠️ GitHub Actions 推送延迟告警\n"
                    f"预期时间: {expected_time}\n"
                    f"实际时间: {actual_time}\n"
                    f"延迟: {delay_minutes:.1f}分钟"
                )
        except Exception as e:
            print(f"告警发送失败: {e}")
```

#### 验证方法
```bash
# 1. 本地测试锁机制
python workflow_lock.py
python workflow_lock.py  # 第二次应该失败
python workflow_lock.py release

# 2. 测试 workflow
gh workflow run daily.yml
# 立即再次触发，应该被取消或跳过
gh workflow run daily.yml

# 3. 观察明天的定时运行是否正常
```

---

<a name="问题2"></a>
## 问题2：AI日报收录窗口显示错误

### 根本原因
直接继承 AI HOT 的 `windowStart/windowEnd`（UTC 00:00-00:00 = 北京08:00-08:00），未根据 cron 时间调整

### 修复计划

#### 步骤2.1：覆盖时间窗口
**文件：** `ai_daily_push.py`

找到第 240-248 行，修改：

```python
def merge_reports(primary, rss_sections):
    """合并 AI HOT 日报和 RSS 抓取结果"""
    # ... 原有代码
    
    # 统一智能分类
    sections = classify_ai_items(all_items)
    
    # ===== 修改开始 =====
    # 计算实际收录窗口（基于 cron 时间）
    now_utc = datetime.now(timezone.utc)
    
    # 读取 cron 配置（小时:分钟）
    cron_hour = int(os.getenv('CRON_HOUR', '23'))  # UTC 23
    cron_minute = int(os.getenv('CRON_MINUTE', '0'))  # 改为 23:00 对应北京7:00
    
    # 计算窗口结束时间（今天的 cron 时间）
    window_end = now_utc.replace(hour=cron_hour, minute=cron_minute, second=0, microsecond=0)
    if now_utc.hour < cron_hour or (now_utc.hour == cron_hour and now_utc.minute < cron_minute):
        # 还没到今天的 cron 时间，使用昨天的
        window_end -= timedelta(days=1)
    
    # 窗口开始时间 = 结束时间 - 24小时
    window_start = window_end - timedelta(hours=24)
    # ===== 修改结束 =====

    return {
        "date": primary.get("date", ""),
        "windowStart": window_start.isoformat(),  # 覆盖
        "windowEnd": window_end.isoformat(),      # 覆盖
        "generatedAt": now_utc.isoformat(),
        "attribution": primary.get("attribution", {}),
        "links": primary.get("links", {}),
        "sections": sections
    }
```

#### 步骤2.2：在 workflow 中传递 cron 配置
**文件：** `.github/workflows/daily.yml`

```yaml
- name: 第一条：AI 日报（图文卡片 + AI 日报网页）
  env:
    # ... 原有环境变量
    CRON_HOUR: "23"      # 新增
    CRON_MINUTE: "0"     # 新增（问题16会改为23:00对应北京7:00）
  run: python ai_daily_push.py
```

#### 验证方法
```bash
# 1. 本地测试
export CRON_HOUR=23
export CRON_MINUTE=0
python ai_daily_push.py --no-push

# 2. 检查生成的 HTML
grep -A 2 "windowStart" ai_daily_dashboard.html
# 应该显示 "2026-09-01T23:00:00" 而非 "00:00:00"

# 3. 浏览器打开，检查收录窗口显示
# 应该是 "9月1日 23:00 - 9月2日 23:00 (北京时间)"
# 问题16完成后会改为 "9月1日 07:00 - 9月2日 07:00"
```

---

<a name="问题3"></a>
## 问题3：AI日报没有两端对齐

### 根本原因
CSS 已设置 `text-align: justify`，但浏览器对短文本（1-2行）不生效，需要 `text-align-last: justify`

### 修复计划

#### 步骤3.1：修改 CSS
**文件：** `ai_daily_push.py`

找到 HTML_TMPL 中的 CSS 部分（约第1071-1090行）：

```css
/* 原有：*/
.card h3{font-size:16.5px;font-weight:700;line-height:1.45;margin-bottom:9px;text-align:justify}
.card .summary{font-size:14px;color:#c4ccd8;flex:1;margin-bottom:10px;text-align:justify}

/* 修改为：*/
.card h3{font-size:16.5px;font-weight:700;line-height:1.45;margin-bottom:9px;text-align:justify;text-align-last:justify;text-justify:inter-ideograph}
.card .summary{font-size:14px;color:#c4ccd8;flex:1;margin-bottom:10px;text-align:justify;text-align-last:justify;text-justify:inter-ideograph}
```

**说明：**
- `text-align-last: justify` - 强制最后一行也两端对齐
- `text-justify: inter-ideograph` - 针对中文优化，字符间分布更均匀

#### 验证方法
```bash
# 1. 生成新的 HTML
python ai_daily_push.py --no-push

# 2. 浏览器打开 ai_daily_dashboard.html
# 检查标题和摘要是否两端对齐
```

---

<a name="问题4"></a>
## 问题4：行业数据洞察缺失

### 根本原因
1. `MarketDataAggregator` 导入可能失败
2. API 调用超时/失败后静默跳过
3. 数据格式不匹配

### 修复计划

#### 步骤4.1：检查模块是否存在
```bash
ls -la analyzers/market_data_aggregator.py
ls -la analyzers/market_report_formatter.py
```

如果不存在，需要从备份或 git 历史恢复。

#### 步骤4.2：增强错误日志
**文件：** `ai_daily_push.py`

找到市场数据采集部分（约第 897-1000行）：

```python
# 原有代码
if MARKET_DATA_AVAILABLE:
    try:
        aggregator = MarketDataAggregator()
        formatter = MarketReportFormatter()
        # ...
    except Exception as e:
        print(f"市场数据采集失败: {e}")

# 修改为：
if MARKET_DATA_AVAILABLE:
    try:
        print("[市场数据] 开始采集 OpenRouter 和 Artificial Analysis 数据...")
        aggregator = MarketDataAggregator()
        
        # 分步采集，记录每步状态
        print("[市场数据] 1/3 采集 OpenRouter 榜单...")
        openrouter_data = aggregator.fetch_openrouter_rankings()
        print(f"[市场数据]   ✓ OpenRouter: {len(openrouter_data.get('models', []))} 个模型")
        
        print("[市场数据] 2/3 采集 Artificial Analysis 数据...")
        aa_data = aggregator.fetch_artificial_analysis()
        print(f"[市场数据]   ✓ Artificial Analysis: {len(aa_data.get('models', []))} 个模型")
        
        print("[市场数据] 3/3 生成趋势报告...")
        formatter = MarketReportFormatter()
        market_report = formatter.format(openrouter_data, aa_data)
        print(f"[市场数据]   ✓ 生成 {len(market_report.get('items', []))} 条洞察")
        
        # 添加到 sections
        if market_report.get('items'):
            sections.append({
                "label": "📈 市场数据与趋势",
                "items": market_report['items']
            })
            print("[市场数据] ✓ 市场数据板块已添加")
        else:
            print("[市场数据] ⚠ 没有生成任何洞察项")
            
    except ImportError as e:
        print(f"[市场数据] ✗ 模块导入失败: {e}")
        print(f"[市场数据]   请检查 analyzers/ 目录是否完整")
    except Exception as e:
        print(f"[市场数据] ✗ 采集失败: {e}")
        import traceback
        traceback.print_exc()
else:
    print("[市场数据] ⚠ 市场数据模块不可用（MARKET_DATA_AVAILABLE=False）")
```

#### 步骤4.3：添加超时控制
**文件：** `analyzers/market_data_aggregator.py`

```python
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

class MarketDataAggregator:
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.session = requests.Session()
        
        # 配置重试策略
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
    
    def fetch_openrouter_rankings(self):
        """采集 OpenRouter 榜单（带超时）"""
        try:
            url = "https://openrouter.ai/api/v1/rankings"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            print(f"  OpenRouter 请求超时（>{self.timeout}秒）")
            return {}
        except Exception as e:
            print(f"  OpenRouter 请求失败: {e}")
            return {}
```

#### 验证方法
```bash
# 1. 测试模块导入
python -c "from analyzers.market_data_aggregator import MarketDataAggregator; print('OK')"

# 2. 测试数据采集
python -c "
from analyzers.market_data_aggregator import MarketDataAggregator
agg = MarketDataAggregator()
data = agg.fetch_openrouter_rankings()
print(f'Models: {len(data.get(\"models\", []))}')
"

# 3. 完整测试
python ai_daily_push.py --no-push
# 检查日志中的 [市场数据] 输出
```

---

<a name="问题5"></a>
## 问题5：AI日报翻译按钮消失

### 根本原因
AI日报从未集成翻译功能，英文新闻无法查看中文翻译

### 修复计划

#### 步骤5.1：集成翻译服务
**文件：** `ai_daily_push.py`

在文件顶部添加导入：

```python
# 导入翻译服务
try:
    from translation_service import TranslationService
    TRANSLATION_AVAILABLE = True
except ImportError:
    TRANSLATION_AVAILABLE = False
```

#### 步骤5.2：生成翻译文件
在 `build_html()` 函数后添加翻译逻辑：

```python
def generate_translations(data):
    """为英文新闻生成翻译页面"""
    if not TRANSLATION_AVAILABLE:
        print("[翻译] 翻译服务不可用")
        return
    
    translator = TranslationService()
    translation_count = 0
    
    for section in data.get('sections', []):
        for item in section.get('items', []):
            # 判断是否为英文新闻
            title = item.get('title', '')
            summary = item.get('summary', '')
            
            if _looks_english(title + summary):
                original_url = item.get('links', {}).get('original', '')
                if original_url:
                    try:
                        # 生成翻译页面
                        translated_url = translator.translate_and_save(
                            original_url=original_url,
                            title=title,
                            content=summary
                        )
                        # 添加翻译链接
                        item['links']['translated'] = translated_url
                        translation_count += 1
                    except Exception as e:
                        print(f"[翻译] 翻译失败 {original_url}: {e}")
    
    print(f"[翻译] 生成了 {translation_count} 个翻译页面")

def _looks_english(text):
    """判断文本是否主要为英文"""
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.7
```

#### 步骤5.3：在 HTML 中添加翻译按钮
**文件：** `ai_daily_push.py`

找到 HTML 渲染部分（约第1150-1200行），修改卡片渲染：

```javascript
// 原有代码：
main+='<div class="card"><a href="'+esc(item.links.aihot||item.links.original||'#')+'" target="_blank" class="orig">原文</a>';

// 修改为：
main+='<div class="card">';
// 原文链接
main+='<a href="'+esc(item.links.aihot||item.links.original||'#')+'" target="_blank" class="orig">原文</a>';
// 翻译链接（如果有）
if(item.links.translated){
  main+='<a href="'+esc(item.links.translated)+'" target="_blank" class="orig" style="margin-left:8px;background:var(--accent2)">中文翻译</a>';
}
```

#### 步骤5.4：在主流程中调用
**文件：** `ai_daily_push.py`

在 `main()` 函数中，生成 HTML 之前：

```python
def main():
    # ... 原有代码：采集数据
    
    print("[5/6] 生成 AI 日报仪表盘 ...")
    data = shape_ai_daily(report, news_metrics)
    
    # 新增：生成翻译
    if not args.no_push:
        print("[5.5/6] 生成英文新闻翻译 ...")
        generate_translations(data)
    
    html_content = build_html(data)
    # ... 后续代码
```

#### 验证方法
```bash
# 1. 测试翻译服务
python -c "from translation_service import TranslationService; print('OK')"

# 2. 生成完整日报
python ai_daily_push.py --no-push

# 3. 检查是否生成了 translated_*.html 文件
ls -l translated_*.html

# 4. 浏览器打开 ai_daily_dashboard.html
# 英文新闻应该有"中文翻译"按钮
```

---

<a name="问题6"></a>
## 问题6：财经日报指数显示0.00%

### 根本原因
1. 非交易时间（开盘前<09:30）指数未更新
2. 浏览器缓存
3. 数据源异常

### 修复计划

#### 步骤6.1：添加数据验证
**文件：** `finance_daily_push.py`

找到 `fetch_quotes()` 调用处（约第1411-1418行）：

```python
print("[1/6] 抓取指数行情 ...")
try:
    quotes = fetch_quotes()
    
    # 新增：数据验证
    all_zero = all(q.get('pct', 0) == 0 for q in quotes)
    
    if all_zero and quotes:
        print("     ⚠️ 所有指数涨跌幅为0%，可能是非交易时间或数据异常")
        print("     使用提示：数据将显示最新收盘价")
        # 可选：添加标记
        for q in quotes:
            q['is_stale'] = True
    
    for q in quotes:
        status = " (非交易时间)" if q.get('is_stale') else ""
        print(f"     {q['name']}：{q['price']}（{q['pct']:+.2f}%）{status}")
        
except Exception as exc:
    quotes = []
    print(f"     [!] 行情抓取失败，继续执行：{exc!r}")
```

#### 步骤6.2：在 HTML 中显示数据时间
**文件：** `finance_daily_push.py`

在 `build_finance_html()` 函数中（约第1225行）：

```python
def build_finance_html(data):
    """生成财经日报 HTML（单文件，内联 CSS/JS）"""
    
    # 添加数据更新时间
    data_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="generated-at" content="{data_time}">
  <title>财经日报 · {data['meta']['date']}</title>
  <!-- ... CSS ... -->
</head>
<body>
  <div class="hero">
    <h1>📈 财经日报</h1>
    <div class="date">{data['meta']['date']}</div>
    <div style="font-size:12px;color:var(--muted);margin-top:8px;">
      数据更新时间: {data_time} (北京时间)
    </div>
    <!-- ... 后续内容 ... -->
```

#### 步骤6.3：添加交易状态提示
**文件：** `finance_daily_push.py`

在指数显示区域添加状态：

```javascript
// 在渲染指数时
quotes.forEach(q => {
  const staleHint = q.is_stale ? '<span style="font-size:10px;color:var(--muted)">非交易时间</span>' : '';
  heroQuotes += `
    <div class="quote ${q.pct>=0?'up':'down'}">
      <div class="qname">${q.name}</div>
      <div class="qprice">${q.price.toFixed(2)} ${staleHint}</div>
      <div class="qchange">${q.pct>=0?'+':''}${q.pct.toFixed(2)}%</div>
    </div>
  `;
});
```

#### 验证方法
```bash
# 1. 非交易时间测试（周末或晚上）
python finance_daily_push.py --no-push
# 检查日志是否有"非交易时间"提示

# 2. 浏览器测试
# 打开 finance_dashboard.html
# 按 Ctrl+Shift+R 强制刷新（清除缓存）
# 检查是否显示"数据更新时间"

# 3. 检查 meta 标签
curl -I file://$(pwd)/finance_dashboard.html | grep Cache-Control
```

---

<a name="问题7"></a>
## 问题7：财经日报收录窗口错误

### 根本原因
使用脚本实际运行时间 `now_utc`，而非 cron 设定时间

### 修复计划

#### 步骤7.1：修改时间窗口计算
**文件：** `finance_daily_push.py`

找到 `shape_finance()` 函数（约第1100-1187行）：

```python
def shape_finance(sections_domestic, sections_international, quotes, analysis_domestic,
                  analysis_international, strategy, money_flow_data=None, window_hours=24,
                  bloggers=None, breaking_events_domestic=None, breaking_events_international=None):
    """组装财经日报数据结构"""
    
    # ===== 修改开始 =====
    # 原有代码：
    # now_utc = datetime.now(timezone.utc)
    
    # 新代码：使用 cron 时间作为锚点
    now_utc = datetime.now(timezone.utc)
    
    # 读取 cron 配置
    cron_hour = int(os.getenv('CRON_HOUR', '23'))
    cron_minute = int(os.getenv('CRON_MINUTE', '0'))
    
    # 计算窗口结束时间（今天的 cron 时间）
    window_end = now_utc.replace(hour=cron_hour, minute=cron_minute, second=0, microsecond=0)
    if now_utc.hour < cron_hour or (now_utc.hour == cron_hour and now_utc.minute < cron_minute):
        # 还没到今天的 cron 时间，使用昨天的
        window_end -= timedelta(days=1)
    
    # 窗口开始时间
    window_start = window_end - timedelta(hours=window_hours)
    # ===== 修改结束 =====
    
    meta = {
        "date": window_end.strftime("%Y-%m-%d"),
        "windowStart": window_start.isoformat(),
        "windowEnd": window_end.isoformat(),
        "generatedAt": now_utc.isoformat(),
        # ... 其余不变
    }
```

#### 步骤7.2：在 workflow 中传递 cron 配置
**文件：** `.github/workflows/daily.yml`

```yaml
- name: 第二条：财经日报（markdown + 财经网页）
  env:
    # ... 原有环境变量
    CRON_HOUR: "23"      # 新增
    CRON_MINUTE: "0"     # 新增
  run: python finance_daily_push.py
```

#### 验证方法
```bash
# 1. 本地测试
export CRON_HOUR=23
export CRON_MINUTE=0
python finance_daily_push.py --no-push

# 2. 检查生成的 HTML
grep "windowStart" finance_dashboard.html
# 应该显示 "2026-09-01T23:00:00" 而非实际运行时间

# 3. 浏览器检查
# 应该显示 "9月1日 23:00 - 9月2日 23:00 (北京时间)"
```

---

<a name="问题8"></a>
## 问题8：Node.js 20弃用警告

### 根本原因
`actions/cache@v4` 依赖 Node.js 20，GitHub Actions 已弃用

### 修复计划

#### 步骤8.1：检查当前使用的 actions
```bash
grep "uses:" .github/workflows/daily.yml | grep -v "#"
```

#### 步骤8.2：升级到最新版本
**文件：** `.github/workflows/daily.yml`

```yaml
# 查找并替换

# 1. cache (如果有用到)
# 原有：uses: actions/cache@v4
# 修改为：
- uses: actions/cache@v5

# 2. 确认其他 actions 已是最新
- uses: actions/checkout@v7           # ✓ 已是最新
- uses: actions/setup-python@v7       # ✓ 已是最新
- uses: actions/upload-pages-artifact@v5  # ✓ 已是最新
- uses: actions/deploy-pages@v5       # ✓ 已是最新
```

#### 步骤8.3：检查间接依赖
有些 action 内部可能调用旧版 action，查看运行日志：

```bash
gh run view <run-id> --log | grep "Node.js 20"
```

如果仍有警告，可以临时忽略（不影响功能）。

#### 验证方法
```bash
# 1. 提交并触发 workflow
git add .github/workflows/daily.yml
git commit -m "⬆️ 升级 actions 到最新版本，解决 Node.js 20 警告"
git push

# 2. 手动触发测试
gh workflow run daily.yml

# 3. 查看日志
gh run list --limit 1
gh run view <run-id> --log | grep -i "node\|deprecated" | wc -l
# 应该减少或没有警告
```

---

<a name="问题9"></a>
## 问题9：GitHub Pages缺少导航

### 根本原因
AI日报首页没有链接到财经日报和监控页面

### 修复计划

#### 步骤9.1：添加全局导航
**文件：** `ai_daily_push.py`

在 HTML_TMPL 的 CSS 部分添加导航样式（约第1070-1090行）：

```css
/* 新增：全局导航 */
.global-nav{
  position:fixed;
  top:0;
  left:0;
  right:0;
  background:rgba(14,16,20,0.95);
  backdrop-filter:blur(10px);
  border-bottom:1px solid var(--border);
  z-index:1000;
  padding:12px 0;
}
.global-nav .wrap{
  max-width:1160px;
  margin:0 auto;
  padding:0 20px;
  display:flex;
  gap:20px;
  align-items:center;
}
.global-nav a{
  color:var(--text);
  text-decoration:none;
  font-size:14px;
  font-weight:600;
  padding:6px 12px;
  border-radius:6px;
  transition:all .2s;
}
.global-nav a:hover{
  background:var(--card-hover);
  color:var(--accent);
}
.global-nav a.active{
  background:var(--accent);
  color:#0c1320;
}
/* 给 body 添加顶部间距 */
body{
  padding-top:50px;
}
```

在 `<body>` 标签后添加导航HTML：

```html
<body>
<nav class="global-nav">
  <div class="wrap">
    <a href="/" class="active">🤖 AI 日报</a>
    <a href="/finance.html">📈 财经日报</a>
    <a href="/push_history.html">📊 推送监控</a>
    <a href="https://github.com/yunix-intel/ai-daily-push" target="_blank">💻 GitHub</a>
  </div>
</nav>
<header class="hero">
  <!-- ... 原有内容 ... -->
```

#### 步骤9.2：在财经日报中也添加导航
**文件：** `finance_daily_push.py`

在 `build_finance_html()` 中添加相同的导航：

```python
def build_finance_html(data):
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <!-- ... meta 和 style ... -->
  <style>
    /* 添加导航样式（同 AI 日报）*/
    .global-nav{...}
    /* ... 其余样式 ... */
  </style>
</head>
<body>
<nav class="global-nav">
  <div class="wrap">
    <a href="/">🤖 AI 日报</a>
    <a href="/finance.html" class="active">📈 财经日报</a>
    <a href="/push_history.html">📊 推送监控</a>
    <a href="https://github.com/yunix-intel/ai-daily-push" target="_blank">💻 GitHub</a>
  </div>
</nav>
  <!-- ... 原有内容 ... -->
```

#### 步骤9.3：在监控页面添加导航
**文件：** `push_history_recorder.py`

找到 `generate_html_report()` 函数（约第200-300行）：

```python
def generate_html_report(history_data):
    """生成 HTML 监控报告"""
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>推送历史监控</title>
  <style>
    /* 添加导航样式 */
    .global-nav{...}
    /* ... 其余样式 ... */
  </style>
</head>
<body>
<nav class="global-nav">
  <div class="wrap">
    <a href="/">🤖 AI 日报</a>
    <a href="/finance.html">📈 财经日报</a>
    <a href="/push_history.html" class="active">📊 推送监控</a>
    <a href="https://github.com/yunix-intel/ai-daily-push" target="_blank">💻 GitHub</a>
  </div>
</nav>
  <!-- ... 原有内容 ... -->
```

#### 验证方法
```bash
# 1. 重新生成所有页面
python ai_daily_push.py --no-push
python finance_daily_push.py --no-push
python push_history_recorder.py --expected-time "23:00" --task "Test"

# 2. 本地测试导航
# 启动本地服务器
python -m http.server 8000

# 3. 浏览器打开 http://localhost:8000/ai_daily_dashboard.html
# 点击导航，验证：
# - 🤖 AI 日报 → index.html (当前高亮)
# - 📈 财经日报 → finance.html
# - 📊 推送监控 → push_history.html
# - 💻 GitHub → 新标签打开仓库

# 4. 部署后测试
# 访问 https://yunix-intel.github.io/ai-daily-push/
# 验证所有导航链接正常工作
```

---

<a name="问题10"></a>
## 问题10：财经日报无资金流向

### 根本原因
`ModuleNotFoundError: No module named 'bs4'` - beautifulsoup4 未安装

### 修复计划

#### 步骤10.1：检查 requirements.txt
**文件：** `requirements.txt`

确认是否包含 beautifulsoup4：

```bash
grep -i "beautifulsoup\|bs4" requirements.txt
```

如果没有，添加：

```txt
beautifulsoup4>=4.12.0,<5.0.0
lxml>=4.9.0,<5.0.0  # beautifulsoup4 的解析器依赖
```

#### 步骤10.2：安装依赖
```bash
pip install beautifulsoup4 lxml
```

#### 步骤10.3：验证模块可用
```bash
python -c "from bs4 import BeautifulSoup; print('✓ bs4 可用')"
python -c "from scrapers.money_flow_scraper import MoneyFlowScraper; print('✓ MoneyFlowScraper 可用')"
```

#### 步骤10.4：测试资金流向抓取
```bash
python -c "
from scrapers.money_flow_scraper import MoneyFlowScraper

scraper = MoneyFlowScraper()
print('测试北向资金...')
north = scraper.fetch_north_flow()
print(f'  北向资金: {north}')

print('测试行业资金流向...')
sector = scraper.fetch_sector_flow()
print(f'  行业流向: {len(sector.get(\"top_inflow\", []))} 个')

print('测试个股资金流向...')
stock = scraper.fetch_stock_flow()
print(f'  个股流向: {len(stock.get(\"top_inflow\", []))} 个')
"
```

#### 步骤10.5：完整测试
```bash
python finance_daily_push.py --no-push --hours 24
```

检查日志输出：
- 应该显示 `[1.5/6] 抓取资金流向数据 ...`
- 应该显示 `北向资金：...`、`行业流入 Top 1：...`
- **不应该**显示 `资金流向抓取失败`

#### 步骤10.6：验证 HTML 中的数据
```bash
# 检查 finance_dashboard.html 是否包含资金流向数据
grep -A 5 "moneyFlow" finance_dashboard.html | head -20
# 应该看到 north_flow, sector_flow, stock_flow 数据
```

#### 验证方法
```bash
# 1. 提交依赖更新
git add requirements.txt
git commit -m "📦 添加 beautifulsoup4 依赖，修复资金流向功能"
git push

# 2. GitHub Actions 会自动安装
# 查看下次运行的日志，确认没有 ModuleNotFoundError

# 3. 检查生成的页面
# 应该显示：
# - 北向资金（沪股通/深股通）
# - 行业资金流向 Top 5
# - 个股资金流向 Top 5
```

---

<a name="问题11"></a>
## 问题11：财经日报无分类tab

### 根本原因
数据已分类（domestic/international），但前端未实现 tab 切换

### 修复计划

#### 步骤11.1：添加 tab 样式
**文件：** `finance_daily_push.py`

在 `build_finance_html()` 的 CSS 部分添加：

```css
/* Tab 导航 */
.tabs{
  display:flex;
  gap:12px;
  margin:24px 0 16px;
  border-bottom:2px solid var(--border);
  padding-bottom:12px;
}
.tab{
  background:transparent;
  border:none;
  color:var(--muted);
  font-size:15px;
  font-weight:600;
  padding:8px 16px;
  cursor:pointer;
  border-radius:6px 6px 0 0;
  transition:all .2s;
  position:relative;
}
.tab:hover{
  background:var(--card-hover);
  color:var(--text);
}
.tab.active{
  color:var(--accent);
  background:var(--card);
}
.tab.active::after{
  content:'';
  position:absolute;
  bottom:-14px;
  left:0;
  right:0;
  height:2px;
  background:var(--accent);
}
.tab .count{
  display:inline-block;
  margin-left:6px;
  padding:2px 8px;
  background:var(--chip);
  border-radius:12px;
  font-size:12px;
  font-weight:700;
}
.tab.active .count{
  background:var(--accent);
  color:#0c1320;
}

/* 新闻项的分类标记 */
.news-item[data-category="domestic"]{}
.news-item[data-category="international"]{}
.news-item.hidden{
  display:none !important;
}
```

#### 步骤11.2：修改 HTML 结构
在新闻列表前添加 tab：

```javascript
// 在渲染新闻前（约 shape_finance 返回的数据结构中）
// 修改 build_finance_html() 中的渲染逻辑

function render(){
  // ... 原有代码：渲染 hero、quotes 等
  
  // 新增：Tab 导航
  const domesticCount = DATA.meta.domesticCount || 0;
  const intlCount = DATA.meta.internationalCount || 0;
  const totalCount = DATA.meta.total || 0;
  
  main += `
    <div class="tabs">
      <button class="tab active" data-filter="all">
        全部新闻<span class="count">${totalCount}</span>
      </button>
      <button class="tab" data-filter="domestic">
        国内要闻<span class="count">${domesticCount}</span>
      </button>
      <button class="tab" data-filter="international">
        国际要闻<span class="count">${intlCount}</span>
      </button>
    </div>
  `;
  
  // 渲染新闻时添加 data-category 属性
  // 在 renderSection() 中修改
  function renderSection(title, items, category){
    items.forEach(item => {
      // 添加 data-category
      main += `<div class="news-item" data-category="${category}">`;
      // ... 原有渲染逻辑
      main += `</div>`;
    });
  }
  
  // 调用时传入 category
  renderSection('国内要闻', DATA.domestic.sections, 'domestic');
  renderSection('国际要闻', DATA.international.sections, 'international');
}
```

#### 步骤11.3：添加 tab 切换逻辑
在 JavaScript 部分添加：

```javascript
// Tab 切换功能
document.addEventListener('DOMContentLoaded', function(){
  const tabs = document.querySelectorAll('.tab');
  const newsItems = document.querySelectorAll('.news-item');
  
  tabs.forEach(tab => {
    tab.addEventListener('click', function(){
      const filter = this.dataset.filter;
      
      // 更新 tab 状态
      tabs.forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      
      // 过滤新闻
      newsItems.forEach(item => {
        const category = item.dataset.category;
        if(filter === 'all' || category === filter){
          item.classList.remove('hidden');
        } else {
          item.classList.add('hidden');
        }
      });
      
      // 平滑滚动到新闻区域
      document.querySelector('.news-item:not(.hidden)').scrollIntoView({
        behavior: 'smooth',
        block: 'nearest'
      });
    });
  });
});
```

#### 步骤11.4：确保数据结构正确
**文件：** `finance_daily_push.py`

确认 `shape_finance()` 返回的数据包含分类信息：

```python
def shape_finance(...):
    # ... 原有代码
    
    return {
        "meta": {
            "date": ...,
            "total": len(sections_domestic) + len(sections_international),
            "domesticCount": len(sections_domestic),      # 确保有这个
            "internationalCount": len(sections_international),  # 确保有这个
        },
        "domestic": {
            "sections": sections_domestic,
            "analysis": analysis_domestic,
            "mustRead": [...],
            "breakingEvents": breaking_events_domestic or [],
        },
        "international": {
            "sections": sections_international,
            "analysis": analysis_international,
            "mustRead": [...],
            "breakingEvents": breaking_events_international or [],
        },
        # ... 其余不变
    }
```

#### 验证方法
```bash
# 1. 生成新页面
python finance_daily_push.py --no-push

# 2. 检查 HTML
grep "data-category" finance_dashboard.html | head -5
grep "class=\"tab\"" finance_dashboard.html

# 3. 浏览器测试
# 打开 finance_dashboard.html
# 点击三个 tab：
# - 全部新闻：显示所有
# - 国内要闻：只显示 domestic
# - 国际要闻：只显示 international
# 验证数量徽章正确
```

---

<a name="问题12"></a>
## 问题12：突发事件分类错误

### 根本原因
依赖 `news_classifier.py` 的分类结果，分类器将"美军袭击伊朗"误判为国内

### 修复计划

参见 **问题15** 的修复，这是连带问题。

额外增强：在突发事件识别时添加二次验证

#### 步骤12.1：突发事件识别时添加地域检查
**文件：** `news_classifier.py`

在 `identify_breaking_news()` 函数中添加：

```python
def identify_breaking_news(items, llm_wrapper):
    """识别突发事件（带地域验证）"""
    # ... 原有 LLM 调用逻辑
    
    # 新增：二次验证地域分类
    for event in breaking_events:
        title = event.get('title', '')
        impact = event.get('impact', '')
        content = title + ' ' + impact
        
        # 强制地域关键词检查
        intl_keywords = ['美国', '美军', '伊朗', '以色列', '俄罗斯', '乌克兰',
                        'US', 'USA', 'Iran', 'Israel', 'Russia', 'Ukraine',
                        '美联储', 'Fed', '欧洲央行', 'ECB']
        
        if any(kw in content for kw in intl_keywords):
            # 检测到国际关键词，标记
            event['_region_hint'] = 'international'
        
        china_keywords = ['中国', '央行', 'A股', '上证', '深证', '证监会',
                         'PBOC', '人民银行', '国务院', '发改委']
        
        if any(kw in content for kw in china_keywords):
            event['_region_hint'] = 'domestic'
    
    return breaking_events
```

#### 步骤12.2：在调用处过滤错误分类
**文件：** `finance_daily_push.py`

```python
# 识别突发事件（约第1552-1554行）
breaking_events_domestic_raw = identify_breaking_news(items_domestic, llm_wrapper)
breaking_events_international_raw = identify_breaking_news(items_international, llm_wrapper)

# 新增：根据 _region_hint 重新分配
breaking_events_domestic = []
breaking_events_international = []

for event in breaking_events_domestic_raw:
    if event.get('_region_hint') == 'international':
        print(f"     [重新分类] {event['title']} → 国际")
        breaking_events_international.append(event)
    else:
        breaking_events_domestic.append(event)

for event in breaking_events_international_raw:
    if event.get('_region_hint') == 'domestic':
        print(f"     [重新分类] {event['title']} → 国内")
        breaking_events_domestic.append(event)
    else:
        breaking_events_international.append(event)

print(f"     突发事件：国内 {len(breaking_events_domestic)} 个，国际 {len(breaking_events_international)} 个")
```

#### 验证方法
参见问题15的验证，修复分类器后此问题自动解决。

---

<a name="问题13"></a>
## 问题13：盘中信息未过滤

### 根本原因
无盘中时间判断，收盘后推送盘中信息无意义

### 修复计划

#### 步骤13.1：添加交易时间判断函数
**文件：** `trading_calendar.py`（如果没有则新建）

```python
from datetime import datetime, time, timezone, timedelta

# 北京时间 UTC+8
BEIJING_TZ = timezone(timedelta(hours=8))

# A股交易时间
A_SHARE_SESSIONS = [
    (time(9, 30), time(11, 30)),   # 上午
    (time(13, 0), time(15, 0)),    # 下午
]

def is_trading_hour(dt=None, market='A'):
    """判断是否为交易时间"""
    if dt is None:
        dt = datetime.now(BEIJING_TZ)
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
    """判断是否为盘中实时新闻"""
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
```

#### 步骤13.2：在新闻收集时过滤
**文件：** `finance_daily_push.py`

```python
def fetch_finance_items(hours=24, per_feed=20):
    """抓取财经新闻（过滤盘中信息）"""
    # ... 原有代码：抓取新闻
    
    # 新增：过滤盘中信息
    from trading_calendar import is_intraday_news, is_trading_hour
    
    current_time = datetime.now(timezone(timedelta(hours=8)))
    is_trading_now = is_trading_hour(current_time)
    
    filtered_items = []
    intraday_filtered_count = 0
    
    for item in all_items:
        # 判断是否为盘中新闻
        if is_intraday_news(item['title'], item['summary'], item.get('pub_time')):
            # 如果现在不是交易时间，跳过
            if not is_trading_now:
                intraday_filtered_count += 1
                continue
        
        filtered_items.append(item)
    
    if intraday_filtered_count > 0:
        print(f"     [过滤盘中信息] 跳过 {intraday_filtered_count} 条实时播报类新闻")
    
    return filtered_items
```

#### 步骤13.3：添加配置选项
**文件：** `finance_daily_push.py`

```python
# 在 main() 函数添加参数
parser.add_argument("--include-intraday", action="store_true",
                   help="包含盘中实时信息（默认收盘后自动过滤）")

# 在调用处
items = fetch_finance_items(hours=args.hours, per_feed=20)
if not args.include_intraday and not is_trading_hour():
    items = filter_intraday_news(items)
```

#### 验证方法
```bash
# 1. 交易时间测试（周一-周五 09:30-15:00）
python finance_daily_push.py --no-push
# 应该保留盘中新闻

# 2. 非交易时间测试（晚上/周末）
python finance_daily_push.py --no-push
# 应该显示 "[过滤盘中信息] 跳过 X 条"

# 3. 强制包含测试
python finance_daily_push.py --no-push --include-intraday
# 应该保留所有新闻

# 4. 检查生成的 HTML
# 不应该包含"XX股涨停"、"盘中直线拉升"等实时播报
```

---

<a name="问题14"></a>
## 问题14：财经日报无翻译按钮

### 根本原因
英文新闻已批量翻译成中文，但未保留原文链接

### 修复计划

#### 步骤14.1：保留原文信息
**文件：** `finance_daily_push.py`

找到翻译逻辑（约第462-517行）：

```python
def translate_finance_items(items):
    """翻译英文财经新闻（保留原文）"""
    # ... 原有代码
    
    # 在翻译后添加标记
    for idx in translated_indexes:
        items[idx]['_was_translated'] = True
        items[idx]['_original_title_en'] = items[idx].get('_original_title', items[idx]['title'])
        items[idx]['_original_summary_en'] = items[idx].get('_original_summary', items[idx]['summary'])
    
    return items
```

#### 步骤14.2：在 HTML 中添加"查看原文"按钮
**文件：** `finance_daily_push.py`

在新闻卡片渲染时（约第1225行的 HTML 模板中）：

```javascript
// 渲染新闻项
function renderNewsItem(item){
  let html = '<div class="news-card">';
  html += '<h3>' + esc(item.title) + '</h3>';
  html += '<div class="summary">' + esc(item.summary) + '</div>';
  
  // 新增：翻译标记和原文按钮
  if(item._was_translated){
    html += '<div class="translation-hint">';
    html += '<span class="badge">🌐 已翻译</span>';
    html += '<button class="show-original-btn" data-title="' + esc(item._original_title_en) + '" ';
    html += 'data-summary="' + esc(item._original_summary_en) + '">查看英文原文</button>';
    html += '</div>';
  }
  
  html += '</div>';
  return html;
}

// 添加原文弹窗功能
document.addEventListener('click', function(e){
  if(e.target.classList.contains('show-original-btn')){
    const title = e.target.dataset.title;
    const summary = e.target.dataset.summary;
    
    // 显示原文（使用模态框）
    showOriginalDialog(title, summary);
  }
});

function showOriginalDialog(title, summary){
  const dialog = document.createElement('div');
  dialog.className = 'original-dialog';
  dialog.innerHTML = `
    <div class="dialog-overlay" onclick="this.parentElement.remove()"></div>
    <div class="dialog-content">
      <button class="dialog-close" onclick="this.parentElement.parentElement.remove()">×</button>
      <h3>English Original</h3>
      <div class="original-title">${esc(title)}</div>
      <div class="original-summary">${esc(summary)}</div>
    </div>
  `;
  document.body.appendChild(dialog);
}
```

#### 步骤14.3：添加原文弹窗样式
在 CSS 中添加：

```css
/* 翻译提示 */
.translation-hint{
  margin-top:8px;
  display:flex;
  align-items:center;
  gap:8px;
}
.translation-hint .badge{
  font-size:11px;
  padding:2px 8px;
  background:var(--accent2);
  color:#0c1320;
  border-radius:12px;
  font-weight:700;
}
.show-original-btn{
  background:transparent;
  border:1px solid var(--border);
  color:var(--text);
  font-size:12px;
  padding:4px 12px;
  border-radius:4px;
  cursor:pointer;
  transition:all .2s;
}
.show-original-btn:hover{
  border-color:var(--accent);
  color:var(--accent);
  background:var(--card-hover);
}

/* 原文弹窗 */
.original-dialog{
  position:fixed;
  top:0;
  left:0;
  right:0;
  bottom:0;
  z-index:9999;
}
.dialog-overlay{
  position:absolute;
  top:0;
  left:0;
  right:0;
  bottom:0;
  background:rgba(0,0,0,0.8);
  backdrop-filter:blur(4px);
}
.dialog-content{
  position:absolute;
  top:50%;
  left:50%;
  transform:translate(-50%,-50%);
  background:var(--card);
  border:1px solid var(--border);
  border-radius:12px;
  padding:24px;
  max-width:600px;
  width:90%;
  max-height:80vh;
  overflow-y:auto;
  box-shadow:0 20px 60px rgba(0,0,0,0.5);
}
.dialog-close{
  position:absolute;
  top:12px;
  right:12px;
  background:transparent;
  border:none;
  color:var(--muted);
  font-size:28px;
  cursor:pointer;
  line-height:1;
  padding:0;
  width:32px;
  height:32px;
}
.dialog-close:hover{
  color:var(--text);
}
.dialog-content h3{
  margin-bottom:16px;
  color:var(--accent);
}
.original-title{
  font-size:16px;
  font-weight:700;
  margin-bottom:12px;
  line-height:1.4;
}
.original-summary{
  font-size:14px;
  color:var(--muted);
  line-height:1.6;
}
```

#### 验证方法
```bash
# 1. 生成页面
python finance_daily_push.py --no-push

# 2. 检查数据
grep "_was_translated" finance_dashboard.html | head -3

# 3. 浏览器测试
# 打开 finance_dashboard.html
# 找到有 "🌐 已翻译" 标记的新闻
# 点击"查看英文原文"按钮
# 应该弹出模态框显示英文原文
```

---

<a name="问题15"></a>
## 问题15：新闻分类逻辑错误

### 根本原因
`news_classifier.py` 按来源判断（Bloomberg→国际），忽略内容（中国债券应该是国内）

### 修复计划

#### 步骤15.1：重写分类逻辑
**文件：** `news_classifier.py`

找到 `classify_by_keywords()` 或 `classify_news_category()` 函数：

```python
def classify_news_category(item):
    """
    新闻分类：国内 vs 国际
    
    优先级：
    1. 内容强关键词（中国相关 → 国内）
    2. 内容国际关键词（美国/欧洲 → 国际）
    3. 来源判断（兜底）
    
    Args:
        item: {title, summary, source: {name}}
    
    Returns:
        'domestic' or 'international'
    """
    title = item.get('title', '')
    summary = item.get('summary', '')
    source_name = item.get('source', {}).get('name', '')
    content = title + ' ' + summary
    
    # ===== 第1优先级：强制国内关键词 =====
    domestic_strong = [
        # 地名
        '中国', 'China', 'Chinese', '中华', 
        # 市场
        'A股', 'A-share', '上证', '深证', '沪市', '深市',
        '创业板', 'ChiNext', '科创板', 'STAR Market',
        '港股', 'H股', '香港', 'Hong Kong', 'HK',
        # 机构
        '央行', 'PBOC', '人民银行', 'PBoC',
        '证监会', 'CSRC', '银保监', 'CBIRC',
        '发改委', 'NDRC', '商务部', 'MOFCOM',
        '国务院', 'State Council',
        # 企业
        '华为', 'Huawei', '腾讯', 'Tencent', '阿里', 'Alibaba',
        '中石油', 'PetroChina', '中石化', 'Sinopec',
        '工商银行', 'ICBC', '建设银行', 'CCB',
        # 货币
        '人民币', 'CNY', 'RMB', 'Yuan',
    ]
    
    for keyword in domestic_strong:
        if keyword in content:
            return 'domestic'
    
    # ===== 第2优先级：强制国际关键词 =====
    international_strong = [
        # 国家/地区（排除中国/香港）
        '美国', 'US', 'USA', 'America', 'American',
        '欧洲', 'Europe', 'European', 'EU', '欧盟',
        '日本', 'Japan', 'Japanese',
        '英国', 'UK', 'Britain', 'British',
        '德国', 'Germany', 'German',
        '法国', 'France', 'French',
        '俄罗斯', 'Russia', 'Russian',
        '印度', 'India', 'Indian',
        '韩国', 'Korea', 'Korean',
        # 机构
        '美联储', 'Fed', 'Federal Reserve',
        '欧央行', 'ECB', 'European Central Bank',
        '日本央行', 'BOJ', 'Bank of Japan',
        # 市场
        'S&P', '标普', 'Dow', '道琼斯',
        'Nasdaq', '纳斯达克',
        'NYSE', '纽交所',
        # 冲突
        '乌克兰', 'Ukraine', '伊朗', 'Iran',
        '以色列', 'Israel', '巴勒斯坦', 'Palestine',
    ]
    
    for keyword in international_strong:
        if keyword in content:
            return 'international'
    
    # ===== 第3优先级：来源判断（兜底）=====
    domestic_sources = [
        '新华社', 'Xinhua',
        '财联社', 'Yicai',
        '证券时报', 'Securities Times',
        '中国证券报', 'China Securities',
        '上海证券报', 'Shanghai Securities',
        '经济参考报',
        '第一财经',
        '财新', 'Caixin',
        '东方财富', 'East Money',
    ]
    
    for source in domestic_sources:
        if source in source_name:
            return 'domestic'
    
    international_sources = [
        'Bloomberg', 'Reuters', 'CNBC', 'WSJ',
        'Financial Times', 'FT',
        'The Economist',
        'MarketWatch',
    ]
    
    for source in international_sources:
        if source in source_name:
            return 'international'
    
    # ===== 默认：国内 =====
    # 如果以上都不匹配，默认归为国内
    # 因为项目主要关注中国市场
    return 'domestic'
```

#### 步骤15.2：添加分类验证日志
**文件：** `finance_daily_push.py`

在分类后添加验证：

```python
# 分类后（约第1470-1490行）
print(f"[2.1] 新闻分类完成：国内 {len(items_domestic)} 条，国际 {len(items_international)} 条")

# 新增：抽样验证
print("[2.2] 分类抽样验证 ...")
for item in items_domestic[:3]:
    print(f"  [国内] {item['title'][:40]}...")
for item in items_international[:3]:
    print(f"  [国际] {item['title'][:40]}...")
```

#### 步骤15.3：添加测试用例
**新文件：** `test_news_classifier.py`

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""新闻分类器单元测试"""

import unittest
from news_classifier import classify_news_category

class TestNewsClassifier(unittest.TestCase):
    
    def test_china_bonds_bloomberg(self):
        """中国债券（Bloomberg来源）应该归为国内"""
        item = {
            'title': 'China Bond Issuance Hits Record',
            'summary': 'Chinese companies issued $50B in bonds',
            'source': {'name': 'Bloomberg'}
        }
        self.assertEqual(classify_news_category(item), 'domestic')
    
    def test_fed_meeting(self):
        """美联储会议应该归为国际"""
        item = {
            'title': 'Fed Raises Rates',
            'summary': 'Federal Reserve increases rates by 25bps',
            'source': {'name': 'Reuters'}
        }
        self.assertEqual(classify_news_category(item), 'international')
    
    def test_a_share_market(self):
        """A股市场应该归为国内"""
        item = {
            'title': 'A股大涨',
            'summary': '上证指数上涨2%',
            'source': {'name': '财联社'}
        }
        self.assertEqual(classify_news_category(item), 'domestic')
    
    def test_huawei_english_title(self):
        """华为新闻（英文标题）应该归为国内"""
        item = {
            'title': 'Huawei Reports Strong Earnings',
            'summary': 'The Chinese tech giant beat expectations',
            'source': {'name': 'CNBC'}
        }
        self.assertEqual(classify_news_category(item), 'domestic')

if __name__ == '__main__':
    unittest.main()
```

#### 验证方法
```bash
# 1. 运行单元测试
python test_news_classifier.py
# 应该全部通过

# 2. 完整流程测试
python finance_daily_push.py --no-push --hours 24

# 3. 检查分类结果
# 看日志中的 "[国内]" 和 "[国际]" 抽样
# "中国债券" 应该在国内
# "美军袭击伊朗" 应该在国际

# 4. 检查生成的 HTML
# 在浏览器中切换 tab
# 验证分类正确
```

---

<a name="问题16"></a>
## 问题16：统一触发时间为北京7:00

### 根本原因
当前 cron 为 `23 23 * * *` (UTC 23:23 = 北京07:23)，需要改为 `23 00 * * *` (UTC 23:00 = 北京07:00)

### 关联修改
需要修改：
1. GitHub Actions workflow cron
2. AI 日报收录窗口计算
3. 财经日报收录窗口计算
4. 推送历史 expected_time
5. 阿里云函数触发时间（用户手动）
6. 云函数监控 expected_time

### 修复计划

#### 步骤16.1：修改 workflow cron 时间
**文件：** `.github/workflows/daily.yml`

```yaml
on:
  schedule:
    # UTC 23:00 = 北京时间 07:00（次日）
    # 避开整点高峰，选择 23:00（非整5整10）
    - cron: '0 23 * * *'  # 从 '23 23' 改为 '0 23'
  workflow_dispatch:
```

#### 步骤16.2：更新环境变量
**文件：** `.github/workflows/daily.yml`

```yaml
- name: 第一条：AI 日报
  env:
    # ... 其他环境变量
    CRON_HOUR: "23"      # 保持不变
    CRON_MINUTE: "0"     # 从 "23" 改为 "0"
  run: python ai_daily_push.py

- name: 第二条：财经日报
  env:
    # ... 其他环境变量
    CRON_HOUR: "23"
    CRON_MINUTE: "0"
  run: python finance_daily_push.py

- name: 记录推送时间
  if: always()
  run: python push_history_recorder.py --expected-time "23:00" --task "AI Daily Push"
  # 从 "23:23" 改为 "23:00"
```

#### 步骤16.3：验证AI日报窗口计算
**文件：** `ai_daily_push.py`

确认第242-247行的代码使用 `CRON_HOUR` 和 `CRON_MINUTE`：

```python
# 应该已经在问题2中修复
cron_hour = int(os.getenv('CRON_HOUR', '23'))
cron_minute = int(os.getenv('CRON_MINUTE', '0'))  # 默认值改为 0
```

#### 步骤16.4：验证财经日报窗口计算
**文件：** `finance_daily_push.py`

确认第1160行附近使用了 cron 配置：

```python
# 应该已经在问题7中修复
cron_hour = int(os.getenv('CRON_HOUR', '23'))
cron_minute = int(os.getenv('CRON_MINUTE', '0'))  # 默认值改为 0
```

#### 步骤16.5：更新推送历史默认时间
**文件：** `push_history_recorder.py`

```python
# 找到 expected_time 的默认值（约第50行）
parser.add_argument(
    "--expected-time",
    default="23:00",  # 从 "08:00" 或其他值改为 "23:00"
    help="预期推送时间 (HH:MM, UTC)"
)
```

#### 步骤16.6：更新阿里云函数监控配置
**说明：** 用户需要手动在阿里云控制台修改

**操作步骤：**
1. 登录阿里云函数计算控制台
2. 找到 `github-workflow-monitor` 函数
3. 修改触发器时间：
   - 原时间：`CRON: 0 30 8 * * *`（北京08:30）
   - 新时间：`CRON: 0 7 7 * * *`（北京07:07，比推送时间晚7分钟检查）
4. 保存并发布

#### 步骤16.7：更新云函数中的 expected_time
**文件：** `cloudfunction_handler.py`

```python
# 找到 EXPECTED_RUN_TIME 常量（约第20-30行）
EXPECTED_RUN_TIME = "23:00"  # UTC，对应北京时间 07:00
# 从 "23:23" 改为 "23:00"
```

#### 步骤16.8：更新所有文档和注释
**文件：** `README.md`, `CHANGELOG.md`, 代码注释

全局搜索替换：
- `07:23` → `07:00` （北京时间）
- `23:23` → `23:00` （UTC时间）

```bash
# 搜索所有相关引用
grep -r "23:23\|07:23" --include="*.md" --include="*.py" --include="*.yml"

# 逐个检查并更新
```

#### 步骤16.9：更新监控报告页面
**文件：** `push_history_recorder.py`

在生成 HTML 时显示正确的时间：

```python
def generate_html_report(history_data):
    html = f"""
    <div class="info-box">
      <h3>⏰ 预期推送时间</h3>
      <p>UTC 23:00（北京时间次日 07:00）</p>
      <!-- 从 "UTC 23:23（北京时间次日 07:23）" 改为上面 -->
    </div>
    """
```

#### 步骤16.10：创建迁移检查清单
**新文件：** `MIGRATION_CHECKLIST_TIME_CHANGE.md`

```markdown
# 时间变更检查清单（23:23 → 23:00 / 07:23 → 07:00）

## GitHub 端（自动生效）
- [ ] .github/workflows/daily.yml - cron 表达式
- [ ] workflow 环境变量 CRON_MINUTE
- [ ] push_history_recorder.py --expected-time 参数

## 代码端（自动生效）
- [ ] ai_daily_push.py - 窗口计算默认值
- [ ] finance_daily_push.py - 窗口计算默认值
- [ ] push_history_recorder.py - 默认 expected_time
- [ ] cloudfunction_handler.py - EXPECTED_RUN_TIME

## 阿里云端（手动操作）
- [ ] 函数触发器时间：0 30 8 → 0 7 7
- [ ] 函数配置验证

## 文档端
- [ ] README.md
- [ ] CHANGELOG.md
- [ ] 代码注释

## 验证
- [ ] 本地测试：export CRON_MINUTE=0
- [ ] 手动触发 workflow 测试
- [ ] 明天早上查看定时运行日志
- [ ] 检查推送到达时间
- [ ] 检查页面显示窗口时间
```

#### 验证方法
```bash
# 1. 本地测试
export CRON_HOUR=23
export CRON_MINUTE=0
python ai_daily_push.py --no-push
python finance_daily_push.py --no-push

# 2. 检查生成的 HTML
grep "windowStart\|windowEnd" ai_daily_dashboard.html
# 应该显示 "23:00:00" 而非 "23:23:00"

grep "windowStart\|windowEnd" finance_dashboard.html
# 同上

# 3. 浏览器检查
# AI 日报：收录窗口应显示 "9月1日 07:00 - 9月2日 07:00"
# 财经日报：收录窗口应显示 "9月1日 07:00 - 9月2日 07:00"

# 4. 提交代码
git add .
git commit -m "⏰ 调整推送时间：北京07:23→07:00 (UTC 23:23→23:00)"
git push

# 5. 手动触发测试
gh workflow run daily.yml

# 6. 查看推送历史
# 访问 https://yunix-intel.github.io/ai-daily-push/push_history.html
# 预期时间列应显示 "23:00 UTC"

# 7. 明天早上7:05查看企业微信
# AI日报应该在 07:00-07:10 之间到达
# 财经日报应该在 07:00-07:15 之间到达
```

---

## 总体实施计划

### 第一批（立即执行 - P0）
**预计耗时：2小时**

```bash
# 1. 修复依赖
pip install beautifulsoup4 lxml
git add requirements.txt
git commit -m "📦 添加 beautifulsoup4 依赖 (问题10)"

# 2. 修复新闻分类器
# 编辑 news_classifier.py（按步骤15.1）
python test_news_classifier.py
git add news_classifier.py test_news_classifier.py
git commit -m "🐛 修复新闻分类逻辑：内容优先于来源 (问题15)"

# 3. 修复突发事件分类
# 编辑 news_classifier.py（按步骤12.1）
# 编辑 finance_daily_push.py（按步骤12.2）
git add news_classifier.py finance_daily_push.py
git commit -m "🐛 修复突发事件分类 (问题12)"

# 4. 推送第一批修复
git push
```

### 第二批（今天完成 - P1）
**预计耗时：3小时**

```bash
# 5. 添加互斥锁
# 按步骤1.1-1.3操作
git add .github/workflows/daily.yml workflow_lock.py
git commit -m "🔒 添加互斥锁，防止重复推送 (问题1)"

# 6. 修复时间窗口
# 按步骤2.1-2.2（AI日报）和步骤7.1-7.2（财经日报）
git add ai_daily_push.py finance_daily_push.py .github/workflows/daily.yml
git commit -m "⏰ 修复收录窗口时间显示 (问题2,7)"

# 7. 修复指数0.00%
# 按步骤6.1-6.3
git add finance_daily_push.py
git commit -m "🐛 修复指数显示和缓存问题 (问题6)"

# 8. 添加页面导航
# 按步骤9.1-9.3
git add ai_daily_push.py finance_daily_push.py push_history_recorder.py
git commit -m "🔗 添加全局导航栏 (问题9)"

# 9. 推送第二批
git push
```

### 第三批（明天完成 - P2）
**预计耗时：4小时**

```bash
# 10. 恢复行业数据
# 按步骤4.1-4.3
# 需要检查 analyzers/ 目录是否完整

# 11. 添加AI日报翻译
# 按步骤5.1-5.4
git add ai_daily_push.py translation_service.py
git commit -m "✨ 添加AI日报翻译功能 (问题5)"

# 12. 添加财经分类tab
# 按步骤11.1-11.4
git add finance_daily_push.py
git commit -m "✨ 添加国内/国际要闻tab切换 (问题11)"

# 13. 过滤盘中信息
# 按步骤13.1-13.3
git add trading_calendar.py finance_daily_push.py
git commit -m "🔧 过滤盘中实时信息 (问题13)"

# 14. 添加财经翻译按钮
# 按步骤14.1-14.3
git add finance_daily_push.py
git commit -m "✨ 添加财经日报原文查看 (问题14)"

# 15. 推送第三批
git push
```

### 第四批（本周内 - P3 + 时间变更）
**预计耗时：2小时**

```bash
# 16. 两端对齐优化
# 按步骤3.1
git add ai_daily_push.py
git commit -m "💄 优化文本两端对齐 (问题3)"

# 17. 升级Node.js actions
# 按步骤8.2
git add .github/workflows/daily.yml
git commit -m "⬆️ 升级actions版本 (问题8)"

# 18. 时间变更（重要）
# 按步骤16.1-16.9
git add .github/workflows/daily.yml ai_daily_push.py finance_daily_push.py \
        push_history_recorder.py cloudfunction_handler.py README.md
git commit -m "⏰ 统一推送时间为北京07:00 (问题16)"

# 19. 推送最后一批
git push

# 20. 手动更新阿里云函数
# 按步骤16.6
```

### 验证清单

#### 每批推送后
- [ ] GitHub Actions 运行无错误
- [ ] 手动触发测试成功
- [ ] 本地生成测试成功

#### 第一批验证
- [ ] 资金流向数据出现
- [ ] "中国债券"归为国内
- [ ] "美军袭击"归为国际

#### 第二批验证
- [ ] 无重复推送
- [ ] 收录窗口显示正确
- [ ] 页面导航可用

#### 第三批验证
- [ ] AI日报有翻译按钮
- [ ] 财经日报有tab切换
- [ ] 盘中信息被过滤

#### 第四批验证（关键）
- [ ] 推送时间改为07:00
- [ ] 所有页面窗口显示07:00
- [ ] 阿里云监控在07:07触发

---

## 风险点和注意事项

### 高风险操作
1. **问题16（时间变更）**
   - 影响范围大，需要谨慎测试
   - 先在本地验证，再提交
   - 准备回滚方案

2. **问题1（互斥锁）**
   - 可能影响正常运行
   - 需要充分测试锁的获取和释放

### 中风险操作
3. **问题15（分类器重写）**
   - 可能改变大量新闻的分类
   - 需要抽样验证

4. **问题11（tab切换）**
   - JavaScript错误可能导致页面不可用
   - 需要浏览器测试

### 低风险操作
5. 其他CSS/文案修改

### 回滚方案
如果某批修复后出现问题：

```bash
# 查看最近的提交
git log --oneline -10

# 回滚到上一个版本
git revert <commit-hash>
git push

# 或者硬回滚（危险）
git reset --hard <good-commit-hash>
git push --force
```

---

## 测试脚本

**文件：** `test_all_fixes.sh`

```bash
#!/bin/bash
# 全面测试所有修复

echo "=== AI Daily Push 修复验证 ==="
echo ""

# 设置环境变量
export CRON_HOUR=23
export CRON_MINUTE=0

# 1. 测试依赖
echo "[1/10] 测试依赖..."
python -c "from bs4 import BeautifulSoup; print('  ✓ bs4')"
python -c "from scrapers.money_flow_scraper import MoneyFlowScraper; print('  ✓ money_flow_scraper')"

# 2. 测试分类器
echo "[2/10] 测试新闻分类器..."
python test_news_classifier.py

# 3. 测试AI日报
echo "[3/10] 测试AI日报生成..."
python ai_daily_push.py --no-push
if [ -f ai_daily_dashboard.html ]; then
  echo "  ✓ HTML生成成功"
  grep "windowStart.*23:00" ai_daily_dashboard.html && echo "  ✓ 窗口时间正确"
  grep "class=\"global-nav\"" ai_daily_dashboard.html && echo "  ✓ 导航存在"
fi

# 4. 测试财经日报
echo "[4/10] 测试财经日报生成..."
python finance_daily_push.py --no-push
if [ -f finance_dashboard.html ]; then
  echo "  ✓ HTML生成成功"
  grep "windowStart.*23:00" finance_dashboard.html && echo "  ✓ 窗口时间正确"
  grep "moneyFlow" finance_dashboard.html && echo "  ✓ 资金流向存在"
  grep "class=\"tab\"" finance_dashboard.html && echo "  ✓ tab存在"
fi

# 5. 测试互斥锁
echo "[5/10] 测试互斥锁..."
python workflow_lock.py && echo "  ✓ 锁获取成功"
python workflow_lock.py && echo "  ✗ 应该失败" || echo "  ✓ 重复运行被阻止"
python workflow_lock.py release && echo "  ✓ 锁释放成功"

# 6. 测试推送历史
echo "[6/10] 测试推送历史..."
python push_history_recorder.py --expected-time "23:00" --task "Test"
if [ -f push_history_report.html ]; then
  echo "  ✓ 报告生成成功"
  grep "23:00" push_history_report.html && echo "  ✓ 预期时间正确"
fi

# 7-10 省略其他测试...

echo ""
echo "=== 测试完成 ==="
```

---

**报告结束**

生成工具：Claude Opus 5
生成时间：2026-09-02 16:00
