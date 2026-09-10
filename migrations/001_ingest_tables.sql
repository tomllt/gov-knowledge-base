-- M1-S2a: PDF 文件采集器接入记录与审计日志 DDL
-- 适用 SQLite 3。Idempotent: 可重复执行。

-- ----------------------------------------------------------------------
-- 接入记录主表：每一次采集尝试登记一行,作为 RawDocument 的永久业务凭证。
-- 业务规则（来自 P1-F01 §业务规则）：接入记录永久保留,不可删除。
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingest_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    access_record_id TEXT NOT NULL UNIQUE,           -- 业务接入单号 (如 AR-2026-0001)
    source_type     TEXT NOT NULL,                    -- SourceType 枚举值 (pdf / word / html ...)
    source_uri      TEXT NOT NULL,                    -- 原始数据 URI/路径 (已脱敏)
    doc_id          TEXT NOT NULL,                    -- RawDocument.doc_id (ULID)
    sha256          TEXT NOT NULL,                    -- 原始字节流 SHA-256 摘要
    size_bytes      INTEGER NOT NULL CHECK (size_bytes >= 0),
    encoding        TEXT NOT NULL,                    -- 标准化后的编码
    collected_at    TEXT NOT NULL,                    -- ISO-8601 带时区
    status          TEXT NOT NULL,                    -- ok | failed | quarantined
    error_message   TEXT,                             -- 失败/隔离原因 (成功时 NULL)
    quarantine_path TEXT,                             -- 隔离文件相对路径 (成功时 NULL)
    redaction_hits  INTEGER NOT NULL DEFAULT 0        -- 敏感字段命中次数
        CHECK (redaction_hits >= 0),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_ingest_record_source_uri  ON ingest_record(source_uri);
CREATE INDEX IF NOT EXISTS idx_ingest_record_collected_at ON ingest_record(collected_at);
CREATE INDEX IF NOT EXISTS idx_ingest_record_status       ON ingest_record(status);

-- ----------------------------------------------------------------------
-- 审计日志表：记录采集过程中的关键事件,日志不可篡改 (append-only)。
-- 与 ingest_record 一对多:一次采集可能产生多条审计记录 (开始/完成/失败)。
-- ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingest_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    access_record_id TEXT NOT NULL,                   -- 关联 ingest_record.access_record_id
    event           TEXT NOT NULL,                    -- start | collected | validated | redacted |
                                                       -- persisted | failed | quarantined
    level           TEXT NOT NULL DEFAULT 'info',     -- info | warning | error
    detail          TEXT,                             -- 自由文本,JSON 或单行
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_ingest_log_access_record_id ON ingest_log(access_record_id);
CREATE INDEX IF NOT EXISTS idx_ingest_log_event            ON ingest_log(event);
