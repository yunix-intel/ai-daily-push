#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
告警通知渠道实现

支持多种通知渠道：
1. 企业微信 Webhook
2. 钉钉 Webhook
3. 飞书 Webhook
4. 邮件 SMTP
5. 自定义 Webhook
"""
import json
import os
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class NotificationChannel(Enum):
    """通知渠道枚举"""
    WECOM = "wecom"
    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    EMAIL = "email"
    WEBHOOK = "webhook"


class AlertNotifier:
    """告警通知器"""

    def __init__(self):
        """初始化通知器"""
        self.channels = self._load_channels()

    def _load_channels(self) -> Dict[str, Any]:
        """加载配置的通知渠道"""
        channels = {}

        # 企业微信
        wecom_webhook = os.environ.get("ALERT_WECOM_WEBHOOK", "").strip()
        if wecom_webhook:
            channels[NotificationChannel.WECOM] = {
                "webhook": wecom_webhook,
                "enabled": True
            }

        # 钉钉
        dingtalk_webhook = os.environ.get("ALERT_DINGTALK_WEBHOOK", "").strip()
        dingtalk_secret = os.environ.get("ALERT_DINGTALK_SECRET", "").strip()
        if dingtalk_webhook:
            channels[NotificationChannel.DINGTALK] = {
                "webhook": dingtalk_webhook,
                "secret": dingtalk_secret,
                "enabled": True
            }

        # 飞书
        feishu_webhook = os.environ.get("ALERT_FEISHU_WEBHOOK", "").strip()
        if feishu_webhook:
            channels[NotificationChannel.FEISHU] = {
                "webhook": feishu_webhook,
                "enabled": True
            }

        # 自定义 Webhook
        custom_webhook = os.environ.get("ALERT_WEBHOOK", "").strip()
        if custom_webhook:
            channels[NotificationChannel.WEBHOOK] = {
                "webhook": custom_webhook,
                "enabled": True
            }

        return channels

    def send_alert(self, level: str, title: str, message: str, details: Optional[Dict] = None) -> bool:
        """
        发送告警到所有配置的渠道

        Args:
            level: 告警级别 (INFO/WARNING/ERROR/CRITICAL)
            title: 告警标题
            message: 告警消息
            details: 额外详情

        Returns:
            是否至少有一个渠道发送成功
        """
        if not self.channels:
            return False

        success_count = 0
        for channel_type, config in self.channels.items():
            if not config.get("enabled", False):
                continue

            try:
                if channel_type == NotificationChannel.WECOM:
                    self._send_wecom(level, title, message, details, config)
                elif channel_type == NotificationChannel.DINGTALK:
                    self._send_dingtalk(level, title, message, details, config)
                elif channel_type == NotificationChannel.FEISHU:
                    self._send_feishu(level, title, message, details, config)
                elif channel_type == NotificationChannel.WEBHOOK:
                    self._send_webhook(level, title, message, details, config)

                success_count += 1
            except Exception as e:
                print(f"告警发送失败 [{channel_type.value}]: {e}")

        return success_count > 0

    def _send_wecom(self, level: str, title: str, message: str, details: Optional[Dict], config: Dict):
        """发送企业微信告警"""
        webhook = config["webhook"]

        # 构建 Markdown 消息
        color_map = {
            "INFO": "info",
            "WARNING": "warning",
            "ERROR": "warning",
            "CRITICAL": "warning"
        }

        content = f"### {self._get_emoji(level)} {title}\n\n"
        content += f"**级别**: {level}\n\n"
        content += f"**消息**: {message}\n\n"
        content += f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        if details:
            content += "**详情**:\n\n"
            for key, value in details.items():
                content += f"- {key}: {value}\n"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }

        self._http_post(webhook, payload)

    def _send_dingtalk(self, level: str, title: str, message: str, details: Optional[Dict], config: Dict):
        """发送钉钉告警"""
        webhook = config["webhook"]

        content = f"## {self._get_emoji(level)} {title}\n\n"
        content += f"**级别**: {level}\n\n"
        content += f"**消息**: {message}\n\n"
        content += f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        if details:
            content += "**详情**:\n\n"
            for key, value in details.items():
                content += f"- {key}: {value}\n"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": content
            }
        }

        # TODO: 如果配置了 secret，需要签名
        self._http_post(webhook, payload)

    def _send_feishu(self, level: str, title: str, message: str, details: Optional[Dict], config: Dict):
        """发送飞书告警"""
        webhook = config["webhook"]

        content = f"**{self._get_emoji(level)} {title}**\n\n"
        content += f"级别: {level}\n"
        content += f"消息: {message}\n"
        content += f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"

        if details:
            content += "\n详情:\n"
            for key, value in details.items():
                content += f"- {key}: {value}\n"

        payload = {
            "msg_type": "text",
            "content": {
                "text": content
            }
        }

        self._http_post(webhook, payload)

    def _send_webhook(self, level: str, title: str, message: str, details: Optional[Dict], config: Dict):
        """发送自定义 Webhook 告警"""
        webhook = config["webhook"]

        payload = {
            "level": level,
            "title": title,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }

        self._http_post(webhook, payload)

    def _http_post(self, url: str, payload: Dict, timeout: int = 10):
        """发送 HTTP POST 请求"""
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = response.read().decode('utf-8')
                return json.loads(result) if result else {}
        except urllib.error.HTTPError as e:
            raise Exception(f"HTTP {e.code}: {e.read().decode('utf-8')}")
        except urllib.error.URLError as e:
            raise Exception(f"URL Error: {e.reason}")

    def _get_emoji(self, level: str) -> str:
        """获取告警级别对应的 emoji"""
        emoji_map = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨"
        }
        return emoji_map.get(level, "📢")


# 全局实例
_notifier = None


def get_notifier() -> AlertNotifier:
    """获取全局告警通知器实例"""
    global _notifier
    if _notifier is None:
        _notifier = AlertNotifier()
    return _notifier


def send_alert(level: str, title: str, message: str, details: Optional[Dict] = None) -> bool:
    """
    快捷方法：发送告警

    Args:
        level: 告警级别
        title: 标题
        message: 消息
        details: 详情

    Returns:
        是否发送成功
    """
    notifier = get_notifier()
    return notifier.send_alert(level, title, message, details)


if __name__ == "__main__":
    # 测试告警通知
    print("=== 告警通知测试 ===\n")

    # 检查配置
    notifier = get_notifier()
    print(f"已配置 {len(notifier.channels)} 个通知渠道:")
    for channel_type in notifier.channels.keys():
        print(f"  - {channel_type.value}")

    if notifier.channels:
        print("\n发送测试告警...")
        success = send_alert(
            level="INFO",
            title="系统测试",
            message="这是一条测试告警消息",
            details={
                "模块": "alerting",
                "环境": "测试"
            }
        )
        print(f"发送结果: {'成功' if success else '失败'}")
    else:
        print("\n未配置任何通知渠道，请设置环境变量：")
        print("  - ALERT_WECOM_WEBHOOK: 企业微信 Webhook")
        print("  - ALERT_DINGTALK_WEBHOOK: 钉钉 Webhook")
        print("  - ALERT_FEISHU_WEBHOOK: 飞书 Webhook")
        print("  - ALERT_WEBHOOK: 自定义 Webhook")
