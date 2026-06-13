#!/usr/bin/env python3
"""同步本地 SQLAlchemy schema 到现有 SQLite 数据库。

用于服务端部署后出现 ``no such column: xxx`` 类错误的场景：
遍历 ORM 中定义的所有表和列，自动创建缺失的表，并为已有表添加缺失的列。

执行方式（推荐在项目根目录执行）：

    cd /root/workspace/cd-agent
    python scripts/migrate_sync_schema.py

非默认数据库路径可通过环境变量指定：

    MEMORY_DB_URL=sqlite:////path/to/memory.db python scripts/migrate_sync_schema.py

安全提示：
- 本脚本只添加表/列，不会删除已有数据。
- 添加 NOT NULL 列时会附带合理的默认值，避免破坏旧数据。
- 建议在执行前备份数据库文件。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 将 src 加入 Python 路径，以便导入项目配置与 schema
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from comedy_agent.core.config import settings
from comedy_agent.memory.schema import Base
from sqlalchemy import create_engine, inspect
from sqlalchemy.schema import CreateColumn


def _sqlite_default_for(column) -> str:
    """为 NOT NULL 但没有默认值的列生成 SQLite 兼容的默认值字符串。"""
    from sqlalchemy import Boolean, DateTime, Integer, String, Text, JSON

    col_type = column.type
    if isinstance(col_type, Boolean):
        return "0"
    if isinstance(col_type, Integer):
        return "0"
    if isinstance(col_type, (String, Text)):
        return "''"
    if isinstance(col_type, DateTime):
        return "CURRENT_TIMESTAMP"
    if isinstance(col_type, JSON):
        return "'null'"
    return "''"


def _column_definition(engine, column) -> str:
    """生成 ALTER TABLE ADD COLUMN 可用的列定义字符串。"""
    # SQLAlchemy CreateColumn 直接输出列定义，例如 "is_verified BOOLEAN NOT NULL"
    return str(CreateColumn(column).compile(dialect=engine.dialect))


def migrate(db_url: str | None = None, dry_run: bool = False) -> dict:
    """同步 schema。返回操作摘要。"""
    if db_url is None:
        db_path = settings.memory_db_path
        db_url = f"sqlite:///{db_path}"

    engine = create_engine(db_url, echo=False)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    orm_tables = {table.name: table for table in Base.metadata.sorted_tables}

    summary = {
        "db_url": db_url,
        "created_tables": [],
        "added_columns": [],
        "skipped_columns": [],
        "errors": [],
    }

    with engine.connect() as conn:
        # 1. 创建 ORM 中有但数据库中缺失的表
        for table_name, table in orm_tables.items():
            if table_name not in existing_tables:
                if dry_run:
                    summary["created_tables"].append(table_name)
                    continue
                try:
                    table.create(conn)
                    conn.commit()
                    summary["created_tables"].append(table_name)
                    print(f"[ok] Created table: {table_name}")
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(("create_table", table_name, str(exc)))
                    print(f"[error] Failed to create table {table_name}: {exc}")

        # 2. 为已有表添加缺失的列
        for table_name, table in orm_tables.items():
            if table_name not in existing_tables:
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue
                if column.primary_key:
                    # SQLite 不允许通过 ALTER TABLE 添加主键列
                    summary["skipped_columns"].append((table_name, column.name, "primary_key"))
                    print(f"[skip] Cannot add primary key column: {table_name}.{column.name}")
                    continue

                col_def = _column_definition(engine, column)
                # SQLite 不允许为已有行添加没有默认值的 NOT NULL 列，
                # 因此只要列是 NOT NULL 且没有数据库级默认值，就附加一个默认值。
                if not column.nullable and column.server_default is None:
                    default_value = _sqlite_default_for(column)
                    col_def = f"{col_def} DEFAULT {default_value}"

                sql = f'ALTER TABLE "{table_name}" ADD COLUMN {col_def}'
                if dry_run:
                    summary["added_columns"].append((table_name, column.name))
                    print(f"[dry-run] {sql}")
                    continue
                try:
                    conn.exec_driver_sql(sql)
                    conn.commit()
                    summary["added_columns"].append((table_name, column.name))
                    print(f"[ok] Added column: {table_name}.{column.name}")
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(("add_column", f"{table_name}.{column.name}", str(exc)))
                    print(f"[error] Failed to add column {table_name}.{column.name}: {exc}")

    return summary


if __name__ == "__main__":
    dry_run = os.getenv("DRY_RUN", "0") == "1"
    db_url = os.getenv("MEMORY_DB_URL")
    summary = migrate(db_url, dry_run=dry_run)

    print("\nMigration summary:")
    print(f"  DB URL: {summary['db_url']}")
    print(f"  Created tables: {len(summary['created_tables'])}")
    print(f"  Added columns: {len(summary['added_columns'])}")
    print(f"  Skipped columns: {len(summary['skipped_columns'])}")
    print(f"  Errors: {len(summary['errors'])}")

    if summary["errors"]:
        sys.exit(1)
