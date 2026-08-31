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
- EXPECTED_RUN_TIME: 预期运行时间（默认 08:00）
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
        expected_time_str = os.environ.get('EXPECTED_RUN_TIME', '08:00')
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
        print(f"预期运行时间: {expected_time_str}")
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

        if created_at and run_started_at:
            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            started_time = datetime.fromisoformat(run_started_at.replace('Z', '+00:00'))

            # 计算预期时间
            expected_hour, expected_minute = map(int, expected_time_str.split(':'))
            expected_time = datetime.combine(
                today,
                datetime.min.time().replace(hour=expected_hour, minute=expected_minute)
            ).replace(tzinfo=timezone.utc)

            # 计算延迟
            delay_seconds = (started_time - expected_time).total_seconds()

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
