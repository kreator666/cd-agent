"""重新计算所有 Anyway 打赏记录的手续费与净得。

用法：
    python scripts/recalc_tip_fees.py

说明：
- 根据当前 .env 中的 ANYWAY_FEE_PERCENT 重新计算 tip_records 的 fee_cents / net_amount_cents。
- 对已 paid 的订单，同步更新对应的 earning_records（record_type='tip_anyway'、描述含 tip_id）。
"""

from __future__ import annotations

from comedy_agent.core.config import settings
from comedy_agent.memory.medium_term import SQLMemoryStore
from comedy_agent.memory.schema import EarningRecord, TipRecord


def main() -> None:
    store = SQLMemoryStore()
    session = store.Session()

    fee_percent = settings.anyway_fee_percent
    print(f"当前手续费比例: {fee_percent}%")

    records = session.query(TipRecord).all()
    updated = 0
    for record in records:
        new_fee = int(record.amount_cents * fee_percent / 100)
        new_net = record.amount_cents - new_fee

        if record.fee_cents == new_fee and record.net_amount_cents == new_net:
            continue

        old_fee = record.fee_cents
        old_net = record.net_amount_cents
        record.fee_cents = new_fee
        record.net_amount_cents = new_net
        updated += 1

        print(
            f"更新 tip_id={record.tip_id}: amount={record.amount_cents} 美分, "
            f"fee {old_fee} -> {new_fee}, net {old_net} -> {new_net}"
        )

        if record.status == "paid":
            earning = (
                session.query(EarningRecord)
                .filter_by(record_type="tip_anyway", user_id=record.author_id)
                .filter(EarningRecord.description.like(f"%Anyway 打赏 {record.tip_id}%"))
                .first()
            )
            if earning is not None:
                earning.amount = new_net
                print(f"  同步收益记录: {old_net} -> {new_net} 美分")
            else:
                print(f"  未找到收益记录，跳过同步")

    session.commit()
    session.close()
    print(f"共更新 {updated} 条打赏记录")


if __name__ == "__main__":
    main()
