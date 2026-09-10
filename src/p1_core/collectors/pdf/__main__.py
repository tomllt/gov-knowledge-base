"""PDF 采集器命令行入口。

用法:
    python -m p1_core.collectors.pdf --input <dir> --output <db>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from p1_core.collectors.base import SourceLocator
from p1_core.collectors.pdf.collector import PdfFileCollector
from p1_core.collectors.pdf.ingest_store import IngestStore
from p1_core.collectors.pdf.redactor import SensitiveRedactor
from p1_core.config import CollectorConfig
from p1_core.models.enums import SourceType


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="采集目录中的 PDF 文件")
    parser.add_argument("--input", required=True, type=Path, help="PDF 输入目录")
    parser.add_argument("--output", required=True, type=Path, help="SQLite 数据库路径")
    return parser


def run(input_dir: Path, output_db: Path) -> int:
    """执行一次 PDF 目录采集,返回进程退出码。"""
    base = CollectorConfig.from_defaults()
    config = CollectorConfig.with_overrides(
        data_dir=output_db.parent,
        db_path=output_db,
        quarantine_dir=output_db.parent / "quarantine",
        migrations_dir=base.migrations_dir,
    )
    store = IngestStore(db_path=config.db_path, migrations_dir=config.migrations_dir)
    collector = PdfFileCollector(
        config=config,
        store=store,
        redactor=SensitiveRedactor(),
    )
    source = SourceLocator(path=input_dir, source_type=SourceType.PDF)
    documents = list(collector.collect(source))
    print(f"collected={len(documents)} database={output_db}")
    return 0


def main() -> int:
    """解析参数并运行采集。"""
    args = build_parser().parse_args()
    return run(args.input, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
