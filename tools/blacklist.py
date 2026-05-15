"""敏感应用黑名单 — 用于截图隐藏密码管理器等。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from common.models import WindowInfo

log = logging.getLogger(__name__)

BLACKLIST_PATH = Path.home() / ".active_tracker" / "blacklist.json"

DEFAULT_BLACKLIST = {
    "bundle_ids": [
        "com.agilebits.onepassword",
        "com.1password.",
        "com.keepassxc.",
        "com.lastpass.",
        "com.bitwarden.",
    ],
    "executables": [
        "1Password", "1password.exe",
        "KeePassXC", "keepassxc.exe",
        "Bitwarden", "bitwarden.exe",
    ],
}


def load_blacklist() -> dict:
    if not BLACKLIST_PATH.exists():
        BLACKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            BLACKLIST_PATH.write_text(json.dumps(DEFAULT_BLACKLIST, indent=2))
        except OSError as exc:
            log.warning("写入默认黑名单失败：%s", exc)
        return DEFAULT_BLACKLIST
    try:
        return json.loads(BLACKLIST_PATH.read_text())
    except (OSError, ValueError) as exc:
        log.warning("读取黑名单失败，使用默认值：%s", exc)
        return DEFAULT_BLACKLIST


def is_blacklisted(info: WindowInfo, bl: dict) -> bool:
    bid = (info.app_bundle_id or "").lower()
    for prefix in bl.get("bundle_ids", []):
        if bid and bid.startswith(prefix.lower()):
            return True
    exe = (info.process.executable if info.process and info.process.executable else "").lower()
    name = (info.app_name or "").lower()
    for hint in bl.get("executables", []):
        h = hint.lower()
        if h and (h in exe or h in name):
            return True
    return False
