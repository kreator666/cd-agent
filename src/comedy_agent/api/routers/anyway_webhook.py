"""Anyway 支付 Webhook 路由。"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.models import EarningRecordData
from comedy_agent.services.anyway_client import AnywayClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["anyway"])

_VERIFICATION_KEYS: list[Ed25519PublicKey] = []


def _decode_base64url(value: str) -> bytes:
    """Base64url 解码。"""
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _load_signing_keys() -> list[Ed25519PublicKey]:
    """加载 Anyway webhook 签名公钥。"""
    global _VERIFICATION_KEYS
    if _VERIFICATION_KEYS:
        return _VERIFICATION_KEYS

    signing_key_value = settings.anyway_webhook_signing_key
    if signing_key_value:
        try:
            key_bytes = _decode_base64url(signing_key_value)
            _VERIFICATION_KEYS = [Ed25519PublicKey.from_public_bytes(key_bytes)]
            return _VERIFICATION_KEYS
        except Exception:
            logger.warning("配置的 ANYWAY_WEBHOOK_SIGNING_KEY 无效，尝试从远程获取")

    try:
        import httpx
        resp = httpx.get("https://api.anyway.sh/v1/webhooks/signing-key", timeout=10.0)
        resp.raise_for_status()
        jwks = resp.json()
        keys = [
            Ed25519PublicKey.from_public_bytes(_decode_base64url(jwk["x"]))
            for jwk in jwks.get("keys", [])
            if jwk.get("crv") == "Ed25519"
        ]
        _VERIFICATION_KEYS = keys
        return keys
    except Exception as e:
        logger.error("加载 Anyway webhook 签名公钥失败: %s", e)
        return []


def _verify_webhook(raw_body: bytes, headers: dict[str, Any]) -> dict[str, Any]:
    """验证 Anyway webhook 签名。"""
    webhook_id = headers.get("webhook-id")
    timestamp = headers.get("webhook-timestamp")
    signature_header = headers.get("webhook-signature")
    if not webhook_id or not timestamp or not signature_header:
        raise ValueError("Missing webhook headers")

    timestamp_seconds = int(timestamp)
    if abs(int(time.time()) - timestamp_seconds) > 300:
        raise ValueError("Stale webhook timestamp")

    signed_content = f"{webhook_id}.{timestamp}.".encode() + raw_body
    keys = _load_signing_keys()
    if not keys:
        raise ValueError("No verification keys available")

    for versioned_signature in signature_header.split():
        try:
            version, encoded_signature = versioned_signature.split(",", 1)
            if version != "v1a":
                continue
            signature = base64.b64decode(encoded_signature, validate=True)
            for key in keys:
                try:
                    key.verify(signature, signed_content)
                    return json.loads(raw_body)
                except InvalidSignature:
                    pass
        except (ValueError, TypeError):
            continue
    raise InvalidSignature("Invalid webhook signature")


@router.post(settings.anyway_webhook_path)
async def anyway_webhook(request: Request) -> str:
    """接收 Anyway webhook 事件。"""
    raw_body = await request.body()
    try:
        event = _verify_webhook(raw_body, dict(request.headers))
    except (ValueError, InvalidSignature) as e:
        logger.warning("Anyway webhook 验签失败: %s", e)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_type = event.get("type")
    data = event.get("data", {})
    webhook_id = request.headers.get("webhook-id")

    if event_type == "order.paid":
        await _handle_order_paid(data.get("order", {}), webhook_id)
    elif event_type == "order.failed":
        await _handle_order_failed(data.get("order", {}), webhook_id)
    else:
        logger.info("忽略 Anyway webhook 事件: %s", event_type)

    return ""


def _find_tip_record(order: dict[str, Any]) -> Any | None:
    """根据 order 查找本地 tip_record。"""
    if state.memory is None:
        return None

    merchant_reference = order.get("merchantReference")
    if not merchant_reference:
        return None
    return state.memory.get_tip_record_by_merchant_reference(merchant_reference)


async def _handle_order_paid(order: dict[str, Any], webhook_id: str | None) -> None:
    """处理 order.paid 事件。"""
    if state.memory is None:
        return

    record = _find_tip_record(order)
    if record is None:
        logger.warning("未找到与 order 关联的 tip_record: %s", order.get("merchantReference"))
        return

    # 幂等：已处理则跳过
    if record.status == "paid":
        logger.info("tip_record %s 已处理，跳过", record.tip_id)
        return

    order_id = order.get("orderId")
    amount_cents = order.get("amountCents") or record.amount_cents
    fee_cents = int(amount_cents * settings.anyway_fee_percent / 100)
    net_amount_cents = amount_cents - fee_cents

    metadata = dict(record.metadata_json or {})
    metadata["anyway_order_id"] = order_id
    metadata["webhook_id"] = webhook_id
    metadata["actual_amount_cents"] = str(amount_cents)

    state.memory.update_tip_record_status(
        record.tip_id,
        status="paid",
        anyway_order_id=order_id,
        fee_cents=fee_cents,
        net_amount_cents=net_amount_cents,
        metadata_json=metadata,
    )

    state.memory.save_earning(
        EarningRecordData(
            user_id=record.author_id,
            record_type="tip_anyway",
            amount=net_amount_cents,
            description=f"Anyway 打赏 {record.tip_id}",
        )
    )
    logger.info("记录 Anyway 打赏收益: tip_id=%s amount=%s", record.tip_id, net_amount_cents)


async def _handle_order_failed(order: dict[str, Any], webhook_id: str | None) -> None:
    """处理 order.failed 事件。"""
    record = _find_tip_record(order)
    if record is None:
        return

    metadata = dict(record.metadata_json or {})
    metadata["webhook_id"] = webhook_id
    state.memory.update_tip_record_status(
        record.tip_id,
        status="failed",
        metadata_json=metadata,
    )
    logger.info("标记 Anyway 打赏失败: tip_id=%s", record.tip_id)


@router.post("/tips/sync/{tip_id}")
async def sync_tip_status(
    tip_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """手动同步一条 tip_record 的支付状态（作为 webhook 未送达的后备）。"""
    if state.memory is None:
        raise HTTPException(status_code=503, detail="记忆系统未就绪")

    record = state.memory.get_tip_record(tip_id)
    if record is None:
        raise HTTPException(status_code=404, detail="打赏记录不存在")
    if record.author_id != user_id:
        raise HTTPException(status_code=403, detail="无权查看")

    if record.status == "paid":
        return {"tip_id": tip_id, "status": "paid", "already_paid": True}

    client = AnywayClient()
    orders = await client.list_orders(merchant_reference=record.merchant_reference)
    for order in orders:
        if order.get("status") == "PAID":
            await _handle_order_paid(order, None)
            return {"tip_id": tip_id, "status": "paid"}

    return {"tip_id": tip_id, "status": record.status}
