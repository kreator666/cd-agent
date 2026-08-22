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

_WALLET_BINDING_DOMAIN = {
    "name": "ComedyAgent",
    "version": "1",
    "chainId": 8453,  # Base 主网
    "verifyingContract": "0x0000000000000000000000000000000000000000",
}


def validate_ethereum_address(address: str) -> bool:
    """校验是否为合法的以太坊地址。"""
    return bool(re.fullmatch(r"0x[a-fA-F0-9]{40}", address))


def build_wallet_sign_message(address: str, content: str, nonce: str) -> dict[str, object]:
    """构造钱包绑定 EIP-712 签名消息。

    Args:
        address: 要绑定的钱包地址。
        content: 展示给用户的签名提示内容。
        nonce: 一次性随机串或用户 ID，用于防止签名重放。

    Returns:
        可直接交给钱包 signTypedData 的完整 EIP-712 消息结构。
    """
    return {
        "types": _WALLET_BINDING_TYPES,
        "domain": _WALLET_BINDING_DOMAIN,
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


def verify_wallet_signature(address: str, content: str, nonce: str, signature: str) -> bool:
    """验证 EIP-712 签名是否由指定地址产生。

    Args:
        address: 预期签名的地址。
        content: 签名消息中的 content 字段。
        nonce: 签名消息中的 nonce 字段。
        signature: 0x 开头的签名 hex。

    Returns:
        签名合法且签名者等于 address 时返回 True。
    """
    if not validate_ethereum_address(address):
        return False
    try:
        full_message = build_wallet_sign_message(address, content, nonce)
        signable = encode_typed_data(full_message=full_message)
        recovered = Account.recover_message(signable, signature=signature)
        return to_checksum_address(recovered) == to_checksum_address(address)
    except Exception:
        return False
