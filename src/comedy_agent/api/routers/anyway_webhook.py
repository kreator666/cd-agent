"""Anyway 支付 Webhook 路由。"""

from __future__ import annotations

import base64
import json
import logging
import math
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import APIRouter, Depends, HTTPException, Request

from comedy_agent.api.state import state
from comedy_agent.auth.dependencies import get_current_user
from comedy_agent.core.config import settings
from comedy_agent.memory.models import CryptoTipOrderData, EarningRecordData
from comedy_agent.services.anyway_client import AnywayClient
from comedy_agent.services.crypto_chain import verify_tip_payment

from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(tags=["anyway"])

_VERIFICATION_KEYS: list[Ed25519PublicKey] = []

# Anyway Merchant API 与 webhook 事件字段命名可能不同，统一映射为 webhook  handler 使用的 camelCase
_ANYWAY_ORDER_KEY_MAPPING = {
    "merchant_reference": "merchantReference",
    "order_id": "orderId",
    "id": "orderId",
    "amount_cents": "amountCents",
    "transaction_hash": "transactionHash",
    "tx_hash": "transactionHash",
}


def normalize_anyway_order(order: dict[str, Any]) -> dict[str, Any]:
    """将 Anyway 订单详情统一转换为 webhook handler 内部使用的 camelCase 字段。"""
    normalized: dict[str, Any] = dict(order)
    for source_key, target_key in _ANYWAY_ORDER_KEY_MAPPING.items():
        if source_key in normalized and target_key not in normalized:
            normalized[target_key] = normalized.pop(source_key)
    return normalized


# 常见币种精度：Anyway 的 amountCents 字段实际为最小单位，需换算为美分
_ANYWAY_CURRENCY_DECIMALS: dict[str, int] = {
    "USD": 2,
    "USDC": 6,
    "USDT": 6,
}


def _anyway_amount_to_cents(order: dict[str, Any]) -> int | None:
    """将 Anyway 订单金额统一换算为美分。

    Anyway 的 `amountCents` 在不同币种下代表最小单位：
    - 法币 USD：amountCents 就是美分（2 位小数）
    - 稳定币 USDC/USDT：amountCents 为 micro-units（6 位小数）
    本函数根据币种精度或 amount/amountCents 推导精度，返回美分整数。
    """
    amount_raw = order.get("amount")
    amount_smallest = order.get("amountCents")
    if amount_smallest is None or amount_raw is None:
        return None

    currency = (order.get("currency") or "").upper()
    decimals = _ANYWAY_CURRENCY_DECIMALS.get(currency)
    if decimals is None:
        try:
            # 通过 amountCents / amount 推导精度
            decimals = round(math.log10(amount_smallest / amount_raw))
        except (ValueError, ZeroDivisionError, TypeError):
            decimals = 2

    # 最小单位 -> 美分：除以 10^(decimals - 2)
    factor = 10 ** (decimals - 2)
    return int(amount_smallest / factor)


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


def _find_anyway_record(order: dict[str, Any]) -> tuple[str, Any | None]:
    """根据 order 查找本地记录。

    Returns:
        (record_type, record): record_type 为 "tip" 或 "crypto"；未找到返回 (None, None)。
    """
    if state.memory is None:
        return None, None

    merchant_reference = order.get("merchantReference")
    if not merchant_reference:
        return None, None

    if merchant_reference.startswith("cto_"):
        record = state.memory.get_crypto_tip_order_by_merchant_reference(merchant_reference)
        if record is not None:
            return "crypto", record

    record = state.memory.get_tip_record_by_merchant_reference(merchant_reference)
    if record is not None:
        return "tip", record

    return None, None


async def _handle_order_paid(order: dict[str, Any], webhook_id: str | None) -> None:
    """处理 order.paid 事件。"""
    if state.memory is None:
        return

    record_type, record = _find_anyway_record(order)
    if record is None:
        logger.warning("未找到与 order 关联的本地记录: %s", order.get("merchantReference"))
        return

    order_id = order.get("orderId")

    if record_type == "crypto":
        await _handle_crypto_order_paid(record, order, webhook_id)
        return

    # 幂等：已处理则跳过
    if record.status == "paid":
        logger.info("tip_record %s 已处理，跳过", record.tip_id)
        return

    # Anyway 的 amountCents 在不同币种下精度不同，统一换算为美分
    actual_amount_cents = _anyway_amount_to_cents(order) or record.amount_cents
    fee_cents = int(actual_amount_cents * settings.anyway_fee_percent / 100)
    net_amount_cents = actual_amount_cents - fee_cents
    actual_currency = (order.get("currency") or record.currency or "usd").lower()

    metadata = dict(record.metadata_json or {})
    metadata["anyway_order_id"] = order_id
    metadata["webhook_id"] = webhook_id
    metadata["actual_amount_cents"] = str(actual_amount_cents)
    metadata["anyway_amount_smallest"] = str(order.get("amountCents") or "")
    metadata["anyway_amount"] = str(order.get("amount") or "")

    state.memory.update_tip_record_status(
        record.tip_id,
        status="paid",
        anyway_order_id=order_id,
        amount_cents=actual_amount_cents,
        currency=actual_currency,
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
    logger.info("记录 Anyway 打赏收益: tip_id=%s amount=%s fee=%s net=%s", record.tip_id, actual_amount_cents, fee_cents, net_amount_cents)


async def _handle_crypto_order_paid(
    record: CryptoTipOrderData, order: dict[str, Any], webhook_id: str | None
) -> None:
    """处理加密货币打赏 order.paid 事件。"""
    if record.status == "paid":
        logger.info("crypto_tip_order %s 已处理，跳过", record.order_id)
        return

    tx_hash = order.get("transactionHash") or order.get("txHash")
    metadata = dict(record.metadata_json or {})
    metadata["anyway_order_id"] = order.get("orderId")
    metadata["webhook_id"] = webhook_id
    metadata["anyway_order"] = order

    if not tx_hash:
        # Anyway 未返回交易 hash，等待用户手动提交交易 hash
        state.memory.update_crypto_tip_order(
            record.order_id,
            anyway_order_id=order.get("orderId"),
            metadata_json=metadata,
        )
        logger.info("crypto_tip_order %s 待手动提交交易 hash", record.order_id)
        return

    verification = verify_tip_payment(
        tx_hash=tx_hash,
        expected_author_wallet=record.author_wallet,
        expected_payer_wallet=record.payer_wallet,
        expected_amount=record.amount_cents,
        currency=record.currency,
    )
    if verification["success"]:
        state.memory.update_crypto_tip_order(
            record.order_id,
            anyway_order_id=order.get("orderId"),
            tx_hash=tx_hash,
            status="paid",
            verified_at=datetime.now(timezone.utc),
            paid_at=datetime.now(timezone.utc),
            metadata_json={**metadata, "chain_verification": verification},
        )
        logger.info("crypto_tip_order %s 链上校验通过并入账", record.order_id)
    else:
        state.memory.update_crypto_tip_order(
            record.order_id,
            anyway_order_id=order.get("orderId"),
            tx_hash=tx_hash,
            metadata_json={**metadata, "chain_verification": verification},
        )
        logger.warning("crypto_tip_order %s 链上校验失败: %s", record.order_id, verification.get("error"))


async def _handle_order_failed(order: dict[str, Any], webhook_id: str | None) -> None:
    """处理 order.failed 事件。"""
    if state.memory is None:
        return

    record_type, record = _find_anyway_record(order)
    if record is None:
        return

    metadata = dict(record.metadata_json or {})
    metadata["webhook_id"] = webhook_id

    if record_type == "crypto":
        state.memory.update_crypto_tip_order(
            record.order_id,
            status="failed",
            metadata_json=metadata,
        )
        logger.info("标记 Crypto 打赏失败: order_id=%s", record.order_id)
        return

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
        normalized = normalize_anyway_order(order)
        if normalized.get("status", "").upper() == "PAID":
            await _handle_order_paid(normalized, None)
            return {"tip_id": tip_id, "status": "paid"}

    return {"tip_id": tip_id, "status": record.status}
