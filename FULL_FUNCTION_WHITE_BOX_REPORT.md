# 全软件功能白盒测试报告（v4.0.0-rc.1）

- **测试日期：** 2026-09-06
- **候选版本：** `4.0.0-rc.1`
- **测试范围：** 主流程、配置、交易日历、抓取与并发、分类、翻译降级、市场/资金流、LLM 路由、HTML 契约、推送与监控相关可离线模块。
- **安全边界：** 未输出任何 API key、Webhook、cookie 或凭据；未执行批量推送、force-push 或破坏性操作。

## 1. 执行结果

| 检查 | 命令/证据 | 结果 |
|---|---|---|
| 全量 unittest discovery（当前可收集套件） | `PYTHONIOENCODING=utf-8 python -m unittest discover -v` | **PASS：46 tests，0 failures，0 errors，约 0.79s** |
| 生产代码编译 | `python -m compileall -q ai_daily_push.py finance_daily_push.py llm_helpers.py concurrent_fetcher.py news_classifier.py article_translator.py github_monitor.py trading_calendar.py scrapers analyzers tests` | **PASS** |
| 并发控制专项 | `python test_concurrency_controls.py` | 历史证据：4/4 PASS |
| 页面契约专项 | `python test_dashboard_contracts.py` | 历史证据：5/5 PASS |
| 生成页面脚本检查 | `finance_dashboard.html` / `finance_dashboard_template.html` | **PASS：导航使用 `twitterData`，正文唯一使用 `twitter`，无同作用域重复声明** |
| 浏览器财经页桌面加载 | 静态预览 `finance_dashboard.html` | **PASS：页面可加载，console 无日志错误，snapshot 含行情、策略、Tab、国内/国际导航** |
| 覆盖率 | `python -m coverage ...` | **BLOCKED：环境未安装 coverage（`coverage=False`）** |
| 全目录 compileall | `python -m compileall -q .` | **BLOCKED：未跟踪 `.claude/worktrees/` 副本中的旧 `trading_calendar.py` 在 line 557 有 IndentationError；生产目录定向编译通过** |

## 2. 测试基础设施修复

旧的 `test_*.py` 中有脚本在 import 阶段替换全局 `sys.stdout`，导致 unittest discovery 后续测试出现 `ValueError: I/O operation on closed file`。本候选版已：

1. 将旧脚本式检查改名为 `legacy_*_check.py`，避免导入阶段污染 unittest discovery。
2. 将 `test_full.py` 与 `test_all.py` 的 stdout 替换改为对现有流调用 `reconfigure`，不再包裹/关闭全局流。
3. 保留旧脚本文件内容，未删除其断言；它们仍可按脚本入口单独执行。

这使当前 unittest discovery 从此前 `49 tests / 9 errors` 恢复为 `46 tests / 0 errors`。这不是把失败断言删除后宣称全覆盖；脚本式 legacy 检查仍属于未纳入自动 discovery 的风险项。

## 3. 功能覆盖清单

已由确定性测试或静态/契约证据覆盖：

- 财经文本清理、国内/国际分类、英文识别和聚合新闻过滤。
- LLM 分类批处理、关键词回退、重要性分数边界截断。
- DeepSeek/分析模型 semaphore 路由和并发边界。
- RSS deadline、超时结构化结果、输入 URL 键保留。
- 行情响应解析、北向资金有效零值与失败 shape、资金流排序。
- 交易日历、上一交易日和本地无网络契约。
- GitHub workflow monitor 延迟分析。
- 文章提取确定性 fallback、静态翻译页 HTML 转义。
- WeCom/HTML 渲染不下载外部资源的契约。
- 财经 HTML 内嵌数据、行情、策略、国内/国际 Tab 和导航。
- 标题/摘要翻译保留；生产全文翻译关闭及英文原文回退策略由源码和 workflow 静态证据覆盖。

## 4. 未覆盖或阻塞风险

1. **覆盖率工具未安装。** 因此不能给出可审计的行/分支覆盖率，也不能宣称“所有功能已达到覆盖门槛”。
2. **legacy 脚本尚未全部重构为 unittest TestCase。** 它们包含外部网络依赖和顶层执行逻辑，当前保留为独立脚本，未计入 46 个可收集测试。
3. **全目录编译被未跟踪 worktree 副本阻塞。** 该副本不属于发布内容；生产目录定向编译通过。
4. **微信公众号真实发布仍 BLOCKED。** 已知 Actions runner 出口 IP 不在公众号白名单；没有真实 `access_token`、封面上传、草稿创建、发布成功和 `publish_id`，不得判定成功。
5. **本报告没有把历史 Actions/Pages/企业微信成功记录冒充当前候选提交证据。** 当前候选仍需受控线上 workflow 和消息核验后才具备正式版资格。

## 5. 候选发布判定

**结论：不得发布正式 `v4.0.0`。**

当前候选可以作为 `v4.0.0-rc.1` 进行预发布，原因是：

- 当前可收集 unittest：`46 tests / 0 failures / 0 errors`；
- 但覆盖率不可审计；
- legacy 功能脚本未纳入统一 discovery；
- 全目录编译和微信公众号链路存在明确阻塞；
- 当前提交尚未完成最新线上 workflow、Pages、消息和公众号的完整验收。

升级正式版的必要条件：安装并运行 coverage、将 legacy 功能检查纳入受控测试入口且无失败、清除生产范围编译/测试阻塞、完成当前提交线上验收，并获得公众号真实 `publish_id`（或明确将其从正式门禁中移除并由用户批准）。
