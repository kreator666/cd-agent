"""物品/服务交换平台 (swap) API 测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client_tokens():
    """提供 TestClient 与三个普通用户 + 一个管理员用户的 Token。"""
    with patch(
        "comedy_agent.memory.medium_term.create_engine", side_effect=_patched_create_engine
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch.run.return_value = {"output": "mocked", "messages": []}
        mock_orch_cls.return_value = mock_orch

        with TestClient(app) as c:
            # 注意：TestClient 进入 lifespan 会用真实库覆盖 state.memory，
            # 必须在进入上下文之后再挂载内存库（与 test_api_new_routers 一致）
            from comedy_agent.memory.medium_term import SQLMemoryStore
            store = SQLMemoryStore(db_url="sqlite:///:memory:")
            state.memory = store
            state.orch = mock_orch

            for uid in ("test_user", "user_b", "user_c", "swap_admin"):
                store.get_or_create_user(uid)

            from comedy_agent.auth.router import create_access_token
            tokens = {
                "a": create_access_token("test_user"),
                "b": create_access_token("user_b"),
                "c": create_access_token("user_c"),
                "admin": create_access_token("swap_admin"),
            }

            c.headers["Authorization"] = f"Bearer {tokens['a']}"
            yield c, tokens

        state.memory = None
        state.orch = None


def _create_order(client: TestClient, token: str | None = None, **overrides) -> dict:
    """以默认用户（或指定 token 用户）发布交换订单。"""
    payload = {
        "title": "九成新机械键盘",
        "offer_desc": "提供：樱桃轴机械键盘，箱说全",
        "want_desc": "想换：蓝牙音箱或降噪耳机",
        "images": ["/static/swap_images/demo.png"],
    }
    payload.update(overrides)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    res = client.post("/swap/orders", json=payload, headers=headers)
    assert res.status_code == 200
    return res.json()


def _submit_offer(client: TestClient, token: str, order_id: str, item_desc: str, contact: str) -> dict:
    """以指定用户提交交换意向。"""
    res = client.post(
        f"/swap/orders/{order_id}/offers",
        json={"item_desc": item_desc, "contact": contact, "images": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    return res.json()


class TestSwapAPI:
    """交换平台 API 测试。"""

    def test_create_list_detail(self, client_tokens):
        """发单 → 列表能查到 → 详情正确（未登录也 200）。"""
        client, tokens = client_tokens
        order = _create_order(client)
        assert order["maker_id"] == "test_user"
        assert order["status"] == "open"
        assert order["offer_count"] == 0

        # 公开列表
        res = client.get("/swap/orders")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["page"] == 1
        assert data["page_size"] == 12
        assert data["orders"][0]["order_id"] == order["order_id"]
        assert "contact" not in data["orders"][0]

        # 关键词模糊搜索
        res = client.get("/swap/orders", params={"keyword": "机械键盘"})
        assert res.json()["total"] == 1
        res = client.get("/swap/orders", params={"keyword": "完全不相关的东西"})
        assert res.json()["total"] == 0

        # 未登录详情 200，且不下发 offers
        auth = client.headers.pop("Authorization")
        try:
            res = client.get(f"/swap/orders/{order['order_id']}")
        finally:
            client.headers["Authorization"] = auth
        assert res.status_code == 200
        detail = res.json()
        assert detail["order_id"] == order["order_id"]
        assert detail["offer_count"] == 0
        assert "offers" not in detail

    def test_offer_contact_masking(self, client_tokens):
        """B 提交 offer → maker 详情可见明文 contact；公开/他人视角看不到。"""
        client, tokens = client_tokens
        order = _create_order(client)
        oid = order["order_id"]

        offer = _submit_offer(client, tokens["b"], oid, "提供一个蓝牙音箱", "wechat: user_b")
        assert offer["status"] == "pending"
        # 提交者（非 maker）视角不下发 contact
        assert "contact" not in offer

        # maker（默认头即 A）详情：offers 完整且 contact 明文
        res = client.get(f"/swap/orders/{oid}")
        assert res.status_code == 200
        detail = res.json()
        assert detail["offer_count"] == 1
        assert len(detail["offers"]) == 1
        assert detail["offers"][0]["contact"] == "wechat: user_b"

        # 他人（C）视角：不下发 offers
        res = client.get(f"/swap/orders/{oid}", headers={"Authorization": f"Bearer {tokens['c']}"})
        assert "offers" not in res.json()

        # 匿名视角：不下发 offers
        auth = client.headers.pop("Authorization")
        try:
            res = client.get(f"/swap/orders/{oid}")
        finally:
            client.headers["Authorization"] = auth
        assert "offers" not in res.json()

    def test_my_offer_in_detail(self, client_tokens):
        """taker 的详情响应带 my_offer（含 contact 回填）；maker 响应不带。"""
        client, tokens = client_tokens
        oid = _create_order(client)["order_id"]

        _submit_offer(client, tokens["b"], oid, "一个蓝牙音箱", "wechat: b")

        res = client.get(f"/swap/orders/{oid}", headers={"Authorization": f"Bearer {tokens['b']}"})
        detail = res.json()
        assert detail["my_offer"]["item_desc"] == "一个蓝牙音箱"
        assert detail["my_offer"]["contact"] == "wechat: b"

        # maker 视角走 offers，不下发 my_offer
        res = client.get(f"/swap/orders/{oid}")
        assert "my_offer" not in res.json()

    def test_offer_upsert(self, client_tokens):
        """同一用户重复提交 offer → 更新而非新增。"""
        client, tokens = client_tokens
        order = _create_order(client)
        oid = order["order_id"]

        first = _submit_offer(client, tokens["b"], oid, "一个蓝牙音箱", "wechat: b1")
        second = _submit_offer(client, tokens["b"], oid, "更新为：蓝牙音箱 + 有线耳机", "wechat: b2")

        assert second["offer_id"] == first["offer_id"]
        assert second["item_desc"] == "更新为：蓝牙音箱 + 有线耳机"

        # 仍只有一条意向
        res = client.get(f"/swap/orders/{oid}")
        detail = res.json()
        assert detail["offer_count"] == 1
        assert detail["offers"][0]["contact"] == "wechat: b2"

    def test_cannot_offer_own_order(self, client_tokens):
        """不能对自己发布的订单提交交换。"""
        client, tokens = client_tokens
        order = _create_order(client)
        res = client.post(
            f"/swap/orders/{order['order_id']}/offers",
            json={"item_desc": "自己换自己", "contact": "wechat: me", "images": []},
        )
        assert res.status_code == 400

    def test_accept_deal(self, client_tokens):
        """maker 成交 → 订单 deal、该 offer accepted、其他 pending 自动 rejected。"""
        client, tokens = client_tokens
        order = _create_order(client)
        oid = order["order_id"]

        offer_b = _submit_offer(client, tokens["b"], oid, "B 的蓝牙音箱", "wechat: b")["offer_id"]
        offer_c = _submit_offer(client, tokens["c"], oid, "C 的降噪耳机", "wechat: c")["offer_id"]

        # 非 maker 确认成交 → 403
        res = client.post(
            f"/swap/offers/{offer_b}/accept",
            headers={"Authorization": f"Bearer {tokens['b']}"},
        )
        assert res.status_code == 403

        # maker 确认 B 的意向
        res = client.post(f"/swap/offers/{offer_b}/accept")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "deal"
        assert data["deal_offer_id"] == offer_b

        # 事务性更新生效
        assert state.memory.get_swap_offer(offer_b).status == "accepted"
        assert state.memory.get_swap_offer(offer_c).status == "rejected"
        assert state.memory.get_swap_order(oid).status == "deal"

        # 成交 taker（B）详情可见成交意向且 contact 明文
        res = client.get(f"/swap/orders/{oid}", headers={"Authorization": f"Bearer {tokens['b']}"})
        detail = res.json()
        assert len(detail["offers"]) == 1
        assert detail["offers"][0]["offer_id"] == offer_b
        assert detail["offers"][0]["contact"] == "wechat: b"

        # 被拒绝的 C 视角：不下发 offers
        res = client.get(f"/swap/orders/{oid}", headers={"Authorization": f"Bearer {tokens['c']}"})
        assert "offers" not in res.json()

    def test_write_requires_auth(self, client_tokens):
        """未登录调用写接口 → 401。"""
        client, tokens = client_tokens
        auth = client.headers.pop("Authorization")
        try:
            res = client.post(
                "/swap/orders",
                json={"title": "t", "offer_desc": "o", "want_desc": "w"},
            )
            assert res.status_code == 401
            res = client.get("/swap/my/orders")
            assert res.status_code == 401
        finally:
            client.headers["Authorization"] = auth

    def test_close_order(self, client_tokens):
        """maker 手动关闭订单；重复关闭与非 maker 关闭被拒。"""
        client, tokens = client_tokens
        order = _create_order(client)
        oid = order["order_id"]

        # 非 maker 关闭 → 403
        res = client.post(
            f"/swap/orders/{oid}/close",
            headers={"Authorization": f"Bearer {tokens['b']}"},
        )
        assert res.status_code == 403

        # maker 关闭
        res = client.post(f"/swap/orders/{oid}/close")
        assert res.status_code == 200
        assert res.json()["status"] == "closed"

        # 重复关闭 → 400
        res = client.post(f"/swap/orders/{oid}/close")
        assert res.status_code == 400

        # closed 订单不可再提交意向
        res = client.post(
            f"/swap/orders/{oid}/offers",
            json={"item_desc": "x", "contact": "y", "images": []},
            headers={"Authorization": f"Bearer {tokens['b']}"},
        )
        assert res.status_code == 400

    def test_admin_feature(self, client_tokens):
        """管理员加精 → featured=true；非管理员加精 403；featured=1 列表只返回精选。"""
        client, tokens = client_tokens
        order1 = _create_order(client)
        _create_order(client, title="另一单：复古胶片相机")
        oid1 = order1["order_id"]

        # 非管理员（A）加精 → 403
        res = client.post(f"/swap/admin/orders/{oid1}/feature", json={"featured": True})
        assert res.status_code == 403

        with patch("comedy_agent.api.routers.admin.ADMIN_USERS", {"swap_admin"}):
            # 管理员加精
            res = client.post(
                f"/swap/admin/orders/{oid1}/feature",
                json={"featured": True},
                headers={"Authorization": f"Bearer {tokens['admin']}"},
            )
            assert res.status_code == 200
            assert res.json()["featured"] is True
            assert res.json()["featured_at"] is not None

            # 精选列表只返回加精订单
            res = client.get("/swap/orders", params={"featured": 1})
            data = res.json()
            assert data["total"] == 1
            assert [o["order_id"] for o in data["orders"]] == [oid1]

            # 取消精选
            res = client.post(
                f"/swap/admin/orders/{oid1}/feature",
                json={"featured": False},
                headers={"Authorization": f"Bearer {tokens['admin']}"},
            )
            assert res.status_code == 200
            assert res.json()["featured"] is False
            assert res.json()["featured_at"] is None

        res = client.get("/swap/orders", params={"featured": 1})
        assert res.json()["total"] == 0

    def test_my_orders_and_offers(self, client_tokens):
        """我发的单（带 offer_count/pending_count）与我提交的 offer（带订单摘要）。"""
        client, tokens = client_tokens
        order = _create_order(client)
        oid = order["order_id"]
        _submit_offer(client, tokens["b"], oid, "B 的蓝牙音箱", "wechat: b")
        _submit_offer(client, tokens["c"], oid, "C 的降噪耳机", "wechat: c")

        # my/orders：maker 视角
        res = client.get("/swap/my/orders")
        assert res.status_code == 200
        mine = res.json()
        assert len(mine) == 1
        assert mine[0]["order_id"] == oid
        assert mine[0]["offer_count"] == 2
        assert mine[0]["pending_count"] == 2

        # my/offers：B 视角（未成交，contact 按脱敏规则不下发）
        res = client.get("/swap/my/offers", headers={"Authorization": f"Bearer {tokens['b']}"})
        assert res.status_code == 200
        offers = res.json()
        assert len(offers) == 1
        assert offers[0]["order_title"] == order["title"]
        assert offers[0]["order_status"] == "open"
        assert "contact" not in offers[0]

        # 成交后 B 的 my/offers 中 contact 明文
        offer_b = state.memory.list_swap_offers(order_id=oid, taker_id="user_b")[0]
        res = client.post(f"/swap/offers/{offer_b.offer_id}/accept")
        assert res.status_code == 200
        res = client.get("/swap/my/offers", headers={"Authorization": f"Bearer {tokens['b']}"})
        offers = res.json()
        assert offers[0]["order_status"] == "deal"
        assert offers[0]["contact"] == "wechat: b"

    def test_upload_image(self, client_tokens):
        """上传假图片字节成功；非图片类型 400；未登录 401。"""
        client, tokens = client_tokens
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes" * 16

        res = client.post(
            "/swap/upload",
            files={"file": ("test.png", png_bytes, "image/png")},
        )
        assert res.status_code == 200
        url = res.json()["url"]
        assert url.startswith("/static/swap_images/")
        assert url.endswith(".png")

        # 非图片类型 → 400
        res = client.post(
            "/swap/upload",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        assert res.status_code == 400

        # 未登录 → 401
        auth = client.headers.pop("Authorization")
        try:
            res = client.post(
                "/swap/upload",
                files={"file": ("t.png", png_bytes, "image/png")},
            )
            assert res.status_code == 401
        finally:
            client.headers["Authorization"] = auth

        # 清理测试产生的图片文件
        save_name = url.rsplit("/", 1)[-1]
        images_dir = Path(__file__).resolve().parent.parent / "frontend" / "swap_images"
        (images_dir / save_name).unlink(missing_ok=True)
