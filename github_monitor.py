#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions 推送监测

监测 GitHub Actions workflow 运行状态，记录计划时间 vs 实际执行时间。

功能：
1. 获取 workflow 运行记录
2. 计算推送延迟（实际时间 - 计划时间）
3. 生成延迟报告
4. 集成到监控告警系统
5. 统计成功率、平均延迟

使用示例：
    from github_monitor import GitHubMonitor

    # 创建监控实例
    monitor = GitHubMonitor(
        repo="owner/repo",
        workflow_name="AI Daily Push",
        token="ghp_xxx"  # 可选
    )

    # 获取最近运行记录
    runs = monitor.get_recent_runs(limit=10)

    # 分析延迟
    report = monitor.analyze_delays()
    print(f"平均延迟: {report['average_delay_seconds']}秒")
    print(f"成功率: {report['success_rate']}%")

    # 生成 HTML 报告
    monitor.generate_report("github_monitor_report.html")

配置：
    通过环境变量配置：
    - GITHUB_TOKEN: GitHub Personal Access Token（可选，提高 API 限制）
    - GITHUB_REPO: 仓库名（格式：owner/repo）
    - GITHUB_WORKFLOW: Workflow 名称
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Any
import base64


class GitHubMonitor:
    """GitHub Actions 监控器"""

    def __init__(self, repo: Optional[str] = None, workflow_name: Optional[str] = None, token: Optional[str] = None):
        """
        初始化监控器

        Args:
            repo: 仓库名（格式：owner/repo）
            workflow_name: Workflow 名称
            token: GitHub Personal Access Token（可选）
        """
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self.workflow_name = workflow_name or os.environ.get("GITHUB_WORKFLOW", "")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

        if not self.repo:
            raise ValueError("必须提供仓库名（GITHUB_REPOSITORY 或 repo 参数）")

        self.api_base = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Daily-Push-Monitor"
        }

        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def get_recent_runs(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        获取最近的 workflow 运行记录

        Args:
            limit: 获取数量

        Returns:
            运行记录列表
        """
        url = f"{self.api_base}/repos/{self.repo}/actions/runs"
        params = {
            "per_page": limit,
            "status": "completed"  # 只获取已完成的运行
        }

        if self.workflow_name:
            # 如果指定了 workflow 名称，先获取 workflow ID
            workflow_id = self._get_workflow_id()
            if workflow_id:
                params["workflow_id"] = workflow_id

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"

        try:
            data = self._http_get(full_url)
            return data.get("workflow_runs", [])
        except Exception as e:
            print(f"获取运行记录失败: {e}")
            return []

    def _get_workflow_id(self) -> Optional[int]:
        """获取 workflow ID"""
        url = f"{self.api_base}/repos/{self.repo}/actions/workflows"

        try:
            data = self._http_get(url)
            workflows = data.get("workflows", [])

            for wf in workflows:
                if wf.get("name") == self.workflow_name:
                    return wf.get("id")

            return None
        except Exception:
            return None

    def analyze_delays(self, runs: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        分析推送延迟

        Args:
            runs: 运行记录列表（可选，不提供则自动获取）

        Returns:
            延迟分析报告
        """
        if runs is None:
            runs = self.get_recent_runs()

        if not runs:
            return {
                "total_runs": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0,
                "average_delay_seconds": 0,
                "max_delay_seconds": 0,
                "delays": []
            }

        success_count = 0
        failure_count = 0
        delays = []

        for run in runs:
            conclusion = run.get("conclusion", "")
            if conclusion == "success":
                success_count += 1
            else:
                failure_count += 1

            # 计算延迟
            created_at = run.get("created_at", "")
            run_started_at = run.get("run_started_at", "")

            if created_at and run_started_at:
                created_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                started_time = datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
                delay_seconds = (started_time - created_time).total_seconds()

                delays.append({
                    "run_id": run.get("id"),
                    "run_number": run.get("run_number"),
                    "created_at": created_at,
                    "started_at": run_started_at,
                    "delay_seconds": delay_seconds,
                    "conclusion": conclusion,
                    "html_url": run.get("html_url")
                })

        total_runs = len(runs)
        success_rate = (success_count / total_runs * 100) if total_runs > 0 else 0
        average_delay = sum(d["delay_seconds"] for d in delays) / len(delays) if delays else 0
        max_delay = max((d["delay_seconds"] for d in delays), default=0)

        return {
            "total_runs": total_runs,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_rate, 2),
            "average_delay_seconds": round(average_delay, 2),
            "max_delay_seconds": round(max_delay, 2),
            "delays": sorted(delays, key=lambda x: x["delay_seconds"], reverse=True)
        }

    def check_and_alert(self, threshold_seconds: int = 300) -> bool:
        """
        检查最近一次运行是否延迟超过阈值，超过则告警

        Args:
            threshold_seconds: 延迟阈值（秒）

        Returns:
            是否触发告警
        """
        runs = self.get_recent_runs(limit=1)
        if not runs:
            return False

        report = self.analyze_delays(runs)
        delays = report.get("delays", [])

        if not delays:
            return False

        latest_delay = delays[0]
        delay_seconds = latest_delay["delay_seconds"]

        if delay_seconds > threshold_seconds:
            # 触发告警
            try:
                from alerting import send_alert

                send_alert(
                    level="WARNING",
                    title="GitHub Actions 推送延迟",
                    message=f"延迟 {delay_seconds:.0f} 秒（阈值 {threshold_seconds} 秒）",
                    details={
                        "仓库": self.repo,
                        "Workflow": self.workflow_name,
                        "运行编号": latest_delay["run_number"],
                        "计划时间": latest_delay["created_at"],
                        "实际时间": latest_delay["started_at"],
                        "延迟": f"{delay_seconds:.0f}秒",
                        "链接": latest_delay["html_url"]
                    }
                )
            except ImportError:
                print(f"⚠️  延迟告警: {delay_seconds:.0f}秒")

            return True

        return False

    def generate_report(self, output_file: str = "github_monitor_report.html"):
        """
        生成 HTML 可视化报告

        Args:
            output_file: 输出文件路径
        """
        runs = self.get_recent_runs()
        report = self.analyze_delays(runs)

        html = self._build_html_report(report)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"报告已生成: {output_file}")

    def _build_html_report(self, report: Dict[str, Any]) -> str:
        """构建 HTML 报告"""
        delays = report.get("delays", [])

        # 构建延迟表格
        rows = ""
        for d in delays[:20]:  # 只显示前20条
            delay_class = "delay-high" if d["delay_seconds"] > 300 else "delay-normal"
            conclusion_class = "success" if d["conclusion"] == "success" else "failure"

            rows += f"""
                <tr>
                    <td>{d["run_number"]}</td>
                    <td>{d["created_at"]}</td>
                    <td>{d["started_at"]}</td>
                    <td class="{delay_class}">{d["delay_seconds"]:.0f}秒</td>
                    <td class="{conclusion_class}">{d["conclusion"]}</td>
                    <td><a href="{d["html_url"]}" target="_blank">查看</a></td>
                </tr>
            """

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub Actions 推送监测报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; margin-bottom: 10px; }}
        .subtitle {{ color: #666; margin-bottom: 30px; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .metric {{ background: #f8f9fa; padding: 20px; border-radius: 6px; }}
        .metric-value {{ font-size: 32px; font-weight: bold; color: #0066cc; }}
        .metric-label {{ color: #666; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .delay-high {{ color: #d73a49; font-weight: bold; }}
        .delay-normal {{ color: #28a745; }}
        .success {{ color: #28a745; }}
        .failure {{ color: #d73a49; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 GitHub Actions 推送监测报告</h1>
        <p class="subtitle">仓库: {self.repo} | Workflow: {self.workflow_name or '全部'}</p>

        <div class="metrics">
            <div class="metric">
                <div class="metric-value">{report["total_runs"]}</div>
                <div class="metric-label">总运行次数</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report["success_rate"]}%</div>
                <div class="metric-label">成功率</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report["average_delay_seconds"]:.0f}s</div>
                <div class="metric-label">平均延迟</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report["max_delay_seconds"]:.0f}s</div>
                <div class="metric-label">最大延迟</div>
            </div>
        </div>

        <h2>最近运行记录</h2>
        <table>
            <thead>
                <tr>
                    <th>运行编号</th>
                    <th>创建时间</th>
                    <th>开始时间</th>
                    <th>延迟</th>
                    <th>状态</th>
                    <th>详情</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>

        <p style="margin-top: 30px; color: #666; font-size: 14px;">
            报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </p>
    </div>
</body>
</html>
        """

        return html

    def _http_get(self, url: str, timeout: int = 10) -> Dict:
        """发送 HTTP GET 请求"""
        req = urllib.request.Request(url, headers=self.headers)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise Exception(f"URL Error: {e.reason}")


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="GitHub Actions 推送监测")
    parser.add_argument("--repo", help="仓库名（格式：owner/repo）")
    parser.add_argument("--workflow", help="Workflow 名称")
    parser.add_argument("--token", help="GitHub Token")
    parser.add_argument("--limit", type=int, default=30, help="获取运行记录数量")
    parser.add_argument("--report", default="github_monitor_report.html", help="报告输出路径")
    parser.add_argument("--check-delay", action="store_true", help="检查延迟并告警")
    parser.add_argument("--threshold", type=int, default=300, help="延迟告警阈值（秒）")

    args = parser.parse_args()

    try:
        monitor = GitHubMonitor(
            repo=args.repo,
            workflow_name=args.workflow,
            token=args.token
        )

        print(f"监控仓库: {monitor.repo}")
        if monitor.workflow_name:
            print(f"Workflow: {monitor.workflow_name}")
        print()

        if args.check_delay:
            # 检查延迟
            print("检查最近一次运行延迟...")
            alerted = monitor.check_and_alert(threshold_seconds=args.threshold)
            if alerted:
                print("✓ 已发送延迟告警")
            else:
                print("✓ 延迟正常")
        else:
            # 生成报告
            print(f"获取最近 {args.limit} 次运行记录...")
            runs = monitor.get_recent_runs(limit=args.limit)
            print(f"获取到 {len(runs)} 条记录")

            print("\n分析延迟...")
            report = monitor.analyze_delays(runs)

            print(f"\n=== 统计摘要 ===")
            print(f"总运行次数: {report['total_runs']}")
            print(f"成功: {report['success_count']} | 失败: {report['failure_count']}")
            print(f"成功率: {report['success_rate']}%")
            print(f"平均延迟: {report['average_delay_seconds']}秒")
            print(f"最大延迟: {report['max_delay_seconds']}秒")

            print(f"\n生成 HTML 报告...")
            monitor.generate_report(args.report)
            print(f"✓ 完成")

    except Exception as e:
        print(f"错误: {e}")
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
