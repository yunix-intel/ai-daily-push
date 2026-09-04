import json
import re
from pathlib import Path

src = Path(r"C:\Users\yunix\.claude\projects\D--c-ai-daily-push\a91ec8f2-c72d-4eb2-be4c-c509b43d9691.jsonl")
dst = Path(r"D:\c\ai-daily-push\SESSION_HISTORY.md")

patterns = [
    (re.compile(r"(?i)(OPENAI_API_KEY\s*[:=]\s*)(\S+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(GITHUB_TOKEN\s*[:=]\s*)(\S+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(ALERT_WECOM_WEBHOOK\s*[:=]\s*)(\S+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(WECOM_WEBHOOK\s*[:=]\s*)(\S+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(Bearer\s+)(\S+)"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{12,}\b"), "[REDACTED]"),
    (re.compile(r"https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[^\s]+"), "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=[REDACTED]"),
]


def redact(value):
    for pattern, replacement in patterns:
        value = pattern.sub(replacement, value)
    return value


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                typ = item.get("type", "")
                if typ == "text":
                    chunks.append(item.get("text", ""))
                elif typ == "tool_use":
                    data = json.dumps(item.get("input", {}), ensure_ascii=False, indent=2)
                    chunks.append(f"[tool_use: {item.get('name', '')}]\n```json\n{data}\n```")
                elif typ == "tool_result":
                    chunks.append(f"[tool_result]\n{item.get('content', '')}")
            else:
                chunks.append(str(item))
        return "\n".join(chunks)
    return json.dumps(content, ensure_ascii=False, indent=2)


out = [
    "# 当前会话历史导出",
    "",
    "> 导出范围：当前会话全部可读消息与工具记录。敏感 API Key、Token、Webhook 已脱敏。",
    "",
]
count = 0
for line in src.read_text(encoding="utf-8", errors="replace").splitlines():
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        continue
    msg = record.get("message") or record
    role = msg.get("role") or record.get("type") or "unknown"
    if role == "system":
        continue
    content = msg.get("content", record.get("content", ""))
    body = redact(text_of(content)).strip()
    if not body:
        continue
    label = {"user": "用户", "assistant": "助手", "tool": "工具", "tool_result": "工具结果"}.get(role, role)
    out.extend([f"## {label}", "", body, ""])
    count += 1

out.extend(["---", "", f"共导出 {count} 条消息记录。", ""])
dst.write_text("\n".join(out), encoding="utf-8")
print(f"exported={dst}")
print(f"messages={count}")
print(f"bytes={dst.stat().st_size}")
