# 全软件功能白盒测试报告（v4.0.0-rc.1）

- **测试日期：** 2026-09-09
- **候选版本：** `4.0.0-rc.1`
- **测试范围：** 主流程、配置、交易日历、抓取与并发、分类、翻译降级、市场/资金流、LLM 路由、HTML 契约、推送与监控相关可离线模块。
- **安全边界：** 未输出任何 API key、Webhook、cookie 或凭据；未执行批量推送、force-push 或破坏性操作。

## 1. 执行结果

| 检查 | 命令/证据 | 结果 |
|---|---|---|
| 全量 unittest discovery（当前可收集套件） | `PYTHONIOENCODING=utf-8 python -m unittest discover -v` | **PASS：180 tests，0 failures，0 errors，约 109.5s** |
| 生产代码编译 | `python -m compileall -q ai_daily_push.py finance_daily_push.py scrapers analyzers` | **PASS** |
| `tests/` unittest 套件 | `python -m unittest discover -s tests -v` | **PASS：8 tests，0 failures，0 errors，约 30.0s** |
| 财经完整入口套件 | `python tests/run_all_tests.py` | **PASS：集成 3/3、边界 6/6、性能达标，总耗时 1.80s** |
| 页面契约专项 | `python test_dashboard_contracts.py` | **PASS：5/5** |
| 覆盖率 | `python -m coverage erase && PYTHONIOENCODING=utf-8 python -m coverage run -m unittest discover -q && python -m coverage report -m`（配置见 `.coveragerc`） | **FAIL：测试执行 180/180；生产代码行覆盖率 88%（6372 statements，620 missed），分支 2014、partial branches 284；未达到全面覆盖门槛** |
| 全目录 compileall | `python -m compileall -q .` | **BLOCKED：未跟踪 `.claude/worktrees/` 副本中的旧 `trading_calendar.py` 在 line 557 有 IndentationError；生产目录定向编译通过** |

## 2. 测试基础设施修复

旧的 `test_*.py` 中有脚本在 import 阶段替换全局 `sys.stdout`，导致 unittest discovery 后续测试出现 `ValueError: I/O operation on closed file`。本候选版已：

1. 将旧脚本式检查改名为 `legacy_*_check.py`，避免导入阶段污染 unittest discovery。
2. 将 `test_full.py` 与 `test_all.py` 的 stdout 替换改为对现有流调用 `reconfigure`，不再包裹/关闭全局流。
3. 保留旧脚本文件内容，未删除其断言；它们仍可按脚本入口单独执行。

当前 unittest discovery 从此前不稳定状态提升为 **180 tests / 0 failures / 0 errors**。脚本式 legacy 检查仍属于独立风险项，未因排除 discovery 而被宣称覆盖。

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
- `concurrent_fetcher.py` 当前将 `max_retries` 定义为初始请求之后的重试次数；`max_retries=0` 仍执行一次初始请求。

## 4. 未覆盖或阻塞风险

1. **覆盖率报告已生成，但覆盖不足。** 当前行覆盖率为 **88%（6372 statements，620 missed）**，分支总数 2014、partial branches 284。核心主流程仍偏低：`ai_daily_push.py` 约 79%、`finance_daily_push.py` 约 82%；`enterprise_audit.py` 已纳入确定性测试，约 82%，但全局仍未达到行/分支 100% 门槛。
2. **微信公众号本地发布契约已加强，真实发布仍 BLOCKED。** 本地 mock 已覆盖 token、封面、草稿、发布和状态接口；便捷入口只有收到非空 `publish_id` 才返回成功。个人公众号的认证状态、账号类型及草稿/素材/发布接口权限仍待真实账号核实，目前没有真实 `publish_id`。
3. **X 数据已分为 rumors、media、comments。** 原非正规传言账号保留；官方 API 为可选首选通道，rumors/media 可独立回退 RSSHub；comments 来自 Recent Search，始终标记 `unverified`。真实 X API 权限、配额和可用性尚未线上验收。
4. **legacy 脚本尚未全部重构为 unittest TestCase。** 它们包含外部网络依赖和顶层执行逻辑，当前保留为独立脚本。
5. **本报告没有把历史 Actions/Pages/企业微信成功记录冒充当前候选提交证据。** 当前候选仍需受控线上 workflow 和消息核验后才具备正式版资格。

## 5. 候选发布判定

**结论：不得发布正式 `v4.0.0`。**

当前候选可以作为 `v4.0.0-rc.1` 进行预发布，原因是：

- 当前可收集 unittest：`180 tests / 0 failures / 0 errors`；
- `tests/` 套件：`8 tests / 0 failures / 0 errors`；
- 财经完整入口套件：集成 `3/3`、边界 `6/6`、性能检查全部通过；
- 页面契约：`5/5` 通过；
- 但当前生产范围行覆盖率为 88%，行和分支均未达到 100%；
- legacy 功能脚本未全部纳入统一 discovery；
- 当前提交尚未完成最新线上 X API、Actions、Pages、消息和公众号完整验收。

## 6. 本轮端到端无推送验收

- `PYTHONIOENCODING=utf-8 python ai_daily_push.py --no-push`：**PASS**。生成 `ai_daily_dashboard.html`，本轮收录 21 条；未执行消息推送。VentureBeat 返回 HTTP 429、关键指标接口出现 HTTP 504 后仍按降级路径完成。
- `PYTHONIOENCODING=utf-8 python finance_daily_push.py --no-push --hours 24`：**PASS（本地入口）**。生成 `finance_dashboard.html`；徐小明 24 小时内收录 3 篇、正文合计 1806 字；唐史主任司马迁 RSSHub 两个镜像均 HTTP 503，结构化标记不可用；微博内容未丢失到错误的成功状态。
- 本轮运行未发送企业微信、飞书、PushPlus 或公众号消息。

## 7. 外部验收状态

| 外部目标 | 状态 | 证据/限制 |
|---|---|---|
| GitHub Actions / Pages | **BLOCKED** | 本轮未执行线上 workflow 和页面发布验收，不能用本地生成结果替代。 |
| RSSHub（唐史主任司马迁） | **BLOCKED** | 2026-09-08 本地受控入口对两个镜像均收到 HTTP 503。 |
| X API | **BLOCKED** | 本轮未以真实凭据和配额完成线上验收；页面契约使用 mock/降级路径。 |
| 企业微信 / 飞书 | **BLOCKED** | `--no-push` 明确跳过推送，未执行真实发送。 |
| 公众号 | **BLOCKED** | 未获得真实非空 `publish_id`；本地 mock 不计为外部成功。 |
| GitHub Secret Scanning | **BLOCKED** | 本轮仅完成仓库文件静态扫描，未声称平台侧扫描已启用或通过。 |

## 8. 当前发布判定

**继续保留 `4.0.0-rc.1`，不得发布正式 `v4.0.0`。** 硬门禁中覆盖率为 88%（分支 2014、partial branches 284），且外部 Actions/Pages、RSSHub、X API、推送和公众号验收仍为 BLOCKED。