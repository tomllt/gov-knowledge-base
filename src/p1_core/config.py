"""P1 核心库运行时配置。

集中管理运行时路径与采集相关阈值,采集器实例必须通过 :class:`CollectorConfig`
注入,禁止在模块内部硬编码路径。所有路径默认位于仓库根 ``./data`` 下,
可通过环境变量 ``P1_DATA_DIR`` 覆盖 (便于测试与多环境部署)。

设计原则:
    - 不可变 dataclass,实例可哈希,便于在多处共享同一份配置;
    - 默认值全部由 ``p1_core`` 顶层常量推导,不依赖外部文件;
    - 所有路径为绝对路径,避免 cwd 变化带来的歧义;
    - ``max_bytes`` 默认 100 MiB,符合 P1-AC-01 与 M1-S2a 验收要求。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 路径段名称 ------------------------------------------------------
_DATA_DIRNAME: str = "data"
_QUARANTINE_DIRNAME: str = "quarantine"
_DBNAME: str = "p1_core.db"

# 采集阈值 ------------------------------------------------------
#: 单个 PDF 文件大小硬上限 (bytes)。超过该阈值的文件直接标记为 quarantined,
#: 不会被加载到内存,以避免 OOM 与解析栈异常。
DEFAULT_MAX_BYTES: int = 100 * 1024 * 1024  # 100 MiB

#: 迁移 SQL 脚本所在目录 (相对于 src 上一级,即仓库根)。
_DEFAULT_MIGRATIONS_DIRNAME: str = "migrations"


def _default_data_dir() -> Path:
    """根据环境变量推导默认数据目录,缺失时落到 ``./data`` 绝对路径。"""
    raw = os.environ.get("P1_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    # 仓库根 = src 的上一级
    here = Path(__file__).resolve().parent.parent.parent
    return (here / _DATA_DIRNAME).resolve()


def _default_migrations_dir() -> Path:
    """默认迁移目录 = 仓库根 / migrations。"""
    here = Path(__file__).resolve().parent.parent.parent
    return (here / _DEFAULT_MIGRATIONS_DIRNAME).resolve()


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    """采集器运行时配置 (不可变)。

    Attributes:
        data_dir: 数据根目录,所有运行时产物 (db / quarantine) 位于其下。
        db_path: SQLite 数据库绝对路径。
        quarantine_dir: 隔离文件目录,失败/可疑 PDF 复制到此处。
        migrations_dir: DDL 脚本目录,包含 ``001_ingest_tables.sql``。
        max_bytes: 单文件最大字节数,超过则标记为 quarantined。
    """

    data_dir: Path
    db_path: Path
    quarantine_dir: Path
    migrations_dir: Path
    max_bytes: int = DEFAULT_MAX_BYTES

    @classmethod
    def from_defaults(cls) -> CollectorConfig:
        """基于环境变量与默认目录构造配置实例。"""
        data_dir = _default_data_dir()
        return cls(
            data_dir=data_dir,
            db_path=data_dir / _DBNAME,
            quarantine_dir=data_dir / _QUARANTINE_DIRNAME,
            migrations_dir=_default_migrations_dir(),
            max_bytes=DEFAULT_MAX_BYTES,
        )

    @classmethod
    def with_overrides(
        cls,
        *,
        data_dir: Path | None = None,
        db_path: Path | None = None,
        quarantine_dir: Path | None = None,
        migrations_dir: Path | None = None,
        max_bytes: int | None = None,
    ) -> CollectorConfig:
        """基于可选覆盖构造配置,未提供的字段使用 ``from_defaults()`` 的值。"""
        base = cls.from_defaults()
        return cls(
            data_dir=(data_dir or base.data_dir).resolve(),
            db_path=(db_path or base.db_path).resolve(),
            quarantine_dir=(quarantine_dir or base.quarantine_dir).resolve(),
            migrations_dir=(migrations_dir or base.migrations_dir).resolve(),
            max_bytes=max_bytes if max_bytes is not None else base.max_bytes,
        )

    def ensure_dirs(self) -> None:
        """确保 ``data_dir`` 与 ``quarantine_dir`` 存在。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)


__all__ = ["DEFAULT_MAX_BYTES", "CollectorConfig"]
