# GitHub Actions 推送监测部署指南

本文档提供 4 种监测方案，可以根据你的情况选择：

---

## 📊 方案对比

| 方案 | 优点 | 缺点 | 成本 | 推荐度 |
|------|------|------|------|--------|
| **方案1: 本地定时任务** | 完全掌控、免费 | 需要电脑开机 | 免费 | ⭐⭐⭐ |
| **方案2: 云函数** | 独立可靠、免费额度大 | 需要注册账号 | 免费 | ⭐⭐⭐⭐⭐ |
| **方案3: Actions 自监测** | 无需外部服务 | 无法检测 Actions 整体故障 | 免费 | ⭐⭐⭐⭐ |
| **方案4: 历史记录** | 最简单、无需监测 | 无主动告警 | 免费 | ⭐⭐⭐⭐ |

**推荐组合**: 方案2（云函数） + 方案4（历史记录）

---

## 🎯 方案 1: 本地电脑定时任务

### 适用场景
- 你的电脑经常开机（如台式机、服务器）
- 不想注册云服务账号
- 需要完全掌控监测逻辑

### Windows 部署步骤

#### 1. 配置环境

在 `push_config.json` 中添加：
```json
{
  "github_repository": "owner/repo",
  "github_token": "ghp_xxx",
  "expected_run_time": "08:00",
  "delay_threshold": 600,
  "alert_wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
}
```

或设置环境变量：
```bash
setx GITHUB_REPOSITORY "owner/repo"
setx GITHUB_TOKEN "ghp_xxx"
setx ALERT_WECOM_WEBHOOK "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

#### 2. 创建 Windows 任务计划

1. 按 `Win + R`，输入 `taskschd.msc`，打开任务计划程序
2. 点击右侧"创建基本任务"
3. 配置如下：

**常规**:
- 名称: `GitHub Actions 监测`
- 描述: `每天 08:10 监测 GitHub Actions 推送状态`

**触发器**:
- 触发器类型: `每天`
- 开始时间: `08:10:00`
- 重复任务间隔: `不重复`

**操作**:
- 操作: `启动程序`
- 程序或脚本: `python.exe` 或 `pythonw.exe`（后台运行）
- 添加参数: `D:\c\ai-daily-push\local_monitor.py`
- 起始于: `D:\c\ai-daily-push`

**条件**:
- 取消勾选"只有在计算机使用交流电源时才启动此任务"

4. 完成后，右键任务 → "运行"，测试是否正常

#### 3. 测试

```bash
cd D:\c\ai-daily-push
python local_monitor.py --test
```

### Linux/Mac 部署步骤

#### 1. 配置环境

编辑 `~/.bashrc` 或 `~/.zshrc`：
```bash
export GITHUB_REPOSITORY="owner/repo"
export GITHUB_TOKEN="ghp_xxx"
export ALERT_WECOM_WEBHOOK="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
```

#### 2. 创建 cron 任务

```bash
crontab -e
```

添加：
```cron
# 每天 08:10 运行监测
10 8 * * * cd /path/to/ai-daily-push && python3 local_monitor.py >> /tmp/github_monitor.log 2>&1
```

#### 3. 测试

```bash
python3 local_monitor.py --test
```

---

## ☁️ 方案 2: 云函数（推荐）

### 适用场景
- 需要可靠的独立监测
- 电脑不是 24 小时开机
- 可以接受简单的账号注册

### 腾讯云函数部署

#### 1. 注册账号
- 访问 https://cloud.tencent.com/
- 注册账号并完成实名认证（需要身份证）

#### 2. 创建云函数

1. 进入控制台 → 搜索"云函数 SCF"
2. 选择地域（如"广州"）
3. 点击"新建"

**基础配置**:
- 函数名称: `github-actions-monitor`
- 运行环境: `Python 3.9`
- 创建方式: `空白函数`

**函数代码**:
- 提交方法: `本地上传 zip 包`

**准备代码包**:
```bash
cd D:\c\ai-daily-push

# 创建部署目录
mkdir deploy
cp cloudfunction_handler.py deploy/index.py
cp github_monitor.py deploy/
cp alerting.py deploy/
cp logger.py deploy/
cp monitoring.py deploy/

# 打包
cd deploy
powershell Compress-Archive -Path * -DestinationPath ../cloudfunction.zip
cd ..
```

上传 `cloudfunction.zip`

**高级配置**:
- 执行方法: `index.main_handler`
- 内存: `128 MB`（够用）
- 超时时间: `60 秒`

#### 3. 配置环境变量

在"函数配置" → "环境变量"中添加：

| 键 | 值 | 说明 |
|---|---|---|
| `GITHUB_REPOSITORY` | `owner/repo` | 你的仓库名 |
| `GITHUB_TOKEN` | `ghp_xxx` | GitHub Token（可选） |
| `EXPECTED_RUN_TIME` | `08:00` | 预期运行时间 |
| `DELAY_THRESHOLD` | `600` | 延迟阈值（秒） |
| `ALERT_WECOM_WEBHOOK` | `https://qyapi...` | 企业微信 Webhook |

#### 4. 创建定时触发器

在"触发管理" → "创建触发器"：
- 触发方式: `定时触发`
- 触发周期: `自定义`
- Cron 表达式: `0 10 0 * * * *`（每天 08:10 北京时间）

#### 5. 测试

点击"测试" → 查看"执行日志"

**查看日志**:
- 左侧菜单 → "日志查询"
- 查看运行结果

### 阿里云函数计算部署

步骤类似腾讯云，主要区别：

1. 访问 https://www.aliyun.com/
2. 控制台 → "函数计算 FC"
3. 创建服务 → 创建函数
4. 入口函数: `index.handler`（注意不是 main_handler）
5. Cron 表达式格式略有不同

**成本**: 完全免费（每月 100 万次调用，每天只用 1 次）

---

## 🔄 方案 3: GitHub Actions 自我监测

### 适用场景
- 不想配置外部服务
- 可以接受"Actions 整体故障时无法监测"的限制
- 希望一切都在 GitHub 内部

### 部署步骤

#### 1. 文件已创建

文件 `.github/workflows/monitor.yml` 已经创建好。

#### 2. 配置 Secrets

在 GitHub 仓库设置中添加（如果还没有）：
- `Settings` → `Secrets and variables` → `Actions`
- 添加以下 Secrets:
  - `ALERT_WECOM_WEBHOOK`
  - `ALERT_DINGTALK_WEBHOOK`（可选）
  - `ALERT_FEISHU_WEBHOOK`（可选）

#### 3. 启用 workflow

1. 提交 `.github/workflows/monitor.yml` 到仓库
2. 在 `Actions` 标签页可以看到新的 workflow
3. 第二天 08:15 会自动运行

#### 4. 手动测试

在 Actions 页面 → 选择 "Monitor Push Status" → "Run workflow"

### 工作原理

```
08:00 - 主任务运行（ai_daily_push.py）
08:15 - 监测任务运行
        ├─ 检查主任务是否在 08:00-08:15 之间运行
        ├─ 如果主任务延迟超过 15 分钟 → 告警
        └─ 如果主任务失败 → 告警
```

### 局限性

- 如果 GitHub Actions 整体故障（两个 workflow 都无法运行），无法监测
- 但能检测到"主任务延迟，监测任务正常"的情况（这是最常见的）

---

## 📈 方案 4: 推送时间历史记录（推荐）

### 适用场景
- 不需要实时告警
- 希望看到历史趋势
- 最简单，无需任何外部服务

### 部署步骤

#### 1. 修改主 workflow

编辑 `.github/workflows/daily-push.yml`，在推送任务**最后**添加：

```yaml
      # ... 现有步骤 ...

      - name: Record push time
        if: always()  # 即使前面失败也记录
        run: python push_history_recorder.py --expected-time "08:00"

      - name: Commit history
        if: always()
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add push_history.json push_history_report.html
          git diff --quiet && git diff --staged --quiet || git commit -m "📊 Update push history [skip ci]"
          git push
```

#### 2. 查看报告

每次推送后，访问：
```
https://你的用户名.github.io/ai-daily-push/push_history_report.html
```

或者在仓库中直接查看 `push_history_report.html`

### 报告内容

- **总推送次数**: 累计记录
- **平均延迟**: 历史平均值
- **最大/最小延迟**: 极值
- **延迟趋势图**: 可视化最近 30 天
- **详细记录表**: 每次推送的具体时间

### 优点

- ✅ 无需任何外部服务
- ✅ 可视化历史趋势
- ✅ 随时查看，不需要等告警
- ✅ 可以发现延迟规律（如某些日期总是慢）

---

## 🎯 推荐部署方案

### 最佳组合: 方案 2 + 方案 4

**为什么**:
1. **方案 4（历史记录）** - 先部署，最简单
   - 可以看到历史趋势
   - 主动发现问题

2. **方案 2（云函数）** - 再部署，可靠监测
   - 独立于 GitHub，真正的监测
   - 延迟超过阈值立即告警
   - 免费额度完全够用

### 快速开始（5 分钟）

#### 第一步: 部署历史记录（1 分钟）

编辑 `.github/workflows/daily-push.yml`，添加记录步骤（见上方）。

#### 第二步: 部署云函数（4 分钟）

1. 注册腾讯云账号（如果没有）
2. 创建云函数，上传代码包
3. 配置环境变量
4. 创建定时触发器

#### 完成！

- 每天自动记录推送时间
- 延迟超过 10 分钟自动告警到企业微信
- 随时查看历史趋势报告

---

## 🔧 故障排查

### 本地监测不运行

**问题**: Windows 任务计划没有执行
**解决**:
1. 检查任务是否启用
2. 检查"条件"选项卡，取消"只有在使用交流电源时"
3. 右键任务 → "运行"，查看是否报错
4. 查看"历史记录"标签页

### 云函数无法访问 GitHub

**问题**: GitHub API 超时
**解决**:
1. 检查云函数网络配置
2. 增加超时时间到 60 秒
3. 检查 GITHUB_TOKEN 是否有效

### Actions 监测不告警

**问题**: 主任务延迟，但监测任务没有告警
**解决**:
1. 检查 Secrets 是否配置
2. 手动运行监测 workflow，查看日志
3. 确认 github_monitor.py 语法正确

### 历史记录不更新

**问题**: push_history.json 没有提交
**解决**:
1. 检查 workflow 中是否有 `git push` 步骤
2. 检查是否有权限问题
3. 查看 Actions 日志，确认 commit 是否成功

---

## 📞 技术支持

如遇到问题，可以：
1. 查看本文档的故障排查部分
2. 检查 GitHub Actions 运行日志
3. 查看云函数执行日志
4. 提交 Issue 到仓库

---

## 📝 总结

4 种方案各有优劣，建议：

| 你的情况 | 推荐方案 |
|---------|---------|
| 电脑 24 小时开机 | 方案 1（本地） + 方案 4（历史） |
| 愿意注册云服务 | **方案 2（云函数） + 方案 4（历史）** ⭐ |
| 不想配置外部服务 | 方案 3（Actions） + 方案 4（历史） |
| 只想看历史，不需要告警 | 方案 4（历史） |

**最省心**: 方案 2 + 方案 4
