#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Exit-code matrix for github_monitor.

约束：调度延迟告警（success-but-late）只发 WARNING，不让 monitor workflow 失败；
只有 missing / failed 才非零；monitor 自身异常非零。
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from github_monitor import GitHubMonitor, exit_code_for_state

EXPECTED = "23:00"
# 固定 now=23:30：当日 23:00 计划已过 30 分钟（超 900 秒阈值），匹配逻辑稳定。
FIXED_NOW = datetime(2026, 9, 16, 23, 30, tzinfo=timezone.utc)


def _run(created_min_after=2, status="completed", conclusion="success", number=1):
    scheduled = datetime(2026, 9, 16, 23, 0, tzinfo=timezone.utc)
    created = scheduled + timedelta(minutes=created_min_after)
    started = created + timedelta(seconds=30)
    updated = started + timedelta(minutes=5)
    return {"id": number, "run_number": number, "event": "schedule",
            "status": status, "conclusion": conclusion,
            "created_at": created.isoformat(),
            "run_started_at": started.isoformat(),
            "updated_at": updated.isoformat(),
            "html_url": "https://example.invalid/run"}


def _eval(runs, threshold=900, now=FIXED_NOW):
    mon = GitHubMonitor(repo="o/r", workflow_name="W", token="t",
                        expected_time=EXPECTED)
    return mon.evaluate_latest(runs, threshold, now=now)


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def test_success_on_time_no_alert_exit_0():
    ev = _eval([_run(created_min_after=2)])
    _check(ev["state"] == "success", f"expected success, got {ev['state']}")
    _check(ev["alert"] is False, "on-time success must not alert")
    _check(exit_code_for_state(ev["state"]) == 0, "on-time success must exit 0")
    print("[PASS] success on time: no alert, exit 0")


def test_success_late_warns_but_exit_0():
    ev = _eval([_run(created_min_after=20)])
    _check(ev["state"] == "success", f"expected success, got {ev['state']}")
    _check(ev["alert"] is True, "late success must raise a delay WARNING")
    _check(exit_code_for_state(ev["state"]) == 0,
            "scheduling-delay WARNING must not fail the monitor workflow")
    print("[PASS] success-but-late: WARNING alert, exit 0")


def test_failed_run_exit_1():
    ev = _eval([_run(conclusion="failure")])
    _check(ev["state"] == "failed", f"expected failed, got {ev['state']}")
    _check(ev["alert"] is True, "failed run must alert")
    _check(exit_code_for_state(ev["state"]) == 1, "failed run must exit 1")
    print("[PASS] failed run: alert, exit 1")


def test_missing_run_exit_1():
    ev = _eval([])
    _check(ev["state"] == "missing", f"expected missing, got {ev['state']}")
    _check(ev["alert"] is True, "missing run must alert")
    _check(exit_code_for_state(ev["state"]) == 1, "missing run must exit 1")
    print("[PASS] missing run: alert, exit 1")


def test_in_progress_within_threshold_exit_0():
    now = datetime(2026, 9, 16, 23, 5, tzinfo=timezone.utc)  # 计划后 5 分钟，未超阈值
    run = _run(created_min_after=2, status="in_progress", conclusion=None)
    ev = _eval([run], now=now)
    _check(ev["state"] == "in_progress", f"expected in_progress, got {ev['state']}")
    _check(ev["alert"] is False, "in-progress run within threshold must not alert")
    _check(exit_code_for_state(ev["state"]) == 0, "in-progress run must exit 0")
    print("[PASS] in-progress within threshold: no alert, exit 0")


def main():
    tests = [
        test_success_on_time_no_alert_exit_0,
        test_success_late_warns_but_exit_0,
        test_failed_run_exit_1,
        test_missing_run_exit_1,
        test_in_progress_within_threshold_exit_0,
    ]
    for test in tests:
        test()
    print(f"[PASS] {len(tests)}/{len(tests)} monitor exit-matrix tests passed")


if __name__ == "__main__":
    main()
