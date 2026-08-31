# 阿里云函数计算配置指南

本指南说明如何将 AI Daily Push 的 GitHub Actions 监控部署到阿里云函数计算（FC 3.0）。

---

## 📋 概述

**目的**: 定时检查 GitHub Actions 推送任务的运行状态，异常时告警
**触发方式**: 定时触发器
**告警渠道**: 企业微信 / 钉钉 / 飞书

**核心特点**: 三个文件、零第三方依赖、直接复用仓库现有代码，不需要写任何新代码。

---

## 🚀 快速开始

### 前提条件

1. ✅ 阿里云账号（[注册地址](https://www.aliyun.com/)）
2. ✅ 已开通函数计算服务
3. ✅ GitHub Personal Access Token
4. ✅ 企业微信 / 钉钉 / 飞书 Webhook

### 核心步骤

1. 打包代码
2. 创建函数
3. 配置环境变量
4. 配置定时触发器
5. 测试验证

---

## 📦 步骤 1: 打包代码

仓库里的 `cloudfunction_handler.py` **已经包含阿里云入口函数** `handler(event, context)`，直接打包即可，不需要新建 `index.py`，也不需要改任何代码。

**推荐方式（跨平台，Windows / macOS / Linux 通用）**：

```bash
python -c "import zipfile; z=zipfile.ZipFile('function.zip','w',zipfile.ZIP_DEFLATED); [z.write(f,f) for f in ['cloudfunction_handler.py','github_monitor.py','alerting.py']]; z.close(); print('done')"
```

**macOS / Linux 也可以用 zip 命令**：

```bash
zip -j function.zip cloudfunction_handler.py github_monitor.py alerting.py
```

> ⚠️ Windows 的 Git Bash **不自带 `zip` 命令**（会报 `zip: command not found`），请用上面的 Python 方式，或在 PowerShell 中执行：
> ```powershell
> Compress-Archive -Path cloudfunction_handler.py,github_monitor.py,alerting.py -DestinationPath function.zip -Force
> ```

无论哪种方式，**三个 `.py` 必须位于压缩包根目录**（函数计算要求入口文件在根目录，不能带目录层级）。验证：

```bash
python -c "import zipfile; print(zipfile.ZipFile('function.zip').namelist())"
```

应输出 `['cloudfunction_handler.py', 'github_monitor.py', 'alerting.py']`，文件名前不带任何路径前缀。

### 关于依赖

**不需要 `requirements.txt`，也不需要配置层（Layer）。**

这三个模块只使用 Python 标准库（`json`、`os`、`urllib`、`datetime`、`typing`、`base64`、`enum`），HTTP 请求走 `urllib.request` 而非 `requests`。可自行验证：

```bash
grep -nE "^\s*(import|from) (requests|bs4|akshare|pandas)" cloudfunction_handler.py github_monitor.py alerting.py
```

无输出即确认零第三方依赖。

### 入口函数说明

| 函数 | 位置 | 用途 |
|------|------|------|
| `handler(event, context)` | `cloudfunction_handler.py` | **阿里云入口**，解析 bytes 型 event 后转交 `main_handler` |
| `main_handler(event, context)` | `cloudfunction_handler.py` | 实际监控逻辑，腾讯云也直接用这个 |

---

## 🌐 步骤 2: 创建函数

访问 [函数计算控制台](https://fc.console.aliyun.com/)，选择地域（推荐 **华东2（上海）**）。

> **注意**: FC 3.0 已取消「服务（Service）」层级，函数是一级实体，角色、日志、VPC 都在函数级别配置。**不需要先创建服务**——如果你看到的控制台仍要求创建服务，说明在 FC 2.0 界面，建议切换到 3.0。

### 2.1 基本配置

点击 **创建函数** → **从零开始创建**：

```yaml
函数名称: github-actions-monitor
运行环境: Python 3.10
代码上传方式: 上传代码包 → 本地上传 ZIP 包（function.zip）
```

### 2.2 函数配置

```yaml
请求处理程序: cloudfunction_handler.handler    # ← 注意不是 index.handler
内存规格: 128 MB
超时时间: 60 秒
实例并发度: 1
网络配置: 允许公网访问                          # ← 必须开启，需访问 api.github.com
```

「请求处理程序」的格式是 `文件名.函数名`，文件名不带 `.py` 后缀。填错会报 `Handler not found`。

---

## ⚙️ 步骤 3: 配置环境变量

在函数配置的「环境变量」中添加：

```yaml
GITHUB_REPOSITORY: yunix-intel/ai-daily-push
GITHUB_TOKEN: ghp_your_token_here
EXPECTED_RUN_TIME: "00:00"
DELAY_THRESHOLD: "1800"
ALERT_WECOM_WEBHOOK: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
```

### 变量说明

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `GITHUB_REPOSITORY` | ✅ | 无 | 仓库名，格式 `owner/repo` |
| `GITHUB_TOKEN` | 推荐 | 空 | 无 token 时 GitHub API 限流为 60 次/小时 |
| `GITHUB_WORKFLOW` | ❌ | 空 | **建议留空**，见下方陷阱 2 |
| `EXPECTED_RUN_TIME` | ❌ | `08:00` | **UTC 时间**，见下方陷阱 1 |
| `DELAY_THRESHOLD` | ❌ | `600` | 延迟告警阈值（秒） |
| `ALERT_WECOM_WEBHOOK` | 至少一个 | 空 | 企业微信机器人 |
| `ALERT_DINGTALK_WEBHOOK` | 至少一个 | 空 | 钉钉机器人，见下方陷阱 3 |
| `ALERT_FEISHU_WEBHOOK` | 至少一个 | 空 | 飞书机器人 |
| `ALERT_WEBHOOK` | 至少一个 | 空 | 自定义 webhook |

---

## ⚠️ 三个必读陷阱

以下三点配错不会报错，但会让监控**静默失效**。

### 陷阱 1: `EXPECTED_RUN_TIME` 必须填 UTC 时间

代码把这个值按 **UTC** 解析（`cloudfunction_handler.py` 中 `.replace(tzinfo=timezone.utc)`），而本项目的 workflow 是：

```yaml
schedule:
  - cron: '0 0 * * *'    # UTC 00:00 = 北京时间 08:00
```

所以这里要填 **`00:00`**，不是 `08:00`。

**填错的后果**: 若填 `08:00`，计算出的 `delay_seconds` 恒为约 −28800（负 8 小时），永远小于阈值，**延迟告警永不触发**。运行失败告警不受影响。

> 📌 如果日后修改了 workflow 的 cron，这里要同步改成对应的 UTC 时间。

### 陷阱 2: `GITHUB_WORKFLOW` 建议留空

代码用 `wf.get("name") == self.workflow_name` **精确匹配** workflow 名称，而本仓库的 workflow 叫：

```
每日推送：AI 日报 + 财经日报（企业微信 + GitHub Pages）
```

含中文全角冒号和括号，极易填错。**填错不会报错**，只是匹配不到 workflow ID，静默退化为监控全部 run。

既然如此，直接留空更省事，行为一致且不会误导。

### 陷阱 3: 钉钉加签暂未实现

`alerting.py` 中钉钉签名部分是 `# TODO: 如果配置了 secret，需要签名`，`ALERT_DINGTALK_SECRET` 虽然会被读取，但**从未参与请求签名**。

所以用钉钉时：
- 机器人安全设置选 **「自定义关键词」**（关键词建议填 `GitHub` 或告警标题中的固定词）
- 或选 **「IP 地址段」**（需要函数固定出口 IP，较麻烦）
- **不要选「加签」**——会一直返回 `310000` 签名校验失败

推荐直接用企业微信，无此问题。

---

## ⏰ 步骤 4: 配置定时触发器

在函数详情页 → **触发器** → **创建触发器**：

```yaml
触发器类型: 定时触发器
名称: monitor-schedule
触发方式: 自定义 CRON 表达式
CRON 表达式: 0 30 0 * * *
触发消息: {}
```

### CRON 表达式格式

阿里云 FC 使用 **6 段式**：`秒 分 时 日 月 周`，**默认 UTC 时区**。

| 表达式 | 含义（UTC） | 北京时间 | 适用场景 |
|--------|------------|---------|---------|
| `0 30 0 * * *` | 每天 00:30 | 08:30 | **推荐**，workflow 08:00 跑完后检查 |
| `0 0 */2 * * *` | 每 2 小时 | — | 高频监控 |
| `0 0 1 * * *` | 每天 01:00 | 09:00 | 留更多缓冲时间 |
| `0 0 0,12 * * *` | 每天 00:00、12:00 | 08:00、20:00 | 一天两次 |

### 用北京时间书写

不想做时区换算的话，加 `CRON_TZ` 前缀：

```
CRON_TZ=Asia/Shanghai 0 30 8 * * *
```

这与 `0 30 0 * * *` 完全等价。

> ⚠️ 常见错误：写成 5 段式（如 `0 */2 * * *`）会被当作 `秒 分 时 日 月` 解析，触发时间完全错乱。**务必写满 6 段。**

---

## ✅ 步骤 5: 测试验证

### 5.1 本地先跑一遍（推荐）

部署前先在本地确认逻辑正常，`cloudfunction_handler.py` 自带 `__main__` 入口：

```bash
PYTHONIOENCODING=utf-8 GITHUB_REPOSITORY=yunix-intel/ai-daily-push GITHUB_TOKEN=ghp_xxx EXPECTED_RUN_TIME=00:00 python cloudfunction_handler.py
```

> **Windows 用户注意** `PYTHONIOENCODING=utf-8` 不能省。代码里有 `✅` `❌` 等符号，Windows 控制台默认 GBK 编码会抛 `UnicodeEncodeError`，导致函数误报 500。**这只影响本地运行**，阿里云函数计算的运行环境是 UTF-8，不受影响。

预期输出监测详情，最后是 `statusCode: 200`。

若看到 `错误: 未配置 GITHUB_REPOSITORY 环境变量`，说明变量名写错了（常见错误是写成 `GITHUB_REPO`）。

### 5.2 控制台测试

1. 函数详情页点击 **测试函数**
2. 事件内容填 `{}`
3. 点击 **执行**

**预期返回**:

```json
{
  "statusCode": 200,
  "body": "{\"status\": \"success\", \"message\": \"All good\", ...}"
}
```

**其他可能的返回**:

| statusCode | status | 含义 |
|-----------|--------|------|
| 200 | `success` | 一切正常 |
| 200 | `warning` | 今天还没有运行记录（已发告警） |
| 200 | `error` | 运行失败或延迟超阈值（已发告警） |
| 400 | — | `GITHUB_REPOSITORY` 未配置 |
| 500 | — | 执行异常，看日志排查 |

### 5.3 验证告警

检查企业微信 / 钉钉 / 飞书群是否收到消息。收不到就查函数日志中 `发送告警失败` 的输出。

---

## 🔧 常见问题排查

### `Handler not found` / 找不到入口

请求处理程序应为 `cloudfunction_handler.handler`。检查：
- 是否误填了 `index.handler`
- ZIP 包内 `.py` 文件是否在根目录（见「步骤 1」的验证命令）

### `statusCode: 400`，提示未配置 GITHUB_REPOSITORY

环境变量名是 `GITHUB_REPOSITORY`（完整单词），不是 `GITHUB_REPO`。

### `ModuleNotFoundError: No module named 'github_monitor'`

ZIP 包里漏了文件，或打包时带了目录层级。用上文「步骤 1」的打包方式重新打包，并确认 `namelist()` 输出的文件名不带路径前缀。

### 连接 GitHub 超时

1. 确认函数配置中已开启 **允许公网访问**
2. 若函数配置了 VPC，需额外配置 NAT 网关才能出公网

### `API rate limit exceeded`

配置 `GITHUB_TOKEN`。未认证请求限额 60 次/小时，认证后 5000 次/小时。

### 函数执行超时

默认 60 秒足够。若超时，先看是不是卡在网络访问上，再考虑调到 120 秒。

### 告警一直不触发

按上文「三个必读陷阱」逐条检查，尤其是 `EXPECTED_RUN_TIME` 的时区。

---

## 💰 费用说明

FC 3.0 采用 **CU（计算单元）** 计费，涵盖 vCPU、内存、GPU、磁盘消耗。

### 本场景用量

| 项目 | 值 |
|------|-----|
| 内存 | 128 MB |
| 单次执行 | ~5 秒 |
| 频率 | 1 次/天（推荐配置） |
| 月调用量 | ~30 次 |

### 免费额度

新用户试用额度为 **每月 15 万 CU，最长 3 个月**（每自然月 1 日重置，中途领取则首月后半月与末月前半月合并算一个周期）。本场景用量远在额度内。

试用期结束后转按量付费，本场景月成本约几分钱。但注意两点：

- **公网出流量单独计费**，不含在 CU 额度内（本场景流量极小，可忽略）
- 单小时内若函数被调用过，折算金额低于 0.01 元时**按 0.01 元计费**。按每天 1 次算，月成本上限约 0.3 元

> 免费额度政策与单价可能调整，以[阿里云官方计费文档](https://help.aliyun.com/zh/functioncompute/fc-3-0/product-overview/billing-overview-of-fc)为准。

---

## 📊 告警规则

### 触发条件

| 场景 | 级别 | 判定逻辑 |
|------|------|---------|
| 今天无运行记录 | WARNING | 当天（UTC）没有任何 completed 的 run |
| 推送延迟 | ERROR | 实际启动时间 − `EXPECTED_RUN_TIME` > `DELAY_THRESHOLD` |
| 运行失败 | ERROR | 最近一次 run 的 `conclusion != "success"` |

### 告警内容

包含仓库名、运行编号、预期/实际时间、延迟秒数、状态、以及指向该次 run 的链接。

---

## 🔐 安全建议

### GitHub Token 权限最小化

只需勾选：
- `repo:status` — 查看 workflow 状态
- `actions:read` — 读取 Actions 运行记录

不需要任何写权限。私有仓库需要 `repo` 范围。

### 环境变量加密

敏感信息（Token、Webhook）建议在函数配置中启用 KMS 加密。

---

## 🔄 更新函数代码

改动 `github_monitor.py` 或 `alerting.py` 后，重新打包上传：

```bash
python -c "import zipfile; z=zipfile.ZipFile('function.zip','w',zipfile.ZIP_DEFLATED); [z.write(f,f) for f in ['cloudfunction_handler.py','github_monitor.py','alerting.py']]; z.close(); print('done')"
```

在控制台「代码」标签上传新 ZIP，点击 **部署代码**。

---

## 📚 参考资源

- [函数计算 FC 3.0 文档](https://help.aliyun.com/zh/functioncompute/fc/)
- [定时触发器](https://help.aliyun.com/zh/functioncompute/fc/user-guide/time-triggers)
- [FC 计费说明](https://help.aliyun.com/zh/functioncompute/fc-3-0/product-overview/billing-overview-of-fc)
- [新用户试用额度](https://help.aliyun.com/zh/functioncompute/fc-3-0/product-overview/trial-quota-1)

---

## ✨ 配置检查清单

部署完成后逐项核对：

- [ ] ZIP 包内三个 `.py` 在根目录（`namelist()` 无路径前缀）
- [ ] 请求处理程序为 `cloudfunction_handler.handler`
- [ ] 已开启「允许公网访问」
- [ ] `GITHUB_REPOSITORY`（不是 `GITHUB_REPO`）已配置
- [ ] `EXPECTED_RUN_TIME` 填的是 UTC 时间（本项目为 `00:00`）
- [ ] `GITHUB_WORKFLOW` 留空
- [ ] 至少配置了一个告警渠道 Webhook
- [ ] 钉钉机器人未使用「加签」模式
- [ ] CRON 表达式是 6 段式
- [ ] 手动测试返回 `statusCode: 200`
- [ ] 告警群收到过测试消息

---

**配置耗时**: 约 10-15 分钟
**维护成本**: 试用额度内免费，之后约 0.3 元/月
