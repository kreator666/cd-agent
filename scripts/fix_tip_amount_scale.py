"""按比例缩放指定时间的打赏记录手续费与净得金额。

用途：修复因单位换算错误导致 fee_cents / net_amount_cents 被放大 N 倍的数据。
用法：
    python scripts/fix_tip_amount_scale.py --scale 1000 "2026-08-22 10:30:06" "2026-08-22 09:44:21"

默认 --scale 1000，即把金额除以 1000。
可使用 --dry-run 预览变更而不写入数据库。
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# 确保从项目 src 目录导入 comedy_agent
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from comedy_agent.core.config import settings
from comedy_agent.memory.medium_term import SQLMemoryStore
from comedy_agent.memory.models import EarningRecordData
from comedy_agent.memory.schema import EarningRecord, TipRecord

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_timestamps(values: list[str]) -> list[datetime]:
    """解析命令行传入的时间字符串，支持多种格式。"""
    parsed: list[datetime] = []
    for value in values:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S.%f",
        ):
            try:
                parsed.append(datetime.strptime(value, fmt))
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"无法解析时间: {value}")
    return parsed


def match_records(session, timestamps: list[datetime], window_seconds: int = 300):
    """根据创建时间或支付时间匹配打赏记录，默认前后 5 分钟窗口。"""
    from datetime import timedelta

    candidates: list[TipRecord] = []
    for ts in timestamps:
        start = ts - timedelta(seconds=window_seconds)
        end = ts + timedelta(seconds=window_seconds)
        for r in (
            session.query(TipRecord)
            .filter(
                ((TipRecord.created_at >= start) & (TipRecord.created_at <= end))
                | ((TipRecord.paid_at >= start) & (TipRecord.paid_at <= end))
            )
            .all()
        ):
            if r not in candidates:
                candidates.append(r)
    return candidates


def list_records(store: SQLMemoryStore) -> None:
    """列出所有打赏记录，方便用户核对时间。"""
    with store._new_session() as session:
        rows = session.query(TipRecord).order_by(TipRecord.created_at.desc()).all()
    logger.info("共有 %d 条打赏记录", len(rows))
    for r in rows:
        logger.info(
            "tip_id=%s created=%s paid=%s amount=%s fee=%s net=%s status=%s currency=%s",
            r.tip_id,
            r.created_at,
            r.paid_at,
            r.amount_cents,
            r.fee_cents,
            r.net_amount_cents,
            r.status,
            r.currency,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="缩放打赏记录金额")
    parser.add_argument("timestamps", nargs="*", help="打赏记录的创建/支付时间，如 '2026-08-22 10:30:06'")
    parser.add_argument("--scale", type=int, default=1000, help="被放大的倍数，默认 1000")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入数据库")
    parser.add_argument("--fix-amount", action="store_true", help="同时缩放 amount_cents（默认只缩放 fee 和 net）")
    parser.add_argument("--tip-id", nargs="+", help="直接指定 tip_id 进行修正")
    parser.add_argument("--window", type=int, default=300, help="时间匹配窗口（秒），默认 300")
    parser.add_argument("--list", action="store_true", dest="list_records", help="列出所有打赏记录后退出")
    args = parser.parse_args()

    store = SQLMemoryStore()

    if args.list_records:
        list_records(store)
        return 0

    with store._new_session() as session:
        if args.tip_id:
            records = session.query(TipRecord).filter(TipRecord.tip_id.in_(args.tip_id)).all()
        elif args.timestamps:
            timestamps = parse_timestamps(args.timestamps)
            records = match_records(session, timestamps, window_seconds=args.window)
        else:
            logger.error("请提供 timestamps 或 --tip-id，或使用 --list 查看记录")
            return 1

    if not records:
        logger.warning("未找到匹配的打赏记录")
        return 1

    logger.info("找到 %d 条待修正记录", len(records))

    for r in records:
        new_amount = r.amount_cents // args.scale if args.fix_amount else r.amount_cents
        new_fee = r.fee_cents // args.scale
        new_net = r.net_amount_cents // args.scale

        logger.info(
            "tip_id=%s: amount %s -> %s, fee %s -> %s, net %s -> %s",
            r.tip_id,
            r.amount_cents,
            new_amount,
            r.fee_cents,
            new_fee,
            r.net_amount_cents,
            new_net,
        )

        if args.dry_run:
            continue

        # 更新打赏记录
        store.update_tip_record_status(
            r.tip_id,
            status=r.status,
            amount_cents=new_amount if args.fix_amount else None,
            fee_cents=new_fee,
            net_amount_cents=new_net,
            metadata_json={
                "scale_fix": {
                    "scale": args.scale,
                    "fixed_at": datetime.utcnow().isoformat(),
                    "old_amount_cents": r.amount_cents,
                    "old_fee_cents": r.fee_cents,
                    "old_net_amount_cents": r.net_amount_cents,
                }
            },
        )

        # 同步修正对应的收益记录
        with store._new_session() as s:
            old_earnings = (
                s.query(EarningRecord)
                .filter(
                    EarningRecord.user_id == r.author_id,
                    EarningRecord.record_type == "tip_anyway",
                    EarningRecord.description.contains(r.tip_id),
                )
                .all()
            )
            for e in old_earnings:
                logger.info("  删除旧收益记录 %s (amount=%s)", e.record_id, e.amount)
                s.delete(e)
            s.commit()

        # 如果记录已支付，重新写入正确收益
        if r.status == "paid":
            store.save_earning(
                EarningRecordData(
                    user_id=r.author_id,
                    record_type="tip_anyway",
                    amount=new_net,
                    description=f"Anyway 打赏 {r.tip_id}",
                )
            )
            logger.info("  写入新收益记录: amount=%s", new_net)

    logger.info("完成%s", "（预览模式，未写入）" if args.dry_run else "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
