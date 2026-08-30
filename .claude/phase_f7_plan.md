# Phase F7: 测试与优化 - 实施计划

## 📊 当前状态分析

### 已完成的财经日报功能（Phase F1-F5）
✅ **Phase F1**: 交易日历与节假日处理
✅ **Phase F2**: 新闻分类优化  
✅ **Phase F3**: 国际要闻翻译
✅ **Phase F4**: 全文翻译优化
✅ **Phase F5**: UI/UX 优化

### 测试范围
1. **单元测试** - 核心功能模块
2. **集成测试** - 完整流程测试
3. **边界测试** - 异常场景处理
4. **性能优化** - 响应时间和资源使用

---

## 🎯 Phase F7 目标

### 核心任务
1. **单元测试**（1小时）
   - 交易日历判断
   - 新闻分类逻辑
   - 翻译功能
   - HTML 生成

2. **集成测试**（1.5小时）
   - 常规交易日场景
   - 非交易日场景（周末）
   - 节假日后首日场景
   - 完整推送流程

3. **边界测试**（1小时）
   - LLM API 失败场景
   - 数据源不可用
   - 网络超时
   - 数据格式异常

4. **性能优化**（0.5小时）
   - 响应时间分析
   - 并发处理
   - 缓存优化

---

## 📋 实施步骤

### 步骤 1: 创建测试框架（15分钟）

**文件结构**：
```
tests/
├── __init__.py
├── test_finance_calendar.py      # 交易日历测试
├── test_finance_translation.py   # 翻译功能测试
├── test_finance_integration.py   # 集成测试
└── test_finance_edge_cases.py    # 边界测试
```

### 步骤 2: 单元测试（45分钟）

**test_finance_calendar.py**：
```python
import pytest
from datetime import datetime
from finance_daily_push import is_trading_day, get_display_date

def test_weekday_is_trading_day():
    """测试工作日是交易日"""
    # 2026-08-31 是周一
    assert is_trading_day(datetime(2026, 8, 31))

def test_weekend_not_trading_day():
    """测试周末不是交易日"""
    # 2026-08-30 是周日
    assert not is_trading_day(datetime(2026, 8, 30))

def test_holiday_not_trading_day():
    """测试节假日不是交易日"""
    # 2026-10-01 是国庆节
    assert not is_trading_day(datetime(2026, 10, 1))

def test_display_date_format():
    """测试日期显示格式"""
    date = datetime(2026, 8, 30)
    display = get_display_date(date)
    assert "2026" in display
    assert "08" in display or "8" in display
```

**test_finance_translation.py**：
```python
def test_translation_fallback():
    """测试翻译失败时的降级处理"""
    # 模拟翻译 API 失败
    pass

def test_translation_cache():
    """测试翻译缓存机制"""
    pass
```

### 步骤 3: 集成测试（1小时）

**test_finance_integration.py**：
```python
def test_regular_trading_day():
    """测试常规交易日完整流程"""
    # 1. 抓取行情数据
    # 2. 抓取新闻
    # 3. 翻译
    # 4. LLM 分析
    # 5. 生成 HTML
    pass

def test_weekend_scenario():
    """测试周末场景"""
    # 应该显示上周五的行情
    pass

def test_post_holiday_scenario():
    """测试节后首日场景"""
    # 应该正确处理跨假期行情
    pass

def test_html_generation():
    """测试 HTML 生成完整性"""
    # 验证所有板块都存在
    pass
```

### 步骤 4: 边界测试（45分钟）

**test_finance_edge_cases.py**：
```python
def test_llm_api_failure():
    """测试 LLM API 失败场景"""
    # 应该跳过分析，显示原始数据
    pass

def test_data_source_unavailable():
    """测试数据源不可用"""
    # 应该使用缓存或降级处理
    pass

def test_network_timeout():
    """测试网络超时"""
    # 应该有重试机制
    pass

def test_invalid_data_format():
    """测试数据格式异常"""
    # 应该有验证和错误处理
    pass

def test_empty_news_list():
    """测试无新闻数据场景"""
    # 应该优雅降级
    pass
```

### 步骤 5: 性能优化（30分钟）

**优化方向**：
1. 并发抓取多个数据源
2. 翻译批处理
3. LLM 调用合并
4. 缓存策略优化

---

## 🧪 测试清单

### 单元测试
- [ ] 交易日历判断（工作日/周末/节假日）
- [ ] 日期显示格式
- [ ] 新闻分类逻辑
- [ ] 翻译功能
- [ ] HTML 模板渲染

### 集成测试
- [ ] 常规交易日完整流程
- [ ] 周末场景（显示上周五）
- [ ] 节假日场景
- [ ] 节后首日场景
- [ ] HTML 生成完整性
- [ ] 推送功能（mock）

### 边界测试
- [ ] LLM API 失败
- [ ] 数据源不可用
- [ ] 网络超时
- [ ] 数据格式异常
- [ ] 空数据处理
- [ ] 编码问题

### 性能测试
- [ ] 总执行时间 < 3 分钟
- [ ] 内存使用 < 500MB
- [ ] 并发抓取效果
- [ ] 缓存命中率

---

## 📝 待办清单

- [ ] 1. 创建测试文件结构
- [ ] 2. 编写交易日历测试
- [ ] 3. 编写翻译功能测试
- [ ] 4. 编写集成测试
- [ ] 5. 编写边界测试
- [ ] 6. 运行所有测试
- [ ] 7. 修复发现的问题
- [ ] 8. 性能优化
- [ ] 9. 文档更新
- [ ] 10. 提交代码

---

## ⚠️ 注意事项

### 测试环境
- 使用 mock 数据避免真实 API 调用
- 设置测试用的环境变量
- 隔离测试数据和生产数据

### 性能基准
- 完整流程：< 3 分钟
- 数据抓取：< 30 秒
- LLM 分析：< 60 秒
- HTML 生成：< 5 秒

### 质量标准
- 单元测试覆盖率 > 70%
- 所有集成测试通过
- 边界测试无未处理异常
- 性能满足基准要求

---

## 🚀 准备开始实施

预计总时间：3-4 小时
优先级：🔴 高

准备退出计划模式，开始实施。
