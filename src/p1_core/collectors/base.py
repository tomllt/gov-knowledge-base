"""采集器抽象基类与源定位描述。

M1-S1 骨架约定的协议:

    class BaseCollector(Protocol):
        source_type: SourceType
        def collect(self, source: SourceLocator) -> Iterator[RawDocument]: ...
        def validate(self, doc: RawDocument) -> bool: ...
        def quarantine(self, doc: RawDocument, reason: str) -> Path: ...

本模块以 :class:`abc.ABC` 实现该协议,使得子类必须显式实现三个方法
并声明 ``source_type``;同时提供 :class:`SourceLocator` 不可变数据类。

所有具体采集器 (PDF / Word / HTML / API ...) 继承 :class:`BaseCollector`。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from p1_core.models.enums import SourceType
from p1_core.models.raw_document import RawDocument


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """采集源定位描述 (不可变)。

    Attributes:
        path: 源数据所在路径 (PDF/Word/HTML 时为目录或单文件; API 时为 URL 字符串)。
        source_type: 数据源类型,用于校验与子类匹配。
    """

    path: Path
    source_type: SourceType

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            msg = f"path must be Path, got {type(self.path).__name__}"
            raise TypeError(msg)
        # 允许 path 为尚未存在的目标 (目录/文件),由调用方负责创建或失败处理。
        # 仅排除空字符串构造的非法 Path("")。
        if str(self.path) == "":
            msg = "path must not be empty"
            raise ValueError(msg)


class BaseCollector(ABC):
    """所有采集器实现的抽象基类。

    约束:
        - ``source_type`` 必须声明,且与 ``collect`` 返回的 ``RawDocument.source_type`` 一致;
        - :meth:`collect` 是惰性迭代器,失败文件应通过 :meth:`quarantine` 落盘,
          而非抛出异常阻断后续采集;
        - :meth:`validate` 在采集完成后、解析前调用,用于做格式/大小/编码校验;
        - :meth:`quarantine` 返回隔离文件的绝对路径,供审计日志与人工处理使用。
    """

    #: 子类必须覆盖,声明本采集器处理的数据源类型。
    source_type: SourceType

    @abstractmethod
    def collect(self, source: SourceLocator) -> Iterator[RawDocument]:
        """按 ``source`` 拉取原始数据,产出 ``RawDocument`` 迭代器。"""

    @abstractmethod
    def validate(self, doc: RawDocument) -> bool:
        """校验单条采集结果是否可进入解析阶段。"""

    @abstractmethod
    def quarantine(self, doc: RawDocument, reason: str) -> Path:
        """将失败/可疑数据落盘到隔离区,返回落盘后的绝对路径。"""


__all__ = ["BaseCollector", "SourceLocator"]
