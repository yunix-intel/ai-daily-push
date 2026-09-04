# 剩余原始问题逐项验证报告

**验证日期：** 2026-09-04
**基准：** `FIX_PLAN_16_ISSUES.md` 与当前源码/最新 Actions 运行记录

| 问题 | 结论 | 证据 |
|---|---|---|
| 1 推送次数/时间异常 | ✅ 已实现 | `daily.yml` 有 concurrency；`workflow_lock.py` 存在；主任务最新运行成功 |
| 2 AI收录窗口 | ✅ 已实现 | `ai_daily_push.py` 输出 `windowStart/windowEnd`，由定时窗口计算 |
| 3 AI正文两端对齐 | ✅ 已实现 | `ai_daily_dashboard.html` 含 `text-align:justify` |
| 4 行业数据洞察 | ✅ 已验证 | 最新本地运行抓到 OpenRouter 427 个模型，生成3个市场指标卡片+2条趋势卡片 |
| 5 AI翻译按钮 | ✅ 已验证 | 最新页面包含5条 `translated_content`，且包含“翻译全文”按钮 |
| 6 指数0.00% | ✅ 已实现 | 已加入非交易时段上一交易日收盘价回退逻辑 |
| 7 财经收录窗口 | ✅ 已修复 | 以 cron 时间计算窗口；兼容旧版列表格式推送历史 |
| 8 Node.js弃用警告 | 🟡 代码已修复，待下次运行复核 | `monitor.yml` 已升级 checkout/setup-python 到 v7；升级前日志确认警告来自 v3/v4 action，尚无升级后的运行日志 |
| 9 Pages导航 | ✅ 已实现 | AI日报页面有财经/历史入口；财经页面有国内/国际/博主/Twitter导航逻辑 |
| 10 资金流向 | ✅ 已实现 | 北向/板块/个股独立兜底；不可用时有明确原因 |
| 11 国内/国际Tab | ✅ 已实现 | 财经模板包含国内/国际Tab和切换逻辑 |
| 12 突发事件分类 | ✅ 已实现 | `news_classifier.py` 提供突发识别及分类调用；现有回归覆盖接口 |
| 13 盘中信息过滤 | ✅ 已实现 | `filter_intraday_info()` 存在并在流程中调用 |
| 14 财经翻译按钮 | ✅ 已验证 | 财经模板保留翻译按钮及原文链接；数据契约测试通过 |
| 15 新闻分类逻辑 | ✅ 已实现 | 分类器内容优先于来源；中国关键词归国内 |
| 16 北京07:00触发 | ✅ 已实现 | `daily.yml` cron=`0 23 * * *`（UTC23:00=北京07:00） |

## 衍生问题

| 问题 | 结论 | 证据 |
|---|---|---|
| A Twitter分类展示 | ✅ 已验证 | rumor/media fixture 均进入HTML；传言显示“未经证实”；失败状态可见 |
| B AI全文翻译链路 | ✅ 已验证 | `translated_content` 从条目进入 `shape()` 和最终HTML；5条真实译文已生成 |

## 测试结果

- `test_step1_validation.py`：**6/6通过**
- `test_dashboard_contracts.py`：**5/5通过**
- 核心模块 `py_compile`：**通过**
- `ai_daily_push.py --no-push --date 2026-09-04`：**退出码0**
  - 8条英文条目成功批量翻译
  - 5篇全文翻译完成
  - OpenRouter抓到427个模型
  - 生成3个市场指标卡片、2条趋势卡片
  - 生成页面共34条内容
- `finance_daily_push.py --no-push --hours 24`：**超过10分钟仍未完成，被终止**；未将其标记为通过
- 最新 `daily.yml` run `33822925788`：**success**，未出现 Node20弃用警告
- 最新 `monitor.yml` run `33837015670`：**success**，但它运行的是升级前版本；日志确认 Node20 警告来源为 `actions/checkout@v3`、`actions/setup-python@v4`，需在提交/推送后复核新版运行日志

## 现存注意事项

- 完整旧测试套件 `test_all_functions.py` 当前为 **8通过、13错误**；错误主要来自测试与现有API不匹配（错误的 `self.cls`、过期函数签名、错误patch路径），不是本次核心修复回归。
- 财经日报真实端到端运行受外部网络/接口耗时影响，10分钟内未生成完整日志；因此不能宣称财经全流程真实运行通过。
- `finance_daily_push.py` 已做的结构化降级和页面契约测试通过。
- 最新实际生成的 `ai_daily_dashboard.html` 有未提交的动态产物改动，不应作为源码提交。
