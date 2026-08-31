#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业级结构化日志系统

功能：
1. 结构化日志输出（JSON格式）
2. 日志级别管理
3. 日志轮转（按日期/大小）
4. 上下文追踪（trace_id）
5. 性能日志
6. 审计日志
"""
import logging
import logging.handlers
import json
import os
import sys
import datetime
import traceback
import uuid
from typing import Dict, Any, Optional
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """JSON格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加额外字段
        if hasattr(record, 'trace_id'):
            log_data['trace_id'] = record.trace_id

        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id

        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data

        # 添加异常信息
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLogger:
    """结构化日志器"""

    def __init__(self, name: str, log_dir: str = "logs", level: str = "INFO"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        # 清除已有的处理器
        self.logger.handlers.clear()

        self._setup_handlers()

        self.trace_id = None

    def _setup_handlers(self):
        """设置日志处理器"""

        # 1. 控制台处理器（人类可读格式）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # 2. 文件处理器（JSON格式，按日期轮转）
        json_file = self.log_dir / f"{self.name}.json.log"
        json_handler = logging.handlers.TimedRotatingFileHandler(
            json_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        json_handler.setLevel(logging.DEBUG)
        json_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(json_handler)

        # 3. 错误日志文件（单独记录ERROR及以上）
        error_file = self.log_dir / f"{self.name}.error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JsonFormatter())
        self.logger.addHandler(error_handler)

    def start_trace(self) -> str:
        """开始新的追踪会话"""
        self.trace_id = str(uuid.uuid4())
        return self.trace_id

    def _log(self, level: int, message: str, extra_data: Optional[Dict] = None, **kwargs):
        """内部日志方法"""
        extra = {'extra_data': extra_data or {}}
        if self.trace_id:
            extra['trace_id'] = self.trace_id

        # 合并 kwargs 到 extra_data
        if kwargs:
            extra['extra_data'].update(kwargs)

        self.logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs):
        """调试日志"""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """信息日志"""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """警告日志"""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        """错误日志"""
        if exc_info:
            self.logger.error(message, exc_info=True, extra={
                'trace_id': self.trace_id,
                'extra_data': kwargs
            })
        else:
            self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, exc_info: bool = False, **kwargs):
        """严重错误日志"""
        if exc_info:
            self.logger.critical(message, exc_info=True, extra={
                'trace_id': self.trace_id,
                'extra_data': kwargs
            })
        else:
            self._log(logging.CRITICAL, message, **kwargs)

    def performance(self, operation: str, duration: float, **kwargs):
        """性能日志"""
        self.info(f"Performance: {operation}", duration=duration, **kwargs)

    def audit(self, action: str, user: str = None, **kwargs):
        """审计日志"""
        self.info(f"Audit: {action}", user=user, action=action, **kwargs)


class LoggerFactory:
    """日志工厂"""

    _loggers: Dict[str, StructuredLogger] = {}
    _log_dir = "logs"
    _default_level = "INFO"

    @classmethod
    def configure(cls, log_dir: str = "logs", level: str = "INFO"):
        """配置全局日志设置"""
        cls._log_dir = log_dir
        cls._default_level = level

    @classmethod
    def get_logger(cls, name: str) -> StructuredLogger:
        """获取日志器"""
        if name not in cls._loggers:
            cls._loggers[name] = StructuredLogger(
                name,
                log_dir=cls._log_dir,
                level=cls._default_level
            )
        return cls._loggers[name]


def log_execution(logger_name: str = None):
    """装饰器：记录函数执行"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = LoggerFactory.get_logger(logger_name or func.__module__)
            trace_id = logger.start_trace()

            logger.info(
                f"开始执行: {func.__name__}",
                function=func.__name__,
                args=str(args)[:100],  # 截断过长的参数
            )

            start_time = datetime.datetime.now()

            try:
                result = func(*args, **kwargs)
                duration = (datetime.datetime.now() - start_time).total_seconds()

                logger.performance(
                    func.__name__,
                    duration,
                    status="success"
                )

                return result

            except Exception as e:
                duration = (datetime.datetime.now() - start_time).total_seconds()

                logger.error(
                    f"执行失败: {func.__name__}",
                    exc_info=True,
                    function=func.__name__,
                    duration=duration,
                    error_type=type(e).__name__
                )
                raise

        return wrapper
    return decorator


if __name__ == "__main__":
    # 测试日志系统
    print("=== 日志系统测试 ===\n")

    # 配置日志
    LoggerFactory.configure(log_dir="logs", level="DEBUG")

    # 获取日志器
    logger = LoggerFactory.get_logger("test")

    # 开始追踪
    trace_id = logger.start_trace()
    print(f"Trace ID: {trace_id}\n")

    # 各级别日志
    logger.debug("这是调试信息", key="value")
    logger.info("程序启动", version="2.0.0")
    logger.warning("配置文件缺失，使用默认配置")

    # 性能日志
    logger.performance("数据抓取", 2.5, items=100)

    # 审计日志
    logger.audit("用户登录", user="admin", ip="192.168.1.1")

    # 错误日志
    try:
        1 / 0
    except Exception:
        logger.error("计算错误", exc_info=True, operation="division")

    # 装饰器测试
    @log_execution("test")
    def test_function(x, y):
        import time
        time.sleep(0.1)
        return x + y

    result = test_function(1, 2)

    print("\n日志文件已生成在 logs/ 目录")
    print("- test.json.log: 完整JSON格式日志")
    print("- test.error.log: 仅错误日志")
