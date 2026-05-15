"""文件管理器集成抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from common.models import FileManagerState, WindowInfo


class FileManagerIntegration(ABC):
    @abstractmethod
    def matches(self, info: WindowInfo) -> bool:
        """根据 bundle_id / executable / window_class 判断是否归本集成处理。"""

    @abstractmethod
    async def query(self, info: WindowInfo) -> Optional[FileManagerState]:
        """查询当前文件管理器状态。必须带超时（≤ 1.5s），失败返回 None。"""
