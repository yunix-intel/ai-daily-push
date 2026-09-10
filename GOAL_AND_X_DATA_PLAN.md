# v4.0.0 发布目标与 X 财经信息采集方案

## Goal

在不伪造线上证据、不依赖真实网络的前提下，完成 `v4.0.0-rc.1` 的本地质量门禁：

1. `python -m unittest discover -v`：0 failures、0 errors。
2. 纳入审计范围的生产代码达到 100% 行覆盖率和 100% 分支覆盖率；不能用 pragma 隐藏业务分支。
3. 所有网络、LLM、推送、GitHub、Pages 和公众号路径均有确定性成功/空值/非法响应/异常/超时/重试耗尽测试。
4. 报告明确区分本地 mock 证据与真实外部验收；在外部门禁未完成前保持 `v4.0.0-rc.1`。
5. 只有真实公众号接口返回 `publish_id`、线上 workflow/Pages 和推送渠道验收完成后，才允许正式 `v4.0.0`。

## X 财经信息采集结论

**计划修订：不能只覆盖正规媒体。** 原程序已经列入了一组非正规媒体/传言来源，后续必须保留并纳入统一测试和日报数据契约，而不是被新的官方 API 适配替换掉。

### 来源分组（必须全部覆盖）

1. **传言/异动/研究机构来源（非正规媒体）**：沿用 `scrapers/twitter_scraper.py` 中现有的 `RUMOR_ACCOUNTS`，包括 `unusual_whales`、`HindenburgRes`、`muddywatersre`、`CitronResearch`、`zerohedge`、`DeItaone`、`Fxhedgers`。这些账号不是事实权威源，必须标记为 `category=rumors`、`verification=unverified`，并保留原文、作者、时间、链接及互动指标。
2. **正规媒体来源**：沿用现有 `MEDIA_ACCOUNTS`，包括 `WSJ`、`Bloomberg`、`FinancialTimes`、`Reuters`、`business`、`markets`。标记 `category=media`；`confirmed` 只描述来源类别，不代表系统已经独立核实事实。
3. **公开留言/市场讨论**：通过 Recent Search 按 cashtag、公司名、宏观关键词和 `conversation_id` 采集；标记 `category=comments`、`verification=unverified`。回复、引用和普通原创帖不能混为正规媒体消息。
4. **关键词发现的非关注账号**：搜索结果中出现的匿名账号、行业从业者、卖方/买方个人、研究员和做空报告账号可以作为候选传言，但必须经过去重、时间窗、互动量/作者信息保留和 LLM 噪声过滤；不能自动提升为 `media` 或 `confirmed`。

### 采集层（按优先级）

- **官方 X API v2（首选数据通道）**：对上述两组账号先解析用户名到 user ID，再调用用户时间线；Recent Search 用于留言、cashtag 和非关注账号发现。需要按 X 账户权限、配额和付费计划配置，线上可用性单独验收。
- **Filtered Stream（可选实时层）**：按 `from:`、cashtag、关键词和 `-is:retweet` 建立规则，分别写入 rumors/media/comments 队列；适合盘中告警，需要持续进程和规则管理，不作为日报离线任务唯一依赖。
- **RSSHub 镜像（兼容和降级层）**：保留现有账号时间线抓取和镜像重试，尤其保证上述 `RUMOR_ACCOUNTS` 不因官方 API 未配置而消失。RSSHub 不是官方数据源，不能替代线上 API 验收。
- **缓存/历史快照（开发和故障降级层）**：只允许使用带采集时间、来源和过期策略的历史数据；过期或格式损坏必须返回结构化失败，不能伪装成当天消息。

### 统一数据契约与处理规则

每条记录至少保留：`category`、`verification`、`username`、`author_id`、`id`、`title`、`content`、`link`、`pub_date`、`public_metrics`、`source`。传言、留言和正式消息分栏展示，不得互相覆盖。

- rumors：允许进入“传言”区，显著显示“未经证实”；同一事件多账号重复时聚合但保留来源列表。
- comments：默认只作为市场情绪/讨论素材，不作为事实陈述；回复链保留会话标识。
- media：允许进入“正式消息”区，但仍保留原始链接和发布时间。
- 所有类别：去重、24 小时窗口、异常内容过滤、LLM 失败时保留可追溯原文而不是丢失整组数据。

安全与质量约束：API token 只从环境变量读取；请求设置 timeout；分页和结果数量硬上限；解析异常返回结构化失败并 fallback；不抓取私密内容、不绕过登录/验证码、不进行批量账号扩张。测试必须分别验证 `RUMOR_ACCOUNTS`、`MEDIA_ACCOUNTS`、搜索留言和非关注账号发现路径。
## 执行顺序

1. 完成 X API 可选适配和 RSS fallback 的确定性测试。
2. 按 coverage 缺口补齐日报入口、共享模块、运维/发布模块。
3. 每轮运行 unittest、专项 tests、coverage、compileall 和页面契约。
4. 更新白盒报告并清理动态产物。
5. 本地门禁全部通过后，再安排外部验收；未通过则明确 BLOCKED，不发布正式大版本。
