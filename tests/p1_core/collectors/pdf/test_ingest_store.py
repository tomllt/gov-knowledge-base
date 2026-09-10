"""`IngestStore` (SQLite 持久化) 测试。

约束来源:P1-F01 §业务规则 - 接入记录永久保留;以及 M1-S2a 验收点:
    - ``ingest_record`` 表 (主表)
    - ``ingest_log`` 表 (审计日志,append-only)
    - DDL 通过 ``migrations/001_ingest_tables.sql`` 应用
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from p1_core.collectors.pdf.ingest_store import (
    IngestLog,
    IngestRecord,
    IngestStatus,
    IngestStore,
)


def _record(**overrides: object) -> IngestRecord:
    defaults: dict[str, object] = {
        "access_record_id": "AR-2026-0001",
        "source_type": "pdf",
        "source_uri": "s3://bucket/2026/01/sample.pdf",
        "doc_id": "01HV3A1B2C3D4E5F6G7H8J9K0L",
        "sha256": "a" * 64,
        "size_bytes": 1024,
        "encoding": "utf-8",
        "collected_at": datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        "status": IngestStatus.OK,
        "error_message": None,
        "quarantine_path": None,
        "redaction_hits": 0,
    }
    defaults.update(overrides)
    return IngestRecord(**defaults)  # type: ignore[arg-type]


def _log(**overrides: object) -> IngestLog:
    defaults: dict[str, object] = {
        "access_record_id": "AR-2026-0001",
        "event": "start",
        "level": "info",
        "detail": None,
    }
    defaults.update(overrides)
    return IngestLog(**defaults)  # type: ignore[arg-type]


class TestIngestStoreInit:
    """初始化时自动应用迁移脚本。"""

    def test_creates_db_with_required_tables(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "001_ingest_tables.sql").write_text(
            (
                Path(__file__).parent.parent.parent.parent.parent
                / "migrations"
                / "001_ingest_tables.sql"
            ).read_text(),
            encoding="utf-8",
        )
        db = tmp_path / "p1.db"
        IngestStore(db_path=db, migrations_dir=migrations)
        # 直接用 sqlite3 校验表存在
        with sqlite3.connect(db) as conn:
            names = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        assert "ingest_record" in names
        assert "ingest_log" in names

    def test_idempotent_migration(self, tmp_path: Path) -> None:
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "001_ingest_tables.sql").write_text(
            (
                Path(__file__).parent.parent.parent.parent.parent
                / "migrations"
                / "001_ingest_tables.sql"
            ).read_text(),
            encoding="utf-8",
        )
        db = tmp_path / "p1.db"
        IngestStore(db_path=db, migrations_dir=migrations)
        # 再次创建应当无异常 (CREATE TABLE IF NOT EXISTS)
        IngestStore(db_path=db, migrations_dir=migrations)


class TestIngestStoreRecord:
    """`record()` / `list_records()` 行为。"""

    def test_record_persisted_and_readable(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        rec = _record()
        store.record(rec)
        records = store.list_records()
        assert len(records) == 1
        got = records[0]
        assert got.access_record_id == rec.access_record_id
        assert got.source_type == rec.source_type
        assert got.doc_id == rec.doc_id
        assert got.sha256 == rec.sha256
        assert got.size_bytes == rec.size_bytes
        assert got.status is IngestStatus.OK
        assert got.redaction_hits == 0

    def test_duplicate_access_record_id_rejected(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record(_record())
        with pytest.raises(sqlite3.IntegrityError):
            store.record(_record())

    def test_failed_status_with_error_and_quarantine(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        rec = _record(
            status=IngestStatus.QUARANTINED,
            error_message="corrupt pdf header",
            quarantine_path="quarantine/2026/01/sample.bin",
            sha256="b" * 64,
            size_bytes=512,
        )
        store.record(rec)
        [got] = store.list_records()
        assert got.status is IngestStatus.QUARANTINED
        assert got.error_message == "corrupt pdf header"
        assert got.quarantine_path == "quarantine/2026/01/sample.bin"


class TestIngestStoreLog:
    """`log()` / `list_logs()` 行为。"""

    def test_logs_persisted_in_order(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record(_record())  # 先建主记录
        store.log(_log(event="start"))
        store.log(_log(event="collected", detail="size=1024"))
        store.log(_log(event="validated", level="info"))
        store.log(_log(event="persisted"))
        logs = store.list_logs("AR-2026-0001")
        events = [log.event for log in logs]
        assert events == ["start", "collected", "validated", "persisted"]

    def test_logs_filtered_by_access_record_id(self, tmp_path: Path) -> None:
        store = _make_store(tmp_path)
        store.record(_record(access_record_id="AR-1"))
        store.log(_log(access_record_id="AR-1", event="start"))
        store.record(
            _record(access_record_id="AR-2", doc_id="01HV3A1B2C3D4E5F6G7H8J9K0M", sha256="c" * 64)
        )
        store.log(_log(access_record_id="AR-2", event="start"))
        assert [entry.event for entry in store.list_logs("AR-1")] == ["start"]
        assert [entry.event for entry in store.list_logs("AR-2")] == ["start"]


def _make_store(tmp_path: Path) -> IngestStore:
    """构造使用仓库内迁移脚本的 IngestStore,DB 落在 tmp_path 下。"""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "001_ingest_tables.sql").write_text(
        (
            Path(__file__).parent.parent.parent.parent.parent
            / "migrations"
            / "001_ingest_tables.sql"
        ).read_text(),
        encoding="utf-8",
    )
    db = tmp_path / "p1.db"
    return IngestStore(db_path=db, migrations_dir=migrations)
