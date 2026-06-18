"""模型计费与消费记录测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlalchemy import StaticPool, create_engine
from unittest.mock import MagicMock, patch

from comedy_agent.api.billing import charge_model_usage, start_usage_tracking
from comedy_agent.api.server import app, state
from comedy_agent.memory.models import TokenConsumptionData
from comedy_agent.memory.unified import UnifiedMemory
from comedy_agent.models.usage_tracker import (
    UsageCallbackHandler,
    _extract_usage_from_response,
    get_model_usage,
    reset_model_usage,
)


def _patched_create_engine(*args, **kwargs):
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def memory():
    with patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ):
        return UnifiedMemory(db_url="sqlite:///:memory:")


def test_extract_usage_from_openai_format():
    response = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(content="hi"),
                    generation_info={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
                )
            ]
        ],
        llm_output={"token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
    )
    usage = _extract_usage_from_response(response, model_name="gpt-4o")
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5
    assert usage.total_tokens == 15
    assert usage.model == "gpt-4o"


def test_usage_callback_accumulates():
    reset_model_usage()
    handler = UsageCallbackHandler(model_name="gpt-4o")
    response = LLMResult(
        generations=[
            [ChatGeneration(message=AIMessage(content="a"), generation_info={"token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})]
        ],
        llm_output={"token_usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    )
    handler.on_llm_end(response)

    response2 = LLMResult(
        generations=[
            [ChatGeneration(message=AIMessage(content="b"), generation_info={"token_usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}})]
        ],
        llm_output={"token_usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}},
    )
    handler.on_llm_end(response2)

    total = get_model_usage()
    assert total is not None
    assert total.prompt_tokens == 4
    assert total.completion_tokens == 3
    assert total.total_tokens == 7


def test_save_and_list_consumption_records(memory: UnifiedMemory):
    record = TokenConsumptionData(
        user_id="u001",
        endpoint="/chat",
        model="gpt-4o",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        cost=15,
        description="test",
    )
    saved = memory.save_consumption_record(record)
    assert saved.consumption_id is not None

    records = memory.list_consumption_records("u001")
    assert len(records) == 1
    assert records[0].total_tokens == 15
    assert records[0].cost == 15


def test_charge_model_usage_deducts_tokens(memory: UnifiedMemory):
    from comedy_agent.api.state import state
    state.memory = memory

    user_id = "u_billing"
    memory.get_or_create_user(user_id)
    start_usage_usage = memory.get_token_account(user_id).balance

    reset_model_usage()
    handler = UsageCallbackHandler(model_name="gpt-4o")
    response = LLMResult(
        generations=[
            [ChatGeneration(message=AIMessage(content="x"), generation_info={"token_usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}})]
        ],
        llm_output={"token_usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}},
    )
    handler.on_llm_end(response)

    result = charge_model_usage(
        user_id=user_id,
        endpoint="/chat",
        description="test billing",
        fallback_cost=5,
    )
    assert result["cost"] == 10
    assert result["record_id"] is not None

    account = memory.get_token_account(user_id)
    assert account.total_consumed == 10
    assert account.balance == start_usage_usage - 10

    records = memory.list_consumption_records(user_id)
    assert len(records) == 1
    assert records[0].endpoint == "/chat"


@pytest.fixture
def client(memory: UnifiedMemory):
    with patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch("comedy_agent.api.server.AgentOrchestrator") as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = ["standup_generator"]
        mock_orch.run.return_value = {"output": "test response", "messages": []}
        mock_orch_cls.return_value = mock_orch

        from comedy_agent.memory.medium_term import SQLMemoryStore
        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        with TestClient(app) as c:
            state.memory = memory
            state.orch = mock_orch
            yield c

    state.orch = None
    state.memory = None


def _register_and_login(client, user_id, password="Test123!"):
    client.post("/auth/register", json={"user_id": user_id, "password": password})
    r = client.post("/auth/login", json={"user_id": user_id, "password": password})
    return r.json()["access_token"]


def test_get_me_consumptions(client, memory):
    user_id = "consumption_user"
    token = _register_and_login(client, user_id)

    memory.save_consumption_record(
        TokenConsumptionData(
            user_id=user_id,
            endpoint="/chat",
            total_tokens=20,
            cost=20,
        )
    )

    res = client.get("/me/consumptions", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["endpoint"] == "/chat"
    assert data["items"][0]["total_tokens"] == 20
