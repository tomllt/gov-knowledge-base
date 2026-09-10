"""P1-F01 知识采集接入基类。

定义所有具体采集器（Word/HTML/PDF/API/...）共享的抽象接口与受控异常类。
设计上保持最小可用面：

  - ``source_type`` 标识数据源分类，写入 ``RawDocument.source_type``。
  - ``supported_extensions`` 用于目录扫描阶段的格式过滤。
  - ``collect`` 采集单个文件并返回 ``RawDocument``，异常情况抛出领域错误。
  - ``iter_directory`` 批量采集目录下所有支持格式的文件，错误隔离到单文件级别。

接入记录 / 审计日志 / 脱敏中间件 / 隔离区等横切关注点由上层编排器与
中间件装饰器注入，本基类不耦合具体实现，以便与 M1-S2a (PDF) /
M1-S2c (API) 采集器共享同一接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import ClassVar

from p1_core.exceptions import IngestError
from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument


class UnsupportedFormatError(IngestError):
    """采集器不支持的格式。

    例如：Word 采集器收到旧二进制 ``.doc`` 文件时不应视为错误，而应抛出
    该异常供上层审计 / 隔离区识别并标记 ``unsupported_format``。
    """


class BaseCollector(ABC):
    """P1-F01 知识采集接入抽象基类。

    所有具体采集器必须实现 :meth:`collect` 并声明 :attr:`source_type` 与
    :meth:`supported_extensions`。批量入口 :meth:`iter_directory` 提供
    通用实现：按扩展名过滤文件、单文件错误隔离、不破坏整体批处理。
    """

    source_type: ClassVar[SourceType]

    @abstractmethod
    def supported_extensions(self) -> frozenset[str]:
        """采集器支持的扩展名集合（含 ``.``，全部小写）。"""
        ...

    @abstractmethod
    def collect(self, path: Path) -> RawDocument:
        """采集单个文件并返回标准化后的 ``RawDocument``。

        Raises:
            UnsupportedFormatError: 文件扩展名不被该采集器支持。
            IngestError: 文件无法读取、解码失败或结构损坏。
        """
        ...

    def iter_directory(
        self,
        directory: Path,
        *,
        recursive: bool = False,
    ) -> Iterator[RawDocument | IngestError]:
        """批量采集目录下所有支持格式的文件。

        实现细节：
          - 仅按 :meth:`supported_extensions` 过滤文件；其它格式静默跳过。
          - 单文件失败（读取/解码）抛出为 :class:`IngestError` 并作为结果
            元素继续后续文件，保证批处理不被个别异常中断。
          - ``UnsupportedFormatError`` 同样以结果元素返回，便于上层审计
            标记 ``unsupported_format`` 状态。

        Yields:
            依次产出每份成功采集得到的 ``RawDocument`` 或单文件 ``IngestError``。
        """
        if not directory.is_dir():
            msg = f"input path is not a directory: {directory}"
            raise IngestError(msg)
        extensions = self.supported_extensions()
        glob = directory.rglob if recursive else directory.glob
        for path in sorted(glob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in extensions:
                continue
            try:
                yield self.collect(path)
            except IngestError as exc:
                yield exc

    def collect_directory(
        self,
        directory: Path,
        *,
        recursive: bool = False,
    ) -> list[RawDocument]:
        """便利方法：仅返回成功的 ``RawDocument`` 列表（丢弃错误）。"""
        return [
            item
            for item in self.iter_directory(directory, recursive=recursive)
            if isinstance(item, RawDocument)
        ]


__all__ = ["BaseCollector", "Iterable", "UnsupportedFormatError"]
