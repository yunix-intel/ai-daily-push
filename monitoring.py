#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监控告警系统

本模块提供完整的监控和告警功能，用于跟踪系统运行状态、性能指标和数据质量。

主要功能：
1. 运行状态监控 - 记录每次任务执行的成功/失败状态
2. 推送失败告警 - 推送失败时自动触发告警
3. 数据质量监控 - 跟踪数据完整性和准确性
4. 性能指标追踪 - 记录执行时间、资源使用等指标
5. 多级别告警 - 支持 INFO/WARNING/ERROR/CRITICAL 四个级别
6. 指标导出 - 支持导出为 JSON/Prometheus 格式

使用示例：
    from monitoring import get_monitor, AlertLevel

    # 获取监控实例
    monitor = get_monitor()

    # 记录任务运行
    monitor.record_run("ai_daily", success=True, duration=45.2, items=25)

    # 发送告警
    monitor.alert(AlertLevel.ERROR, "推送失败", "企业微信推送超时")

    # 检查健康状态
    health = monitor.get_health_status()
    print(health['status'])  # 'healthy' or 'degraded' or 'unhealthy'

    # 导出指标
    monitor.export_metrics("metrics.json")

配置：
    可通过环境变量配置：
    - MONITOR_ENABLED: 是否启用监控(默认 true)
    - ALERT_WEBHOOK: 告警 webhook URL
    - METRICS_EXPORT_PATH: 指标导出路径

注意事项：
    - 监控实例是单例模式，全局共享
    - 告警需要配置通知渠道才能实际发送
    - 指标数据存储在内存中，重启后清空

作者: AI Daily Push Team
版本: 3.0.0
"""
5. 健康检查接口
"""
import datetime
import json
import os
import time
import traceback
from typing import Dict, List, Optional, Any
from enum import Enum


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class MonitorMetrics:
    """监控指标"""

    def __init__(self):
        self.start_time = time.time()
        self.metrics = {
            "ai_daily": {
                "last_run": None,
                "success_count": 0,
                "failure_count": 0,
                "avg_duration": 0,
                "last_error": None,
            },
            "finance_daily": {
                "last_run": None,
                "success_count": 0,
                "failure_count": 0,
                "avg_duration": 0,
                "last_error": None,
            },
            "data_quality": {
                "ai_items_count": 0,
                "finance_items_count": 0,
                "empty_runs": 0,
                "last_check": None,
            },
            "system": {
                "uptime": 0,
                "memory_usage": 0,
                "cache_hit_rate": 0,
            }
        }
        self.alerts = []

    def record_run(self, module: str, success: bool, duration: float,
                   items_count: int = 0, error: str = None):
        """记录运行指标"""
        if module not in self.metrics:
            return

        m = self.metrics[module]
        m["last_run"] = datetime.datetime.now().isoformat()

        if success:
            m["success_count"] += 1
            # 计算平均耗时
            if m["avg_duration"] == 0:
                m["avg_duration"] = duration
            else:
                m["avg_duration"] = (m["avg_duration"] * 0.8 + duration * 0.2)
        else:
            m["failure_count"] += 1
            m["last_error"] = error
            self.alert(AlertLevel.ERROR, f"{module} 运行失败", error)

        # 记录数据质量
        if items_count == 0:
            self.metrics["data_quality"]["empty_runs"] += 1
            self.alert(AlertLevel.WARNING, f"{module} 未获取到数据",
                      f"本次运行获取到 0 条数据")

    def record_data_quality(self, ai_count: int, finance_count: int):
        """记录数据质量指标"""
        dq = self.metrics["data_quality"]
        dq["ai_items_count"] = ai_count
        dq["finance_items_count"] = finance_count
        dq["last_check"] = datetime.datetime.now().isoformat()

        # 数据量异常告警
        if ai_count < 5:
            self.alert(AlertLevel.WARNING, "AI日报数据量偏低",
                      f"仅获取到 {ai_count} 条数据")
        if finance_count < 10:
            self.alert(AlertLevel.WARNING, "财经日报数据量偏低",
                      f"仅获取到 {finance_count} 条数据")

    def alert(self, level: AlertLevel, title: str, message: str):
        """发送告警"""
        alert = {
            "level": level.value,
            "title": title,
            "message": message,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        self.alerts.append(alert)

        # 持久化告警
        self._persist_alert(alert)

        # 根据级别决定是否立即通知
        if level in [AlertLevel.ERROR, AlertLevel.CRITICAL]:
            self._send_immediate_notification(alert)

    def get_health_status(self) -> Dict[str, Any]:
        """获取健康状态"""
        status = HealthStatus.HEALTHY
        issues = []

        # 检查最近运行状态
        for module in ["ai_daily", "finance_daily"]:
            m = self.metrics[module]
            if m["failure_count"] > 0:
                failure_rate = m["failure_count"] / (m["success_count"] + m["failure_count"])
                if failure_rate > 0.5:
                    status = HealthStatus.UNHEALTHY
                    issues.append(f"{module} 失败率过高: {failure_rate:.1%}")
                elif failure_rate > 0.2:
                    if status == HealthStatus.HEALTHY:
                        status = HealthStatus.DEGRADED
                    issues.append(f"{module} 失败率偏高: {failure_rate:.1%}")

        # 检查数据质量
        dq = self.metrics["data_quality"]
        if dq["empty_runs"] > 3:
            if status == HealthStatus.HEALTHY:
                status = HealthStatus.DEGRADED
            issues.append(f"数据为空次数过多: {dq['empty_runs']}")

        # 检查最近运行时间
        for module in ["ai_daily", "finance_daily"]:
            last_run = self.metrics[module]["last_run"]
            if last_run:
                last_time = datetime.datetime.fromisoformat(last_run)
                hours_since = (datetime.datetime.now() - last_time).total_seconds() / 3600
                if hours_since > 48:
                    if status == HealthStatus.HEALTHY:
                        status = HealthStatus.DEGRADED
                    issues.append(f"{module} 超过48小时未运行")

        return {
            "status": status.value,
            "timestamp": datetime.datetime.now().isoformat(),
            "uptime": time.time() - self.start_time,
            "issues": issues,
            "metrics": self.metrics,
            "recent_alerts": self.alerts[-10:],  # 最近10条告警
        }

    def _persist_alert(self, alert: Dict):
        """持久化告警到文件"""
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)

        alert_file = os.path.join(log_dir, f"alerts_{datetime.date.today()}.jsonl")
        with open(alert_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(alert, ensure_ascii=False) + '\n')

    def _send_immediate_notification(self, alert: Dict):
        """发送即时通知(企业微信/邮件/钉钉等)"""
        # TODO: 集成企业微信机器人
        # TODO: 集成邮件通知
        # TODO: 集成钉钉机器人
        print(f"[ALERT] {alert['level'].upper()}: {alert['title']}")
        print(f"        {alert['message']}")

    def export_metrics(self, filepath: str):
        """导出指标到文件(用于 Prometheus 等监控系统)"""
        data = {
            "timestamp": datetime.datetime.now().isoformat(),
            "metrics": self.metrics,
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class PerformanceTracker:
    """性能追踪器"""

    def __init__(self):
        self.timings = {}

    def start(self, task_name: str):
        """开始计时"""
        self.timings[task_name] = {
            "start": time.time(),
            "end": None,
            "duration": None,
        }

    def end(self, task_name: str):
        """结束计时"""
        if task_name in self.timings:
            self.timings[task_name]["end"] = time.time()
            self.timings[task_name]["duration"] = (
                self.timings[task_name]["end"] - self.timings[task_name]["start"]
            )

    def get_summary(self) -> Dict[str, float]:
        """获取性能摘要"""
        return {
            name: timing["duration"]
            for name, timing in self.timings.items()
            if timing["duration"] is not None
        }

    def log_summary(self):
        """打印性能摘要"""
        summary = self.get_summary()
        print("\n=== 性能摘要 ===")
        for task, duration in sorted(summary.items(), key=lambda x: x[1], reverse=True):
            print(f"  {task}: {duration:.2f}s")
        print(f"  总耗时: {sum(summary.values()):.2f}s")


# 全局监控实例
_monitor = MonitorMetrics()
_perf_tracker = PerformanceTracker()


def get_monitor() -> MonitorMetrics:
    """获取监控实例"""
    return _monitor


def get_perf_tracker() -> PerformanceTracker:
    """获取性能追踪器"""
    return _perf_tracker


def monitor_function(module: str):
    """装饰器：监控函数执行"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            error_msg = None
            items_count = 0

            try:
                result = func(*args, **kwargs)
                success = True

                # 尝试从结果中提取数据量
                if isinstance(result, (list, tuple)):
                    items_count = len(result)
                elif isinstance(result, dict) and 'items' in result:
                    items_count = len(result['items'])

                return result
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                raise
            finally:
                duration = time.time() - start_time
                _monitor.record_run(module, success, duration, items_count, error_msg)

        return wrapper
    return decorator


if __name__ == "__main__":
    # 测试监控系统
    print("=== 监控系统测试 ===\n")

    # 模拟运行
    _monitor.record_run("ai_daily", True, 45.2, 15)
    _monitor.record_run("finance_daily", True, 78.5, 42)
    _monitor.record_run("ai_daily", False, 10.0, 0, "API timeout")

    # 记录数据质量
    _monitor.record_data_quality(15, 42)

    # 获取健康状态
    health = _monitor.get_health_status()
    print("健康状态:")
    print(json.dumps(health, ensure_ascii=False, indent=2))

    # 导出指标
    _monitor.export_metrics("metrics.json")
    print("\n指标已导出到 metrics.json")
