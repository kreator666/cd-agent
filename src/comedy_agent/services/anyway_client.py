"""Anyway Merchant API 客户端。"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from comedy_agent.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://merchant-api-prod.anyway.sh"


class AnywayClientError(Exception):
    """Anyway 客户端错误。"""

    pass


class AnywayClient:
    """调用 Anyway Merchant API 的轻量客户端。"""

    def __init__(self, api_key: str | None = None, base_url: str = BASE_URL) -> None:
        self.api_key = api_key or settings.anyway_merchant_api_key
        self.base_url = base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise AnywayClientError("Anyway Merchant API key 未配置")
        return {"X-API-Key": self.api_key, "Accept": "application/json"}

    async def get_order(self, order_id: str) -> dict[str, Any] | None:
        """根据 order_id 查询订单详情。"""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.base_url}/v1/orders/{order_id}",
                headers=self._headers(),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            return data.get("data") if data.get("success") else None

    async def list_orders(
        self, merchant_reference: str | None = None, limit: int = 20, page: int = 1
    ) -> list[dict[str, Any]]:
        """按 merchant_reference 查询订单列表。"""
        params: dict[str, Any] = {"size": limit, "page": page}
        if merchant_reference:
            params["merchant_reference"] = merchant_reference

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self.base_url}/v1/orders",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                return []
            paginated = data.get("data", {})
            return paginated.get("records", []) or paginated.get("items", [])
