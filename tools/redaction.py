"""命令行脱敏 — 在显示终端 cmdline 前过滤 token / 密码等敏感参数。

设计原则：宁可误判，不可泄漏。返回 (redacted_cmdline, was_redacted)。
"""

from __future__ import annotations

import re

# --key=value 模式（值整体替换）
SENSITIVE_FLAG_PATTERNS = [
    re.compile(r"^(--?password|--?passwd|--?pass)=(.*)$", re.IGNORECASE),
    re.compile(r"^(--?token|--?api-?key|--?apikey|--?secret|--?auth|--?authorization)=(.*)$", re.IGNORECASE),
    re.compile(r"^(--?bearer)=(.*)$", re.IGNORECASE),
]

# --key value 模式（下一个 token 整体替换）。小写匹配。
SENSITIVE_FLAG_NAMES = {
    "--password", "-p", "--passwd", "--pass",
    "--token", "--api-key", "--apikey", "--secret",
    "--auth", "--authorization", "--bearer",
    "--access-key", "--access-key-id", "--secret-key", "--secret-access-key",
    "--client-secret", "--private-key",
}

# 值本身长得像 token / 高熵串
VALUE_PATTERNS = [
    re.compile(r"^AKIA[0-9A-Z]{16}$"),                 # AWS access key
    re.compile(r"^sk-[A-Za-z0-9_\-]{20,}$"),           # OpenAI / Anthropic
    re.compile(r"^ghp_[A-Za-z0-9]{30,}$"),             # GitHub PAT
    re.compile(r"^gho_[A-Za-z0-9]{30,}$"),             # GitHub OAuth
    re.compile(r"^xox[bpas]-[A-Za-z0-9\-]{20,}$"),     # Slack
    re.compile(r"^[A-Fa-f0-9]{40,}$"),                 # long hex
    re.compile(r"^[A-Za-z0-9+/]{48,}={0,2}$"),         # long base64
]


def _redact_value(v: str) -> str:
    if not v:
        return v
    if len(v) < 8:
        return v
    if len(v) > 12:
        return v[:3] + "***" + v[-2:]
    return "***"


def redact_cmdline(cmdline: list[str]) -> tuple[list[str], bool]:
    """返回 (脱敏后的 cmdline, 是否做过脱敏)。永远不抛异常。"""
    out: list[str] = []
    was_redacted = False
    i = 0
    n = len(cmdline)
    while i < n:
        token = cmdline[i] or ""

        # --key=value
        replaced = False
        for pat in SENSITIVE_FLAG_PATTERNS:
            m = pat.match(token)
            if m:
                out.append(f"{m.group(1)}={_redact_value(m.group(2))}")
                was_redacted = True
                replaced = True
                break
        if replaced:
            i += 1
            continue

        # --key value
        if token.lower() in SENSITIVE_FLAG_NAMES and i + 1 < n:
            out.append(token)
            out.append(_redact_value(cmdline[i + 1]))
            was_redacted = True
            i += 2
            continue

        # 值本身像 token
        if any(p.match(token) for p in VALUE_PATTERNS):
            out.append(_redact_value(token))
            was_redacted = True
            i += 1
            continue

        out.append(token)
        i += 1

    return out, was_redacted
