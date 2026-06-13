#!/usr/bin/env python3
"""为旧版 memory.db 添加 ``user_profiles.bio`` 列。

服务端部署后报错：

    sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such column: user_profiles.bio

执行方式（推荐在项目根目录执行）：

    cd /root/workspace/cd-agent
    python scripts/migrate_add_user_profiles_bio.py

也可以通过环境变量指定数据库 URL（用于非默认路径）：

    MEMORY_DB_URL=sqlite:////path/to/memory.db python scripts/migrate_add_user_profiles_bio.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 将 src 加入 Python 路径，以便导入项目配置
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from comedy_agent.core.config import settings
from sqlalchemy import create_engine


def migrate(db_url: str | None = None) -> None:
    """为 user_profiles 表添加 bio 列（幂等）。"""
    if db_url is None:
        db_path = settings.memory_db_path
        db_url = f"sqlite:///{db_path}"

    engine = create_engine(db_url, echo=False)
    with engine.connect() as conn:
        columns = [
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(user_profiles)")
        ]
        if "bio" in columns:
            print(f"[skip] user_profiles.bio already exists in {db_url}")
            return

        conn.exec_driver_sql("ALTER TABLE user_profiles ADD COLUMN bio TEXT")
        conn.commit()
        print(f"[ok] Added user_profiles.bio to {db_url}")


if __name__ == "__main__":
    migrate(os.getenv("MEMORY_DB_URL"))
