# 监控告警配置指南

本文档说明如何配置和使用监控告警系统。

---

## 📋 概述

AI Daily Push 提供两套独立的推送系统：

| 系统 | 用途 | 配置 |
|------|------|------|
| **日报推送** | 每日定时推送AI日报和财经日报 | `WECOM_WEBHOOK`, `FEISHU_WEBHOOK`, `PUSHPLUS_TOKEN` |
| **监控告警** | 系统异常、推送失败、性能问题实时告警 | `ALERT_WECOM_WEBHOOK`, `ALERT_DINGTALK_WEBHOOK`, `ALERT_FEISHU_WEBHOOK` |

**建议**：使用不同的webhook，避免告警消息干扰日常推送。

---

## 🚀 快速开始

### Step 1: 选择告警渠道

支持4种告警推送方式（可同时配置多个）：

#### 方式1：企业微信群机器人（推荐）

**优点**：免费、稳定、支持Markdown格式

**配置步骤**：
1. 打开企业微信群聊
2. 点击群设置 → 群机器人 → 添加机器人
3. 选择"自定义机器人"，设置名称（如"系统告警"）
4. 复制webhook地址
5. 配置环境变量：
```bash
ALERT_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx
```

#### 方式2：钉钉群机器人

**配置步骤**：
1. 打开钉钉群聊
2. 群设置 → 智能群助手 → 添加机器人 → 自定义
3. 设置名称和安全设置（推荐使用加签）
4. 复制webhook和密钥
5. 配置环境变量：
```bash
ALERT_DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx
ALERT_DINGTALK_SECRET=SECxxxxxxxxxxxxxxx
```

#### 方式3：飞书群机器人

**配置步骤**：
1. 打开飞书群聊
2. 群设置 → 群机器人 → 添加机器人 → 自定义机器人
3. 设置名称和描述
4. 复制webhook地址
5. 配置环境变量：
```bash
ALERT_FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx
```

#### 方式4：自定义Webhook

**适用场景**：对接自研监控平台、PagerDuty、Slack等

**配置步骤**：
```bash
ALERT_WEBHOOK=https://your-monitoring-system.com/webhook/alert
```

**Payload格式**：
```json
{
  "level": "ERROR",
  "title": "推送失败",
  "message": "企业微信推送超时",
  "details": {
    "timestamp": "2026-08-31T10:30:00",
    "module": "ai_daily"
  }
}
```

---

### Step 2: 配置环境变量

#### 方式A：使用 .env 文件（本地运行）

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入实际的webhook地址
# 至少配置一种告警渠道
nano .env  # 或使用其他编辑器
```

#### 方式B：GitHub Actions Secrets

1. 进入仓库 Settings → Secrets and variables → Actions
2. 添加 Secret：
   - Name: `ALERT_WECOM_WEBHOOK`
   - Value: `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`
3. 在 `.github/workflows/daily_push.yml` 中配置：
```yaml
env:
  ALERT_WECOM_WEBHOOK: ${{ secrets.ALERT_WECOM_WEBHOOK }}
```

#### 方式C：云函数环境变量

**腾讯云**：函数配置 → 环境变量
**阿里云**：函数配置 → 环境变量

添加：
- `ALERT_WECOM_WEBHOOK`
- `GITHUB_TOKEN`
- `GITHUB_REPO`

---

### Step 3: 测试告警

运行测试脚本验证配置：

```bash
python -c "
from alerting import send_alert
send_alert(
    level='INFO',
    title='测试告警',
    message='监控系统配置成功！',
    details={'test': True}
)
print('✓ 告警发送成功，请检查群聊')
"
```

**预期结果**：
- 企业微信/钉钉/飞书群收到测试消息
- 终端输出 "✓ 告警发送成功"

---

## 📊 监控系统使用

### 在代码中使用

```python
from monitoring import get_monitor, AlertLevel

# 获取监控实例
monitor = get_monitor()

# 记录任务运行
monitor.record_run(
    module="ai_daily",
    success=True,
    duration=45.2,
    items_count=25
)

# 发送告警（会自动推送到配置的渠道）
monitor.alert(
    AlertLevel.ERROR,
    "推送失败",
    "企业微信推送超时：连接超过30秒"
)

# 检查健康状态
health = monitor.get_health_status()
print(health['status'])  # 'healthy' / 'degraded' / 'unhealthy'
```

### 告警级别

| 级别 | 使用场景 | 是否立即推送 |
|------|----------|------------|
| **INFO** | 正常信息，操作确认 | ✅ 是 |
| **WARNING** | 需要注意的问题 | ✅ 是 |
| **ERROR** | 错误，但系统可继续运行 | ✅ 是 |
| **CRITICAL** | 严重错误，需要立即处理 | ✅ 是 |

**所有级别的告警都会立即推送**，建议合理使用级别避免告警疲劳。

---

## 🔍 GitHub Actions 监控

### 功能

自动监控GitHub Actions运行状态：
- ✅ 检测推送是否按时执行
- ✅ 计算推送延迟时间
- ✅ 检测workflow失败
- ✅ 生成推送历史趋势报告

### 本地监控部署

```bash
# 配置环境变量
export GITHUB_TOKEN=ghp_xxxxx
export GITHUB_REPO=yunix-intel/ai-daily-push
export ALERT_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

# 手动运行一次
python local_monitor.py

# 查看监控报告
open github_monitor_report.html
```

### 云函数部署（推荐）

#### 腾讯云云函数

1. **创建函数**：
   - 登录 [腾讯云云函数控制台](https://console.cloud.tencent.com/scf)
   - 新建函数 → 从头开始
   - 函数名称：`github-actions-monitor`
   - 运行环境：Python 3.9
   - 函数代码：上传 `cloudfunction.zip`

2. **打包代码**：
```bash
zip cloudfunction.zip \
    cloudfunction_handler.py \
    github_monitor.py \
    alerting.py
```

3. **配置环境变量**：
```
GITHUB_TOKEN=ghp_xxxxx
GITHUB_REPO=yunix-intel/ai-daily-push
ALERT_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx
```

4. **配置触发器**：
   - 触发方式：定时触发
   - Cron表达式：`0 */2 * * * * *` （每2小时检查）
   - 或：`0 0 9,18 * * * *` （每天9点和18点检查）

5. **函数配置**：
   - 执行方法：`cloudfunction_handler.main`
   - 超时时间：60秒
   - 内存：128MB

#### 阿里云函数计算

1. **创建服务和函数**：
   - 登录 [阿里云函数计算控制台](https://fc.console.aliyun.com/)
   - 创建服务：`ai-daily-push`
   - 创建函数：`github-monitor`
   - 运行环境：Python 3.9
   - 函数入口：`cloudfunction_handler.main`

2. **上传代码**：
   - 上传方式：上传代码包
   - 将代码打包上传

3. **配置触发器**：
   - 触发器类型：定时触发器
   - Cron表达式：`0 0 */2 * * *` （每2小时）
   - Payload：`{}`

---

## 🔧 告警规则配置

### 自动触发告警的场景

| 场景 | 级别 | 触发条件 |
|------|------|----------|
| 任务执行失败 | ERROR | `success=False` |
| 数据为空 | WARNING | `items_count=0` |
| 性能下降 | WARNING | 执行时间超过历史平均值50% |
| GitHub Actions延迟 | WARNING/ERROR | 延迟超过5分钟 |
| GitHub Actions失败 | ERROR | workflow status = failure |
| 超过48小时未运行 | WARNING | 距离上次运行超过48小时 |

### 自定义告警

```python
# 在代码中自定义告警逻辑
if response_time > 5000:  # 5秒
    monitor.alert(
        AlertLevel.WARNING,
        "响应时间过长",
        f"API响应时间 {response_time}ms 超过阈值 5000ms"
    )

if error_rate > 0.1:  # 10%
    monitor.alert(
        AlertLevel.ERROR,
        "错误率过高",
        f"过去1小时错误率 {error_rate:.1%} 超过阈值 10%"
    )
```

---

## 📈 监控数据

### 查看监控指标

```python
# 获取监控数据
monitor = get_monitor()

# 健康状态
health = monitor.get_health_status()
print(f"状态: {health['status']}")
print(f"运行时间: {health['uptime']}秒")
print(f"问题: {health['issues']}")

# 导出指标
monitor.export_metrics("metrics.json")
```

### metrics.json 格式

```json
{
  "timestamp": "2026-08-31T10:30:00",
  "metrics": {
    "ai_daily": {
      "last_run": "2026-08-31T08:00:00",
      "success_count": 245,
      "failure_count": 3,
      "avg_duration": 180.5,
      "last_error": null
    },
    "finance_daily": {
      "last_run": "2026-08-31T08:05:00",
      "success_count": 243,
      "failure_count": 5,
      "avg_duration": 65.2,
      "last_error": null
    },
    "data_quality": {
      "ai_items_count": 25,
      "finance_items_count": 15,
      "empty_runs": 0,
      "last_check": "2026-08-31T08:05:00"
    }
  }
}
```

---

## 🛠️ 故障排查

### 告警未收到

**检查清单**：

1. **验证环境变量**：
```bash
python -c "import os; print('ALERT_WECOM_WEBHOOK:', os.getenv('ALERT_WECOM_WEBHOOK'))"
```

2. **测试webhook可达性**：
```bash
curl -X POST "YOUR_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"测试消息"}}'
```

3. **查看日志**：
```bash
# 查看告警日志
cat logs/alerts_$(date +%Y-%m-%d).jsonl

# 查看应用日志
cat logs/app.json.log | grep -i alert
```

4. **检查防火墙**：
   - 企业网络可能屏蔽webhook请求
   - 尝试从本地测试，排除网络问题

### 告警频繁

**优化建议**：

1. **调整告警阈值**：
```python
# 增加容忍度
if error_count > 5:  # 从3改为5
    monitor.alert(...)
```

2. **添加告警去重**：
```python
# 记录最近告警时间，避免短时间内重复告警
last_alert_time = {}

def alert_with_dedup(title, cooldown=300):
    now = time.time()
    if title in last_alert_time:
        if now - last_alert_time[title] < cooldown:
            return  # 冷却期内，跳过
    
    monitor.alert(AlertLevel.WARNING, title, "...")
    last_alert_time[title] = now
```

3. **使用聚合告警**：
```python
# 收集错误，定期汇总发送
errors = []
# ... 收集错误 ...

if len(errors) > 10:
    monitor.alert(
        AlertLevel.ERROR,
        f"累计 {len(errors)} 个错误",
        f"详情：{errors[:5]}..."
    )
```

---

## 📚 进阶配置

### 邮件告警

```bash
# .env
ALERT_EMAIL_SMTP_HOST=smtp.gmail.com
ALERT_EMAIL_SMTP_PORT=587
ALERT_EMAIL_USERNAME=your-email@gmail.com
ALERT_EMAIL_PASSWORD=your-app-password
ALERT_EMAIL_FROM=your-email@gmail.com
ALERT_EMAIL_TO=admin@example.com,ops@example.com
```

**注意**：Gmail需要使用应用专用密码，不能使用账号密码。

### 多渠道告警

```bash
# 同时配置多个渠道，所有渠道都会收到告警
ALERT_WECOM_WEBHOOK=https://qyapi.weixin.qq.com/...
ALERT_DINGTALK_WEBHOOK=https://oapi.dingtalk.com/...
ALERT_FEISHU_WEBHOOK=https://open.feishu.cn/...
```

### 告警过滤

```python
# 自定义告警过滤逻辑
class CustomMonitor(MonitorMetrics):
    def alert(self, level, title, message):
        # 过滤INFO级别告警
        if level == AlertLevel.INFO:
            return
        
        # 工作时间外降级
        hour = datetime.now().hour
        if hour < 9 or hour > 18:
            if level == AlertLevel.WARNING:
                return
        
        # 调用父类方法发送
        super().alert(level, title, message)
```

---

## 🎯 最佳实践

1. **分离推送渠道**：日报推送和告警推送使用不同的webhook
2. **合理使用级别**：INFO用于记录，WARNING用于关注，ERROR/CRITICAL用于行动
3. **定期回顾**：每周查看告警日志，优化告警规则
4. **避免告警疲劳**：控制告警频率，使用去重和聚合
5. **建立响应流程**：明确各级别告警的处理责任人和SLA

---

## 📞 支持

如有问题，请：
1. 查看 [故障排查](#故障排查) 章节
2. 查看日志文件：`logs/alerts_*.jsonl`
3. 提交 GitHub Issue：包含日志和配置（隐藏敏感信息）

---

**版本**: v3.0.1  
**更新日期**: 2026年8月31日
