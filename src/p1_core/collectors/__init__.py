"""P1-F01 知识采集接入适配器子包。

Stage 2 阶段按数据源类型填充具体采集器实现：
  - :mod:`p1_core.collectors.document` — Word 文件采集器（``.doc``/``.docx``）
  - :mod:`p1_core.collectors.html` — HTML 文件采集器（``.html``/``.htm``）
  - :mod:`p1_core.collectors.api` — 事项库/工单 API 采集器（M1-S2c 填充）

说明：本 ``__init__`` 仅导出 :class:`BaseCollector` 等轻量基类，具体采集器
通过延迟导入在 ``document`` / ``html`` 子模块中按需加载，避免
``python -m p1_core.collectors.document`` 等 CLI 调用因父包导入触发完整
采集器栈导致 RuntimeWarning。
"""

from __future__ import annotations

from p1_core.collectors.base import BaseCollector, UnsupportedFormatError

__all__ = ["BaseCollector", "UnsupportedFormatError"]
