"""FastAPI HTTP 服务单元测试。"""

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import StaticPool, create_engine

from comedy_agent.api.server import app, state
from comedy_agent.state.schema import ComedyState


def _patched_create_engine(*args, **kwargs):
    """对 SQLite 内存数据库使用 StaticPool，确保多线程共享连接。"""
    if args and ":memory:" in str(args[0]):
        kwargs["poolclass"] = StaticPool
        kwargs.setdefault("connect_args", {})
        kwargs["connect_args"]["check_same_thread"] = False
    return create_engine(*args, **kwargs)


@pytest.fixture
def client(request):
    """提供 TestClient（ lifespan 自动执行，memory 使用内存数据库，带认证）。

    默认会 mock VectorStore / ComedyRetriever 以跳过 HuggingFace 模型加载，加速测试。
    传入 --full-lifespan 则执行完整的 lifespan（包括模型加载）。
    """
    full_lifespan = request.config.getoption("--full-lifespan")

    # 条件 mock：默认跳过 VectorStore 初始化（HuggingFaceEmbeddings 加载极慢）
    cm_vector = patch("comedy_agent.api.server.VectorStore") if not full_lifespan else contextlib.nullcontext()
    cm_retriever = patch("comedy_agent.api.server.ComedyRetriever") if not full_lifespan else contextlib.nullcontext()
    cm_graph = patch("comedy_agent.api.server.build_chat_graph") if not full_lifespan else contextlib.nullcontext()

    with cm_vector, cm_retriever, cm_graph, patch(
        "comedy_agent.memory.medium_term.create_engine",
        side_effect=_patched_create_engine,
    ), patch(
        "comedy_agent.api.server.AgentOrchestrator"
    ) as mock_orch_cls, patch(
        "comedy_agent.auth.router.SQLMemoryStore"
    ) as mock_auth_store_cls:
        mock_orch = MagicMock()
        mock_orch.list_skills.return_value = [
            {"name": "standup_generator", "description": "", "task_type": "creative", "source": "builtin"}
        ]
        mock_orch_cls.return_value = mock_orch

        # auth router 使用内存数据库
        from comedy_agent.memory.medium_term import SQLMemoryStore
        auth_store = SQLMemoryStore(db_url="sqlite:///:memory:")
        mock_auth_store_cls.return_value = auth_store

        # 使用 TestClient 让 lifespan 自动运行
        with TestClient(app) as c:
            # lifespan 已经执行完毕，替换 memory 为内存数据库实例
            from comedy_agent.memory.unified import UnifiedMemory

            state.memory = UnifiedMemory(db_url="sqlite:///:memory:")

            # 注册测试用户并获取 token
            c.post("/auth/register", json={"user_id": "testuser", "password": "testpass"})
            login_resp = c.post("/auth/login", json={"user_id": "testuser", "password": "testpass"})
            token = login_resp.json()["access_token"]

            # 返回带默认认证 header 的 client
            with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as authed_c:
                state.memory = UnifiedMemory(db_url="sqlite:///:memory:")
                yield authed_c

    # 清理
    state.orch = None
    state.graph = None
    state.memory = None


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "memory_ready" in data
        assert "orchestrator_ready" in data
        assert "graph_ready" in data


class TestSkills:
    def test_list_skills(self, client):
        response = client.get("/skills")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        names = [s["name"] for s in data["skills"]]
        assert "standup_generator" in names


class TestChat:
    def test_chat_success(self, client):
        from comedy_agent.api.server import state

        async def _ainvoke(state_input, config=None):
            return ComedyState(
                output="Agent 回答",
                messages=[
                    HumanMessage(content="你好"),
                    AIMessage(content="Agent 回答"),
                ],
            )

        state.graph.ainvoke = _ainvoke

        response = client.post(
            "/chat",
            json={"prompt": "你好"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["output"] == "Agent 回答"
        assert len(data["messages"]) == 2

    def test_chat_with_history(self, client):
        from comedy_agent.api.server import state

        async def _ainvoke(state_input, config=None):
            return ComedyState(
                output="好的",
                messages=[],
                chat_history=state_input.chat_history,
            )

        state.graph.ainvoke = _ainvoke

        response = client.post(
            "/chat",
            json={
                "prompt": "继续",
                "chat_history": [["human", "上一句"], ["ai", "上一答"]],
            },
        )
        assert response.status_code == 200


class TestStandupSkill:
    def test_standup_skill(self, client):
        with patch(
            "comedy_agent.api.server.load_single_skill"
        ) as mock_loader:
            mock_skill = MagicMock()
            mock_skill.invoke.return_value = "生成的段子"
            mock_loader.return_value = mock_skill

            response = client.post(
                "/skills/standup",
                json={
                    "topic": "相亲",
                    "style": "自嘲",
                    "duration": 3,
                    "audience": "年轻人",
                    "density": "密集",
                    "perspective_count": 3,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "生成的段子"


class TestSketchSkill:
    def test_sketch_skill(self, client):
        with patch(
            "comedy_agent.api.server.load_single_skill"
        ) as mock_loader:
            mock_skill = MagicMock()
            mock_skill.invoke.return_value = "生成的小品"
            mock_loader.return_value = mock_skill

            response = client.post(
                "/skills/sketch",
                json={
                    "theme": "家庭聚餐",
                    "characters_count": 4,
                    "setting": "家庭",
                    "duration": 10,
                    "conflict_type": "执念vs执念",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "生成的小品"


class TestManzaiSkill:
    def test_manzai_skill(self, client):
        with patch(
            "comedy_agent.api.server.load_single_skill"
        ) as mock_loader:
            mock_skill = MagicMock()
            mock_skill.invoke.return_value = "生成的漫才"
            mock_loader.return_value = mock_skill

            response = client.post(
                "/skills/manzai",
                json={
                    "topic": "职场加班",
                    "duration": 5,
                    "segments_count": 4,
                    "absurd_level": "极致",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "生成的漫才"


class TestJapaneseSketchSkill:
    def test_japanese_sketch_skill(self, client):
        with patch(
            "comedy_agent.api.server.load_single_skill"
        ) as mock_loader:
            mock_skill = MagicMock()
            mock_skill.invoke.return_value = "生成的日式短剧"
            mock_loader.return_value = mock_skill

            response = client.post(
                "/skills/japanese-sketch",
                json={
                    "theme": "便利店打工",
                    "characters_count": 3,
                    "setting": "便利店",
                    "duration": 5,
                    "character_type": "自大",
                    "punchline_density": 6,
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == "生成的日式短剧"


class TestFeedbackIngest:
    """高评分内容回流端点测试。"""

    def test_feedback_ingest_success(self, client):
        with patch("comedy_agent.api.server.FeedbackLoop") as mock_loop_cls:
            mock_loop = MagicMock()
            mock_loop.ingest_high_rated_scripts.return_value = {
                "ingested_scripts": 2,
                "total_chunks": 5,
                "script_ids": ["s1", "s2"],
                "skipped": [],
                "dry_run": False,
            }
            mock_loop_cls.return_value = mock_loop

            response = client.post(
                "/feedback/ingest",
                json={"min_rating": 4.0, "chunk_strategy": "paragraph"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["ingested_scripts"] == 2
            assert data["total_chunks"] == 5
            assert data["dry_run"] is False
            mock_loop_cls.assert_called_once()
            call_kwargs = mock_loop_cls.call_args[1]
            assert call_kwargs["min_rating"] == 4.0

    def test_feedback_ingest_dry_run(self, client):
        with patch("comedy_agent.api.server.FeedbackLoop") as mock_loop_cls:
            mock_loop = MagicMock()
            mock_loop.ingest_high_rated_scripts.return_value = {
                "ingested_scripts": 0,
                "total_chunks": 0,
                "script_ids": [],
                "skipped": [],
                "dry_run": True,
            }
            mock_loop_cls.return_value = mock_loop

            response = client.post(
                "/feedback/ingest",
                json={"dry_run": True, "min_rating": 4.0},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["dry_run"] is True

    def test_feedback_ingest_memory_not_ready(self, client):
        state.memory = None
        response = client.post(
            "/feedback/ingest",
            json={"min_rating": 4.0},
        )
        assert response.status_code == 503



class TestEvaluateEndpoints:
    """评估端点测试。"""

    def test_evaluate_script(self, client):
        response = client.post(
            "/evaluate/script",
            json={
                "script": "大家好！\n\n甲：你好。\n乙：你好。\n\n谢谢大家！",
                "script_type": "standup",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "overall_score" in data
        assert 0 <= data["overall_score"] <= 10
        assert "suggestions" in data

    def test_evaluate_output(self, client):
        response = client.post(
            "/evaluate/output",
            json={
                "output": "# 报告\n\n- 笑点分析\n- 结构建议\n",
                "expected_format": "markdown",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "overall_score" in data
        assert "has_punchline" in data
        assert "has_dialogue" in data
