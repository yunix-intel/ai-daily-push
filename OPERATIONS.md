# 运维手册

## 目录
1. [系统架构](#系统架构)
2. [部署指南](#部署指南)
3. [监控告警](#监控告警)
4. [日志管理](#日志管理)
5. [故障排查](#故障排查)
6. [性能优化](#性能优化)
7. [备份恢复](#备份恢复)
8. [安全加固](#安全加固)

---

## 系统架构

### 整体架构
```
┌─────────────────────────────────────────────────┐
│                 AI Daily Push                    │
├─────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────┐             │
│  │  AI日报     │  │  财经日报     │             │
│  │  模块       │  │  模块         │             │
│  └─────────────┘  └──────────────┘             │
│         │                 │                      │
│         └────────┬────────┘                      │
│                  ▼                               │
│         ┌────────────────┐                      │
│         │  数据聚合层    │                      │
│         │  - RSS抓取     │                      │
│         │  - API调用     │                      │
│         │  - LLM分类     │                      │
│         └────────────────┘                      │
│                  │                               │
│         ┌────────┴────────┐                      │
│         ▼                 ▼                      │
│  ┌──────────────┐  ┌──────────────┐            │
│  │  交易日历    │  │  推送渠道     │            │
│  │  (自动更新)  │  │  - 企业微信   │            │
│  └──────────────┘  │  - PushPlus   │            │
│                    └──────────────┘            │
│                                                  │
│  ┌─────────────────────────────────────────┐   │
│  │  基础设施层                              │   │
│  │  - 监控告警  - 日志系统  - 配置管理     │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 核心组件

1. **数据采集层**
   - AI HOT API 采集
   - RSS Feed 采集
   - 财经新闻采集
   - 交易日历自动更新

2. **数据处理层**
   - LLM 智能分类
   - 新闻重要性评分
   - 内容去重
   - 智能时间扩展

3. **推送层**
   - 企业微信推送
   - PushPlus 推送
   - Markdown 格式化

4. **基础设施层**
   - 监控告警系统
   - 结构化日志
   - 配置管理
   - 性能追踪

---

## 部署指南

### 环境要求

**硬件要求**
- CPU: 2核心以上
- 内存: 4GB 以上
- 磁盘: 20GB 以上

**软件要求**
- Python: 3.9+
- Git
- 操作系统: Linux/Windows/macOS

### 快速部署

#### 1. 克隆代码
```bash
git clone https://github.com/yunix-intel/ai-daily-push.git
cd ai-daily-push
```

#### 2. 安装依赖
```bash
pip install -r requirements.txt
```

#### 3. 生成配置文件
```bash
python config_manager.py
```

#### 4. 编辑配置
编辑 `config/production.yaml`:
```yaml
environment: production

llm:
  api_key: "your-api-key"
  model: "gpt-4"

push:
  wecom_corpid: "your-corpid"
  wecom_corpsecret: "your-secret"
  wecom_agentid: "1000002"
```

#### 5. 设置环境变量
```bash
# Linux/macOS
export APP_ENV=production
export LLM_API_KEY=sk-xxxxx
export WECOM_CORPID=xxxxx
export WECOM_CORPSECRET=xxxxx

# Windows
set APP_ENV=production
set LLM_API_KEY=sk-xxxxx
```

#### 6. 测试运行
```bash
# AI日报
python ai_daily_push.py --no-push

# 财经日报
python finance_daily_push.py --no-push
```

#### 7. 配置定时任务

**Linux (cron)**
```bash
# 编辑 crontab
crontab -e

# 添加定时任务
# AI日报：每天9点
0 9 * * * cd /path/to/ai-daily-push && python ai_daily_push.py

# 财经日报：工作日8:30
30 8 * * 1-5 cd /path/to/ai-daily-push && python finance_daily_push.py
```

**Windows (任务计划程序)**
```powershell
# 创建任务计划
schtasks /create /tn "AI Daily Push" /tr "python C:\path\to\ai_daily_push.py" /sc daily /st 09:00
```

### Docker 部署

#### 1. 构建镜像
```bash
docker build -t ai-daily-push:2.0.0 .
```

#### 2. 运行容器
```bash
docker run -d \
  --name ai-daily-push \
  -e APP_ENV=production \
  -e LLM_API_KEY=sk-xxxxx \
  -e WECOM_CORPID=xxxxx \
  -e WECOM_CORPSECRET=xxxxx \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/.cache:/app/.cache \
  ai-daily-push:2.0.0
```

#### 3. Docker Compose
```yaml
# docker-compose.yml
version: '3.8'

services:
  ai-daily-push:
    build: .
    image: ai-daily-push:2.0.0
    container_name: ai-daily-push
    environment:
      - APP_ENV=production
      - LLM_API_KEY=${LLM_API_KEY}
      - WECOM_CORPID=${WECOM_CORPID}
      - WECOM_CORPSECRET=${WECOM_CORPSECRET}
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./data:/app/data
      - ./.cache:/app/.cache
    restart: unless-stopped
```

---

## 监控告警

### 监控指标

1. **运行状态监控**
   - 任务执行成功率
   - 任务执行耗时
   - 数据获取数量

2. **数据质量监控**
   - 数据为空次数
   - 数据条数异常
   - API调用失败率

3. **系统资源监控**
   - CPU使用率
   - 内存使用率
   - 磁盘使用率

### 健康检查

```bash
# 查看健康状态
python -c "from monitoring import get_monitor; import json; print(json.dumps(get_monitor().get_health_status(), indent=2, ensure_ascii=False))"
```

### 告警规则

| 级别 | 条件 | 处理方式 |
|------|------|----------|
| WARNING | 数据量偏低（<5条） | 日志记录 |
| WARNING | 失败率 > 20% | 日志记录 |
| ERROR | 单次运行失败 | 日志+通知 |
| CRITICAL | 失败率 > 50% | 立即通知 |

### 配置告警渠道

编辑 `config/production.yaml`:
```yaml
monitoring:
  enabled: true
  alert_channels:
    - log
    - wecom  # 企业微信告警
    - email  # 邮件告警
```

---

## 日志管理

### 日志文件

```
logs/
├── ai_daily.json.log          # AI日报完整日志（JSON格式）
├── ai_daily.error.log         # AI日报错误日志
├── finance_daily.json.log     # 财经日报完整日志
├── finance_daily.error.log    # 财经日报错误日志
└── alerts_YYYY-MM-DD.jsonl    # 告警日志（按天）
```

### 日志查询

**查看最近10条错误**
```bash
tail -n 10 logs/ai_daily.error.log | jq .
```

**查询特定时间范围**
```bash
cat logs/ai_daily.json.log | jq 'select(.timestamp >= "2026-08-31T00:00:00")'
```

**统计错误类型**
```bash
cat logs/ai_daily.error.log | jq -r '.exception.type' | sort | uniq -c
```

### 日志轮转

日志自动轮转规则：
- JSON日志：每天轮转，保留30天
- 错误日志：10MB轮转，保留5个文件

### 日志清理

```bash
# 清理30天前的日志
find logs/ -name "*.log.*" -mtime +30 -delete

# 清理过期的告警日志
find logs/ -name "alerts_*.jsonl" -mtime +90 -delete
```

---

## 故障排查

### 常见问题

#### 1. 推送失败

**症状**: 日志中显示推送失败

**排查步骤**:
1. 检查配置
```bash
python -c "from config_manager import get_config; c=get_config(); print(f'企业微信: {bool(c.push.wecom_corpid)}')"
```

2. 检查网络连接
```bash
curl -X POST https://qyapi.weixin.qq.com/cgi-bin/gettoken
```

3. 验证密钥
```bash
# 检查环境变量
echo $WECOM_CORPID
echo $WECOM_CORPSECRET
```

**解决方案**:
- 确认企业微信配置正确
- 检查 IP 白名单
- 验证 secret 未过期

#### 2. 数据获取失败

**症状**: 获取到0条数据

**排查步骤**:
1. 检查网络
```bash
curl -I https://api.gptapi.us/ai-hot
```

2. 检查API状态
```bash
python -c "from ai_daily_push import fetch_daily; print(fetch_daily('2026-08-31'))"
```

3. 查看详细日志
```bash
python ai_daily_push.py --no-push 2>&1 | tee debug.log
```

**解决方案**:
- 检查数据源API是否正常
- 增加重试次数
- 使用备用数据源

#### 3. 交易日历错误

**症状**: 周一被判断为休市日

**排查步骤**:
1. 检查缓存
```bash
cat .cache/trading_calendar_cache.json | jq .
```

2. 清除缓存重新获取
```bash
rm -rf .cache
python -c "from trading_calendar import is_trading_day; import datetime; print(is_trading_day(datetime.date.today()))"
```

3. 检查GitHub数据源
```bash
curl https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/2026.json
```

**解决方案**:
- 清除缓存
- 检查网络访问 GitHub
- 使用本地预设数据

#### 4. LLM调用超时

**症状**: 任务执行时间过长

**排查步骤**:
1. 检查LLM配置
```bash
python -c "from config_manager import get_config; print(get_config().llm)"
```

2. 测试API连接
```bash
curl -X POST $LLM_BASE_URL/v1/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -d '{"model":"gpt-3.5-turbo","messages":[{"role":"user","content":"test"}]}'
```

**解决方案**:
- 增加超时时间
- 使用更快的模型
- 减少单次处理数据量

### 日志分析

**统计执行成功率**
```bash
cat logs/ai_daily.json.log | \
  jq -r 'select(.message | contains("执行")) | .message' | \
  sort | uniq -c
```

**查找慢查询**
```bash
cat logs/ai_daily.json.log | \
  jq 'select(.duration > 60) | {function, duration}'
```

### 性能分析

```bash
# 查看性能摘要
python -c "from monitoring import get_monitor; m=get_monitor(); print(m.get_health_status()['metrics'])"
```

---

## 性能优化

### 1. 并发优化

使用并发抓取提升速度：
```python
# 修改 ai_daily_push.py
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(fetch_rss, name, url) for name, url in RSS_FEEDS]
    results = [f.result() for f in futures]
```

### 2. 缓存优化

- 交易日历缓存30天
- LLM响应缓存24小时
- RSS内容缓存6小时

### 3. 数据库索引

如果使用数据库存储：
```sql
CREATE INDEX idx_timestamp ON news_items(timestamp);
CREATE INDEX idx_category ON news_items(category);
```

### 4. 资源限制

```yaml
# config/production.yaml
data_source:
  max_concurrent_requests: 10
  connection_pool_size: 20
  request_timeout: 30
```

---

## 备份恢复

### 备份策略

1. **配置文件备份**（每天）
```bash
tar -czf backup/config_$(date +%Y%m%d).tar.gz config/
```

2. **日志备份**（每周）
```bash
tar -czf backup/logs_$(date +%Y%m%d).tar.gz logs/
```

3. **数据备份**（每天）
```bash
tar -czf backup/data_$(date +%Y%m%d).tar.gz data/ .cache/
```

### 自动备份脚本

```bash
#!/bin/bash
# backup.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR="/backup/ai-daily-push"

mkdir -p $BACKUP_DIR

# 备份配置
tar -czf $BACKUP_DIR/config_$DATE.tar.gz config/

# 备份数据
tar -czf $BACKUP_DIR/data_$DATE.tar.gz data/ .cache/

# 清理30天前的备份
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete

echo "备份完成: $DATE"
```

### 恢复步骤

```bash
# 1. 停止服务
pkill -f ai_daily_push

# 2. 恢复配置
tar -xzf backup/config_20260831.tar.gz

# 3. 恢复数据
tar -xzf backup/data_20260831.tar.gz

# 4. 重启服务
python ai_daily_push.py &
```

---

## 安全加固

### 1. 敏感信息加密

```bash
# 使用环境变量而非配置文件
export WECOM_CORPSECRET=$(echo "your-secret" | base64)
```

### 2. API密钥轮转

定期（每90天）更换API密钥：
1. 生成新密钥
2. 更新环境变量
3. 验证新密钥
4. 废弃旧密钥

### 3. 访问控制

```yaml
# config/production.yaml
security:
  allowed_ips:
    - 192.168.1.0/24
  rate_limit:
    requests_per_minute: 60
```

### 4. 日志脱敏

敏感信息自动脱敏：
```python
# logger.py 已实现
# API密钥只显示前4位和后4位
```

---

## 附录

### A. 监控指标说明

| 指标名 | 说明 | 正常范围 |
|--------|------|----------|
| success_rate | 执行成功率 | >95% |
| avg_duration | 平均执行时间 | <120s |
| items_count | 获取数据条数 | >10 |
| cache_hit_rate | 缓存命中率 | >80% |

### B. 错误代码

| 代码 | 说明 | 处理方式 |
|------|------|----------|
| E001 | 配置文件缺失 | 运行 config_manager.py |
| E002 | API调用失败 | 检查网络和密钥 |
| E003 | 推送失败 | 检查推送配置 |
| E004 | 数据解析失败 | 检查数据源格式 |

### C. 联系方式

- GitHub Issues: https://github.com/yunix-intel/ai-daily-push/issues
- 文档: https://github.com/yunix-intel/ai-daily-push/wiki
