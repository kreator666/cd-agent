"""加密货币打赏功能测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state
from comedy_agent.auth.security import create_access_token
from comedy_agent.core.config import settings


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "anyway_payment_link_url", "https://pay.anyway.sh/")

    # 跳过 HuggingFace embedding 模型加载，避免测试挂起
    with patch("comedy_agent.api.server.VectorStore") as mock_vs_cls, patch(
        "comedy_agent.api.server.ComedyRetriever"
    ), patch(
        "comedy_agent.memory.medium_term.create_engine", side_effect=_patched_create_engine
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls:
        mock_vs_cls.return_value = MagicMock()
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "mocked", "messages": []}
        mock_orch.tools = []
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        from comedy_agent.memory.schema import EvalResult, EvalSession

        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        store.get_or_create_user("test_user", "测试读者")
        store.get_or_create_user("author_user", "测试作者")
        store.get_or_create_user("admin", "管理员")
        store.get_token_account("test_user")

        db_session = store.Session()
        eval_session = EvalSession(
            session_id="sess_002",
            user_id="author_user",
            skill_name="standup",
            model="kimi2.6",
            topic="职场内卷",
            attitude="拒绝内耗",
            bias="加班=敬业",
            emotion="憋屈",
            status="done",
        )
        eval_result = EvalResult(
            result_id="res_002",
            session_id="sess_002",
            section_id="sec_002",
            section_title="测试段子",
            section_body="测试内容",
            model="kimi2.6",
            is_published=True,
            published_at=datetime.now(timezone.utc),
            status="done",
        )
        db_session.add(eval_session)
        db_session.add(eval_result)
        db_session.commit()
        db_session.close()

        user_token = create_access_token("test_user")
        admin_token = create_access_token("admin")

        with TestClient(app, headers={"Authorization": f"Bearer {user_token}"}) as c:
            state.memory = store
            state.orch = mock_orch
            c.admin_headers = {"Authorization": f"Bearer {admin_token}"}
            yield c

        state.memory = None
        state.orch = None


def _headers(user_id: str):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


class TestWalletBinding:
    """钱包绑定测试。"""

    def test_bind_wallet_requires_signature(self, client):
        """直接设置地址而不提交签名应失败。"""
        # 这里测的是接口层校验：未提交签名为空会失败
        resp = client.post(
            "/me/wallet-address",
            json={"address": "0x" + "11" * 20, "signature": "0x", "chain": "base"},
        )
        assert resp.status_code == 400
        assert "签名验证失败" in resp.json()["detail"]

    def test_bind_wallet_with_valid_signature(self, client):
        """提交合法 EIP-712 签名可成功绑定。"""
        from comedy_agent.services.crypto_wallet import (
            build_wallet_sign_message,
            get_wallet_sign_content,
        )

        account = Account.create()
        address = account.address
        content = get_wallet_sign_content(address)
        nonce = "nonce123"
        typed_data = build_wallet_sign_message(address, content, nonce)

        from eth_account.messages import encode_typed_data

        signable = encode_typed_data(full_message=typed_data)
        signature = account.sign_message(signable).signature.hex()

        resp = client.post(
            "/me/wallet-address",
            json={"address": address, "signature": signature, "nonce": nonce, "chain": "base"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["wallet_address"].lower() == address.lower()
        assert data["wallet_chain"] == "base"

    def test_bind_wallet_wrong_signature(self, client):
        """错误签名无法绑定。"""
        resp = client.post(
            "/me/wallet-address",
            json={
                "address": "0x" + "11" * 20,
                "signature": "0x" + "00" * 65,
                "nonce": "nonce",
                "chain": "base",
            },
        )
        assert resp.status_code == 400

    def test_get_wallet_address(self, client):
        """绑定后可查询钱包地址。"""
        state.memory.update_user_profile(
            "test_user",
            wallet_address="0x" + "22" * 20,
            wallet_chain="base",
            wallet_signed_at=datetime.now(timezone.utc),
        )
        resp = client.get("/me/wallet-address")
        assert resp.status_code == 200
        assert resp.json()["wallet_address"].lower() == "0x" + "22" * 20


class TestCryptoTipIntent:
    """Crypto 打赏意图测试。"""

    def test_create_intent_both_wallets_bound(self, client):
        """双方都已绑定钱包时可创建意图。"""
        state.memory.update_user_profile("test_user", wallet_address="0x" + "aa" * 20)
        state.memory.update_user_profile("author_user", wallet_address="0x" + "bb" * 20)

        resp = client.post(
            "/tips/crypto/intent",
            json={"result_id": "res_002", "amount_cents": 1000000, "currency": "USDC"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["order_id"].startswith("cto_")
        assert data["payment_url"].startswith("https://pay.anyway.sh/")
        assert "author_wallet" in data["payment_url"]

    def test_create_intent_author_no_wallet(self, client):
        """作者未绑定钱包时报错。"""
        state.memory.update_user_profile("test_user", wallet_address="0x" + "aa" * 20)

        resp = client.post(
            "/tips/crypto/intent",
            json={"result_id": "res_002", "amount_cents": 1000000, "currency": "USDC"},
        )
        assert resp.status_code == 400
        assert "作者未绑定" in resp.json()["detail"]

    def test_create_intent_self_not_allowed(self, client):
        """不能给自己打赏。"""
        # 用作者 token 访问
        resp = client.post(
            "/tips/crypto/intent",
            json={"result_id": "res_002", "amount_cents": 1000000, "currency": "USDC"},
            headers=_headers("author_user"),
        )
        assert resp.status_code == 400
        assert "不能给自己打赏" in resp.json()["detail"]


class TestCryptoTipConfirm:
    """链上确认入账测试。"""

    def test_confirm_success(self, client, monkeypatch):
        """提交交易 hash 并通过链上校验后入账。"""
        from comedy_agent.services import crypto_chain

        monkeypatch.setattr(
            crypto_chain,
            "verify_tip_payment",
            lambda **kwargs: {
                "success": True,
                "from": "0x" + "aa" * 20,
                "to": "0x" + "bb" * 20,
                "amount": 1000000,
                "confirmations": 15,
            },
        )

        state.memory.update_user_profile("test_user", wallet_address="0x" + "aa" * 20)
        state.memory.update_user_profile("author_user", wallet_address="0x" + "bb" * 20)

        resp = client.post(
            "/tips/crypto/intent",
            json={"result_id": "res_002", "amount_cents": 1000000, "currency": "USDC"},
        )
        order_id = resp.json()["order_id"]

        resp = client.post(
            "/tips/crypto/confirm",
            json={"order_id": order_id, "tx_hash": "0x" + "cc" * 32},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "paid"

        # 统计应更新
        resp = client.get("/tips/crypto/stats")
        stats = resp.json()
        assert stats["total_tipped_cents"] == 1000000

        resp = client.get("/tips/crypto/stats", headers=_headers("author_user"))
        stats = resp.json()
        assert stats["total_received_cents"] == 1000000

    def test_confirm_wrong_amount(self, client, monkeypatch):
        """链上金额不足时失败。"""
        from comedy_agent.services import crypto_chain

        monkeypatch.setattr(
            crypto_chain,
            "verify_tip_payment",
            lambda **kwargs: {"success": False, "error": "链上金额不足"},
        )

        state.memory.update_user_profile("test_user", wallet_address="0x" + "aa" * 20)
        state.memory.update_user_profile("author_user", wallet_address="0x" + "bb" * 20)

        resp = client.post(
            "/tips/crypto/intent",
            json={"result_id": "res_002", "amount_cents": 1000000, "currency": "USDC"},
        )
        order_id = resp.json()["order_id"]

        resp = client.post(
            "/tips/crypto/confirm",
            json={"order_id": order_id, "tx_hash": "0x" + "cc" * 32},
        )
        assert resp.status_code == 400
        assert "链上金额不足" in resp.json()["detail"]


class TestCryptoAdmin:
    """管理后台 Crypto 订单审核测试。"""

    def test_admin_list_and_verify(self, client, monkeypatch):
        """管理员可列出订单并手动触发链上校验。"""
        from comedy_agent.services import crypto_chain

        monkeypatch.setattr(
            crypto_chain,
            "verify_tip_payment",
            lambda **kwargs: {
                "success": True,
                "from": "0x" + "aa" * 20,
                "to": "0x" + "bb" * 20,
                "amount": 2000000,
                "confirmations": 15,
            },
        )

        state.memory.update_user_profile("test_user", wallet_address="0x" + "aa" * 20)
        state.memory.update_user_profile("author_user", wallet_address="0x" + "bb" * 20)

        resp = client.post(
            "/tips/crypto/intent",
            json={"result_id": "res_002", "amount_cents": 2000000, "currency": "USDC"},
        )
        order_id = resp.json()["order_id"]

        resp = client.get("/admin/crypto-tip-orders", headers=client.admin_headers)
        assert resp.status_code == 200
        orders = resp.json()["orders"]
        assert any(o["order_id"] == order_id for o in orders)

        resp = client.post(
            f"/admin/crypto-tip-orders/{order_id}/verify?tx_hash=0x{'dd' * 32}",
            headers=client.admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paid"
