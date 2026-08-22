"""修正已有 Anyway 打赏记录的金额单位。

早期实现把 Anyway 返回的 amountCents 直接当“美分”处理，但 crypto 场景下
amountCents 实际为最小单位（如 USDC 是 6 位小数 = micro-units），导致金额
被放大 10000 倍。

本脚本根据当前 Anyway 订单实际金额，重新计算 amount_cents / fee_cents /
net_amount_cents / currency，并同步修正对应的作者收益记录。
"""

from __future__ import annotations

import asyncio
import logging
import sys

from comedy_agent.api.routers.anyway_webhook import _anyway_amount_to_cents
from comedy_agent.core.config import settings
from comedy_agent.memory.medium_term import SQLMemoryStore
from comedy_agent.memory.models import EarningRecordData
from comedy_agent.memory.schema import EarningRecord, TipRecord
from comedy_agent.services.anyway_client import AnywayClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    store = SQLMemoryStore()
    client = AnywayClient()

    with store._new_session() as session:
        records = session.query(TipRecord).filter(TipRecord.status == "paid").all()

    fixed = 0
    skipped = 0
    failed = 0

    for row in records:
        if not row.anyway_order_id:
            skipped += 1
            continue

        try:
            raw_order = await client.get_order(row.anyway_order_id)
            if raw_order is None:
                logger.warning("未找到 Anyway 订单: %s (tip_id=%s)", row.anyway_order_id, row.tip_id)
                failed += 1
                continue

            actual_amount_cents = _anyway_amount_to_cents(raw_order) or row.amount_cents
            fee_cents = int(actual_amount_cents * settings.anyway_fee_percent / 100)
            net_amount_cents = actual_amount_cents - fee_cents
            currency = (raw_order.get("currency") or row.currency or "usd").lower()

            if (
                row.amount_cents == actual_amount_cents
                and row.fee_cents == fee_cents
                and row.net_amount_cents == net_amount_cents
                and row.currency == currency
            ):
                skipped += 1
                continue

            logger.info(
                "修正 tip_id=%s: amount %s->%s, fee %s->%s, net %s->%s, currency %s->%s",
                row.tip_id,
                row.amount_cents,
                actual_amount_cents,
                row.fee_cents,
                fee_cents,
                row.net_amount_cents,
                net_amount_cents,
                row.currency,
                currency,
            )

            # 删除旧的 tip_anyway 收益记录（按描述匹配）
            with store._new_session() as s:
                old_earnings = (
                    s.query(EarningRecord)
                    .filter(
                        EarningRecord.user_id == row.author_id,
                        EarningRecord.record_type == "tip_anyway",
                        EarningRecord.description.contains(row.tip_id),
                    )
                    .all()
                )
                for e in old_earnings:
                    s.delete(e)
                s.commit()

            # 更新打赏记录
            store.update_tip_record_status(
                row.tip_id,
                status="paid",
                amount_cents=actual_amount_cents,
                currency=currency,
                fee_cents=fee_cents,
                net_amount_cents=net_amount_cents,
                metadata_json={
                    "migrated_at": "2026-08-22",
                    "actual_amount_cents": str(actual_amount_cents),
                    "anyway_amount_smallest": str(raw_order.get("amountCents") or ""),
                    "anyway_amount": str(raw_order.get("amount") or ""),
                },
            )

            # 重新写入正确收益
            store.save_earning(
                EarningRecordData(
                    user_id=row.author_id,
                    record_type="tip_anyway",
                    amount=net_amount_cents,
                    description=f"Anyway 打赏 {row.tip_id}",
                )
            )

            fixed += 1
        except Exception as e:
            logger.exception("处理 tip_id=%s 失败: %s", row.tip_id, e)
            failed += 1

    logger.info("完成: 修正 %d 条, 跳过 %d 条, 失败 %d 条", fixed, skipped, failed)


if __name__ == "__main__":
    asyncio.run(main())
