"""加密货币钱包工具。

提供以太坊地址校验、EIP-712 签名验证、签名消息构建等通用函数。
"""

from __future__ import annotations

import re

from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import to_checksum_address


_WALLET_BINDING_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "WalletBinding": [
        {"name": "address", "type": "address"},
        {"name": "content", "type": "string"},
        {"name": "nonce", "type": "string"},
    ],
}

_CHAIN_ID_MAP = {
    "base": 8453,        # Base 主网
    "ethereum": 1,       # 以太坊主网
}


_WALLET_BINDING_DOMAIN_TEMPLATE = {
    "name": "ComedyAgent",
    "version": "1",
    "chainId": 8453,  # 默认 Base 主网，build_wallet_sign_message 会按 chain 覆盖
    "verifyingContract": "0x0000000000000000000000000000000000000000",
}


def validate_ethereum_address(address: str) -> bool:
    """校验是否为合法的以太坊地址。"""
    return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", address))


def build_wallet_sign_message(
    address: str, content: str, nonce: str, chain: str = "base"
) -> dict[str, object]:
    """构造钱包绑定 EIP-712 签名消息。

    Args:
        address: 要绑定的钱包地址。
        content: 展示给用户的签名提示内容。
        nonce: 一次性随机串或用户 ID，用于防止签名重放。
        chain: 链标识：base / ethereum。

    Returns:
        可直接交给钱包 signTypedData 的完整 EIP-712 消息结构。
    """
    chain_id = _CHAIN_ID_MAP.get(chain.lower(), _CHAIN_ID_MAP["base"])
    domain = {**_WALLET_BINDING_DOMAIN_TEMPLATE, "chainId": chain_id}
    return {
        "types": _WALLET_BINDING_TYPES,
        "domain": domain,
        "primaryType": "WalletBinding",
        "message": {
            "address": to_checksum_address(address),
            "content": content,
            "nonce": nonce,
        },
    }


def get_wallet_sign_content(address: str) -> str:
    """获取展示给用户的签名提示内容。"""
    return (
        f"我确认将地址 {address} 绑定为 Comedy Agent 的加密货币打赏地址，"
        "用于接收和支付打赏。"
    )


def verify_wallet_signature(
    address: str, content: str, nonce: str, signature: str, chain: str = "base"
) -> bool:
    """验证 EIP-712 签名是否由指定地址产生。

    Args:
        address: 预期签名的地址。
        content: 签名消息中的 content 字段。
        nonce: 签名消息中的 nonce 字段。
        signature: 0x 开头的签名 hex。
        chain: 链标识：base / ethereum。

    Returns:
        签名合法且签名者等于 address 时返回 True。
    """
    if not validate_ethereum_address(address):
        return False
    try:
        full_message = build_wallet_sign_message(address, content, nonce, chain=chain)
        signable = encode_typed_data(full_message=full_message)
        recovered = Account.recover_message(signable, signature=signature)
        return to_checksum_address(recovered) == to_checksum_address(address)
    except Exception:
        return False
