#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云函数部署脚本

支持腾讯云函数、阿里云函数计算等 Serverless 平台。

部署方式：

1. 腾讯云函数：
   - 登录腾讯云控制台 -> 云函数 SCF
   - 新建函数 -> Python 3.9
   - 上传代码：打包 cloudfunction_handler.py + github_monitor.py + alerting.py
   - 配置环境变量（见下方）
   - 设置定时触发器：cron: 0 10 0 * * * *（每天 08:10 北京时间）

2. 阿里云函数计算：
   - 登录阿里云控制台 -> 函数计算 FC
   - 创建服务 -> 创建函数
   - 运行环境：Python 3.9
   - 上传代码包
   - 配置环境变量
   - 创建定时触发器

环境变量配置：
- GITHUB_REPOSITORY: 仓库名（必需，如 owner/repo）
- GITHUB_TOKEN: GitHub Token（可选）
- GITHUB_WORKFLOW: Workflow 名称（可选）
- EXPECTED_RUN_TIME: 预期运行时间（格式 HH:MM，默认 23:23）。
  * 默认按 **UTC 时间** 解析（本项目定时 cron 是 UTC 23:23 = 北京时间次日 07:23）
  * 若设置了 EXPECTED_TIMEZONE，则按该时区解析（如 Asia/Shanghai 则填 07:23）
- EXPECTED_TIMEZONE: 可选，时区名（如 Asia/Shanghai）。设置后 EXPECTED_RUN_TIME 按此时区解析
- DELAY_THRESHOLD: 延迟阈值秒数（默认 600）
- ALERT_WECOM_WEBHOOK: 企业微信 Webhook
- ALERT_DINGTALK_WEBHOOK: 钉钉 Webhook
- ALERT_FEISHU_WEBHOOK: 飞书 Webhook

成本：
- 腾讯云：每月 100 万次免费调用
- 阿里云：每月 100 万次免费调用
- 每天运行 1 次，全年只用 365 次，完全免费
"""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# 北京时区常量（UTC+8）
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def format_beijing_time(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将 UTC 时间转换为北京时间字符串

    Args:
        dt: UTC datetime 对象
        fmt: 格式化字符串

    Returns:
        北京时间字符串（带时区标注）
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    beijing_dt = dt.astimezone(BEIJING_TZ)
    return beijing_dt.strftime(fmt) + " (北京时间)"


def main_handler(event, context):
    """
    云函数入口（腾讯云）

    Args:
        event: 触发事件
        context: 运行上下文

    Returns:
        响应结果
    """
    print("="*70)
    print("  GitHub Actions 云函数监测")
    print("="*70)
    print(f"触发时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Event: {json.dumps(event, ensure_ascii=False)}")
    print()

    try:
        # 导入监控模块
        from github_monitor import GitHubMonitor

        # 获取配置
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        token = os.environ.get('GITHUB_TOKEN', '')
        workflow = os.environ.get('GITHUB_WORKFLOW', '')
        expected_time_str = os.environ.get('EXPECTED_RUN_TIME', '23:00')  # UTC 23:00 = 北京时间次日 07:00
        expected_tz_str = os.environ.get('EXPECTED_TIMEZONE', '')
        threshold = int(os.environ.get('DELAY_THRESHOLD', 600))

        if not repo:
            error_msg = "错误: 未配置 GITHUB_REPOSITORY 环境变量"
            print(error_msg)
            return {
                'statusCode': 400,
                'body': json.dumps({'error': error_msg}, ensure_ascii=False)
            }

        print(f"监测仓库: {repo}")
        if workflow:
            print(f"Workflow: {workflow}")
        print(f"预期运行时间: {expected_time_str}" +
              (f" ({expected_tz_str})" if expected_tz_str else " (UTC)"))
        print(f"延迟阈值: {threshold} 秒")
        print()

        # Normalize an optional local expected time to the UTC HH:MM contract used
        # by GitHubMonitor. The date matters for zones with daylight saving time.
        expected_time_utc = expected_time_str
        if expected_tz_str:
            try:
                expected_tz = ZoneInfo(expected_tz_str)
                local_now = datetime.now(timezone.utc).astimezone(expected_tz)
                hour, minute = map(int, expected_time_str.split(":"))
                local_expected = local_now.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                expected_time_utc = local_expected.astimezone(
                    timezone.utc).strftime("%H:%M")
            except Exception as exc:
                print(f"  [!] 时区 {expected_tz_str} 无效，回退到 UTC: {exc}")

        monitor = GitHubMonitor(
            repo=repo,
            workflow_name=workflow,
            token=token,
            expected_time=expected_time_utc,
        )
        runs = monitor.get_recent_runs(limit=10)
        evaluation = monitor.evaluate_latest(runs, threshold)
        state = evaluation["state"]
        delay_seconds = float(evaluation.get("delay_seconds") or 0)
        result = {
            "status": state,
            "delay_seconds": delay_seconds,
            "scheduled_at": evaluation.get("scheduled_at", ""),
            "run_number": evaluation.get("run_number"),
            "alert": bool(evaluation.get("alert")),
        }

        if not evaluation.get("alert"):
            label = "等待计划任务" if state == "waiting" else "运行正常"
            print(f"[OK] {label}: {state}，相对计划时间 {delay_seconds:.0f} 秒")
            return {
                "statusCode": 200,
                "body": json.dumps(result, ensure_ascii=False),
            }

        labels = {
            "missing": "GitHub Actions 计划任务未创建",
            "queued": "GitHub Actions 计划任务排队延迟",
            "in_progress": "GitHub Actions 计划任务仍在运行",
            "failed": "GitHub Actions 计划任务运行失败",
            "success": "GitHub Actions 计划任务调度延迟",
        }
        title = labels.get(state, "GitHub Actions 状态异常")
        level = "ERROR" if state in ("missing", "failed") else "WARNING"
        message = f"相对计划时间 {delay_seconds:.0f} 秒（阈值 {threshold} 秒）"
        print(f"[{level}] {title}: {message}")
        send_alert(level, title, message, {
            "仓库": repo,
            "Workflow": workflow,
            "状态": state,
            "运行编号": evaluation.get("run_number", "未创建"),
            "计划时间": evaluation.get("scheduled_at", ""),
            "链接": evaluation.get("html_url", ""),
        })
        result["message"] = message
        # A monitor invocation that detects a hard condition must itself fail so
        # serverless health checks do not mistake an emitted alert for success.
        return {
            "statusCode": 503,
            "body": json.dumps(result, ensure_ascii=False),
        }

    except Exception as e:
        error_msg = f"监测失败: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_msg}, ensure_ascii=False)
        }


def handler(event, context):
    """
    云函数入口（阿里云）

    Args:
        event: 触发事件（bytes）
        context: 运行上下文

    Returns:
        响应结果
    """
    # 阿里云的 event 是 bytes，需要解析
    if isinstance(event, bytes):
        event = json.loads(event.decode('utf-8')) if event else {}

    return main_handler(event, context)


def send_alert(level, title, message, details=None):
    """发送告警"""
    try:
        from alerting import send_alert as send_alert_func
        send_alert_func(level, title, message, details)
    except Exception as e:
        print(f"发送告警失败: {e}")
        print(f"[{level}] {title}: {message}")
        if details:
            for key, value in details.items():
                print(f"  {key}: {value}")


if __name__ == "__main__":
    # 本地测试
    test_event = {}
    test_context = {}
    result = main_handler(test_event, test_context)
    print("\n测试结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
