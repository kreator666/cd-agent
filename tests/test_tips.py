"""Anyway 打赏与提现功能测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
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

    with patch(
        "comedy_agent.memory.medium_term.create_engine", side_effect=_patched_create_engine
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "mocked", "messages": []}
        mock_orch.tools = []
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        from comedy_agent.memory.schema import EvalResult, EvalSession

        store = SQLMemoryStore(db_url="sqlite:///:memory:")
        store.get_or_create_user("test_user", "测试用户")
        store.get_or_create_user("author_user", "作者")
        store.get_or_create_user("admin", "管理员")
        store.get_token_account("test_user")

        # 构造一条已发布的广场段子
        db_session = store.Session()
        eval_session = EvalSession(
            session_id="sess_001",
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
            result_id="res_001",
            session_id="sess_001",
            section_id="sec_001",
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


class TestTipsIntent:
    """打赏意图创建测试。"""

    def test_create_tip_intent(self, client):
        """创建打赏意图应返回 payment_url。"""
        resp = client.post(
            "/tips/intent",
            json={"result_id": "res_001", "amount_cents": 500, "currency": "usd"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["tip_id"].startswith("tip_")
        assert "merchant_reference" in data["payment_url"]
        assert "res_001" in data["payment_url"]

    def test_create_tip_intent_self_not_allowed(self, client):
        """不能给自己打赏。"""
        resp = client.post(
            "/tips/intent",
            json={"result_id": "res_001", "amount_cents": 500, "currency": "usd"},
            headers=_headers("author_user"),
        )
        assert resp.status_code == 400
        assert "不能给自己打赏" in resp.json()["detail"]

    def test_create_tip_intent_result_not_found(self, client):
        """不存在的段子返回 404。"""
        resp = client.post(
            "/tips/intent",
            json={"result_id": "res_missing", "amount_cents": 500, "currency": "usd"},
        )
        assert resp.status_code == 404

    def test_create_tip_intent_amount_too_small(self, client):
        """低于最小金额报错。"""
        resp = client.post(
            "/tips/intent",
            json={"result_id": "res_001", "amount_cents": 1, "currency": "usd"},
        )
        assert resp.status_code == 400


class TestTipsWebhook:
    """Webhook 记账测试。"""

    def test_webhook_order_paid_records_earning(self, client, monkeypatch):
        """order.paid webhook 到账后，作者可看到收益。"""
        resp = client.post(
            "/tips/intent",
            json={"result_id": "res_001", "amount_cents": 1000, "currency": "usd"},
        )
        tip_id = resp.json()["tip_id"]

        # 绕过 Ed25519 验签
        from comedy_agent.api.routers import anyway_webhook

        def fake_verify(raw_body, headers):
            record = state.memory.get_tip_record(tip_id)
            return {
                "type": "order.paid",
                "data": {
                    "order": {
                        "merchantReference": record.merchant_reference,
                        "orderId": "order_123",
                        "amountCents": 1000,
                    }
                },
            }

        monkeypatch.setattr(anyway_webhook, "_verify_webhook", fake_verify)

        webhook_resp = client.post(
            "/webhooks/anyway",
            json={},
            headers={"webhook-id": "wh_1", "webhook-timestamp": "1234567890", "webhook-signature": "v1a,aaa"},
        )
        assert webhook_resp.status_code == 200

        resp = client.get("/tips/earnings", headers=_headers("author_user"))
        assert resp.status_code == 200
        data = resp.json()
        # 默认 5% 手续费，作者净得 950 美分
        assert data["total_cents"] == 950
        assert data["pending_cents"] == 950

    def test_webhook_order_failed(self, client, monkeypatch):
        """order.failed 标记打赏失败。"""
        resp = client.post(
            "/tips/intent",
            json={"result_id": "res_001", "amount_cents": 1000, "currency": "usd"},
        )
        tip_id = resp.json()["tip_id"]

        from comedy_agent.api.routers import anyway_webhook

        def fake_verify(raw_body, headers):
            record = state.memory.get_tip_record(tip_id)
            return {
                "type": "order.failed",
                "data": {
                    "order": {"merchantReference": record.merchant_reference}
                },
            }

        monkeypatch.setattr(anyway_webhook, "_verify_webhook", fake_verify)

        resp = client.post(
            "/webhooks/anyway",
            json={},
            headers={"webhook-id": "wh_2", "webhook-timestamp": "1234567890", "webhook-signature": "v1a,bbb"},
        )
        assert resp.status_code == 200
        record = state.memory.get_tip_record(tip_id)
        assert record.status == "failed"


class TestWithdrawals:
    """提现申请与审核测试。"""

    def test_withdrawal_workflow(self, client):
        """作者提交提现，管理员通过并标记打款。"""
        from comedy_agent.memory.models import EarningRecordData

        state.memory.save_earning(
            EarningRecordData(
                user_id="author_user",
                record_type="tip_anyway",
                amount=1000,
                description="测试打赏收益",
            )
        )

        resp = client.post(
            "/tips/withdrawals",
            json={"amount_cents": 500, "payout_method": "wechat", "payout_account": "wx123"},
            headers=_headers("author_user"),
        )
        assert resp.status_code == 200, resp.text
        request_id = resp.json()["request_id"]

        # 提交后可提现余额减少
        resp = client.get("/tips/earnings", headers=_headers("author_user"))
        assert resp.json()["pending_cents"] == 500

        # 管理员通过
        resp = client.post(
            f"/admin/withdrawals/{request_id}/approve",
            headers=client.admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        # 标记已打款
        resp = client.post(
            f"/admin/withdrawals/{request_id}/paid",
            headers=client.admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paid"

    def test_withdrawal_reject_restores_balance(self, client):
        """拒绝提现后余额恢复。"""
        from comedy_agent.memory.models import EarningRecordData

        state.memory.save_earning(
            EarningRecordData(
                user_id="author_user",
                record_type="tip_anyway",
                amount=1000,
                description="测试打赏收益",
            )
        )

        resp = client.post(
            "/tips/withdrawals",
            json={"amount_cents": 500, "payout_method": "alipay", "payout_account": "alipay123"},
            headers=_headers("author_user"),
        )
        request_id = resp.json()["request_id"]

        resp = client.post(
            f"/admin/withdrawals/{request_id}/reject",
            headers=client.admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        resp = client.get("/tips/earnings", headers=_headers("author_user"))
        data = resp.json()
        assert data["pending_cents"] == 1000

    def test_withdrawal_insufficient_balance(self, client):
        """余额不足时拒绝。"""
        resp = client.post(
            "/tips/withdrawals",
            json={"amount_cents": 100, "payout_method": "wechat", "payout_account": "wx"},
            headers=_headers("author_user"),
        )
        assert resp.status_code == 400
        assert "余额不足" in resp.json()["detail"]
