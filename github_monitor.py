#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monitor one GitHub Actions workflow against its intended daily schedule."""
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_EXPECTED_TIME = "23:00"
EARLY_EVENT_TOLERANCE = timedelta(minutes=15)


def utc_to_beijing(dt: datetime) -> datetime:
    """Convert a UTC or naive-UTC datetime to Asia/Shanghai."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BEIJING_TZ)


def format_beijing_time(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format a datetime in Asia/Shanghai with an explicit label."""
    return utc_to_beijing(dt).strftime(fmt) + " (北京时间)"


def parse_github_time(value: Any) -> Optional[datetime]:
    """Parse a GitHub timestamp as an aware UTC datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve_expected_utc(event_time: datetime,
                         expected_time: str = DEFAULT_EXPECTED_TIME) -> datetime:
    """Resolve the latest relevant daily cron instant for an event timestamp."""
    if event_time.tzinfo is None:
        event_time = event_time.replace(tzinfo=timezone.utc)
    event_time = event_time.astimezone(timezone.utc)
    hour, minute = map(int, expected_time.split(":"))
    candidate = event_time.replace(hour=hour, minute=minute, second=0,
                                   microsecond=0)
    if candidate - event_time > EARLY_EVENT_TOLERANCE:
        candidate -= timedelta(days=1)
    return candidate


def _duration(later: Optional[datetime], earlier: Optional[datetime]) -> Optional[float]:
    if later is None or earlier is None:
        return None
    seconds = (later - earlier).total_seconds()
    return seconds if seconds >= 0 else None


class GitHubMonitor:
    """Monitor scheduled and manually dispatched runs for one workflow."""

    def __init__(self, repo: Optional[str] = None,
                 workflow_name: Optional[str] = None,
                 token: Optional[str] = None,
                 expected_time: Optional[str] = None):
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self.workflow_name = workflow_name or os.environ.get("GITHUB_WORKFLOW", "")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.expected_time = expected_time or os.environ.get(
            "EXPECTED_CRON_UTC", DEFAULT_EXPECTED_TIME)
        if not self.repo:
            raise ValueError("必须提供仓库名（GITHUB_REPOSITORY 或 repo 参数）")

        self.api_base = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "AI-Daily-Push-Monitor",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"
        self._workflow_id: Optional[int] = None
        self._workflow_resolved = False

    def _get_workflow_id(self) -> Optional[int]:
        """Resolve and cache the configured workflow ID."""
        if self._workflow_resolved:
            return self._workflow_id
        self._workflow_resolved = True
        url = f"{self.api_base}/repos/{self.repo}/actions/workflows"
        try:
            data = self._http_get(url)
            for workflow in data.get("workflows", []):
                if workflow.get("name") == self.workflow_name:
                    self._workflow_id = workflow.get("id")
                    break
        except Exception as exc:
            print(f"获取 workflow ID 失败: {exc}")
        return self._workflow_id

    def get_recent_runs(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch all states for the configured workflow, newest first."""
        workflow_id = self._get_workflow_id() if self.workflow_name else None
        if self.workflow_name and workflow_id is None:
            return []
        if workflow_id is not None:
            url = (f"{self.api_base}/repos/{self.repo}/actions/workflows/"
                   f"{workflow_id}/runs")
        else:
            url = f"{self.api_base}/repos/{self.repo}/actions/runs"
        full_url = f"{url}?{urllib.parse.urlencode({'per_page': limit})}"
        try:
            data = self._http_get(full_url)
            runs = data.get("workflow_runs", [])
            return runs if isinstance(runs, list) else []
        except Exception as exc:
            print(f"获取运行记录失败: {exc}")
            return []

    def _run_timing(self, run: Dict[str, Any]) -> Dict[str, Any]:
        event = run.get("event", "")
        created = parse_github_time(run.get("created_at"))
        started = parse_github_time(run.get("run_started_at"))
        completed = parse_github_time(run.get("updated_at"))
        scheduled = (
            resolve_expected_utc(created, self.expected_time)
            if event == "schedule" and created else None
        )
        dispatch = _duration(created, scheduled)
        queue = _duration(started, created)
        runtime = _duration(completed, started)
        total = _duration(completed, scheduled)
        status = run.get("status", "")
        conclusion = run.get("conclusion")
        if event != "schedule":
            state = "manual"
        elif status in ("queued", "waiting", "pending", "requested"):
            state = "queued"
        elif status in ("in_progress", "action_required"):
            state = "in_progress"
        elif status == "completed" and conclusion == "success":
            state = "success"
        elif status == "completed":
            state = "failed"
        else:
            state = status or "unknown"
        return {
            "run_id": run.get("id"),
            "run_number": run.get("run_number"),
            "event": event,
            "state": state,
            "status": status,
            "conclusion": conclusion or "",
            "scheduled_at": scheduled.isoformat() if scheduled else "",
            "created_at": format_beijing_time(created) if created else "",
            "started_at": format_beijing_time(started) if started else "",
            "completed_at": format_beijing_time(completed) if completed else "",
            "dispatch_delay_seconds": dispatch,
            "queue_delay_seconds": queue,
            "runtime_seconds": runtime,
            "schedule_to_completion_seconds": total,
            # Compatibility: delay now consistently means schedule-to-event.
            "delay_seconds": dispatch,
            "html_url": run.get("html_url", ""),
        }

    def analyze_delays(self, runs: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Split scheduling, queueing, and runtime metrics for scheduled runs."""
        if runs is None:
            runs = self.get_recent_runs()
        timings = [self._run_timing(run) for run in runs]
        scheduled = [item for item in timings if item["event"] == "schedule"]
        manual = [item for item in timings if item["event"] != "schedule"]
        successes = [item for item in scheduled if item["state"] == "success"]
        failures = [item for item in scheduled if item["state"] == "failed"]
        dispatches = [item["dispatch_delay_seconds"] for item in scheduled
                      if item["dispatch_delay_seconds"] is not None]
        queues = [item["queue_delay_seconds"] for item in scheduled
                  if item["queue_delay_seconds"] is not None]
        runtimes = [item["runtime_seconds"] for item in scheduled
                    if item["runtime_seconds"] is not None]
        totals = [item["schedule_to_completion_seconds"] for item in scheduled
                  if item["schedule_to_completion_seconds"] is not None]
        completed_count = len(successes) + len(failures)

        def average(values):
            return round(sum(values) / len(values), 2) if values else 0

        invalid_timings = sum(
            1 for run, item in zip(runs, timings)
            if (run.get("created_at") and run.get("run_started_at")
                and item["queue_delay_seconds"] is None)
            or (run.get("run_started_at") and run.get("updated_at")
                and item["runtime_seconds"] is None)
        )
        return {
            "total_runs": len(runs),
            "scheduled_runs": len(scheduled),
            "manual_runs": len(manual),
            "success_count": len(successes),
            "failure_count": len(failures),
            "queued_count": sum(item["state"] == "queued" for item in scheduled),
            "in_progress_count": sum(item["state"] == "in_progress" for item in scheduled),
            "success_rate": round(len(successes) / completed_count * 100, 2)
            if completed_count else 0,
            "average_dispatch_delay_seconds": average(dispatches),
            "max_dispatch_delay_seconds": max(dispatches, default=0),
            "average_queue_delay_seconds": average(queues),
            "average_runtime_seconds": average(runtimes),
            "average_schedule_to_completion_seconds": average(totals),
            "invalid_timing_count": invalid_timings,
            # Compatibility aliases for existing report consumers.
            "average_delay_seconds": average(dispatches),
            "max_delay_seconds": max(dispatches, default=0),
            "delays": sorted(scheduled, key=lambda item: (
                item["dispatch_delay_seconds"] is not None,
                item["dispatch_delay_seconds"] or 0,
            ), reverse=True),
            "manual": manual,
        }

    def evaluate_latest(self, runs: List[Dict[str, Any]], threshold_seconds: int,
                        now: Optional[datetime] = None) -> Dict[str, Any]:
        """Classify the latest expected scheduled run for alerting."""
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        expected = resolve_expected_utc(now, self.expected_time)
        elapsed = max(0, (now - expected).total_seconds())
        scheduled = [self._run_timing(run) for run in runs
                     if run.get("event") == "schedule"]
        matching = [item for item in scheduled if item["scheduled_at"]
                    and parse_github_time(item["scheduled_at"]) == expected]
        if not matching:
            state = "missing" if elapsed > threshold_seconds else "waiting"
            return {"state": state, "alert": state == "missing",
                    "scheduled_at": expected.isoformat(),
                    "delay_seconds": elapsed}
        latest = max(matching, key=lambda item: item["run_number"] or 0)
        state = latest["state"]
        if state == "failed":
            alert = True
        elif state in ("queued", "in_progress"):
            alert = elapsed > threshold_seconds
        elif state == "success":
            alert = ((latest["dispatch_delay_seconds"] or 0)
                     > threshold_seconds)
        else:
            alert = elapsed > threshold_seconds
        return {**latest, "alert": alert,
                "delay_seconds": latest["dispatch_delay_seconds"]
                if latest["dispatch_delay_seconds"] is not None else elapsed}

    def check_and_alert(self, threshold_seconds: int = 300,
                        return_evaluation: bool = False):
        """Alert when needed and optionally return the evaluated run state.

        ``alert`` and workflow failure are intentionally separate: a completed
        successful run may warrant a scheduling-delay warning without making
        the monitor workflow itself fail.
        """
        evaluation = self.evaluate_latest(self.get_recent_runs(limit=10),
                                          threshold_seconds)
        if not evaluation["alert"]:
            return evaluation if return_evaluation else False
        state_labels = {
            "missing": "计划任务未创建",
            "queued": "计划任务排队延迟",
            "in_progress": "计划任务仍在运行",
            "failed": "计划任务运行失败",
            "success": "计划任务调度延迟",
        }
        delay_seconds = evaluation.get("delay_seconds", 0)
        try:
            from alerting import send_alert
            send_alert(
                level="ERROR" if evaluation["state"] in ("missing", "failed") else "WARNING",
                title=state_labels.get(evaluation["state"], "GitHub Actions 状态异常"),
                message=f"相对计划时间 {delay_seconds:.0f} 秒（阈值 {threshold_seconds} 秒）",
                details={
                    "仓库": self.repo,
                    "Workflow": self.workflow_name,
                    "状态": evaluation["state"],
                    "运行编号": evaluation.get("run_number", "未创建"),
                    "计划时间": evaluation.get("scheduled_at", ""),
                    "链接": evaluation.get("html_url", ""),
                },
            )
        except ImportError:
            print(f"GitHub Actions 告警: {evaluation['state']} ({delay_seconds:.0f}秒)")
        return evaluation if return_evaluation else True

    def generate_report(self, output_file: str = "github_monitor_report.html"):
        report = self.analyze_delays(self.get_recent_runs())
        with open(output_file, "w", encoding="utf-8") as stream:
            stream.write(self._build_html_report(report))
        print(f"报告已生成: {output_file}")

    def _build_html_report(self, report: Dict[str, Any]) -> str:
        rows = ""
        for item in report.get("delays", [])[:20]:
            delay = item.get("dispatch_delay_seconds")
            delay_class = "delay-high" if delay is not None and delay > 300 else "delay-normal"
            rows += (
                "<tr>"
                f"<td>{html.escape(str(item.get('run_number', '')))}</td>"
                f"<td>{html.escape(item.get('scheduled_at', ''))}</td>"
                f"<td>{html.escape(item.get('created_at', ''))}</td>"
                f"<td class=\"{delay_class}\">{delay:.0f}秒</td>" if delay is not None else
                "<td>不可用</td>"
            )
            queue = item.get("queue_delay_seconds")
            runtime = item.get("runtime_seconds")
            rows += (
                f"<td>{queue:.0f}秒</td>" if queue is not None else "<td>不可用</td>"
            )
            rows += (
                f"<td>{runtime:.0f}秒</td>" if runtime is not None else "<td>进行中</td>"
            )
            rows += (
                f"<td class=\"{html.escape(item.get('state', ''))}\">"
                f"{html.escape(item.get('state', ''))}</td>"
                f"<td><a href=\"{html.escape(item.get('html_url', ''), quote=True)}\" "
                "target=\"_blank\" rel=\"noopener noreferrer\">查看</a></td></tr>"
            )
        generated = format_beijing_time(datetime.now(timezone.utc))
        return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GitHub Actions 推送监测报告</title><style>
*{{box-sizing:border-box}}body{{font-family:sans-serif;padding:20px;background:#f5f5f5}}
.container{{max-width:1200px;margin:auto;background:white;padding:30px;border-radius:8px}}
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px}}
.metric{{background:#f8f9fa;padding:16px;border-radius:6px}}.metric-value{{font-size:28px;font-weight:bold}}
table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}
.delay-high,.failed{{color:#b42318;font-weight:bold}}.delay-normal,.success{{color:#067647}}
</style></head><body><main class="container"><h1>GitHub Actions 推送监测报告</h1>
<p>仓库: {html.escape(self.repo)} | Workflow: {html.escape(self.workflow_name or '全部')}</p>
<div class="metrics">
<div class="metric"><div class="metric-value">{report['scheduled_runs']}</div><div>计划运行</div></div>
<div class="metric"><div class="metric-value">{report['manual_runs']}</div><div>手工运行（不计统计）</div></div>
<div class="metric"><div class="metric-value">{report['average_dispatch_delay_seconds']:.0f}s</div><div>平均调度延迟</div></div>
<div class="metric"><div class="metric-value">{report['average_queue_delay_seconds']:.0f}s</div><div>平均排队时间</div></div>
</div><h2>计划运行记录</h2><table><thead><tr><th>编号</th><th>计划时间 UTC</th><th>事件创建</th>
<th>调度延迟</th><th>排队</th><th>运行</th><th>状态</th><th>详情</th></tr></thead><tbody>{rows}</tbody></table>
<p>报告生成时间: {generated}</p></main></body></html>"""

    def _http_get(self, url: str, timeout: int = 10) -> Dict:
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")
            raise Exception(f"HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise Exception(f"URL Error: {exc.reason}") from exc


def main():
    import argparse
    parser = argparse.ArgumentParser(description="GitHub Actions 推送监测")
    parser.add_argument("--repo", help="仓库名（格式：owner/repo）")
    parser.add_argument("--workflow", help="Workflow 名称")
    parser.add_argument("--token", help="GitHub Token")
    parser.add_argument("--expected-time", default=DEFAULT_EXPECTED_TIME,
                        help="每日计划时间（HH:MM，UTC）")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--report", default="github_monitor_report.html")
    parser.add_argument("--check-delay", action="store_true")
    parser.add_argument("--threshold", type=int, default=300)
    args = parser.parse_args()
    try:
        monitor = GitHubMonitor(args.repo, args.workflow, args.token,
                                args.expected_time)
        print(f"监控仓库: {monitor.repo}")
        if args.check_delay:
            evaluation = monitor.check_and_alert(
                args.threshold, return_evaluation=True)
            state = evaluation.get("state", "unknown")
            if evaluation.get("alert"):
                print(f"已触发告警：{state}")
            else:
                print(f"计划运行状态正常：{state}")
            # A scheduling warning must not turn a successful daily run into an
            # "all jobs failed" monitor email.  Reserve non-zero status for a
            # missing run, a genuinely failed/cancelled run, or monitor errors.
            return 1 if state in ("missing", "failed") else 0
        runs = monitor.get_recent_runs(args.limit)
        report = monitor.analyze_delays(runs)
        print(f"运行: {report['total_runs']}；计划: {report['scheduled_runs']}；手工: {report['manual_runs']}")
        print(f"平均调度延迟: {report['average_dispatch_delay_seconds']}秒")
        print(f"平均排队时间: {report['average_queue_delay_seconds']}秒")
        monitor.generate_report(args.report)
        return 0
    except Exception as exc:
        print(f"错误: {exc}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
