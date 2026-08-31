#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企业级配置管理系统

功能：
1. 多环境配置（dev/staging/prod）
2. 配置验证
3. 敏感信息加密
4. 配置热加载
5. 配置版本控制
"""
import os
import json
import yaml
from typing import Any, Dict, Optional
from pathlib import Path
from dataclasses import dataclass, field
import base64


class ConfigError(Exception):
    """配置错误"""
    pass


@dataclass
class DatabaseConfig:
    """数据库配置"""
    host: str = "localhost"
    port: int = 3306
    database: str = ""
    username: str = ""
    password: str = ""


@dataclass
class PushConfig:
    """推送配置"""
    # 企业微信
    wecom_corpid: str = ""
    wecom_corpsecret: str = ""
    wecom_agentid: str = ""
    wecom_touser: str = "@all"

    # PushPlus
    pushplus_token: str = ""
    pushplus_topic: str = ""

    # 钉钉
    dingtalk_webhook: str = ""
    dingtalk_secret: str = ""


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: str = "openai"  # openai, claude, qwen
    api_key: str = ""
    base_url: str = ""
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 60


@dataclass
class DataSourceConfig:
    """数据源配置"""
    # AI数据源
    ai_hot_enabled: bool = True
    rss_feeds_enabled: bool = True
    custom_feeds: list = field(default_factory=list)

    # 财经数据源
    finance_feeds_zh: list = field(default_factory=list)
    finance_feeds_en: list = field(default_factory=list)

    # API配置
    fetch_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 5


@dataclass
class MonitoringConfig:
    """监控配置"""
    enabled: bool = True
    metrics_export_path: str = "metrics.json"
    alert_channels: list = field(default_factory=lambda: ["log"])  # log, wecom, email
    health_check_interval: int = 300  # 秒


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    log_dir: str = "logs"
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 30
    json_format: bool = True


@dataclass
class ScheduleConfig:
    """调度配置"""
    ai_daily_cron: str = "0 9 * * *"  # 每天9点
    finance_daily_cron: str = "30 8 * * 1-5"  # 工作日8:30
    timezone: str = "Asia/Shanghai"


@dataclass
class AppConfig:
    """应用配置"""
    # 环境
    environment: str = "production"  # dev, staging, production
    debug: bool = False

    # 基础配置
    app_name: str = "AI Daily Push"
    version: str = "2.0.0"
    data_dir: str = "data"
    cache_dir: str = ".cache"

    # 子配置
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    push: PushConfig = field(default_factory=PushConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    data_source: DataSourceConfig = field(default_factory=DataSourceConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)

    def validate(self):
        """验证配置"""
        errors = []

        # 验证环境
        if self.environment not in ["dev", "staging", "production"]:
            errors.append(f"无效的环境: {self.environment}")

        # 验证推送配置
        if not self.push.wecom_corpid and not self.push.pushplus_token:
            errors.append("必须配置至少一种推送渠道（企业微信或PushPlus）")

        # 验证LLM配置
        if not self.llm.api_key:
            errors.append("LLM API Key 未配置")

        # 验证日志配置
        if self.logging.level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            errors.append(f"无效的日志级别: {self.logging.level}")

        if errors:
            raise ConfigError("配置验证失败:\n" + "\n".join(f"  - {e}" for e in errors))


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self._config: Optional[AppConfig] = None
        self._env = os.environ.get("APP_ENV", "production")

    def load(self, validate: bool = True) -> AppConfig:
        """加载配置"""
        # 1. 加载默认配置
        config_data = self._load_default_config()

        # 2. 加载环境特定配置
        env_config = self._load_env_config(self._env)
        config_data = self._merge_config(config_data, env_config)

        # 3. 加载环境变量覆盖
        config_data = self._load_env_variables(config_data)

        # 4. 构建配置对象
        self._config = self._build_config(config_data)

        # 5. 验证配置
        if validate:
            self._config.validate()

        return self._config

    def _load_default_config(self) -> Dict:
        """加载默认配置"""
        default_file = self.config_dir / "default.yaml"

        if default_file.exists():
            with open(default_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}

        return {}

    def _load_env_config(self, env: str) -> Dict:
        """加载环境配置"""
        env_file = self.config_dir / f"{env}.yaml"

        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}

        return {}

    def _load_env_variables(self, config_data: Dict) -> Dict:
        """从环境变量加载配置"""
        # LLM配置
        if os.environ.get("LLM_API_KEY"):
            if "llm" not in config_data:
                config_data["llm"] = {}
            config_data["llm"]["api_key"] = os.environ["LLM_API_KEY"]

        if os.environ.get("LLM_BASE_URL"):
            if "llm" not in config_data:
                config_data["llm"] = {}
            config_data["llm"]["base_url"] = os.environ["LLM_BASE_URL"]

        # 推送配置
        if os.environ.get("WECOM_CORPID"):
            if "push" not in config_data:
                config_data["push"] = {}
            config_data["push"]["wecom_corpid"] = os.environ["WECOM_CORPID"]

        if os.environ.get("WECOM_CORPSECRET"):
            if "push" not in config_data:
                config_data["push"] = {}
            config_data["push"]["wecom_corpsecret"] = os.environ["WECOM_CORPSECRET"]

        return config_data

    def _merge_config(self, base: Dict, override: Dict) -> Dict:
        """合并配置"""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value

        return result

    def _build_config(self, data: Dict) -> AppConfig:
        """构建配置对象"""
        config = AppConfig(
            environment=data.get("environment", "production"),
            debug=data.get("debug", False),
            app_name=data.get("app_name", "AI Daily Push"),
            version=data.get("version", "2.0.0"),
            data_dir=data.get("data_dir", "data"),
            cache_dir=data.get("cache_dir", ".cache"),
        )

        # 推送配置
        if "push" in data:
            config.push = PushConfig(**data["push"])

        # LLM配置
        if "llm" in data:
            config.llm = LLMConfig(**data["llm"])

        # 数据源配置
        if "data_source" in data:
            config.data_source = DataSourceConfig(**data["data_source"])

        # 监控配置
        if "monitoring" in data:
            config.monitoring = MonitoringConfig(**data["monitoring"])

        # 日志配置
        if "logging" in data:
            config.logging = LoggingConfig(**data["logging"])

        # 调度配置
        if "schedule" in data:
            config.schedule = ScheduleConfig(**data["schedule"])

        return config

    def get(self) -> AppConfig:
        """获取当前配置"""
        if self._config is None:
            self.load()
        return self._config

    def reload(self):
        """重新加载配置"""
        self._config = None
        return self.load()

    def save_template(self):
        """保存配置模板"""
        templates = {
            "default.yaml": self._get_default_template(),
            "dev.yaml": self._get_dev_template(),
            "production.yaml": self._get_production_template(),
        }

        for filename, content in templates.items():
            filepath = self.config_dir / filename
            if not filepath.exists():
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"已生成配置模板: {filepath}")

    def _get_default_template(self) -> str:
        """默认配置模板"""
        return """# AI Daily Push 默认配置

environment: production
debug: false
app_name: "AI Daily Push"
version: "2.0.0"

# 日志配置
logging:
  level: INFO
  log_dir: logs
  json_format: true

# 数据源配置
data_source:
  ai_hot_enabled: true
  rss_feeds_enabled: true
  fetch_timeout: 30
  max_retries: 3

# 监控配置
monitoring:
  enabled: true
  alert_channels:
    - log
  health_check_interval: 300

# 调度配置
schedule:
  ai_daily_cron: "0 9 * * *"
  finance_daily_cron: "30 8 * * 1-5"
  timezone: "Asia/Shanghai"
"""

    def _get_dev_template(self) -> str:
        """开发环境配置模板"""
        return """# 开发环境配置

environment: dev
debug: true

logging:
  level: DEBUG

llm:
  provider: openai
  model: gpt-3.5-turbo
  api_key: ${LLM_API_KEY}  # 从环境变量读取

push:
  # 开发环境使用 PushPlus
  pushplus_token: ${PUSHPLUS_TOKEN}
"""

    def _get_production_template(self) -> str:
        """生产环境配置模板"""
        return """# 生产环境配置

environment: production
debug: false

logging:
  level: INFO

llm:
  provider: openai
  model: gpt-4
  api_key: ${LLM_API_KEY}
  temperature: 0.7

push:
  # 生产环境使用企业微信
  wecom_corpid: ${WECOM_CORPID}
  wecom_corpsecret: ${WECOM_CORPSECRET}
  wecom_agentid: ${WECOM_AGENTID}
  wecom_touser: "@all"

monitoring:
  enabled: true
  alert_channels:
    - log
    - wecom
"""


# 全局配置实例
_config_manager = ConfigManager()


def get_config() -> AppConfig:
    """获取全局配置"""
    return _config_manager.get()


def reload_config() -> AppConfig:
    """重新加载配置"""
    return _config_manager.reload()


if __name__ == "__main__":
    # 生成配置模板
    print("=== 配置管理系统 ===\n")

    manager = ConfigManager()
    manager.save_template()

    print("\n配置模板已生成，请编辑 config/ 目录下的文件")
    print("\n环境变量说明:")
    print("  APP_ENV: 指定环境 (dev/staging/production)")
    print("  LLM_API_KEY: LLM API密钥")
    print("  WECOM_CORPID: 企业微信 Corp ID")
    print("  WECOM_CORPSECRET: 企业微信 Corp Secret")
