#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监控装饰器

提供简单的装饰器来集成监控系统到现有函数，无需大幅修改代码结构
"""
import time
import functools
from typing import Callable, Any


def monitor_task(task_name: str):
    """
    监控任务执行的装饰器

    用法：
        @monitor_task("ai_daily")
        def main():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            error_msg = None
            items_count = 0

            # 尝试导入监控系统
            try:
                from monitoring import get_monitor, AlertLevel
                from logger import LoggerFactory

                monitor = get_monitor()
                logger = LoggerFactory.get_logger(task_name)
                trace_id = logger.start_trace()
                logger.info(f"{task_name} 任务开始", trace_id=trace_id)
                monitoring_available = True
            except ImportError:
                monitoring_available = False

            try:
                # 执行原函数
                result = func(*args, **kwargs)
                success = True

                # 尝试从结果中提取数据量
                if isinstance(result, dict) and 'items_count' in result:
                    items_count = result['items_count']

                return result

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"

                if monitoring_available:
                    logger.error(f"{task_name} 任务失败", exc_info=True)
                    monitor.alert(AlertLevel.ERROR, f"{task_name} 执行失败", error_msg)

                raise

            finally:
                duration = time.time() - start_time

                if monitoring_available:
                    monitor.record_run(task_name, success, duration, items_count, error_msg)
                    logger.performance(task_name, duration, items=items_count, success=success)
                    logger.info(f"{task_name} 任务完成", duration=duration, success=success)

                    # 导出指标
                    try:
                        monitor.export_metrics("metrics.json")
                    except:
                        pass

        return wrapper
    return decorator


if __name__ == "__main__":
    # 测试装饰器
    @monitor_task("test_task")
    def test_function():
        import time
        print("执行测试任务...")
        time.sleep(1)
        return {"items_count": 10}

    print("测试监控装饰器:")
    test_function()
    print("\n装饰器测试完成")
