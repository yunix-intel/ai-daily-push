#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sanitized delivery milestones shared by report jobs and history recording."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


STATUS_SCHEMA_VERSION = 1
WECOM_CHANNELS = {"wecom_webhook", "wecom_application"}


def _parse_utc(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def write_delivery_status(path, report, channel, configured, attempted,
                          success, completed_at=None, reason=""):
    """Write only non-sensitive delivery facts to a job artifact."""
    if not path:
        return None
    completed = _parse_utc(completed_at)
    if success and completed is None:
        completed = datetime.now(timezone.utc)
    payload = {
        "schema_version": STATUS_SCHEMA_VERSION,
        "report": str(report),
        "channel": str(channel),
        "configured": bool(configured),
        "attempted": bool(attempted),
        "success": bool(success),
        "delivery_completed_at": completed.isoformat() if success and completed else None,
        "reason": str(reason)[:120],
    }
    target = Path(path)
    if target.parent != Path("."):
        target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
    return payload


def load_successful_delivery(path):
    """Validate one artifact and return its successful UTC milestone."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"推送状态文件不可读: {path}: {type(exc).__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"推送状态格式无效: {path}")
    if payload.get("schema_version") != STATUS_SCHEMA_VERSION:
        raise ValueError(f"推送状态版本无效: {path}")
    if payload.get("channel") not in WECOM_CHANNELS:
        raise ValueError(f"企业微信推送未配置: {path}")
    if not (payload.get("configured") and payload.get("attempted") and payload.get("success")):
        reason = payload.get("reason") or "delivery_not_successful"
        raise ValueError(f"企业微信推送未成功: {path}: {reason}")
    completed = _parse_utc(payload.get("delivery_completed_at"))
    if completed is None:
        raise ValueError(f"企业微信成功状态缺少完成时间: {path}")
    return completed


def latest_successful_delivery(paths):
    """Require every report delivery to succeed and return the latest milestone."""
    if not paths:
        raise ValueError("未提供推送状态文件")
    return max(load_successful_delivery(path) for path in paths)
