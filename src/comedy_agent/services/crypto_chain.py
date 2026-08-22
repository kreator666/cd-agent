"""Base 链上加密货币打赏校验服务。

支持原生 ETH 与 ERC-20（如 USDC）转账的链上校验。
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from web3 import Web3
from web3.exceptions import Web3Exception

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

# ERC-20 Transfer(address indexed from, address indexed to, uint256 value)
_TRANSFER_EVENT_SIGNATURE = Web3.keccak(text="Transfer(address,address,uint256)").hex()


@lru_cache(maxsize=1)
def get_web3() -> Web3:
    """获取 Base 链 Web3 连接（延迟初始化）。"""
    w3 = Web3(Web3.HTTPProvider(settings.base_rpc_url))
    if not w3.is_connected():
        logger.warning("Base RPC 连接失败: %s", settings.base_rpc_url)
    return w3


def _erc20_transfer_event_topics(author_wallet: str) -> list[Any]:
    """构造 ERC-20 Transfer 事件的 topic0 + topic2（to = author）。"""
    w3 = get_web3()
    return [
        _TRANSFER_EVENT_SIGNATURE,
        None,
        Web3.to_bytes(hexstr=w3.to_checksum_address(author_wallet)),
    ]


def verify_tip_payment(
    tx_hash: str,
    expected_author_wallet: str,
    expected_payer_wallet: str | None,
    expected_amount: int,
    currency: str = "USDC",
    min_confirmations: int | None = None,
) -> dict[str, Any]:
    """校验一笔链上交易是否符合打赏要求。

    Args:
        tx_hash: Base 链上交易 hash。
        expected_author_wallet: 预期收款地址。
        expected_payer_wallet: 预期付款地址（可选）。
        expected_amount: 预期最小金额（最小货币单位）。
        currency: 币种；USDC 按 ERC-20 解析，ETH/BASE 按原生转账解析。
        min_confirmations: 最小确认数，默认取配置。

    Returns:
        dict: 包含 success、from、to、amount、confirmations、error。
    """
    if min_confirmations is None:
        min_confirmations = settings.tip_chain_confirmations

    result: dict[str, Any] = {
        "success": False,
        "from": None,
        "to": None,
        "amount": 0,
        "confirmations": 0,
        "error": None,
        "currency": currency,
    }

    try:
        w3 = get_web3()
        if not w3.is_connected():
            result["error"] = "无法连接 Base RPC"
            return result

        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt is None:
            result["error"] = "交易未上链"
            return result
        if receipt.status != 1:  # type: ignore[attr-defined]
            result["error"] = "交易执行失败"
            return result

        current_block = w3.eth.block_number
        confirmations = current_block - receipt.blockNumber
        if confirmations < min_confirmations:
            result["error"] = f"确认数不足: {confirmations} < {min_confirmations}"
            return result
        result["confirmations"] = confirmations

        is_native = currency.upper() in {"ETH", "BASE", "BASE_ETH"}

        if is_native:
            tx = w3.eth.get_transaction(tx_hash)
            to = tx.get("to")
            value = int(tx.get("value", 0))
            sender = tx.get("from")
            if to is None or value <= 0:
                result["error"] = "不是有效的原生币转账"
                return result
            result["to"] = w3.to_checksum_address(to)
            result["from"] = w3.to_checksum_address(sender) if sender else None
            result["amount"] = value
        else:
            # ERC-20：查找收款地址的 Transfer 事件
            token_contract = w3.to_checksum_address(settings.tip_token_contract)
            logs = receipt.logs
            matched = None
            for log in logs:
                if log.address.lower() != token_contract.lower():
                    continue
                if len(log.topics) < 3:
                    continue
                if log.topics[0].hex() != _TRANSFER_EVENT_SIGNATURE:
                    continue
                to_addr = w3.to_checksum_address(log.topics[2][-20:].hex())
                if to_addr.lower() != expected_author_wallet.lower():
                    continue
                value = int(log.data.hex(), 16) if isinstance(log.data, bytes) else int.from_bytes(log.data, "big")
                from_addr = w3.to_checksum_address(log.topics[1][-20:].hex())
                matched = {"from": from_addr, "to": to_addr, "amount": value}
                break

            if matched is None:
                result["error"] = "未找到给收款地址的 ERC-20 转账记录"
                return result
            result["from"] = matched["from"]
            result["to"] = matched["to"]
            result["amount"] = matched["amount"]

        # 校验收款地址
        if result["to"].lower() != expected_author_wallet.lower():
            result["error"] = "链上收款地址与预期不符"
            return result

        # 校验付款地址（若提供）
        if expected_payer_wallet and result["from"].lower() != expected_payer_wallet.lower():
            result["error"] = "链上付款地址与预期不符"
            return result

        # 校验金额
        if result["amount"] < expected_amount:
            result["error"] = f"链上金额不足: {result['amount']} < {expected_amount}"
            return result

        result["success"] = True
        return result

    except Web3Exception as e:
        result["error"] = f"链上查询失败: {e}"
        return result
    except Exception as e:
        logger.exception("链上校验异常")
        result["error"] = f"链上校验异常: {e}"
        return result
