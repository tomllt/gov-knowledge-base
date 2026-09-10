"""采集记录与审计日志的 SQLite 持久化。

对应 DDL 脚本:``migrations/001_ingest_tables.sql``。本模块负责:
    1. 启动时自动应用迁移 (idempotent);
    2. 写入 :class:`IngestRecord` 主记录;
    3. 写入 :class:`IngestLog` 审计日志 (append-only);
    4. 提供简单的查询接口。

设计取舍:
    - 不引入 ORM / 连接池,直接用标准库 ``sqlite3``,确保依赖最小;
    - 每个方法内自建短连接,避免长连接占用文件锁;
    - 类型与表 schema 一一对应,任何字段类型不匹配由 SQLite 直接报错。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class IngestStatus(StrEnum):
    """采集状态。"""

    OK = "ok"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class IngestRecord:
    """接入记录主表数据模型。"""

    access_record_id: str
    source_type: str
    source_uri: str
    doc_id: str
    sha256: str
    size_bytes: int
    encoding: str
    collected_at: datetime
    status: IngestStatus
    error_message: str | None
    quarantine_path: str | None
    redaction_hits: int


@dataclass(frozen=True, slots=True)
class IngestLog:
    """采集审计日志数据模型。"""

    access_record_id: str
    event: str
    level: str
    detail: str | None


_SCHEMA_FILES: tuple[str, ...] = ("001_ingest_tables.sql",)


class IngestStore:
    """SQLite 接入记录持久化器。

    使用方式:
        store = IngestStore(db_path=Path("data/p1_core.db"),
                            migrations_dir=Path("migrations"))
        store.record(IngestRecord(...))
        store.log(IngestLog(...))
    """

    __slots__ = ("db_path", "migrations_dir")

    def __init__(self, *, db_path: Path, migrations_dir: Path) -> None:
        if not isinstance(db_path, Path):
            msg = f"db_path must be Path, got {type(db_path).__name__}"
            raise TypeError(msg)
        if not isinstance(migrations_dir, Path):
            msg = f"migrations_dir must be Path, got {type(migrations_dir).__name__}"
            raise TypeError(msg)
        if not migrations_dir.exists():
            msg = f"migrations_dir does not exist: {migrations_dir}"
            raise FileNotFoundError(msg)
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self._apply_migrations()

    # ------------------------------------------------------------------
    # 迁移
    # ------------------------------------------------------------------
    def _apply_migrations(self) -> None:
        """按文件名升序执行 ``migrations_dir`` 下所有 SQL 脚本。"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        scripts = sorted(p for p in self.migrations_dir.glob("*.sql") if p.is_file())
        with sqlite3.connect(self.db_path) as conn:
            for script in scripts:
                conn.executescript(script.read_text(encoding="utf-8"))
            conn.commit()

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def record(self, rec: IngestRecord) -> None:
        """写入一条接入记录 (UNIQUE on access_record_id)。"""
        sql = (
            "INSERT INTO ingest_record ("
            "access_record_id, source_type, source_uri, doc_id, sha256, "
            "size_bytes, encoding, collected_at, status, error_message, "
            "quarantine_path, redaction_hits"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            rec.access_record_id,
            rec.source_type,
            rec.source_uri,
            rec.doc_id,
            rec.sha256,
            rec.size_bytes,
            rec.encoding,
            rec.collected_at.isoformat(),
            rec.status.value,
            rec.error_message,
            rec.quarantine_path,
            rec.redaction_hits,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, params)
            conn.commit()

    def log(self, entry: IngestLog) -> None:
        """写入一条审计日志 (append-only)。"""
        sql = "INSERT INTO ingest_log (access_record_id, event, level, detail) VALUES (?, ?, ?, ?)"
        params = (entry.access_record_id, entry.event, entry.level, entry.detail)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(sql, params)
            conn.commit()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_records(self) -> list[IngestRecord]:
        """按 ``id`` 升序返回所有接入记录。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT access_record_id, source_type, source_uri, doc_id, sha256,"
                " size_bytes, encoding, collected_at, status, error_message,"
                " quarantine_path, redaction_hits"
                " FROM ingest_record ORDER BY id ASC"
            ).fetchall()
        return [_row_to_record(r) for r in rows]

    def list_logs(self, access_record_id: str) -> list[IngestLog]:
        """返回指定接入单号下的全部审计日志,按 ``id`` 升序。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT access_record_id, event, level, detail FROM ingest_log"
                " WHERE access_record_id = ? ORDER BY id ASC",
                (access_record_id,),
            ).fetchall()
        return [IngestLog(access_record_id=r[0], event=r[1], level=r[2], detail=r[3]) for r in rows]


def _row_to_record(row: tuple[object, ...]) -> IngestRecord:
    """将 SQLite 行映射回 :class:`IngestRecord`。"""
    return IngestRecord(
        access_record_id=str(row[0]),
        source_type=str(row[1]),
        source_uri=str(row[2]),
        doc_id=str(row[3]),
        sha256=str(row[4]),
        size_bytes=int(str(row[5])),
        encoding=str(row[6]),
        collected_at=datetime.fromisoformat(str(row[7])),
        status=IngestStatus(str(row[8])),
        error_message=str(row[9]) if row[9] is not None else None,
        quarantine_path=str(row[10]) if row[10] is not None else None,
        redaction_hits=int(str(row[11])),
    )


__all__ = [
    "IngestLog",
    "IngestRecord",
    "IngestStatus",
    "IngestStore",
]
