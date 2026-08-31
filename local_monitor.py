#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地定时监测脚本

用于在本地电脑上定时运行，监测 GitHub Actions 是否按时执行。

使用方式：
1. Windows 任务计划程序：
   - 打开"任务计划程序"
   - 创建基本任务
   - 触发器：每天 08:10
   - 操作：启动程序 python.exe
   - 参数：D:\c\ai-daily-push\local_monitor.py

2. Linux/Mac cron：
   10 8 * * * cd /path/to/ai-daily-push && python3 local_monitor.py

3. 直接运行测试：
   python local_monitor.py --test

配置：
通过环境变量或 push_config.json 配置：
- GITHUB_REPOSITORY: 仓库名（如 owner/repo）
- GITHUB_TOKEN: GitHub Token（可选，提高 API 限制）
- ALERT_WECOM_WEBHOOK: 企业微信 Webhook（告警通知）
- EXPECTED_RUN_TIME: 预期运行时间（默认 08:00）
- DELAY_THRESHOLD: 延迟阈值秒数（默认 600，即 10 分钟）
"""
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from github_monitor import GitHubMonitor

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def load_config():
    """加载配置"""
    config = {}

    # 尝试从 push_config.json 读取
    config_file = os.path.join(os.path.dirname(__file__), "push_config.json")
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            print(f"读取配置文件失败: {e}")

    # 环境变量优先级更高
    env_keys = {
        'GITHUB_REPOSITORY': 'github_repository',
        'GITHUB_TOKEN': 'github_token',
        'ALERT_WECOM_WEBHOOK': 'alert_wecom_webhook',
        'EXPECTED_RUN_TIME': 'expected_run_time',
        'DELAY_THRESHOLD': 'delay_threshold'
    }

    for env_key, config_key in env_keys.items():
        value = os.environ.get(env_key)
        if value:
            config[config_key] = value

    return config


def check_github_actions():
    """检查 GitHub Actions 运行状态"""
    config = load_config()

    # 获取配置
    repo = config.get('github_repository', os.environ.get('GITHUB_REPOSITORY', ''))
    token = config.get('github_token', os.environ.get('GITHUB_TOKEN', ''))
    expected_time_str = config.get('expected_run_time', '08:00')
    threshold = int(config.get('delay_threshold', 600))  # 默认 10 分钟

    if not repo:
        print("错误: 未配置 GITHUB_REPOSITORY")
        print("请在 push_config.json 中添加 'github_repository' 或设置环境变量")
        return False

    print(f"监测仓库: {repo}")
    print(f"预期运行时间: {expected_time_str}")
    print(f"延迟阈值: {threshold} 秒")
    print()

    try:
        # 创建监控器
        monitor = GitHubMonitor(repo=repo, token=token)

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
            print("⚠️  今天还没有运行记录")
            send_alert(
                "WARNING",
                "GitHub Actions 未运行",
                f"今天 {today} 还没有发现运行记录",
                {"仓库": repo, "检查时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            )
            return False

        # 检查最近一次运行
        latest_run = today_runs[0]
        created_at = latest_run.get('created_at', '')
        run_started_at = latest_run.get('run_started_at', '')
        conclusion = latest_run.get('conclusion', '')

        if created_at and run_started_at:
            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            started_time = datetime.fromisoformat(run_started_at.replace('Z', '+00:00'))

            # 计算预期时间（今天的 expected_time_str）
            expected_hour, expected_minute = map(int, expected_time_str.split(':'))
            expected_time = datetime.combine(
                today,
                datetime.min.time().replace(hour=expected_hour, minute=expected_minute)
            ).replace(tzinfo=timezone.utc)

            # 计算延迟
            delay_seconds = (started_time - expected_time).total_seconds()

            print(f"最近运行:")
            print(f"  运行编号: {latest_run.get('run_number')}")
            print(f"  创建时间: {created_at}")
            print(f"  开始时间: {run_started_at}")
            print(f"  预期时间: {expected_time.isoformat()}")
            print(f"  延迟: {delay_seconds:.0f} 秒 ({delay_seconds/60:.1f} 分钟)")
            print(f"  状态: {conclusion}")
            print()

            # 检查延迟
            if delay_seconds > threshold:
                print(f"❌ 延迟超过阈值 {threshold} 秒")
                send_alert(
                    "ERROR",
                    "GitHub Actions 推送延迟",
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
                return False

            # 检查运行状态
            if conclusion != "success":
                print(f"❌ 运行失败: {conclusion}")
                send_alert(
                    "ERROR",
                    "GitHub Actions 运行失败",
                    f"运行状态: {conclusion}",
                    {
                        "仓库": repo,
                        "运行编号": latest_run.get('run_number'),
                        "状态": conclusion,
                        "链接": latest_run.get('html_url', '')
                    }
                )
                return False

            print("✅ 运行正常")
            return True

    except Exception as e:
        print(f"监测失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_alert(level, title, message, details=None):
    """发送告警"""
    try:
        from alerting import send_alert as send_alert_func
        send_alert_func(level, title, message, details)
    except ImportError:
        print(f"[{level}] {title}: {message}")
        if details:
            for key, value in details.items():
                print(f"  {key}: {value}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="本地定时监测 GitHub Actions")
    parser.add_argument('--test', action='store_true', help="测试模式（立即运行一次）")
    args = parser.parse_args()

    print("="*70)
    print("  GitHub Actions 本地监测")
    print("="*70)
    print(f"运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    success = check_github_actions()

    print()
    print("="*70)
    if success:
        print("✅ 监测完成，一切正常")
    else:
        print("⚠️  监测完成，发现问题")
    print("="*70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
