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
- EXPECTED_RUN_TIME: 预期运行时间（格式 HH:MM，默认 00:00）。
  * 默认按 **UTC 时间** 解析（本项目定时 cron 是 UTC 00:00）
  * 若设置了 EXPECTED_TIMEZONE，则按该时区解析（如 Asia/Shanghai 则填 08:00）
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
        expected_time_str = os.environ.get('EXPECTED_RUN_TIME', '00:00')
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

        # 创建监控器
        monitor = GitHubMonitor(repo=repo, workflow_name=workflow, token=token)

        # 获取今天的运行记录
        today = datetime.now(timezone.utc).date()
        runs = monitor.get_recent_runs(limit=10)

        # 过滤今天的运行
        today_runs = []
        for run in runs:
            created_at = run.get('created_at', '')
            if created_at:
                created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                if created_time.date() == today:
                    today_runs.append(run)

        if not today_runs:
            msg = f"今天 {today} 还没有运行记录"
            print(f"⚠️  {msg}")
            send_alert("WARNING", "GitHub Actions 未运行", msg, {
                "仓库": repo,
                "检查时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'warning', 'message': msg}, ensure_ascii=False)
            }

        # 检查最近一次运行
        latest_run = today_runs[0]
        created_at = latest_run.get('created_at', '')
        run_started_at = latest_run.get('run_started_at', '')
        conclusion = latest_run.get('conclusion', '')
        status = latest_run.get('status', '')

        # 还在跑的运行没有 conclusion（是 None/空），拿它跟 "success" 比
        # 会判定成「运行失败」，每天定时器早于 workflow 结束时都会误报。
        if status in ("queued", "in_progress", "waiting", "requested", "pending"):
            msg = f"运行 #{latest_run.get('run_number')} 仍在进行中（{status}），跳过本次判定"
            print(f"⏳ {msg}")
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'running', 'message': msg},
                                   ensure_ascii=False)
            }

        if created_at and run_started_at:
            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            started_time = datetime.fromisoformat(run_started_at.replace('Z', '+00:00'))

            # 计算预期时间
            expected_hour, expected_minute = map(int, expected_time_str.split(':'))

            # 根据 EXPECTED_TIMEZONE 决定时区
            if expected_tz_str:
                try:
                    tz = ZoneInfo(expected_tz_str)
                    # 在指定时区构造时间，然后转为 UTC
                    expected_time = datetime.combine(
                        today,
                        datetime.min.time().replace(hour=expected_hour, minute=expected_minute)
                    ).replace(tzinfo=tz).astimezone(timezone.utc)
                except Exception as e:
                    print(f"  [!] 时区 {expected_tz_str} 无效，回退到 UTC: {e}")
                    expected_time = datetime.combine(
                        today,
                        datetime.min.time().replace(hour=expected_hour, minute=expected_minute)
                    ).replace(tzinfo=timezone.utc)
            else:
                # 默认 UTC
                expected_time = datetime.combine(
                    today,
                    datetime.min.time().replace(hour=expected_hour, minute=expected_minute)
                ).replace(tzinfo=timezone.utc)

            # 计算延迟
            delay_seconds = (started_time - expected_time).total_seconds()

            # 负延迟 = 跑在预期时间之前（多半是手动触发，或 EXPECTED_RUN_TIME
            # 填成了北京时间）。这种情况不该按「提前」处理，夹到 0，
            # 否则日志里会出现 -11482 秒这种没意义的数字。
            if delay_seconds < 0:
                print(f"  [i] 实际启动早于预期时间 {abs(delay_seconds):.0f} 秒"
                      f"（手动触发，或 EXPECTED_RUN_TIME={expected_time_str} 未按 UTC 填写）")
                delay_seconds = 0

            print(f"最近运行:")
            print(f"  运行编号: {latest_run.get('run_number')}")
            print(f"  延迟: {delay_seconds:.0f} 秒 ({delay_seconds/60:.1f} 分钟)")
            print(f"  状态: {conclusion}")

            # 检查延迟
            if delay_seconds > threshold:
                print(f"❌ 延迟超过阈值")
                send_alert("ERROR", "GitHub Actions 推送延迟",
                    f"延迟 {delay_seconds:.0f} 秒（{delay_seconds/60:.1f} 分钟）",
                    {
                        "仓库": repo,
                        "运行编号": latest_run.get('run_number'),
                        "预期时间": expected_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "实际时间": started_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "延迟": f"{delay_seconds:.0f}秒",
                        "状态": conclusion,
                        "链接": latest_run.get('html_url', '')
                    }
                )
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'Delay detected',
                        'delay_seconds': delay_seconds
                    }, ensure_ascii=False)
                }

            # 检查运行状态
            if conclusion != "success":
                print(f"❌ 运行失败: {conclusion}")
                send_alert("ERROR", "GitHub Actions 运行失败",
                    f"运行状态: {conclusion}",
                    {
                        "仓库": repo,
                        "运行编号": latest_run.get('run_number'),
                        "状态": conclusion,
                        "链接": latest_run.get('html_url', '')
                    }
                )
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'status': 'error',
                        'message': 'Run failed',
                        'conclusion': conclusion
                    }, ensure_ascii=False)
                }

            print("✅ 运行正常")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'message': 'All good',
                    'delay_seconds': delay_seconds,
                    'conclusion': conclusion
                }, ensure_ascii=False)
            }

        # created_at / run_started_at 缺失时原来会直接落到函数末尾返回 None。
        # 阿里云 FC 对 None 返回值会报调用错误（函数被判定为执行异常），
        # 而且这条路径什么都没告警，等于静默失灵。
        msg = (f"运行 #{latest_run.get('run_number')} 缺少时间字段"
               f"（created_at={created_at!r}, run_started_at={run_started_at!r}），"
               f"无法计算延迟")
        print(f"⚠️  {msg}")
        return {
            'statusCode': 200,
            'body': json.dumps({'status': 'warning', 'message': msg,
                                'conclusion': conclusion}, ensure_ascii=False)
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
