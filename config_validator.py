#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置验证模块

功能：
1. 验证必需的配置项
2. 验证 API 密钥有效性
3. 验证推送配置
4. 环境检查
"""
import os
import sys
import json
from typing import Dict, List, Tuple


class ConfigValidator:
    """配置验证器"""

    def __init__(self):
        self.errors = []
        self.warnings = []

    def validate_all(self) -> Tuple[bool, List[str], List[str]]:
        """
        验证所有配置

        Returns:
            (是否通过, 错误列表, 警告列表)
        """
        self.errors = []
        self.warnings = []

        # 1. 验证推送配置
        self._validate_push_config()

        # 2. 验证 LLM 配置
        self._validate_llm_config()

        # 3. 验证文件权限
        self._validate_file_permissions()

        # 4. 验证网络连接
        self._validate_network()

        return len(self.errors) == 0, self.errors, self.warnings

    def _validate_push_config(self):
        """验证推送配置"""
        # 检查企业微信
        wecom_corpid = os.environ.get("WECOM_CORPID", "")
        wecom_secret = os.environ.get("WECOM_CORPSECRET", "")
        wecom_agentid = os.environ.get("WECOM_AGENTID", "")

        # 检查 PushPlus
        pushplus_token = os.environ.get("PUSHPLUS_TOKEN", "")

        # 检查钉钉
        dingtalk_webhook = os.environ.get("DINGTALK_WEBHOOK", "")

        # 检查飞书
        feishu_webhook = os.environ.get("FEISHU_WEBHOOK", "")

        has_any_push = any([
            (wecom_corpid and wecom_secret and wecom_agentid),
            pushplus_token,
            dingtalk_webhook,
            feishu_webhook
        ])

        if not has_any_push:
            self.errors.append("未配置任何推送渠道（企业微信/PushPlus/钉钉/飞书）")
        else:
            if wecom_corpid and wecom_secret and wecom_agentid:
                print("  ✓ 企业微信配置已设置")
            if pushplus_token:
                print("  ✓ PushPlus 配置已设置")
            if dingtalk_webhook:
                print("  ✓ 钉钉配置已设置")
            if feishu_webhook:
                print("  ✓ 飞书配置已设置")

    def _validate_llm_config(self):
        """验证 LLM 配置"""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

        if not api_key:
            self.warnings.append("未配置 OPENAI_API_KEY，LLM 功能将不可用")
        else:
            print(f"  ✓ LLM API Key 已设置（前4位: {api_key[:4]}...）")

            # 验证 API Key 格式
            if not api_key.startswith("sk-"):
                self.warnings.append("API Key 格式可能不正确（应以 sk- 开头）")

        print(f"  ✓ LLM Base URL: {base_url}")

    def _validate_file_permissions(self):
        """验证文件权限"""
        import tempfile

        # 检查是否可以写入当前目录
        try:
            test_file = "test_write_permission.tmp"
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            print("  ✓ 当前目录可写")
        except Exception as e:
            self.errors.append(f"当前目录不可写: {e}")

        # 检查必要的目录
        dirs = ["logs", "data", ".cache", "config"]
        for d in dirs:
            if not os.path.exists(d):
                try:
                    os.makedirs(d, exist_ok=True)
                    print(f"  ✓ 创建目录: {d}")
                except Exception as e:
                    self.errors.append(f"无法创建目录 {d}: {e}")

    def _validate_network(self):
        """验证网络连接"""
        import urllib.request
        import urllib.error

        test_urls = [
            ("AI HOT API", "https://api.gptapi.us/ai-hot"),
            ("GitHub", "https://api.github.com"),
        ]

        for name, url in test_urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                urllib.request.urlopen(req, timeout=5)
                print(f"  ✓ {name} 可访问")
            except urllib.error.URLError as e:
                self.warnings.append(f"{name} 不可访问: {e}")
            except Exception as e:
                self.warnings.append(f"{name} 连接测试失败: {e}")

    def validate_config_file(self, config_path: str = "push_config.json") -> bool:
        """验证配置文件"""
        if not os.path.exists(config_path):
            self.warnings.append(f"配置文件 {config_path} 不存在，将使用环境变量")
            return True

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 验证必需字段
            if "pushplus_token" not in config and "wecom" not in config:
                self.warnings.append("配置文件中缺少推送配置")

            print(f"  ✓ 配置文件 {config_path} 格式正确")
            return True

        except json.JSONDecodeError as e:
            self.errors.append(f"配置文件 JSON 格式错误: {e}")
            return False
        except Exception as e:
            self.errors.append(f"读取配置文件失败: {e}")
            return False

    def print_report(self):
        """打印验证报告"""
        print("\n" + "="*60)
        print("配置验证报告")
        print("="*60)

        if self.errors:
            print(f"\n❌ 错误 ({len(self.errors)}):")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")

        if self.warnings:
            print(f"\n⚠️  警告 ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")

        if not self.errors and not self.warnings:
            print("\n✓ 所有检查通过！")

        print("="*60 + "\n")


def validate_environment() -> bool:
    """
    验证运行环境

    Returns:
        是否通过验证
    """
    print("="*60)
    print("环境配置验证")
    print("="*60 + "\n")

    validator = ConfigValidator()

    # 验证配置文件
    print("1. 验证配置文件...")
    validator.validate_config_file()

    # 验证所有配置
    print("\n2. 验证环境配置...")
    passed, errors, warnings = validator.validate_all()

    # 打印报告
    validator.print_report()

    if not passed:
        print("❌ 配置验证失败，请修复上述错误后重试")
        return False

    if warnings:
        print("⚠️  配置验证通过，但存在警告")
        return True

    print("✓ 配置验证完全通过")
    return True


if __name__ == "__main__":
    # 运行验证
    success = validate_environment()
    sys.exit(0 if success else 1)
